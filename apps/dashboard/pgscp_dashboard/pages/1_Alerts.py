"""Alerts page -- live feed of every rule firing.

Click into a row to see the rule's evidence + audit trail + partner deliveries.
"""

import json

import pandas as pd
import streamlit as st

from pgscp_dashboard import db
from pgscp_dashboard.settings import get_settings

st.set_page_config(page_title="Alerts | PGSCP", page_icon="🚨", layout="wide")
st.title("🚨 Alerts")

settings = get_settings()
limit = settings.alerts_limit

with st.sidebar:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

try:
    rows = db.recent_alerts(limit=limit)
except Exception as exc:
    st.error(f"Could not load alerts: {exc}")
    st.stop()

if not rows:
    st.info(
        "No alerts yet. POST an event to the API service to trigger one -- "
        "see the home page for a curl recipe."
    )
    st.stop()

df = pd.DataFrame(rows)
df["created_at"] = pd.to_datetime(df["created_at"])

# Filters --------------------------------------------------------------------

c1, c2, c3 = st.columns(3)
severities = sorted(df["severity"].unique().tolist())
rules = sorted(df["rule"].unique().tolist())
models = sorted(df["model"].unique().tolist())
sel_severity = c1.multiselect("Severity", severities, default=severities)
sel_rule = c2.multiselect("Rule", rules, default=rules)
sel_model = c3.multiselect("Model", models, default=models)

mask = (
    df["severity"].isin(sel_severity)
    & df["rule"].isin(sel_rule)
    & df["model"].isin(sel_model)
)
filtered = df[mask].copy()

st.caption(f"Showing **{len(filtered)}** of {len(df)} loaded alerts (limit: {limit}).")

# Color-code severity in the table -------------------------------------------

def _severity_emoji(sev: str) -> str:
    return {"critical": "🔴", "warn": "🟡", "info": "🔵"}.get(sev, "⚪")


display = filtered[["id", "severity", "rule", "model", "message", "created_at", "status"]].copy()
display["severity"] = display["severity"].apply(lambda s: f"{_severity_emoji(s)} {s}")

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "severity": st.column_config.TextColumn("Severity", width="small"),
        "rule": st.column_config.TextColumn("Rule", width="medium"),
        "model": st.column_config.TextColumn("Model", width="small"),
        "message": st.column_config.TextColumn("Message", width="large"),
        "created_at": st.column_config.DatetimeColumn("Created", width="medium"),
        "status": st.column_config.TextColumn("Status", width="small"),
    },
)

st.divider()

# Drill-down -----------------------------------------------------------------

st.subheader("🔍 Inspect alert")
alert_ids = filtered["id"].tolist()
if not alert_ids:
    st.info("No alerts match the current filters.")
    st.stop()

selected_id = st.selectbox("Pick an alert id", alert_ids, format_func=lambda i: f"alert {i}")
alert_row = filtered[filtered["id"] == selected_id].iloc[0].to_dict()

c1, c2, c3 = st.columns(3)
c1.metric("Severity", alert_row["severity"])
c2.metric("Rule", alert_row["rule"])
c3.metric("Model", alert_row["model"])

st.markdown(f"**Message:** {alert_row['message']}")
st.markdown(f"**Event id:** `{alert_row['event_id']}`")
st.markdown(f"**Created:** `{alert_row['created_at']}`")

with st.expander("Evidence (rule output)", expanded=False):
    evidence = alert_row.get("evidence")
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            pass
    st.json(evidence or {})

with st.expander("Audit trail", expanded=False):
    events = db.alert_events_for(int(selected_id))
    if events:
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
    else:
        st.write("No audit-trail entries.")

with st.expander("Partner delivery attempts", expanded=False):
    attempts = db.partner_attempts_for(int(selected_id))
    if attempts:
        st.dataframe(pd.DataFrame(attempts), use_container_width=True, hide_index=True)
    else:
        st.write("No partner deliveries recorded.")

# Link to investigations -----------------------------------------------------

st.markdown(
    f"➡️ Looking for the LangGraph investigation for this alert? "
    f"Check the **Investigations** page; investigations are keyed by `alert_id = {selected_id}`."
)
