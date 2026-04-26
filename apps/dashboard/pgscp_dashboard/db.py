"""Read-only DB layer for the dashboard.

Uses raw SQLAlchemy core queries (no ORM mapping needed -- we only read).
Centralizing queries here keeps the page files thin and lets us cache results
with Streamlit's @st.cache_data without leaking SQLAlchemy connections into
the cache layer.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .settings import get_settings


@st.cache_resource
def get_engine() -> Engine:
    return create_engine(get_settings().db_dsn, pool_pre_ping=True, future=True)


def _rows(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        result = conn.execute(text(query), params or {})
        cols = result.keys()
        return [dict(zip(cols, row)) for row in result.fetchall()]


@st.cache_data(ttl=15)
def recent_alerts(limit: int = 200) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, event_id, model, rule, severity, status, message, evidence, created_at
        FROM alerts
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )


@st.cache_data(ttl=15)
def recent_investigations(limit: int = 100) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, alert_id, event_id, model, rule, severity,
               root_cause, root_cause_label, confidence,
               report_json, tool_calls, verify_loops, cost_usd, latency_ms,
               llm_backend, llm_model_id,
               feedback_correct, feedback_correct_root_cause, feedback_notes,
               created_at
        FROM investigations
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )


@st.cache_data(ttl=30)
def get_investigation(investigation_id: int) -> dict[str, Any] | None:
    rows = _rows(
        """
        SELECT id, alert_id, event_id, model, rule, severity,
               root_cause, root_cause_label, confidence,
               report_json, tool_calls, verify_loops, cost_usd, latency_ms,
               llm_backend, llm_model_id,
               feedback_correct, feedback_correct_root_cause, feedback_notes,
               created_at
        FROM investigations
        WHERE id = :id
        """,
        {"id": investigation_id},
    )
    return rows[0] if rows else None


@st.cache_data(ttl=15)
def alert_events_for(alert_id: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, kind, note, created_at
        FROM alert_events
        WHERE alert_id = :alert_id
        ORDER BY created_at ASC
        """,
        {"alert_id": alert_id},
    )


@st.cache_data(ttl=15)
def partner_attempts_for(alert_id: int) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, partner, partner_request_id, attempt, status,
               http_status, error, latency_ms, created_at
        FROM partner_delivery_attempts
        WHERE alert_id = :alert_id
        ORDER BY created_at ASC
        """,
        {"alert_id": alert_id},
    )


@st.cache_data(ttl=30)
def overview_metrics(window_hours: int = 24) -> dict[str, Any]:
    """Single round-trip overview for the home page."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with get_engine().connect() as conn:
        alerts_total = conn.execute(
            text("SELECT COUNT(*) FROM alerts WHERE created_at >= :c"),
            {"c": cutoff},
        ).scalar_one()
        critical = conn.execute(
            text(
                "SELECT COUNT(*) FROM alerts WHERE created_at >= :c AND severity = 'critical'"
            ),
            {"c": cutoff},
        ).scalar_one()
        investigations_total = conn.execute(
            text("SELECT COUNT(*) FROM investigations WHERE created_at >= :c"),
            {"c": cutoff},
        ).scalar_one()
        avg_conf = (
            conn.execute(
                text(
                    "SELECT AVG(confidence) FROM investigations WHERE created_at >= :c"
                ),
                {"c": cutoff},
            ).scalar_one()
            or 0.0
        )
        feedback_pending = conn.execute(
            text(
                "SELECT COUNT(*) FROM investigations "
                "WHERE created_at >= :c AND feedback_correct IS NULL"
            ),
            {"c": cutoff},
        ).scalar_one()

        rule_breakdown = [
            dict(zip(("rule", "count"), row))
            for row in conn.execute(
                text(
                    "SELECT rule, COUNT(*) AS count FROM alerts "
                    "WHERE created_at >= :c GROUP BY rule ORDER BY count DESC"
                ),
                {"c": cutoff},
            ).fetchall()
        ]

    return {
        "window_hours": window_hours,
        "alerts_total": int(alerts_total),
        "alerts_critical": int(critical),
        "investigations_total": int(investigations_total),
        "investigations_avg_confidence": float(avg_conf),
        "investigations_feedback_pending": int(feedback_pending),
        "rule_breakdown": rule_breakdown,
    }
