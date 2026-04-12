"""LLM evaluation rule engine.

Each rule is a small callable class. `evaluate(record, context)` returns None
(rule did not fire) or a `RuleResult` describing the alert to create. The engine
runs every rule against every record; rules are stateless and receive any
historical context they need via `RuleContext`.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import InferenceRecordRow
from .settings import get_settings


@dataclass
class InferenceInput:
    """The subset of an InferenceRecord the rule engine cares about."""

    event_id: str
    model: str
    provider: str
    timestamp: datetime
    latency_ms: int
    cost_usd: float
    prompt: str
    completion: str
    predicted_label: str | None
    expected_label: str | None


@dataclass
class RuleContext:
    """Historical stats for the record's model. Populated once per message."""

    avg_cost_usd: float | None  # rolling mean over last N records for this model
    recent_labels: list[str]  # last N non-null predicted_labels for this model
    rolling_accuracy: float | None  # over last N records where expected_label is set
    last_record_at: datetime | None  # most recent record for this model before `now`
    now: datetime


@dataclass
class RuleResult:
    rule: str
    severity: str  # info | warn | critical
    message: str
    evidence: dict


class Rule(Protocol):
    name: str

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None: ...


# --------------------------------------------------------------------------- #
#  Rules
# --------------------------------------------------------------------------- #


class LatencyBreach:
    name = "LatencyBreach"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        threshold = get_settings().latency_breach_ms
        if record.latency_ms > threshold:
            return RuleResult(
                rule=self.name,
                severity="warn" if record.latency_ms < threshold * 2 else "critical",
                message=(
                    f"{record.model} latency {record.latency_ms}ms exceeded "
                    f"threshold {threshold}ms"
                ),
                evidence={
                    "latency_ms": record.latency_ms,
                    "threshold_ms": threshold,
                    "model": record.model,
                },
            )
        return None


class CostAnomaly:
    name = "CostAnomaly"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        s = get_settings()
        if record.cost_usd > s.cost_anomaly_threshold_usd:
            return RuleResult(
                rule=self.name,
                severity="warn",
                message=(
                    f"{record.model} single-call cost ${record.cost_usd:.4f} "
                    f"exceeds threshold ${s.cost_anomaly_threshold_usd:.4f}"
                ),
                evidence={
                    "cost_usd": record.cost_usd,
                    "threshold_usd": s.cost_anomaly_threshold_usd,
                    "model": record.model,
                },
            )
        if ctx.avg_cost_usd is not None and ctx.avg_cost_usd > 0:
            # Anomaly when cost is >2x the rolling baseline and the baseline is meaningful.
            ratio = record.cost_usd / ctx.avg_cost_usd
            if ratio >= 2.0 and record.cost_usd >= 0.01:
                return RuleResult(
                    rule=self.name,
                    severity="warn",
                    message=(
                        f"{record.model} cost ${record.cost_usd:.4f} is "
                        f"{ratio:.1f}x the rolling avg ${ctx.avg_cost_usd:.4f}"
                    ),
                    evidence={
                        "cost_usd": record.cost_usd,
                        "rolling_avg_usd": ctx.avg_cost_usd,
                        "ratio": ratio,
                        "model": record.model,
                    },
                )
        return None


class AccuracyDrift:
    name = "AccuracyDrift"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        if ctx.rolling_accuracy is None:
            return None
        floor = get_settings().accuracy_drift_floor
        if ctx.rolling_accuracy < floor:
            return RuleResult(
                rule=self.name,
                severity="critical",
                message=(
                    f"{record.model} rolling accuracy "
                    f"{ctx.rolling_accuracy:.2%} fell below floor {floor:.2%}"
                ),
                evidence={
                    "rolling_accuracy": ctx.rolling_accuracy,
                    "floor": floor,
                    "model": record.model,
                },
            )
        return None


class StuckModel:
    name = "StuckModel"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        window = get_settings().stuck_model_window
        labels = ctx.recent_labels
        if len(labels) < window:
            return None
        if len(set(labels)) == 1 and record.predicted_label == labels[0]:
            return RuleResult(
                rule=self.name,
                severity="warn",
                message=(
                    f"{record.model} returned label '{labels[0]}' "
                    f"for the last {window} records — possible stuck classifier"
                ),
                evidence={
                    "stuck_label": labels[0],
                    "window": window,
                    "model": record.model,
                },
            )
        return None


