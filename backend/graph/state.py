"""LangGraph state definition shared across all agent nodes."""

from __future__ import annotations

from typing import Annotated, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from models.schemas import (
    ResearchPlan,
    SearchResult,
    ResearchSummary,
    CitationOutput,
)


class ResearchState(dict):
    """
    Typed state dict threaded through the LangGraph pipeline.

    Fields
    ------
    query           : original user query
    max_sources     : max results per sub-query (from request)
    plan            : structured research plan (Planner output)
    search_results  : aggregated search results (Retriever output)
    summary         : synthesized summary (Summarizer output)
    citations       : formatted citations (CitationFormatter output)
    current_step    : human-readable label of the active agent
    step_log        : ordered list of step metadata for the UI timeline
    messages        : LangChain message history (add_messages reducer)
    error           : set if any node raises an unrecoverable error
    """

    # We annotate the messages key so LangGraph uses its built-in reducer
    # (appending rather than overwriting).  All other keys overwrite on update.

    # NOTE: LangGraph requires TypedDict for typed states but we keep a plain
    # dict subclass here for flexibility; the annotations below are docstrings
    # rather than runtime-enforced — Pydantic validation happens inside agents.

    def __class_getitem__(cls, _):  # noqa: D105
        return cls


def make_initial_state(query: str, max_sources: int = 5) -> dict[str, Any]:
    return {
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
