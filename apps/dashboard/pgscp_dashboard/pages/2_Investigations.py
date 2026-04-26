"""Investigations page -- the LangGraph trace + verdict + feedback widget.

Each row in `investigations` is one full graph run. Click into one to see:
  - Inputs: alert + event metadata
  - Evidence: every Evidence object the gather/verify nodes collected
  - Hypotheses: every theory the LLM ranked, with confidence
  - Verdict: chosen root cause + remediation list
  - Feedback: button to mark the investigation correct/incorrect; staged
    regressions are picked up by a GitHub Action (see investigator/feedback.py)
"""

import json
from typing import Any

import pandas as pd
import streamlit as st

from pgscp_dashboard import api_client, db

st.set_page_config(page_title="Investigations | PGSCP", page_icon="🧠", layout="wide")
st.title("🧠 Investigations")
st.caption(
    "Each row is one autonomous run of the LangGraph investigator. "
    "Pick one to see the evidence it gathered, the hypotheses it considered, "
    "and the root cause it landed on."
)

with st.sidebar:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

try:
    rows = db.recent_investigations(limit=100)
except Exception as exc:
    st.error(f"Could not load investigations: {exc}")
    st.stop()

if not rows:
    st.info(
        "No investigations yet. The investigator only runs on **critical** alerts. "
        "Trip a critical rule via the API to populate this page."
    )
    st.stop()

# Summary table --------------------------------------------------------------

df = pd.DataFrame(rows)
df["created_at"] = pd.to_datetime(df["created_at"])

def _feedback_glyph(val: Any) -> str:
    if val is True:
        return "✅"
    if val is False:
        return "❌"
    return "❓"

display = df.copy()
display["fb"] = display["feedback_correct"].apply(_feedback_glyph)
display["confidence"] = (display["confidence"] * 100).round(0).astype(int).astype(str) + "%"
display = display[
    [
        "id", "fb", "alert_id", "rule", "model", "root_cause_label",
        "confidence", "tool_calls", "verify_loops", "llm_backend", "created_at",
    ]
].rename(columns={"id": "investigation_id"})

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "investigation_id": st.column_config.NumberColumn("ID", width="small"),
        "fb": st.column_config.TextColumn("Feedback", width="small"),
        "alert_id": st.column_config.NumberColumn("Alert", width="small"),
        "rule": st.column_config.TextColumn("Rule", width="medium"),
        "model": st.column_config.TextColumn("Model"),
        "root_cause_label": st.column_config.TextColumn("Root cause", width="large"),
        "confidence": st.column_config.TextColumn("Confidence", width="small"),
        "tool_calls": st.column_config.NumberColumn("Tool calls", width="small"),
        "verify_loops": st.column_config.NumberColumn("Verify loops", width="small"),
        "llm_backend": st.column_config.TextColumn("Backend", width="small"),
        "created_at": st.column_config.DatetimeColumn("Created", width="medium"),
    },
)

st.divider()

# Drill-down -----------------------------------------------------------------

st.subheader("🔬 Inspect an investigation")
ids = df["id"].tolist()
selected_id = st.selectbox(
    "Pick an investigation id",
    ids,
    format_func=lambda i: f"investigation {i}",
)
inv = db.get_investigation(int(selected_id))
if not inv:
    st.warning("Selected investigation not found.")
    st.stop()

# Top header card ------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Root cause", inv["root_cause_label"])
c2.metric("Confidence", f"{inv['confidence']:.0%}")
c3.metric("Tool calls", inv["tool_calls"])
c4.metric("Verify loops", inv["verify_loops"])

st.markdown(
    f"**Alert id:** `{inv['alert_id']}`  ·  **Event id:** `{inv['event_id']}`  ·  "
    f"**Rule:** `{inv['rule']}`  ·  **Severity:** `{inv['severity']}`  ·  "
    f"**LLM:** `{inv['llm_backend']}` ({inv['llm_model_id']})  ·  "
    f"**Cost:** `${inv['cost_usd']:.4f}`  ·  **Latency:** `{inv['latency_ms']} ms`"
)

st.markdown("**Root cause statement:**")
st.success(inv["root_cause"])

# LangGraph trace ------------------------------------------------------------

report = inv.get("report_json") or {}
if isinstance(report, str):
    try:
        report = json.loads(report)
    except Exception:
        report = {}

