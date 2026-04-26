"""Tiny HTTP client for the investigator's feedback endpoint."""

from typing import Any

import httpx

from .settings import get_settings


def post_feedback(
    investigation_id: int,
    correct: bool,
    correct_root_cause: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """POST /investigations/{id}/feedback. Raises on non-2xx."""
    s = get_settings()
    url = f"{s.investigator_feedback_url.rstrip('/')}/investigations/{investigation_id}/feedback"
    payload = {
        "correct": correct,
        "correct_root_cause": correct_root_cause,
        "notes": notes,
    }
    with httpx.Client(timeout=5.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
