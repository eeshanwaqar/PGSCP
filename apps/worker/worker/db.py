from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InferenceRecordRow(Base):
    """Metadata + idempotency record. Raw prompt/completion live in S3, not here."""

    __tablename__ = "inference_records"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_inference_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)

    model: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)

    predicted_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    s3_bucket: Mapped[str] = mapped_column(String(256))
    s3_key: Mapped[str] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    rule: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))  # info | warn | critical
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved
    message: Mapped[str] = mapped_column(String(1024))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AlertEvent(Base):
    """Immutable transitions on an alert. Append-only."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # created | escalated | resolved
    note: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PartnerDeliveryAttempt(Base):
    __tablename__ = "partner_delivery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    partner: Mapped[str] = mapped_column(String(32))  # slack | pagerduty
    partner_request_id: Mapped[str] = mapped_column(String(128), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # success | failure | skipped
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    """Create all tables. Used by local init path; in AWS, Alembic handles this."""
    Base.metadata.create_all(bind=get_engine())
