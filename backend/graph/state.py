"""LangGraph state definition shared across all agent nodes."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from models.schemas import (
    CitationOutput,
    EvidenceValidation,
    ResearchPlan,
    ResearchSummary,
    SearchResult,
    SelfReview,
)


class ResearchState(TypedDict, total=False):
    """
    Typed state threaded through the LangGraph pipeline.

    Using TypedDict ensures LangGraph merges partial node updates instead of
    replacing the entire state dict on each step.
    """

    query: str
    max_sources: int
    retrieved_count: int
    clarification: str | None
    needs_clarification: bool
    clarification_question: str | None
    ambiguities: list[str]
    plan: ResearchPlan | None
    search_results: list[SearchResult]
    evidence_validation: EvidenceValidation | None
    summary: ResearchSummary | None
    citations: CitationOutput | None
    self_review: SelfReview | None
    current_step: str
    step_log: list[dict[str, Any]]
    messages: Annotated[list[BaseMessage], add_messages]
    error: str | None


def make_initial_state(
    query: str,
    max_sources: int = 5,
    clarification: str | None = None,
) -> ResearchState:
    return {
        "query": query,
        "max_sources": max_sources,
        "retrieved_count": 0,
        "clarification": clarification,
        "needs_clarification": False,
        "clarification_question": None,
        "ambiguities": [],
        "plan": None,
        "search_results": [],
        "evidence_validation": None,
        "summary": None,
        "citations": None,
        "self_review": None,
        "current_step": "initializing",
        "step_log": [],
        "messages": [],
        "error": None,
    }
