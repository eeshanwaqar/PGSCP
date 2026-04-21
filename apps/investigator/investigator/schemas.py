"""Pydantic contracts for the investigator.

`InvestigationReport` is the structured artifact the graph produces and what the
eval harness scores. Keep the field names stable — golden.jsonl references them.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    id: str = Field(description="Stable id used by the graph to cite evidence.")
    source: Literal[
        "alert", "inference_record", "recent_alerts", "logs", "deployments", "partner_attempts"
    ]
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    label: str = Field(description="Short machine-readable root-cause label.")
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    alert_id: int
    event_id: str
    model: str
    rule: str
    severity: str

    root_cause: str = Field(description="Human-readable root cause statement.")
    root_cause_label: str = Field(description="Machine-readable enum (e.g. `upstream_latency`).")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
    remediation: list[str]

    hypotheses_considered: list[Hypothesis] = Field(default_factory=list)
    tool_calls: int = 0
    verify_loops: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_backend: str = ""
    llm_model_id: str = ""


class InvestigationEnvelope(BaseModel):
    """What gets stored in Postgres — the report plus versioning."""

    schema_version: Literal["v1"] = "v1"
    report: InvestigationReport
