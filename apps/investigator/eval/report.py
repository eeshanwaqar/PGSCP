"""Markdown rendering for the eval report — used by CI gate to post a PR comment."""

from typing import Any

from .metrics import CaseScore


def render_markdown(summary: dict[str, Any], scores: list[CaseScore]) -> str:
    lines = [
        "# Investigator eval",
        "",
        f"**Backend:** `{summary.get('backend', 'scripted')}`",
        f"**Cases:** {summary.get('n', 0)}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| root_cause_accuracy | {summary.get('root_cause_accuracy', 0):.2%} |",
        f"| evidence_precision | {summary.get('evidence_precision', 0):.2%} |",
        f"| tool_call_efficiency | {summary.get('tool_call_efficiency', 0):.2f} |",
        f"| mean_cost_usd | ${summary.get('mean_cost_usd', 0):.6f} |",
        f"| p95_latency_ms | {summary.get('p95_latency_ms', 0)} ms |",
        "",
        "## Per-case",
        "",
        "| case_id | correct | evidence_precision | tool_calls | cost_usd | latency_ms |",
        "|---|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s.case_id} | {'yes' if s.root_cause_correct else 'no'} "
            f"| {s.evidence_precision:.2f} | {s.tool_calls} "
            f"| ${s.cost_usd:.6f} | {s.latency_ms} |"
        )
    return "\n".join(lines) + "\n"
