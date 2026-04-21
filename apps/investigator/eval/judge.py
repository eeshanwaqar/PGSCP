"""LLM-as-judge fallback scorer for unlabelled cases.

Used when a case does not yet have a hand-labelled root_cause. Asks a second
LLM (ideally Claude Opus in prod) to grade the investigation against a rubric.
The judge's output is never used to gate CI — only the hand-labelled cases do
that. This exists so growing the dataset is cheap: new cases get a provisional
score until a human confirms them.
"""

import json
from typing import Any

from investigator.llm import LLMMessage, get_backend

_RUBRIC = """\
Rate the investigation on a 0.0-1.0 scale against these criteria:
  1. root_cause_label is a plausible snake_case cause for the alert
  2. rationale is consistent with the evidence
  3. remediation items are specific and actionable
  4. hypotheses_considered shows genuine alternatives, not rehashed top pick
  5. confidence is calibrated to the evidence quality

Return JSON:
{"overall": <0..1>, "notes": "<one sentence>", "criteria": {"c1":<0..1>,"c2":<0..1>,"c3":<0..1>,"c4":<0..1>,"c5":<0..1>}}
"""


def judge(case: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    payload = {"case": case.get("seed", {}), "report": report}
    messages = [
        LLMMessage(role="system", content=_RUBRIC),
        LLMMessage(role="user", content=json.dumps(payload, default=str)),
    ]
    resp = get_backend().invoke(messages)
    return resp.parsed or {"overall": 0.0, "notes": "judge_unparseable", "criteria": {}}
