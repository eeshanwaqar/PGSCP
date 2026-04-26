"""PGSCP dashboard -- home page.

Shows a 24h overview of the platform: alerts fired, investigations completed,
mean confidence, and which rules are firing most.
"""

import pandas as pd
import streamlit as st

from pgscp_dashboard import db

st.set_page_config(
    page_title="PGSCP Investigations Dashboard",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛰️ PGSCP Investigations Dashboard")
st.caption(
    "Real-time view of the LLM observability + auto-investigation pipeline. "
    "Every alert and every LangGraph investigation lands here."
)

with st.sidebar:
    st.header("Window")
    window_hours = st.slider("Hours to look back", min_value=1, max_value=168, value=24, step=1)
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown(
        "### Pages\n"
        "- **Home** -- overview metrics\n"
        "- **Alerts** -- live feed of rule firings\n"
        "- **Investigations** -- LangGraph traces + feedback\n"
    )

try:
    metrics = db.overview_metrics(window_hours=window_hours)
except Exception as exc:
    st.error(f"Could not load metrics from Postgres: {exc}")
    st.stop()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric(
    "Alerts fired",
    metrics["alerts_total"],
    help=f"In the last {window_hours}h",
)
col2.metric(
    "Critical alerts",
    metrics["alerts_critical"],
    delta=None if metrics["alerts_critical"] == 0 else "needs attention",
    delta_color="inverse",
)
col3.metric(
    "Investigations",
    metrics["investigations_total"],
)
col4.metric(
    "Mean confidence",
    f"{metrics['investigations_avg_confidence']:.0%}"
    if metrics["investigations_total"]
    else "--",
)
col5.metric(
    "Awaiting feedback",
    metrics["investigations_feedback_pending"],
    help="Investigations not yet labelled correct/incorrect by a human reviewer",
)

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Rules firing most")
    if metrics["rule_breakdown"]:
        df = pd.DataFrame(metrics["rule_breakdown"])
        st.bar_chart(df.set_index("rule"))
    else:
        st.info("No alerts in the selected window. Fire a synthetic event via the API to populate.")

with right:
    st.subheader("How to feed it")
    st.markdown(
        "The dashboard is a **read-only view** over the same Postgres + investigator API "
        "the worker and investigator services already write to.\n\n"
        "Generate traffic by POSTing an `InferenceRecord` to the API service:\n"
    )
    st.code(
        "curl -X POST http://localhost:8000/events \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d '{\"request_id\":\"demo-1\",\"timestamp\":\"2026-04-25T12:00:00Z\","
        "\"model\":\"gpt-4o-mini\",\"provider\":\"openai\","
        "\"prompt\":\"hi\",\"completion\":\"hello at test@example.com\","
        "\"prompt_tokens\":5,\"completion_tokens\":10,"
        "\"latency_ms\":5500,\"cost_usd\":0.95}'",
        language="bash",
    )
    st.caption(
        "That payload is crafted to trip 3 rules: **LatencyBreach**, **CostAnomaly**, **PiiLeak** -- "
        "two are critical, so two investigations will run."
    )

st.divider()
st.caption(
    f"Data window: last {window_hours}h. "
    "Auto-cached for 30 seconds to avoid hammering Postgres on every refresh."
)
