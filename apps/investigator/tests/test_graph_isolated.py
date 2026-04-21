"""Graph-level tests — run hypothesize + draft_postmortem against a pre-seeded
state (skipping DB-backed nodes). Mirrors the eval runner's isolated path.
"""

from investigator import nodes
from investigator.schemas import Evidence


def _seed_state(rule: str) -> dict:
    return {
        "alert_id": 42,
        "event_id": "evt-test",
        "model": "gpt-4o-mini",
        "rule": rule,
        "severity": "warn",
        "alert_message": f"{rule} test",
        "alert_evidence": {},
        "alert_created_at": "2026-04-14T10:00:00Z",
        "evidence": [
            Evidence(id="alert", source="alert", summary="test alert", data={}),
            Evidence(
                id="inference_record",
                source="inference_record",
                summary="test metadata",
                data={"metadata": {"latency_ms": 2000}},
            ),
        ],
        "hypotheses": [],
        "verify_loops": 0,
        "tool_calls": 2,
        "cost_usd": 0.0,
    }


def test_graph_happy_latency_breach():
    state = _seed_state("LatencyBreach")
    state.update(nodes.hypothesize(state))
    assert state["hypotheses"], "hypothesize should populate at least one hypothesis"
    assert state["hypotheses"][0].confidence >= 0.5

    state.update(nodes.draft_postmortem(state))
    report = state["report"]
    assert report is not None
    assert report.root_cause_label == "upstream_latency"
    assert report.rule == "LatencyBreach"
    assert len(report.remediation) >= 1


def test_graph_pii_leak_produces_critical_remediation():
    state = _seed_state("PiiLeak")
    state["severity"] = "critical"
    state.update(nodes.hypothesize(state))
    state.update(nodes.draft_postmortem(state))
    report = state["report"]
    assert report.root_cause_label == "weakened_pii_redaction"
    assert any("roll back" in r.lower() or "redaction" in r.lower() for r in report.remediation)


def test_graph_no_hypotheses_falls_back_to_undetermined():
    """If the LLM parse produces nothing, draft_postmortem should degrade to a
    low-confidence 'undetermined' report rather than crashing."""
    state = _seed_state("LatencyBreach")
    # Force empty hypotheses, simulating an LLM parse failure
    state["hypotheses"] = []
    state["llm_response"] = type(
        "R",
        (),
        {
            "parsed": None,
            "backend": "scripted",
            "model_id": "scripted-v1",
            "text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "raw": None,
        },
    )()
    state.update(nodes.draft_postmortem(state))
    report = state["report"]
    assert report is not None
    assert report.confidence <= 0.5
