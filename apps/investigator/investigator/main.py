"""Investigator entrypoint.

Polls the investigations SQS queue. Each message carries `{"alert_id": <int>}`.
For each message we invoke the LangGraph agent, persist the report, and ack.

The worker publishes to this queue whenever it creates a high-severity alert.
Publishing is best-effort: if enqueue fails, the worker still commits its own
transaction — investigator coverage is recoverable (backfill via the feedback
endpoint), worker alerting is not.

Also runs the feedback FastAPI mini-app in a background thread so `GET/POST
/investigations/{id}` is available on the same container.
"""

import json
import signal
import sys
import threading
import time
from typing import Any

import boto3
from botocore.config import Config

from .db import init_db
from .feedback import run_feedback_server
from .graph import get_graph
from .observability import configure_logging, get_logger
from .settings import get_settings

_shutdown = False


def _install_signal_handlers() -> None:
    def _handler(signum, _frame):
        global _shutdown
        _shutdown = True
        get_logger(__name__).info("investigator.shutdown_requested", signal=signum)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _sqs_client():
    s = get_settings()
    kwargs: dict[str, Any] = {
        "region_name": s.aws_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if s.aws_endpoint_url:
        kwargs["endpoint_url"] = s.aws_endpoint_url
    return boto3.client("sqs", **kwargs)


def _process_message(msg: dict) -> None:
    log = get_logger(__name__)
    body = json.loads(msg["Body"])
    alert_id = int(body["alert_id"])
    log.info("investigator.message_received", alert_id=alert_id)

    initial_state: dict[str, Any] = {
        "alert_id": alert_id,
        "evidence": [],
        "hypotheses": [],
        "verify_loops": 0,
        "tool_calls": 0,
        "cost_usd": 0.0,
    }
    final_state = get_graph().invoke(initial_state)
    if final_state.get("error"):
        log.warning("investigator.error", error=final_state["error"])
        return
    report = final_state.get("report")
    if report is None:
        log.warning("investigator.no_report_produced")
        return
    log.info(
        "investigator.completed",
        alert_id=alert_id,
        root_cause_label=report.root_cause_label,
        confidence=report.confidence,
        tool_calls=report.tool_calls,
        verify_loops=report.verify_loops,
        cost_usd=report.cost_usd,
        latency_ms=report.latency_ms,
    )


def run_once() -> int:
    s = get_settings()
    if not s.investigations_queue_url:
        return 0
    sqs = _sqs_client()
    resp = sqs.receive_message(
        QueueUrl=s.investigations_queue_url,
        MaxNumberOfMessages=s.sqs_max_messages,
        WaitTimeSeconds=s.sqs_wait_time_seconds,
        VisibilityTimeout=s.sqs_visibility_timeout,
        MessageAttributeNames=["All"],
    )
    messages = resp.get("Messages", [])
    if not messages:
        return 0
    log = get_logger(__name__)
    handled = 0
    for msg in messages:
        try:
            _process_message(msg)
            sqs.delete_message(QueueUrl=s.investigations_queue_url, ReceiptHandle=msg["ReceiptHandle"])
            handled += 1
        except Exception:
            log.exception("investigator.message_failed")
    return handled


def main() -> int:
    configure_logging()
    _install_signal_handlers()
    log = get_logger(__name__)

    try:
        init_db()
        log.info("investigator.db_ready")
    except Exception:
        log.exception("investigator.db_init_failed")
        time.sleep(2)
        init_db()

    feedback_thread = threading.Thread(target=run_feedback_server, daemon=True)
    feedback_thread.start()

    log.info("investigator.started", settings=get_settings().model_dump())

    while not _shutdown:
        try:
            run_once()
        except Exception:
            log.exception("investigator.poll_failed")
            time.sleep(1)

    log.info("investigator.stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