class MissingHeartbeat:
    """Fires when the current record is the first one after a long silence
    from this model — i.e., the model was silent for longer than the heartbeat
    window. This is the near-real-time analogue of a background heartbeat check;
    a scheduled sweep job would complement it in production.
    """

    name = "MissingHeartbeat"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        if ctx.last_record_at is None:
            return None
        gap = record.timestamp - ctx.last_record_at
        threshold = timedelta(minutes=get_settings().missing_heartbeat_minutes)
        if gap > threshold:
            return RuleResult(
                rule=self.name,
                severity="warn",
                message=(
                    f"{record.model} had no records for "
                    f"{gap.total_seconds() / 60:.1f} min "
                    f"(threshold {threshold.total_seconds() / 60:.0f} min)"
                ),
                evidence={
                    "gap_seconds": gap.total_seconds(),
                    "threshold_seconds": threshold.total_seconds(),
                    "model": record.model,
                },
            )
        return None


_PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


class PiiLeak:
    name = "PiiLeak"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        hits: dict[str, int] = {}
        for kind, pattern in _PII_PATTERNS.items():
            count = len(pattern.findall(record.completion))
            if count > 0:
                hits[kind] = count
        if hits:
            return RuleResult(
                rule=self.name,
                severity="critical",
                message=f"{record.model} completion contains possible PII: {sorted(hits)}",
                evidence={"pii_hits": hits, "model": record.model},
            )
        return None


_TOXICITY_KEYWORDS = {
    "kill yourself",
    "i hate you",
    "you are worthless",
    "retard",
    "slur",  # placeholder — real system would use a proper classifier
}


class ToxicityHeuristic:
    """Intentionally simple placeholder — a real deployment plugs in a trained
    classifier (e.g., Detoxify, Perspective API). The point is to demonstrate
    where such a hook belongs in the architecture, not to ship a toxicity model.
    """

    name = "ToxicityHeuristic"

    def evaluate(self, record: InferenceInput, ctx: RuleContext) -> RuleResult | None:
        text = record.completion.lower()
        matched = [kw for kw in _TOXICITY_KEYWORDS if kw in text]
        if matched:
            return RuleResult(
                rule=self.name,
                severity="critical",
                message=f"{record.model} completion matched toxicity keywords: {matched}",
                evidence={"matched": matched, "model": record.model},
            )
        return None


ALL_RULES: list[Rule] = [
    LatencyBreach(),
    CostAnomaly(),
    AccuracyDrift(),
    StuckModel(),
    MissingHeartbeat(),
    PiiLeak(),
    ToxicityHeuristic(),
]


# --------------------------------------------------------------------------- #
#  Context loader
# --------------------------------------------------------------------------- #


def load_context(session: Session, record: InferenceInput) -> RuleContext:
    """Build a RuleContext for the given record using recent history from Postgres."""
    s = get_settings()
    window = max(s.stuck_model_window, 50)

    stmt = (
        select(InferenceRecordRow)
        .where(InferenceRecordRow.model == record.model)
        .where(InferenceRecordRow.event_timestamp < record.timestamp)
        .order_by(InferenceRecordRow.event_timestamp.desc())
        .limit(window)
    )
    rows = list(session.execute(stmt).scalars())

    avg_cost = None
    if rows:
        avg_cost = sum(r.cost_usd for r in rows) / len(rows)

    recent_labels = [r.predicted_label for r in rows if r.predicted_label][: s.stuck_model_window]
    recent_labels.reverse()  # chronological order

    labeled = [r for r in rows if r.expected_label and r.predicted_label]
    rolling_accuracy = None
    if labeled:
        hits = sum(1 for r in labeled if r.predicted_label == r.expected_label)
        rolling_accuracy = hits / len(labeled)

    last_record_at = rows[0].event_timestamp if rows else None

    return RuleContext(
        avg_cost_usd=avg_cost,
        recent_labels=recent_labels,
        rolling_accuracy=rolling_accuracy,
        last_record_at=last_record_at,
        now=datetime.now(timezone.utc),
    )


def evaluate_all(record: InferenceInput, ctx: RuleContext) -> list[RuleResult]:
    results = []
    for rule in ALL_RULES:
        r = rule.evaluate(record, ctx)
        if r is not None:
            results.append(r)
    return results
