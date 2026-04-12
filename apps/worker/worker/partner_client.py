"""Outbound partner integration client.

Base class wraps httpx with:
  - strict connect + total timeouts
  - exponential backoff with jitter via tenacity (transient errors only)
  - pybreaker circuit breaker per partner (isolates one bad partner from another)
  - HMAC signing over body + timestamp (replay-resistant even if the webhook URL leaks)
  - idempotency key header so partners can deduplicate on their side

Two concrete clients: Slack webhooks and PagerDuty Events API v2.
"""

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

import httpx
import pybreaker
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .observability import get_logger
from .settings import get_settings

log = get_logger(__name__)


class PartnerError(Exception):
    """Raised for non-retryable partner failures."""


class TransientPartnerError(Exception):
    """Raised for retryable partner failures (5xx, timeouts)."""


@dataclass
class DeliveryResult:
    success: bool
    attempts: int
    http_status: int | None
    latency_ms: int
    error: str | None
    partner_request_id: str


def _sign(body: bytes, timestamp: str, key: str) -> str:
    mac = hmac.new(key.encode(), msg=f"{timestamp}.".encode() + body, digestmod=hashlib.sha256)
    return f"v1={mac.hexdigest()}"


class _BasePartner:
    name: str = "base"
    # One breaker per partner — isolated blast radius.
    _breakers: dict[str, pybreaker.CircuitBreaker] = {}

    def __init__(self, url: str):
        self.url = url
        if self.name not in _BasePartner._breakers:
            _BasePartner._breakers[self.name] = pybreaker.CircuitBreaker(
                fail_max=5, reset_timeout=30
            )
        self.breaker = _BasePartner._breakers[self.name]

    def _build_payload(self, alert) -> dict:
        raise NotImplementedError

    def send(self, alert) -> DeliveryResult:
        partner_request_id = str(uuid.uuid4())
        payload = self._build_payload(alert)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = _sign(body, timestamp, get_settings().hmac_signing_key)
        headers = {
            "Content-Type": "application/json",
            "X-PGSCP-Timestamp": timestamp,
            "X-PGSCP-Signature": signature,
            "X-PGSCP-Idempotency-Key": partner_request_id,
        }

        start = time.monotonic()
        attempts = 0
        last_status: int | None = None
        last_error: str | None = None

        def _do_request() -> httpx.Response:
            nonlocal attempts, last_status, last_error
            attempts += 1
            try:
                with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
                    resp = client.post(self.url, content=body, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                raise TransientPartnerError(last_error) from exc
            last_status = resp.status_code
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                raise TransientPartnerError(last_error)
            if resp.status_code >= 400:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                raise PartnerError(last_error)
            return resp

        @retry(
            retry=retry_if_exception_type(TransientPartnerError),
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.2, max=2.0),
            reraise=True,
        )
        def _retrying() -> httpx.Response:
            return self.breaker.call(_do_request)

        try:
            _retrying()
            success = True
        except pybreaker.CircuitBreakerError as exc:
            last_error = f"circuit_open: {exc}"
            success = False
        except (TransientPartnerError, PartnerError, RetryError) as exc:
            last_error = last_error or str(exc)
            success = False

        latency_ms = int((time.monotonic() - start) * 1000)
        result = DeliveryResult(
            success=success,
            attempts=attempts,
            http_status=last_status,
            latency_ms=latency_ms,
            error=last_error,
            partner_request_id=partner_request_id,
        )
        log.info(
            "partner.delivery",
            partner=self.name,
            success=success,
            attempts=attempts,
            http_status=last_status,
            latency_ms=latency_ms,
            error=last_error,
        )
        return result


class SlackWebhookClient(_BasePartner):
    name = "slack"

    def _build_payload(self, alert) -> dict:
        return {
            "text": f":rotating_light: *{alert.severity.upper()}* — {alert.rule} on `{alert.model}`",
            "attachments": [
                {
                    "color": {"critical": "#d00000", "warn": "#f39c12", "info": "#3498db"}.get(
                        alert.severity, "#cccccc"
                    ),
                    "text": alert.message,
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in (alert.evidence or {}).items()
                    ],
                    "footer": f"pgscp • event {alert.event_id}",
                }
            ],
        }


class PagerDutyClient(_BasePartner):
    name = "pagerduty"

    def _build_payload(self, alert) -> dict:
        return {
            "routing_key": "local-dev-routing-key",
            "event_action": "trigger",
            "dedup_key": f"pgscp-{alert.rule}-{alert.model}",
            "payload": {
                "summary": alert.message,
                "severity": alert.severity,
                "source": f"pgscp/{alert.model}",
                "component": alert.rule,
                "custom_details": alert.evidence,
            },
        }
