"""Unit tests for the rule engine. Each test constructs an InferenceInput + RuleContext
directly so rules can be exercised without a database or SQS."""

from datetime import datetime, timedelta, timezone

import pytest

from worker.rules import (
    AccuracyDrift,
    CostAnomaly,
    InferenceInput,
    LatencyBreach,
    MissingHeartbeat,
    PiiLeak,
    RuleContext,
    StuckModel,
    ToxicityHeuristic,
    evaluate_all,
)


def _base_input(**overrides) -> InferenceInput:
    defaults = dict(
        event_id="evt-1",
        model="gpt-4o",
        provider="openai",
        timestamp=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        latency_ms=300,
        cost_usd=0.001,
        prompt="hi",
        completion="hello",
        predicted_label=None,
        expected_label=None,
    )
    defaults.update(overrides)
    return InferenceInput(**defaults)


def _empty_ctx(**overrides) -> RuleContext:
    defaults = dict(
        avg_cost_usd=None,
        recent_labels=[],
        rolling_accuracy=None,
        last_record_at=None,
        now=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RuleContext(**defaults)


class TestLatencyBreach:
    def test_fires_above_threshold(self):
        result = LatencyBreach().evaluate(_base_input(latency_ms=4200), _empty_ctx())
        assert result is not None
        assert result.rule == "LatencyBreach"
        assert result.severity == "critical"  # 4200 > 2*1500
        assert result.evidence["latency_ms"] == 4200

    def test_warn_severity_just_above(self):
        result = LatencyBreach().evaluate(_base_input(latency_ms=1800), _empty_ctx())
        assert result is not None
        assert result.severity == "warn"

    def test_silent_under_threshold(self):
        assert LatencyBreach().evaluate(_base_input(latency_ms=400), _empty_ctx()) is None


class TestCostAnomaly:
    def test_hard_threshold(self):
        result = CostAnomaly().evaluate(_base_input(cost_usd=0.95), _empty_ctx())
        assert result is not None
        assert result.rule == "CostAnomaly"

    def test_rolling_ratio(self):
        result = CostAnomaly().evaluate(
            _base_input(cost_usd=0.06),
            _empty_ctx(avg_cost_usd=0.01),
        )
        assert result is not None
        assert result.evidence["ratio"] == pytest.approx(6.0)

    def test_silent_when_within_baseline(self):
        assert (
            CostAnomaly().evaluate(_base_input(cost_usd=0.011), _empty_ctx(avg_cost_usd=0.01))
            is None
        )


class TestAccuracyDrift:
    def test_fires_below_floor(self):
        result = AccuracyDrift().evaluate(_base_input(), _empty_ctx(rolling_accuracy=0.62))
        assert result is not None
        assert result.severity == "critical"

    def test_silent_without_context(self):
        assert AccuracyDrift().evaluate(_base_input(), _empty_ctx()) is None


class TestStuckModel:
    def test_fires_when_window_full_of_same_label(self):
        labels = ["cancellation_request"] * 20
        result = StuckModel().evaluate(
            _base_input(predicted_label="cancellation_request"),
            _empty_ctx(recent_labels=labels),
        )
        assert result is not None
        assert result.evidence["stuck_label"] == "cancellation_request"

    def test_silent_with_varied_labels(self):
        labels = ["a", "b"] * 10
        assert (
            StuckModel().evaluate(_base_input(predicted_label="a"), _empty_ctx(recent_labels=labels))
            is None
        )


class TestMissingHeartbeat:
    def test_fires_after_long_silence(self):
        now = datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc)
        result = MissingHeartbeat().evaluate(
            _base_input(timestamp=now),
            _empty_ctx(last_record_at=now - timedelta(minutes=30)),
        )
        assert result is not None
        assert result.evidence["gap_seconds"] == 1800

    def test_silent_within_window(self):
        now = datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc)
        assert (
            MissingHeartbeat().evaluate(
                _base_input(timestamp=now),
                _empty_ctx(last_record_at=now - timedelta(minutes=2)),
            )
            is None
        )


class TestPiiLeak:
    def test_detects_email_and_phone(self):
        completion = "Reach out at jane.doe@example.com or 415-555-0199."
        result = PiiLeak().evaluate(_base_input(completion=completion), _empty_ctx())
        assert result is not None
        assert "email" in result.evidence["pii_hits"]
        assert "phone" in result.evidence["pii_hits"]

    def test_silent_on_clean_text(self):
        assert PiiLeak().evaluate(_base_input(completion="hello world"), _empty_ctx()) is None


class TestToxicityHeuristic:
    def test_fires_on_keyword_match(self):
        result = ToxicityHeuristic().evaluate(
            _base_input(completion="I hate you and everything you stand for"), _empty_ctx()
        )
        assert result is not None

    def test_silent_on_clean_text(self):
        assert (
            ToxicityHeuristic().evaluate(_base_input(completion="thanks for your help"), _empty_ctx())
            is None
        )


def test_evaluate_all_returns_multiple_rules():
    results = evaluate_all(
        _base_input(latency_ms=5000, cost_usd=0.95),
        _empty_ctx(),
    )
    rule_names = {r.rule for r in results}
    assert "LatencyBreach" in rule_names
    assert "CostAnomaly" in rule_names
