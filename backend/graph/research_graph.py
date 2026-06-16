"""
Research Graph
──────────────
Defines the 4-node LangGraph pipeline:

    START → planner → retriever → summarizer → citation_formatter → END

Each node is an async function that reads from / writes to the shared state.
The compiled graph is exported as `research_graph` and used by the FastAPI app.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langgraph.graph import StateGraph, START, END

from agents.planner import planner_node
from agents.retriever import retriever_node
from agents.summarizer import summarizer_node
from agents.citation_formatter import citation_formatter_node

logger = logging.getLogger(__name__)


def build_graph() -> Any:
    """Construct and compile the LangGraph research pipeline."""
    builder = StateGraph(dict)  # state is a plain dict

    # ── Register nodes ────────────────────────────────────────────────────
    builder.add_node("planner", planner_node)
    builder.add_node("retriever", retriever_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("citation_formatter", citation_formatter_node)

    # ── Wire edges ────────────────────────────────────────────────────────
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "retriever")
    builder.add_edge("retriever", "summarizer")
    builder.add_edge("summarizer", "citation_formatter")
    builder.add_edge("citation_formatter", END)

    graph = builder.compile()
    logger.info("Research graph compiled: planner → retriever → summarizer → citation_formatter")
    return graph


# Singleton compiled graph
research_graph = build_graph()


async def stream_research(query: str, max_sources: int = 5) -> AsyncIterator[dict[str, Any]]:
    """
    Async generator that streams node-level updates from the graph.

    Yields dicts of the form:
        {"node": "<node_name>", "state_patch": {...updated keys...}}

    The FastAPI SSE endpoint converts these into typed AgentEvent payloads.
    """
    initial_state = {
        "query": query,
        "max_sources": max_sources,
        "plan": None,
        "search_results": [],
        "summary": None,
        "citations": None,
        "current_step": "initializing",
        "step_log": [],
        "messages": [],
        "error": None,
    }

    async for chunk in research_graph.astream(initial_state, stream_mode="updates"):
        for node_name, patch in chunk.items():
            yield {"node": node_name, "state_patch": patch}
