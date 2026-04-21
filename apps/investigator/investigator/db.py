"""DB layer for the investigator.

Defines the `investigations` table and shares a sessionmaker. The investigator
reads the worker's `alerts` / `inference_records` / `partner_delivery_attempts`
tables but writes only to its own table — so we redeclare only what we read
rather than importing the worker's models (keeps services decoupled at the
Python level even though they share a Postgres schema).
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Investigation(Base):
    """A persisted investigation produced by the LangGraph agent."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))

    root_cause: Mapped[str] = mapped_column(Text)
    root_cause_label: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float)

    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    verify_loops: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    llm_backend: Mapped[str] = mapped_column(String(32))
    llm_model_id: Mapped[str] = mapped_column(String(128))

    feedback_correct: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    feedback_correct_root_cause: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    feedback_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_dsn, pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


def init_db() -> None:
    """Create investigator-owned tables. Safe to call repeatedly."""
    Base.metadata.create_all(bind=get_engine())
