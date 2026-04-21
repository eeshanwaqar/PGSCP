"""LangGraph state definition.

LangGraph accepts any dict-compatible typed state. Keeping this separate from
the public `InvestigationReport` schema means we can let the graph accumulate
intermediate working data without leaking it into the persisted artifact.
"""

from typing import Any, TypedDict

from .schemas import Evidence, Hypothesis, InvestigationReport


class InvestigationState(TypedDict, total=False):
    alert_id: int
    event_id: str
    model: str
    rule: str
    severity: str
    alert_message: str
    alert_evidence: dict[str, Any]
    alert_created_at: str

    raw_event: dict[str, Any]
    recent_alerts: list[dict[str, Any]]
    recent_deployments: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    partner_history: list[dict[str, Any]]

    evidence: list[Evidence]
    hypotheses: list[Hypothesis]
    verify_loops: int
    tool_calls: int
    cost_usd: float

    report: InvestigationReport | None
    error: str | None
