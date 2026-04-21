from eval.metrics import aggregate, score_case


def _case(rule_label: str, evidence_ids: list[str]) -> dict:
    return {
        "id": f"test-{rule_label}",
        "seed": {"alert_id": 1, "rule": "LatencyBreach"},
        "label": {
            "root_cause_label": rule_label,
            "evidence_ids": evidence_ids,
            "min_tool_calls": 3,
        },
    }


def _report(rule_label: str, cited: list[str], tool_calls: int = 4) -> dict:
    return {
        "root_cause_label": rule_label,
        "hypotheses_considered": [
            {"label": rule_label, "confidence": 0.8, "evidence_ids": cited}
        ],
        "tool_calls": tool_calls,
        "cost_usd": 0.001,
        "latency_ms": 500,
    }


def test_score_case_correct_label_and_evidence():
    case = _case("upstream_latency", ["alert", "recent_alerts"])
    report = _report("upstream_latency", ["alert", "recent_alerts"])
    score = score_case(case, report)
    assert score.root_cause_correct is True
    assert score.evidence_precision == 1.0


def test_score_case_wrong_label():
    case = _case("upstream_latency", ["alert"])
    report = _report("network_path_degradation", ["alert"])
    score = score_case(case, report)
    assert score.root_cause_correct is False


def test_score_case_partial_evidence_precision():
    case = _case("upstream_latency", ["alert", "recent_alerts"])
    report = _report("upstream_latency", ["alert", "deployments", "logs"])
    score = score_case(case, report)
    # cited = {alert, deployments, logs} (3)
    # expected ∩ cited = {alert} (1)
    # precision = 1/3
    assert round(score.evidence_precision, 4) == round(1 / 3, 4)


def test_aggregate_handles_empty():
    summary = aggregate([])
    assert summary["n"] == 0
    assert summary["root_cause_accuracy"] == 0.0


def test_aggregate_basic():
    scores = [
        score_case(
            _case("upstream_latency", ["alert"]),
            _report("upstream_latency", ["alert"], tool_calls=4),
        ),
        score_case(
            _case("prompt_size_growth", ["inference_record"]),
            _report("prompt_size_growth", ["inference_record"], tool_calls=3),
        ),
    ]
    summary = aggregate(scores)
    assert summary["n"] == 2
    assert summary["root_cause_accuracy"] == 1.0
