from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InferenceRecord(BaseModel):
    """One LLM inference call, posted by a client application for evaluation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"] = "v1"

    request_id: str = Field(..., min_length=1, max_length=128)
    timestamp: datetime

    model: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(..., min_length=1, max_length=64)

    prompt: str
    completion: str

    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    latency_ms: int = Field(..., ge=0)
    cost_usd: float = Field(..., ge=0)

    temperature: float | None = None
    user_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)

    expected_label: str | None = Field(default=None, max_length=128)
    predicted_label: str | None = Field(default=None, max_length=128)

    tags: dict[str, str] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    event_id: str
    trace_id: str
    status: Literal["accepted"] = "accepted"
