"""Eval metrics.

Each metric is a pure function over (case, report). `aggregate` rolls per-case
scores into the headline numbers that the CI gate compares against `main`.
"""

from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass
class CaseScore:
    case_id: str
    root_cause_correct: bool
    evidence_precision: float
    tool_calls: int
    min_tool_calls: int
    cost_usd: float
    latency_ms: int


def score_case(case: dict[str, Any], report: dict[str, Any]) -> CaseScore:
    label = case.get("label", {})
    expected_label = label.get("root_cause_label")
    predicted_label = report.get("root_cause_label")

    root_cause_correct = bool(
        expected_label and predicted_label and expected_label == predicted_label
    )

    expected_evidence = set(label.get("evidence_ids") or [])
    cited_evidence = set()
    for h in report.get("hypotheses_considered") or []:
        cited_evidence.update(h.get("evidence_ids") or [])
    if expected_evidence and cited_evidence:
        evidence_precision = len(expected_evidence & cited_evidence) / len(cited_evidence)
    elif expected_evidence:
        evidence_precision = 0.0
    else:
        evidence_precision = 1.0

    return CaseScore(
        case_id=case.get("id", "unknown"),
        root_cause_correct=root_cause_correct,
        evidence_precision=evidence_precision,
        tool_calls=int(report.get("tool_calls", 0)),
        min_tool_calls=int(label.get("min_tool_calls", 3)),
        cost_usd=float(report.get("cost_usd", 0.0)),
        latency_ms=int(report.get("latency_ms", 0)),
    )


def aggregate(scores: list[CaseScore]) -> dict[str, Any]:
    if not scores:
        return {
            "n": 0,
            "root_cause_accuracy": 0.0,
            "evidence_precision": 0.0,
            "tool_call_efficiency": 0.0,
            "mean_cost_usd": 0.0,
            "p95_latency_ms": 0,
        }
    n = len(scores)
    root_cause_accuracy = sum(1 for s in scores if s.root_cause_correct) / n
    evidence_precision_mean = mean(s.evidence_precision for s in scores)
    efficiency_pairs = [
        (s.min_tool_calls / max(s.tool_calls, 1)) for s in scores if s.tool_calls > 0
    ]
    tool_call_efficiency = mean(efficiency_pairs) if efficiency_pairs else 0.0
    mean_cost_usd = mean(s.cost_usd for s in scores)
    latencies = sorted(s.latency_ms for s in scores)
    p95_index = max(0, int(round(n * 0.95)) - 1)
    p95_latency_ms = latencies[p95_index] if latencies else 0
    return {
        "n": n,
        "root_cause_accuracy": round(root_cause_accuracy, 4),
        "evidence_precision": round(evidence_precision_mean, 4),
        "tool_call_efficiency": round(tool_call_efficiency, 4),
        "mean_cost_usd": round(mean_cost_usd, 6),
        "p95_latency_ms": int(p95_latency_ms),
    }
