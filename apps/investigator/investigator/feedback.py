"""Feedback FastAPI mini-app.

Runs alongside the investigator worker loop on a secondary port. Two endpoints:

- `GET /investigations/{id}` — returns the full report + evidence trail
- `POST /investigations/{id}/feedback` — `{correct, correct_root_cause?, notes?}`

When `correct=false`, the service persists the feedback to Postgres and writes
a staged JSON file under `/tmp/pgscp/regressions/<id>.json`. A separate GitHub
Action picks those up and opens a PR to append them to the eval dataset —
keeps the running service stateless and dataset changes in git history.
"""

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .db import Investigation, get_sessionmaker
from .observability import configure_logging, get_logger
from .settings import get_settings

log = get_logger(__name__)

app = FastAPI(title="PGSCP Investigator Feedback", version="0.1.0")


class FeedbackPayload(BaseModel):
    correct: bool
    correct_root_cause: str | None = None
    notes: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: int) -> dict[str, Any]:
    session = get_sessionmaker()()
    try:
        row = session.execute(
            select(Investigation).where(Investigation.id == investigation_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="investigation not found")
        return {
            "id": row.id,
            "alert_id": row.alert_id,
            "event_id": row.event_id,
            "model": row.model,
            "rule": row.rule,
            "severity": row.severity,
            "root_cause": row.root_cause,
            "root_cause_label": row.root_cause_label,
            "confidence": row.confidence,
            "report": row.report_json,
            "tool_calls": row.tool_calls,
            "verify_loops": row.verify_loops,
            "cost_usd": row.cost_usd,
            "latency_ms": row.latency_ms,
            "llm_backend": row.llm_backend,
            "llm_model_id": row.llm_model_id,
            "feedback_correct": row.feedback_correct,
            "feedback_correct_root_cause": row.feedback_correct_root_cause,
            "feedback_notes": row.feedback_notes,
            "created_at": row.created_at.isoformat(),
        }
    finally:
        session.close()


@app.post("/investigations/{investigation_id}/feedback")
def submit_feedback(investigation_id: int, payload: FeedbackPayload) -> dict[str, Any]:
    session = get_sessionmaker()()
    try:
        row = session.execute(
            select(Investigation).where(Investigation.id == investigation_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="investigation not found")
        row.feedback_correct = payload.correct
        row.feedback_correct_root_cause = payload.correct_root_cause
        row.feedback_notes = payload.notes
        session.commit()

        if not payload.correct:
            _stage_regression_for_pr(row, payload)

        return {"status": "recorded", "investigation_id": investigation_id}
    finally:
        session.close()


def _stage_regression_for_pr(row: Investigation, payload: FeedbackPayload) -> None:
    staging_dir = os.environ.get("PGSCP_REGRESSION_STAGING_DIR", "/tmp/pgscp/regressions")
    try:
        os.makedirs(staging_dir, exist_ok=True)
        staged = {
            "investigation_id": row.id,
            "alert_id": row.alert_id,
            "event_id": row.event_id,
            "model": row.model,
            "rule": row.rule,
            "severity": row.severity,
            "predicted_root_cause_label": row.root_cause_label,
            "correct_root_cause": payload.correct_root_cause,
            "notes": payload.notes,
            "report": row.report_json,
        }
        with open(os.path.join(staging_dir, f"{row.id}.json"), "w", encoding="utf-8") as f:
            json.dump(staged, f, indent=2)
        log.info("feedback.regression_staged", investigation_id=row.id, dir=staging_dir)
    except Exception as exc:
        log.warning("feedback.regression_staging_failed", error=str(exc))


def run_feedback_server() -> None:
    """Entrypoint used by `main.py` to run the feedback app in a thread."""
    import uvicorn

    configure_logging()
    s = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=s.feedback_port, log_level=s.log_level.lower())
