"""Worker long-poll loop.

Consumes SQS messages produced by the API, fetches the raw event from S3,
deduplicates on `idempotency_key`, runs the rule engine, persists any alerts,
delivers notifications to partner APIs, and records delivery audit rows.
"""

import json
import signal
import sys
import time
from datetime import datetime

import boto3
import structlog
from botocore.config import Config
from sqlalchemy.orm import Session

from . import rules
from .db import Alert, AlertEvent, PartnerDeliveryAttempt, get_sessionmaker, init_db
from .dedupe import try_claim_idempotency
from .observability import configure_logging, get_logger
from .partner_client import PagerDutyClient, SlackWebhookClient
from .settings import get_settings

_shutdown = False


def _install_signal_handlers() -> None:
    def _handler(signum, _frame):
        global _shutdown
        _shutdown = True
        get_logger(__name__).info("worker.shutdown_requested", signal=signum)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _aws_client(service: str):
    s = get_settings()
    kwargs = {
        "region_name": s.aws_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if s.aws_endpoint_url:
        kwargs["endpoint_url"] = s.aws_endpoint_url
    return boto3.client(service, **kwargs)


def _load_raw_event(s3_bucket: str, s3_key: str) -> dict:
    resp = _aws_client("s3").get_object(Bucket=s3_bucket, Key=s3_key)
    return json.loads(resp["Body"].read())


def _to_rule_input(raw: dict, event_id: str) -> rules.InferenceInput:
    return rules.InferenceInput(
        event_id=event_id,
        model=raw["model"],
        provider=raw["provider"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        latency_ms=raw["latency_ms"],
        cost_usd=float(raw["cost_usd"]),
        prompt=raw.get("prompt", ""),
        completion=raw.get("completion", ""),
        predicted_label=raw.get("predicted_label"),
        expected_label=raw.get("expected_label"),
    )


def _enqueue_investigations(alert_rows: list[Alert]) -> None:
    s = get_settings()
    if not s.investigations_queue_url:
        return
    log = get_logger(__name__)
    sqs = _aws_client("sqs")
    for alert in alert_rows:
        if alert.severity != "critical":
            continue
        try:
            resp = sqs.send_message(
                QueueUrl=s.investigations_queue_url,
                MessageBody=json.dumps(
                    {
                        "alert_id": alert.id,
                        "event_id": alert.event_id,
                        "rule": alert.rule,
                        "severity": alert.severity,
                    }
                ),
            )
            log.info(
                "worker.investigation_enqueued",
                alert_id=alert.id,
                rule=alert.rule,
                sqs_message_id=resp.get("MessageId"),
            )
        except Exception:
            log.exception("worker.investigation_enqueue_failed", alert_id=alert.id)


def _deliver_alerts(session: Session, alert_rows: list[Alert]) -> None:
    s = get_settings()
    clients = []
    if s.slack_webhook_url:
        clients.append(SlackWebhookClient(s.slack_webhook_url))
    if s.pagerduty_url:
        clients.append(PagerDutyClient(s.pagerduty_url))

    for alert in alert_rows:
        for client in clients:
            # PagerDuty only for critical alerts; Slack for everything.
            if client.name == "pagerduty" and alert.severity != "critical":
                continue
            result = client.send(alert)
            session.add(
                PartnerDeliveryAttempt(
                    alert_id=alert.id,
                    partner=client.name,
                    partner_request_id=result.partner_request_id,
                    attempt=result.attempts,
                    status="success" if result.success else "failure",
                    http_status=result.http_status,
                    error=result.error,
                    latency_ms=result.latency_ms,
                )
            )
    session.flush()


def _process_message(session: Session, msg: dict) -> None:
    log = get_logger(__name__)
    body = json.loads(msg["Body"])
    event_id = body["event_id"]
    idempotency_key = body["idempotency_key"]

    structlog.contextvars.bind_contextvars(
        event_id=event_id, model=body.get("model"), idempotency_key=idempotency_key
    )

    raw = _load_raw_event(body["s3_bucket"], body["s3_key"])
    rule_input = _to_rule_input(raw, event_id)

    claimed = try_claim_idempotency(
        session,
        event_id=event_id,
        idempotency_key=idempotency_key,
        model=rule_input.model,
        provider=rule_input.provider,
        event_timestamp=rule_input.timestamp,
        latency_ms=rule_input.latency_ms,
        cost_usd=rule_input.cost_usd,
        prompt_tokens=raw.get("prompt_tokens", 0),
        completion_tokens=raw.get("completion_tokens", 0),
        predicted_label=rule_input.predicted_label,
        expected_label=rule_input.expected_label,
        s3_bucket=body["s3_bucket"],
        s3_key=body["s3_key"],
    )
    if not claimed:
        log.info("worker.duplicate_dropped")
        return

    ctx = rules.load_context(session, rule_input)
    results = rules.evaluate_all(rule_input, ctx)
    log.info("worker.evaluated", rules_fired=[r.rule for r in results])

    alert_rows: list[Alert] = []
    for result in results:
        alert = Alert(
            event_id=event_id,
            model=rule_input.model,
            rule=result.rule,
            severity=result.severity,
            status="open",
            message=result.message,
            evidence=result.evidence,
        )
        session.add(alert)
        session.flush()  # populate alert.id
        session.add(AlertEvent(alert_id=alert.id, kind="created", note=result.message[:500]))
        alert_rows.append(alert)

    if alert_rows:
        _deliver_alerts(session, alert_rows)

    session.commit()

    if alert_rows:
        _enqueue_investigations(alert_rows)


def run_once() -> int:
    """Poll once and process whatever we receive. Returns # of messages handled."""
    s = get_settings()
    sqs = _aws_client("sqs")
    resp = sqs.receive_message(
        QueueUrl=s.sqs_queue_url,
        MaxNumberOfMessages=s.sqs_max_messages,
        WaitTimeSeconds=s.sqs_wait_time_seconds,
        VisibilityTimeout=s.sqs_visibility_timeout,
        MessageAttributeNames=["All"],
    )
    messages = resp.get("Messages", [])
    if not messages:
        return 0

    session_factory = get_sessionmaker()
    handled = 0
    for msg in messages:
        log = get_logger(__name__)
        session = session_factory()
        try:
            _process_message(session, msg)
            sqs.delete_message(QueueUrl=s.sqs_queue_url, ReceiptHandle=msg["ReceiptHandle"])
            handled += 1
        except Exception:
            log.exception("worker.message_failed")
            session.rollback()
            # Don't delete the message — SQS will make it visible again and eventually DLQ it.
        finally:
            session.close()
            structlog.contextvars.clear_contextvars()
    return handled


def main() -> int:
    configure_logging()
    _install_signal_handlers()
    log = get_logger(__name__)

    # Initialize tables on first boot; a no-op if they already exist.
    try:
        init_db()
        log.info("worker.db_ready")
    except Exception:
        log.exception("worker.db_init_failed")
        # Keep trying — Postgres may not be up yet on cold compose start.
        time.sleep(2)
        init_db()

    log.info("worker.started", settings=get_settings().model_dump())

    while not _shutdown:
        try:
            run_once()
        except Exception:
            log.exception("worker.poll_failed")
            time.sleep(1)

    log.info("worker.stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
