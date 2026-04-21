"""Database tools — read-only queries against the worker's schema."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def load_alert(session: Session, alert_id: int) -> dict[str, Any] | None:
    """Fetch a single alert row with its event/model/rule/severity."""
    row = session.execute(
        text(
            """
            SELECT id, event_id, model, rule, severity, status, message, evidence, created_at
            FROM alerts WHERE id = :id
            """
        ),
        {"id": alert_id},
    ).mappings().first()
    if row is None:
        return None
    return _row_to_dict(row)


def query_recent_alerts(
    session: Session, *, model: str, minutes: int, exclude_alert_id: int | None = None
) -> list[dict[str, Any]]:
    """Recent alerts for this model within `minutes`. Used to detect alert bursts."""
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    params: dict[str, Any] = {"model": model, "since": since}
    sql = """
        SELECT id, event_id, rule, severity, message, created_at
        FROM alerts
        WHERE model = :model AND created_at >= :since
    """
    if exclude_alert_id is not None:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = exclude_alert_id
    sql += " ORDER BY created_at DESC LIMIT 50"
    rows = session.execute(text(sql), params).mappings().all()
    return [_row_to_dict(r) for r in rows]


def load_inference_record_metadata(session: Session, event_id: str) -> dict[str, Any] | None:
    """Metadata row (S3 raw payload location, tokens, latency, cost)."""
    row = session.execute(
        text(
            """
            SELECT event_id, model, provider, event_timestamp, latency_ms, cost_usd,
                   prompt_tokens, completion_tokens, predicted_label, expected_label,
                   s3_bucket, s3_key
            FROM inference_records WHERE event_id = :event_id
            """
        ),
        {"event_id": event_id},
    ).mappings().first()
    return _row_to_dict(row) if row else None


def partner_delivery_history(session: Session, alert_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT id, partner, partner_request_id, attempt, status, http_status,
                   error, latency_ms, created_at
            FROM partner_delivery_attempts
            WHERE alert_id = :alert_id
            ORDER BY created_at ASC
            """
        ),
        {"alert_id": alert_id},
    ).mappings().all()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in dict(row).items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
