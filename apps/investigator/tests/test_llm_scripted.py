import json

from investigator.llm import LLMMessage, ScriptedBackend


def _rule_payload(rule: str) -> str:
    return json.dumps({"rule": rule, "model": "test", "alert_id": 1})


def test_scripted_backend_latency_breach():
    backend = ScriptedBackend()
    resp = backend.invoke(
        [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(role="user", content=_rule_payload("LatencyBreach")),
        ]
    )
    assert resp.backend == "scripted"
    assert resp.parsed is not None
    assert resp.parsed["root_cause_label"] == "upstream_latency"
    assert resp.parsed["confidence"] >= 0.5
    assert len(resp.parsed["remediation"]) >= 1


def test_scripted_backend_pii_leak():
    backend = ScriptedBackend()
    resp = backend.invoke(
        [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(role="user", content=_rule_payload("PiiLeak")),
        ]
    )
    assert resp.parsed["root_cause_label"] == "weakened_pii_redaction"


def test_scripted_backend_tokens_nonzero():
    backend = ScriptedBackend()
    resp = backend.invoke(
        [LLMMessage(role="user", content=_rule_payload("CostAnomaly"))]
    )
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
