"""
Research Graph
──────────────
Defines the 6-node LangGraph pipeline:

    START → planner → retriever → evidence_validator → summarizer
          → citation_formatter → self_review → END
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langgraph.graph import StateGraph, START, END

from agents.planner import planner_node
from agents.retriever import retriever_node
from agents.evidence_validator import evidence_validator_node
from agents.summarizer import summarizer_node
from agents.citation_formatter import citation_formatter_node
from agents.self_review import self_review_node
from graph.state import ResearchState, make_initial_state

logger = logging.getLogger(__name__)


def _route_after_planner(state: ResearchState) -> str:
    if state.get("needs_clarification"):
        return END
    return "retriever"


def build_graph() -> Any:
    """Construct and compile the LangGraph research pipeline."""
    builder = StateGraph(ResearchState)

    builder.add_node("planner", planner_node)
    builder.add_node("retriever", retriever_node)
    builder.add_node("evidence_validator", evidence_validator_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("citation_formatter", citation_formatter_node)
    builder.add_node("self_review", self_review_node)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"retriever": "retriever", END: END},
    )
    builder.add_edge("retriever", "evidence_validator")
    builder.add_edge("evidence_validator", "summarizer")
    builder.add_edge("summarizer", "citation_formatter")
    builder.add_edge("citation_formatter", "self_review")
    builder.add_edge("self_review", END)

    graph = builder.compile()
    logger.info(
        "Research graph compiled: planner → retriever → evidence_validator "
        "→ summarizer → citation_formatter → self_review"
    )
    return graph


research_graph = build_graph()


async def stream_research(
    query: str,
    max_sources: int = 5,
    clarification: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Async generator that streams node-level updates from the graph.

    Yields dicts of the form:
        {"node": "<node_name>", "state_patch": {...updated keys...}}
    """
    initial_state = make_initial_state(query, max_sources, clarification)

    async for chunk in research_graph.astream(initial_state, stream_mode="updates"):
        for node_name, patch in chunk.items():
            yield {"node": node_name, "state_patch": patch}
