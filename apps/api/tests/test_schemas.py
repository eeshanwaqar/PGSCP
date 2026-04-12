"""Schema-level tests for the API ingestion contract."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import InferenceRecord


def _valid_payload() -> dict:
    return {
        "schema_version": "v1",
        "request_id": "req-1",
        "timestamp": "2026-04-12T10:00:00+00:00",
        "model": "gpt-4o",
        "provider": "openai",
        "prompt": "hi",
        "completion": "hello",
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "latency_ms": 250,
        "cost_usd": 0.001,
    }


def test_valid_record_parses():
    rec = InferenceRecord.model_validate(_valid_payload())
    assert rec.model == "gpt-4o"
    assert rec.timestamp == datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc)
    assert rec.tags == {}


def test_schema_version_locked_to_v1():
    payload = _valid_payload()
    payload["schema_version"] = "v2"
    with pytest.raises(ValidationError):
        InferenceRecord.model_validate(payload)


def test_rejects_extra_fields():
    payload = _valid_payload()
    payload["nonsense_field"] = "should be rejected"
    with pytest.raises(ValidationError):
        InferenceRecord.model_validate(payload)


def test_negative_cost_rejected():
    payload = _valid_payload()
    payload["cost_usd"] = -0.01
    with pytest.raises(ValidationError):
        InferenceRecord.model_validate(payload)


def test_roundtrip_json():
    rec = InferenceRecord.model_validate(_valid_payload())
    roundtrip = InferenceRecord.model_validate_json(rec.model_dump_json())
    assert roundtrip == rec


def test_sample_event_parses():
    """The happy.json sample must stay in sync with the schema."""
    import pathlib

    path = pathlib.Path(__file__).parents[3] / "local" / "sample-events" / "happy.json"
    payload = json.loads(path.read_text())
    InferenceRecord.model_validate(payload)
