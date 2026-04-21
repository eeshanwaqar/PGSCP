"""Eval runner — replays the golden dataset through the investigator graph.

Each `golden.jsonl` line is a self-contained case: an `InvestigationState` seed
(alert + inference metadata + pre-baked evidence) and a `label` with the expected
`root_cause_label`, `evidence_ids`, and `min_tool_calls`. Cases are self-contained
so the harness does not need a running database or SQS queue — it can run in CI
against the configured LLM backend (default: scripted) and produce stable numbers.

Usage:
    python -m eval.runner --dataset eval/dataset/golden.jsonl
    python -m eval.runner --dataset eval/dataset/golden.jsonl --backend scripted
    python -m eval.runner --dataset eval/dataset/golden.jsonl --output eval-report.json
"""

import argparse
import json
import os
import sys
import time
from typing import Any

from investigator.llm import reset_backend
from investigator.observability import configure_logging, get_logger
from investigator.schemas import Evidence, InvestigationReport

from .metrics import CaseScore, aggregate, score_case
from .report import render_markdown

log = get_logger(__name__)


def _seed_state(case: dict[str, Any]) -> dict[str, Any]:
    seed = case["seed"]
    evidence = [Evidence(**e) for e in seed.get("evidence", [])]
    return {
        "alert_id": seed["alert_id"],
        "event_id": seed["event_id"],
        "model": seed["model"],
        "rule": seed["rule"],
        "severity": seed["severity"],
        "alert_message": seed.get("alert_message", ""),
        "alert_evidence": seed.get("alert_evidence", {}),
        "alert_created_at": seed.get("alert_created_at", ""),
        "evidence": evidence,
        "hypotheses": [],
        "verify_loops": 0,
        "tool_calls": len(evidence),
        "cost_usd": 0.0,
    }


def _run_case_isolated(case: dict[str, Any]) -> dict[str, Any]:
    """Run only the LLM-backed nodes: hypothesize → draft_postmortem.

    We skip gather_context here because the case already provides canonical
    evidence. This makes the harness pure-function and independent of DB/S3.
    """
    from investigator import nodes

    state = _seed_state(case)
    start = time.monotonic()
    delta = nodes.hypothesize(state)
    state.update(delta)
    delta = nodes.draft_postmortem(state)
    state.update(delta)
    report: InvestigationReport | None = state.get("report")
    latency_ms = int((time.monotonic() - start) * 1000)

    if report is None:
        return {
            "root_cause_label": "undetermined",
            "confidence": 0.0,
            "hypotheses_considered": [],
            "tool_calls": state.get("tool_calls", 0),
            "cost_usd": state.get("cost_usd", 0.0),
            "latency_ms": latency_ms,
        }
    return {
        "root_cause_label": report.root_cause_label,
        "root_cause": report.root_cause,
        "confidence": report.confidence,
        "hypotheses_considered": [
            {
                "label": h.label,
                "rationale": h.rationale,
                "confidence": h.confidence,
                "evidence_ids": h.evidence_ids,
            }
            for h in report.hypotheses_considered
        ],
        "tool_calls": report.tool_calls,
        "cost_usd": report.cost_usd,
        "latency_ms": latency_ms,
    }


def run(dataset_path: str, *, backend: str | None = None) -> tuple[dict[str, Any], list[CaseScore]]:
    if backend:
        os.environ["PGSCP_LLM_BACKEND"] = backend
        reset_backend()

    configure_logging()
    scores: list[CaseScore] = []
    per_case: list[dict[str, Any]] = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            report = _run_case_isolated(case)
            score = score_case(case, report)
            scores.append(score)
            per_case.append({"case_id": score.case_id, "report": report, "score": score.__dict__})

    summary = aggregate(scores)
    summary["backend"] = os.environ.get("PGSCP_LLM_BACKEND", "scripted")
    summary["per_case"] = per_case
    return summary, scores


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval.runner")
    parser.add_argument(
        "--dataset", default=os.path.join(os.path.dirname(__file__), "dataset", "golden.jsonl")
    )
    parser.add_argument("--backend", default=None, help="scripted | bedrock | openai")
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    summary, scores = run(args.dataset, backend=args.backend)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_case"}, indent=2))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(render_markdown(summary, scores))
    return 0


if __name__ == "__main__":
    sys.exit(main())
