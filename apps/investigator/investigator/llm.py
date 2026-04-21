"""LLM backend abstraction.

One interface, three backends:

- `ScriptedBackend` — deterministic, no network, no credentials. Produces plausible
  root-cause labels based on the alert rule. Used for local bootstrap, tests, and
  as the default so `docker compose up --build investigator` works out of the box.
- `BedrockBackend` — AWS Bedrock (Claude family). Production target. Requires
  `langchain-aws` extra + IAM permission.
- `OpenAIBackend` — OpenAI-compatible endpoint (official API or a local llama.cpp
  OpenAI-shim). Dev convenience. Requires `openai` extra + `PGSCP_OPENAI_API_KEY`.

All backends return an `LLMResponse` with usage metadata so the eval harness can
compute `cost_usd` consistently.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from .observability import get_logger
from .settings import get_settings

log = get_logger(__name__)


@dataclass
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    backend: str = ""
    model_id: str = ""
    raw: Any = field(default=None, repr=False)


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMBackend:
    name: str = "base"

    def invoke(self, messages: list[LLMMessage], *, response_schema: dict | None = None) -> LLMResponse:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Scripted backend — no credentials required
# --------------------------------------------------------------------------- #

_RULE_TO_SCRIPT = {
    "LatencyBreach": {
        "root_cause_label": "upstream_latency",
        "root_cause": (
            "Upstream LLM provider p95 latency spiked beyond the configured threshold, "
            "likely due to provider-side queueing or a model-server cold start."
        ),
        "confidence": 0.82,
        "remediation": [
            "Check provider status page for the affected model",
            "Inspect recent deployments to rule out client-side timeout regression",
            "Consider falling back to a secondary provider for critical traffic",
        ],
    },
    "CostAnomaly": {
        "root_cause_label": "prompt_size_growth",
        "root_cause": (
            "Per-call cost deviates from the rolling baseline. Most likely driver: "
            "prompt length has grown (RAG context bloat or unbounded history window)."
        ),
        "confidence": 0.78,
        "remediation": [
            "Diff the prompt template against the previous deployment",
            "Inspect retrieved-context length for RAG flows",
            "Add a max-tokens guard on the prompt assembly step",
        ],
    },
    "AccuracyDrift": {
        "root_cause_label": "labelled_distribution_shift",
        "root_cause": (
            "Rolling accuracy has fallen below floor. Most likely driver: inbound "
            "traffic distribution shift (new intent classes or a client-side change)."
        ),
        "confidence": 0.74,
        "remediation": [
            "Break down errors by predicted_label to find the worst class",
            "Pull recent labelled samples into the eval set for regression check",
            "Roll back the most recent prompt or model revision",
        ],
    },
    "PiiLeak": {
        "root_cause_label": "weakened_pii_redaction",
        "root_cause": (
            "Completion contains PII matching the configured patterns. Most likely driver: "
            "redaction step was skipped or regex weakened in the most recent release."
        ),
        "confidence": 0.88,
        "remediation": [
            "Immediately disable the affected route if leakage is active",
            "Audit the redaction middleware for recent diffs",
            "Purge the offending completion from S3 raw archive",
        ],
    },
    "StuckModel": {
        "root_cause_label": "classifier_collapsed_to_majority",
        "root_cause": (
            "Predicted label has not changed for the stuck-window. Most likely driver: "
            "the classifier has collapsed to its majority class (e.g. due to a bad finetune "
            "or a prompt template losing its system instructions)."
        ),
        "confidence": 0.71,
        "remediation": [
            "Check recent deploys for prompt template or model revision changes",
            "Replay 5 labelled samples through the model to confirm collapse",
            "Roll back to the last known-good model revision",
        ],
    },
    "MissingHeartbeat": {
        "root_cause_label": "upstream_traffic_halt",
        "root_cause": (
            "No records received from this model for longer than the heartbeat window. "
            "Most likely driver: upstream client has stopped sending traffic or the "
            "ingestion API is rejecting this model's records."
        ),
        "confidence": 0.69,
        "remediation": [
            "Confirm upstream client liveness and deployment state",
            "Check API 4xx rate for this model over the silent window",
            "Verify SQS depth — messages may be backed up rather than missing",
        ],
    },
    "ToxicityHeuristic": {
        "root_cause_label": "toxicity_keyword_match",
        "root_cause": (
            "Completion matched a toxicity heuristic keyword. Most likely driver: "
            "an adversarial prompt caused the model to echo disallowed content."
        ),
        "confidence": 0.65,
        "remediation": [
            "Inspect the prompt for jailbreak patterns",
            "Strengthen the system prompt's refusal instructions",
            "Route the flagged completion to human review",
        ],
    },
}


class ScriptedBackend(LLMBackend):
    name = "scripted"

    def invoke(self, messages: list[LLMMessage], *, response_schema: dict | None = None) -> LLMResponse:
        rule = ""
        for m in messages:
            if m.role == "user" and '"rule":' in m.content:
                try:
                    payload = json.loads(m.content[m.content.find("{") : m.content.rfind("}") + 1])
                    rule = payload.get("rule", "")
                except Exception:
                    pass
                break

        script = _RULE_TO_SCRIPT.get(rule, _RULE_TO_SCRIPT["LatencyBreach"])
        response_obj = {
            "root_cause_label": script["root_cause_label"],
            "root_cause": script["root_cause"],
            "confidence": script["confidence"],
            "remediation": script["remediation"],
            "hypotheses_considered": [
                {
                    "label": script["root_cause_label"],
                    "rationale": script["root_cause"],
                    "confidence": script["confidence"],
                    "evidence_ids": ["alert", "inference_record"],
                }
            ],
            "evidence_citations": ["alert", "inference_record", "recent_alerts"],
        }
        text = json.dumps(response_obj, indent=2)

        # Approximate token accounting so eval metrics have a number to work with.
        prompt_tokens = sum(len(m.content) for m in messages) // 4
        completion_tokens = len(text) // 4

        return LLMResponse(
            text=text,
            parsed=response_obj,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=0.0,
            backend=self.name,
            model_id="scripted-v1",
        )


# --------------------------------------------------------------------------- #
#  Bedrock backend — real prod target
# --------------------------------------------------------------------------- #


class BedrockBackend(LLMBackend):
    name = "bedrock"

    # Very rough per-million-token prices for Claude 3.5 Sonnet in us-east-1.
    # Override in production from a pricing file; this is enough for eval accounting.
    _PRICE_PROMPT_PER_M = 3.0
    _PRICE_COMPLETION_PER_M = 15.0

    def __init__(self) -> None:
        try:
            import boto3  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("boto3 is required for BedrockBackend") from exc
        self._client = None

    def _lazy_client(self):
        if self._client is None:
            import boto3

            s = get_settings()
            kwargs: dict[str, Any] = {"region_name": s.aws_region}
            if s.aws_endpoint_url:
                kwargs["endpoint_url"] = s.aws_endpoint_url
            self._client = boto3.client("bedrock-runtime", **kwargs)
        return self._client

    def invoke(self, messages: list[LLMMessage], *, response_schema: dict | None = None) -> LLMResponse:
        s = get_settings()
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": m.role, "content": [{"type": "text", "text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": s.llm_max_tokens,
            "temperature": s.llm_temperature,
            "system": system,
            "messages": turns,
        }

        resp = self._lazy_client().invoke_model(
            modelId=s.llm_model_id,
            body=json.dumps(body).encode("utf-8"),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(resp["body"].read())
        text = "".join(
            block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
        )

        usage = payload.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        cost_usd = (
            (prompt_tokens / 1_000_000) * self._PRICE_PROMPT_PER_M
            + (completion_tokens / 1_000_000) * self._PRICE_COMPLETION_PER_M
        )

        parsed = _try_parse_json_block(text)
        return LLMResponse(
            text=text,
            parsed=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            backend=self.name,
            model_id=s.llm_model_id,
            raw=payload,
        )


# --------------------------------------------------------------------------- #
#  OpenAI-compatible backend — dev/test convenience
# --------------------------------------------------------------------------- #


class OpenAIBackend(LLMBackend):
    name = "openai"

    _PRICE_PROMPT_PER_M = 0.15
    _PRICE_COMPLETION_PER_M = 0.60

    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package is required for OpenAIBackend") from exc
        s = get_settings()
        kwargs: dict[str, Any] = {"api_key": s.openai_api_key or "not-a-real-key"}
        if s.openai_base_url:
            kwargs["base_url"] = s.openai_base_url
        self._client = OpenAI(**kwargs)

    def invoke(self, messages: list[LLMMessage], *, response_schema: dict | None = None) -> LLMResponse:
        s = get_settings()
        resp = self._client.chat.completions.create(
            model=s.openai_model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cost_usd = (
            (prompt_tokens / 1_000_000) * self._PRICE_PROMPT_PER_M
            + (completion_tokens / 1_000_000) * self._PRICE_COMPLETION_PER_M
        )
        parsed = _try_parse_json_block(text)
        return LLMResponse(
            text=text,
            parsed=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            backend=self.name,
            model_id=s.openai_model,
            raw=resp,
        )


# --------------------------------------------------------------------------- #


def _try_parse_json_block(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


_BACKEND: LLMBackend | None = None


def get_backend() -> LLMBackend:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    choice = get_settings().llm_backend.lower()
    if choice == "bedrock":
        _BACKEND = BedrockBackend()
    elif choice == "openai":
        _BACKEND = OpenAIBackend()
    else:
        _BACKEND = ScriptedBackend()
    log.info("llm.backend_selected", backend=_BACKEND.name)
    return _BACKEND


def reset_backend() -> None:
    """Test helper — clears the memoized backend."""
    global _BACKEND
    _BACKEND = None
