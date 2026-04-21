"""LangGraph StateGraph for incident investigation.

Nodes:
  receive_alert → gather_context → hypothesize → (verify?) → draft_postmortem → deliver

Design notes:
  - Verification loops are capped at `graph_verify_max_loops` to bound cost + latency.
  - Every tool output becomes a typed `Evidence` item with a stable id that the LLM
    must cite. This makes `evidence_precision` computable in the eval harness.
  - The graph does not call the LLM directly — it calls `nodes.call_llm`, which
    routes through the `llm.get_backend()` abstraction. That lets the eval harness
    swap backends deterministically.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from . import nodes
from .settings import get_settings
from .state import InvestigationState


def _route_after_hypothesize(state: InvestigationState) -> str:
    s = get_settings()
    verify_loops = state.get("verify_loops", 0)
    hypotheses = state.get("hypotheses", [])
    if not hypotheses:
        return "draft_postmortem"
    top = hypotheses[0]
    if top.confidence >= s.graph_confidence_threshold:
        return "draft_postmortem"
    if verify_loops >= s.graph_verify_max_loops:
        return "draft_postmortem"
    return "verify"


def build_graph() -> Any:
    g = StateGraph(InvestigationState)
    g.add_node("receive_alert", nodes.receive_alert)
    g.add_node("gather_context", nodes.gather_context)
    g.add_node("hypothesize", nodes.hypothesize)
    g.add_node("verify", nodes.verify)
    g.add_node("draft_postmortem", nodes.draft_postmortem)
    g.add_node("deliver", nodes.deliver)

    g.set_entry_point("receive_alert")
    g.add_edge("receive_alert", "gather_context")
    g.add_edge("gather_context", "hypothesize")
    g.add_conditional_edges(
        "hypothesize",
        _route_after_hypothesize,
        {"verify": "verify", "draft_postmortem": "draft_postmortem"},
    )
    g.add_edge("verify", "hypothesize")
    g.add_edge("draft_postmortem", "deliver")
    g.add_edge("deliver", END)

    return g.compile()


_COMPILED: Any | None = None


def get_graph() -> Any:
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED
