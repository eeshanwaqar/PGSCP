"""Graph node implementations.

Each node is a `(state) -> state_delta` function. LangGraph merges the delta
into the running `InvestigationState`. Nodes are deliberately small so they can
be tested in isolation without spinning up the full graph.
"""

import json
import time
from importlib.resources import files
from typing import Any

from sqlalchemy.orm import Session

from .db import Investigation, get_sessionmaker
from .llm import LLMMessage, LLMResponse, get_backend
from .observability import get_logger
from .schemas import Evidence, Hypothesis, InvestigationReport
from .settings import get_settings
from .tools import cloudwatch, db as db_tools, ecs, s3 as s3_tools

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
#  Prompt loading
# --------------------------------------------------------------------------- #


def _load_prompt(name: str) -> str:
    try:
        return (files("investigator") / "prompts" / name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        import os

        here = os.path.dirname(__file__)
        with open(os.path.join(here, "prompts", name), encoding="utf-8") as f:
            return f.read()


_SYSTEM_PROMPT: str | None = None
_EXAMPLES: str | None = None


def _system_prompt() -> str:
    global _SYSTEM_PROMPT, _EXAMPLES
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _load_prompt("system.md")
    if _EXAMPLES is None:
        _EXAMPLES = _load_prompt("examples.md")
    return f"{_SYSTEM_PROMPT}\n\n---\n\n{_EXAMPLES}"


# --------------------------------------------------------------------------- #
#  Node: receive_alert
# --------------------------------------------------------------------------- #


def _open_session() -> Session:
    return get_sessionmaker()()


def receive_alert(state: dict[str, Any]) -> dict[str, Any]:
    """Load the alert row and its associated inference_record metadata."""
    alert_id = state["alert_id"]
    session = _open_session()
    try:
        alert = db_tools.load_alert(session, alert_id)
        if alert is None:
            return {"error": f"alert {alert_id} not found"}
        inference_meta = db_tools.load_inference_record_metadata(session, alert["event_id"])
    finally:
        session.close()

    delta: dict[str, Any] = {
        "event_id": alert["event_id"],
        "model": alert["model"],
        "rule": alert["rule"],
        "severity": alert["severity"],
        "alert_message": alert["message"],
        "alert_evidence": alert.get("evidence") or {},
        "alert_created_at": alert["created_at"],
        "tool_calls": state.get("tool_calls", 0) + 1,
    }
    if inference_meta:
        delta["inference_meta"] = inference_meta
    return delta


# --------------------------------------------------------------------------- #
#  Node: gather_context
# --------------------------------------------------------------------------- #


def gather_context(state: dict[str, Any]) -> dict[str, Any]:
    """Parallel-ish context fetching. Populates state.evidence."""
    s = get_settings()
    session = _open_session()
    tool_calls = state.get("tool_calls", 0)
    evidence: list[Evidence] = list(state.get("evidence") or [])
    try:
        alert_evidence_item = Evidence(
            id="alert",
            source="alert",
            summary=f"{state['rule']} on {state['model']}: {state['alert_message']}",
            data={
                "severity": state["severity"],
                "evidence": state.get("alert_evidence") or {},
                "created_at": state.get("alert_created_at"),
            },
        )
        evidence.append(alert_evidence_item)

        inference_meta = state.get("inference_meta")
        raw_event: dict[str, Any] = {}
        if inference_meta and inference_meta.get("s3_bucket") and inference_meta.get("s3_key"):
            try:
                raw_event = s3_tools.fetch_inference_record(
                    inference_meta["s3_bucket"], inference_meta["s3_key"]
                )
                tool_calls += 1
            except Exception as exc:
                log.warning("node.gather_context.s3_failed", error=str(exc))
                raw_event = {}

        evidence.append(
            Evidence(
                id="inference_record",
                source="inference_record",
                summary=(
                    f"model={state['model']} latency_ms={inference_meta.get('latency_ms') if inference_meta else '?'} "
                    f"cost_usd={inference_meta.get('cost_usd') if inference_meta else '?'}"
                ),
                data={
                    "metadata": inference_meta or {},
                    "prompt": raw_event.get("prompt", ""),
                    "completion": raw_event.get("completion", ""),
                    "temperature": raw_event.get("temperature"),
                    "tags": raw_event.get("tags", {}),
                },
            )
        )

        recent = db_tools.query_recent_alerts(
            session,
            model=state["model"],
            minutes=30,
            exclude_alert_id=state["alert_id"],
        )
        tool_calls += 1
        evidence.append(
            Evidence(
                id="recent_alerts",
                source="recent_alerts",
                summary=f"{len(recent)} alerts for {state['model']} in the last 30 min",
                data={"alerts": recent[:10]},
            )
        )

        partner_hist = db_tools.partner_delivery_history(session, state["alert_id"])
        tool_calls += 1
        if partner_hist:
            evidence.append(
                Evidence(
                    id="partner_attempts",
                    source="partner_attempts",
                    summary=f"{len(partner_hist)} delivery attempts recorded",
                    data={"attempts": partner_hist},
                )
            )

        deploys = ecs.recent_deployments(service="any", hours=24)
        tool_calls += 1
        evidence.append(
            Evidence(
                id="deployments",
                source="deployments",
                summary=f"{len(deploys)} deploys in last 24h",
                data={"deployments": deploys},
            )
        )

        trace_id = (raw_event.get("tags") or {}).get("trace_id") if raw_event else None
        logs = cloudwatch.query_logs(
            trace_id=trace_id,
            log_group=s.cloudwatch_api_log_group,
            window_minutes=15,
        )
        tool_calls += 1
        if logs:
            evidence.append(
                Evidence(
                    id="logs",
                    source="logs",
                    summary=f"{len(logs)} log lines for trace_id={trace_id}",
                    data={"lines": logs[:20]},
                )
            )
    finally:
        session.close()

    return {"evidence": evidence, "tool_calls": tool_calls, "raw_event": raw_event}


# --------------------------------------------------------------------------- #
#  Node: hypothesize
# --------------------------------------------------------------------------- #


def _evidence_for_prompt(evidence: list[Evidence]) -> list[dict[str, Any]]:
    return [
        {"id": e.id, "source": e.source, "summary": e.summary, "data": e.data} for e in evidence
    ]


def call_llm(state: dict[str, Any]) -> LLMResponse:
    """Single place the graph touches an LLM. Easy to stub in tests."""
    user_payload = {
        "alert_id": state["alert_id"],
        "model": state["model"],
        "rule": state["rule"],
        "severity": state["severity"],
        "alert_message": state.get("alert_message", ""),
        "evidence": _evidence_for_prompt(state.get("evidence") or []),
        "verify_loop": state.get("verify_loops", 0),
    }
    messages = [
        LLMMessage(role="system", content=_system_prompt()),
        LLMMessage(
            role="user",
            content=(
                "Produce a root-cause investigation JSON object for the following alert. "
                "Cite only evidence ids from the evidence array.\n\n"
                + json.dumps(user_payload, default=str)
            ),
        ),
    ]
    return get_backend().invoke(messages)


def hypothesize(state: dict[str, Any]) -> dict[str, Any]:
    response = call_llm(state)
    parsed = response.parsed or {}
    hypotheses_raw = parsed.get("hypotheses_considered") or []
    if not hypotheses_raw and parsed.get("root_cause_label"):
        hypotheses_raw = [
            {
                "label": parsed["root_cause_label"],
                "rationale": parsed.get("root_cause", ""),
                "confidence": parsed.get("confidence", 0.5),
                "evidence_ids": parsed.get("evidence_citations", []),
            }
        ]
    hypotheses: list[Hypothesis] = []
    for h in hypotheses_raw:
        try:
            hypotheses.append(
                Hypothesis(
                    label=h.get("label", "unknown"),
                    rationale=h.get("rationale", ""),
                    confidence=float(h.get("confidence", 0.0)),
                    evidence_ids=list(h.get("evidence_ids", [])),
                )
            )
        except Exception:
            continue
    hypotheses.sort(key=lambda x: x.confidence, reverse=True)

    return {
        "hypotheses": hypotheses,
        "cost_usd": state.get("cost_usd", 0.0) + response.cost_usd,
        "llm_response": response,
    }


# --------------------------------------------------------------------------- #
#  Node: verify
# --------------------------------------------------------------------------- #


def verify(state: dict[str, Any]) -> dict[str, Any]:
    """One more targeted context pass. For now, re-queries recent alerts over a
    larger window as a cheap 'did I miss anything' check. Keeps the node real
    without inflating tool budget.
    """
    session = _open_session()
    evidence: list[Evidence] = list(state.get("evidence") or [])
    try:
        recent = db_tools.query_recent_alerts(
            session,
            model=state["model"],
            minutes=180,
            exclude_alert_id=state["alert_id"],
        )
        evidence = [e for e in evidence if e.id != "recent_alerts_wide"]
        evidence.append(
            Evidence(
                id="recent_alerts_wide",
                source="recent_alerts",
                summary=f"{len(recent)} alerts for {state['model']} in the last 3h (verify pass)",
                data={"alerts": recent[:20]},
            )
        )
    finally:
        session.close()

    return {
        "evidence": evidence,
        "verify_loops": state.get("verify_loops", 0) + 1,
        "tool_calls": state.get("tool_calls", 0) + 1,
    }


# --------------------------------------------------------------------------- #
#  Node: draft_postmortem
# --------------------------------------------------------------------------- #


def draft_postmortem(state: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    top_hypothesis = (state.get("hypotheses") or [None])[0]
    response: LLMResponse = state.get("llm_response") or call_llm(state)
    parsed = response.parsed or {}

    if top_hypothesis is None:
        root_cause_label = parsed.get("root_cause_label", "undetermined")
        root_cause = parsed.get("root_cause", "Evidence insufficient to determine a root cause.")
        confidence = float(parsed.get("confidence", 0.3))
    else:
        root_cause_label = top_hypothesis.label
        root_cause = parsed.get("root_cause") or top_hypothesis.rationale
        confidence = top_hypothesis.confidence

    remediation = parsed.get("remediation") or []
    if not isinstance(remediation, list):
        remediation = [str(remediation)]

    latency_ms = int((time.monotonic() - start) * 1000)
    report = InvestigationReport(
        alert_id=state["alert_id"],
        event_id=state["event_id"],
        model=state["model"],
        rule=state["rule"],
        severity=state["severity"],
        root_cause=root_cause,
        root_cause_label=root_cause_label,
        confidence=confidence,
        evidence=list(state.get("evidence") or []),
        remediation=[str(r) for r in remediation],
        hypotheses_considered=list(state.get("hypotheses") or []),
        tool_calls=state.get("tool_calls", 0),
        verify_loops=state.get("verify_loops", 0),
        cost_usd=state.get("cost_usd", 0.0),
        latency_ms=latency_ms,
        llm_backend=response.backend,
        llm_model_id=response.model_id,
    )
    return {"report": report}


# --------------------------------------------------------------------------- #
#  Node: deliver
# --------------------------------------------------------------------------- #


def deliver(state: dict[str, Any]) -> dict[str, Any]:
    report: InvestigationReport | None = state.get("report")
    if report is None:
        return {"error": "no report to deliver"}
    session = _open_session()
    try:
        row = Investigation(
            alert_id=report.alert_id,
            event_id=report.event_id,
            model=report.model,
            rule=report.rule,
            severity=report.severity,
            root_cause=report.root_cause,
            root_cause_label=report.root_cause_label,
            confidence=report.confidence,
            report_json=json.loads(report.model_dump_json()),
            tool_calls=report.tool_calls,
            verify_loops=report.verify_loops,
            cost_usd=report.cost_usd,
            latency_ms=report.latency_ms,
            llm_backend=report.llm_backend,
            llm_model_id=report.llm_model_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        log.info(
            "investigation.persisted",
            investigation_id=row.id,
            alert_id=report.alert_id,
            root_cause_label=report.root_cause_label,
            confidence=report.confidence,
        )
        _post_to_slack(report)
    finally:
        session.close()
    return {}


def _post_to_slack(report: InvestigationReport) -> None:
    s = get_settings()
    if not s.slack_webhook_url:
        return
    try:
        import httpx

        bullets = "\n".join(f"• {r}" for r in report.remediation[:5])
        body = {
            "text": (
                f":mag: *Investigation* — {report.rule} on `{report.model}` "
                f"(confidence {report.confidence:.0%})"
            ),
            "attachments": [
                {
                    "color": "#3498db",
                    "title": report.root_cause_label,
                    "text": f"{report.root_cause}\n\n*Remediation*\n{bullets}",
                    "footer": (
                        f"pgscp-investigator • alert {report.alert_id} • "
                        f"tools={report.tool_calls} loops={report.verify_loops}"
                    ),
                }
            ],
        }
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
            client.post(s.slack_webhook_url, json=body)
    except Exception as exc:
        log.warning("investigation.slack_post_failed", error=str(exc))
        