with st.expander("🛰️ LangGraph trace", expanded=True):
    st.markdown(
        "The graph followed this sequence (deterministic; same shape every run):\n\n"
        "1. **receive_alert** — load alert + inference metadata from Postgres\n"
        f"2. **gather_context** — collected **{len(report.get('evidence') or [])} Evidence objects** "
        "via 4 deterministic tools (db, s3, cloudwatch, ecs)\n"
        f"3. **hypothesize** — LLM ranked **{len(report.get('hypotheses_considered') or [])} hypotheses** "
        "by confidence\n"
        f"4. **verify** — looped **{inv['verify_loops']}× ** "
        "(stops when confidence ≥ 0.7 or after 2 loops)\n"
        "5. **draft_postmortem** — assembled the report you're reading\n"
        "6. **deliver** — persisted to Postgres + posted to Slack"
    )

# Evidence -------------------------------------------------------------------

evidence = report.get("evidence") or []
with st.expander(f"📂 Evidence bundle ({len(evidence)} items)", expanded=False):
    if not evidence:
        st.info("No evidence captured.")
    else:
        for ev in evidence:
            st.markdown(f"**`{ev.get('id')}`** — _{ev.get('source')}_")
            st.markdown(f"> {ev.get('summary')}")
            if ev.get("data"):
                with st.expander("data", expanded=False):
                    st.json(ev["data"])
            st.markdown("---")

# Hypotheses -----------------------------------------------------------------

hypotheses = report.get("hypotheses_considered") or []
with st.expander(f"💡 Hypotheses considered ({len(hypotheses)})", expanded=False):
    if not hypotheses:
        st.info("No hypotheses captured.")
    else:
        hyp_df = pd.DataFrame(hypotheses)
        if not hyp_df.empty:
            hyp_df = hyp_df.sort_values("confidence", ascending=False)
            for _, h in hyp_df.iterrows():
                st.markdown(
                    f"**{h['label']}** &nbsp; · &nbsp; confidence "
                    f"`{h['confidence']:.0%}`"
                )
                st.markdown(f"> {h.get('rationale', '')}")
                ev_ids = h.get("evidence_ids") or []
                if ev_ids:
                    st.caption("Evidence cited: " + ", ".join(f"`{e}`" for e in ev_ids))
                st.markdown("---")

# Remediation ----------------------------------------------------------------

remediation = report.get("remediation") or []
with st.expander(f"🛠️ Remediation steps ({len(remediation)})", expanded=False):
    if remediation:
        for i, step in enumerate(remediation, 1):
            st.markdown(f"{i}. {step}")
    else:
        st.info("No remediation steps captured.")

# Raw report -----------------------------------------------------------------

with st.expander("📄 Raw report JSON", expanded=False):
    st.json(report)

st.divider()

# Feedback widget ------------------------------------------------------------

st.subheader("📝 Was this investigation correct?")

current_correct = inv.get("feedback_correct")
current_correct_rc = inv.get("feedback_correct_root_cause")
current_notes = inv.get("feedback_notes")

if current_correct is None:
    status_msg = "🕓 No feedback recorded yet."
elif current_correct:
    status_msg = "✅ Marked correct."
else:
    status_msg = (
        f"❌ Marked incorrect. "
        f"Correct root cause: `{current_correct_rc or '(not provided)'}`"
    )
st.info(status_msg)

with st.form(key=f"feedback-{selected_id}", clear_on_submit=False):
    is_correct = st.radio(
        "Verdict",
        options=["correct", "incorrect"],
        index=0 if (current_correct is None or current_correct) else 1,
        horizontal=True,
    )
    correct_root_cause = st.text_input(
        "If incorrect, what's the actual root cause label?",
        value=current_correct_rc or "",
        placeholder="e.g. corrupt_input, model_throttled, ...",
    )
    notes = st.text_area(
        "Notes (optional)",
        value=current_notes or "",
        placeholder="Anything a future reviewer should know...",
    )
    submitted = st.form_submit_button("Submit feedback")

if submitted:
    try:
        result = api_client.post_feedback(
            investigation_id=int(selected_id),
            correct=(is_correct == "correct"),
            correct_root_cause=correct_root_cause or None,
            notes=notes or None,
        )
        st.success(
            f"Feedback saved: `{result}`. "
            "If marked incorrect, the case has also been staged as a regression "
            "for the next golden-set PR."
        )
        st.cache_data.clear()
    except Exception as exc:
        st.error(f"Could not POST feedback: {exc}")
