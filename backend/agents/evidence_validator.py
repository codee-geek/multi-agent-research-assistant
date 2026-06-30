"""
Evidence Validator Agent
────────────────────────
Reviews retrieved search results for relevance, credibility, and coverage.
Filters out low-quality or off-topic sources before synthesis.

Uses GPT-4o with structured output.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from models.schemas import EvidenceValidation, ResearchPlan, SearchResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an evidence validation specialist. Given a research plan and a list of \
web search results, assess each source for relevance and credibility.

Rules:
- Judge relevance against the **research plan** (reasoning + sub-queries), not \
  only the raw user query. Sources retrieved for planned sub-queries should be \
  scored on whether they help answer that planned scope.
- Score relevance from 0.0 (completely off-topic) to 1.0 (highly relevant).
- Mark is_relevant=true for sources with relevance_score >= 0.4 that contribute \
  to the planned research scope.
- credibility_note should flag spam, outdated, or low-trust domains.
- evidence_gaps should list important sub-topics NOT covered by relevant sources.
- Be strict about spam and clearly off-topic sources, but do not reject sources \
  that legitimately address the planner's sub-queries.
- source_index is 1-based, matching the numbered list provided.
"""

_MAX_SOURCES = 20
_MAX_SNIPPET_CHARS = 300
_FALLBACK_KEEP = 3
_FALLBACK_MIN_SCORE = 0.25


def _format_sources(results: list[SearchResult]) -> str:
    lines: list[str] = []
    for i, r in enumerate(results[:_MAX_SOURCES], 1):
        lines.append(
            f"[{i}] Title: {r.title}\n"
            f"    URL: {r.url}\n"
            f"    Query: {r.query}\n"
            f"    Snippet: {r.snippet[:_MAX_SNIPPET_CHARS]}\n"
        )
    return "\n".join(lines)


def _format_plan_context(query: str, plan: ResearchPlan | None) -> str:
    if not plan:
        return f"Original user query: {query}"

    sub_queries = "\n".join(f"  - {q}" for q in plan.sub_queries)
    return (
        f"Original user query: {query}\n"
        f"Research plan reasoning: {plan.reasoning}\n"
        f"Sub-queries used for retrieval:\n{sub_queries}"
    )


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.1, max_tokens=2048)


def _filter_validated(
    results: list[SearchResult], validation: EvidenceValidation
) -> list[SearchResult]:
    """Keep only sources marked is_relevant by the validator."""
    keep_indices = {
        a.source_index
        for a in validation.assessments
        if a.is_relevant and 1 <= a.source_index <= len(results)
    }
    return [r for i, r in enumerate(results, 1) if i in keep_indices]


def _fallback_keep_top_scored(
    results: list[SearchResult], validation: EvidenceValidation
) -> list[SearchResult]:
    """If strict filtering removed everything, keep the highest-scored sources."""
    scored = sorted(
        (
            (a.source_index, a.relevance_score)
            for a in validation.assessments
            if 1 <= a.source_index <= len(results)
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    keep_indices = {
        idx for idx, score in scored[:_FALLBACK_KEEP] if score >= _FALLBACK_MIN_SCORE
    }
    return [r for i, r in enumerate(results, 1) if i in keep_indices]


async def evidence_validator_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: validate and filter retrieved sources."""
    query: str = state["query"]
    plan: ResearchPlan | None = state.get("plan")
    results: list[SearchResult] = state.get("search_results") or []
    assessed = results[:_MAX_SOURCES]

    logger.info("[EvidenceValidator] Validating %d sources for %r", len(results), query)

    if not results:
        validation = EvidenceValidation(
            assessments=[],
            rejected_count=0,
            validation_summary="No sources retrieved to validate.",
            evidence_gaps=["No web sources were retrieved for this query."],
        )
        return {
            "evidence_validation": validation,
            "search_results": [],
            "current_step": "summarizer",
            "step_log": state.get("step_log", []) + [{
                "agent": "evidence_validator",
                "output": {"kept": 0, "rejected": 0, "gaps": validation.evidence_gaps},
            }],
            "messages": state.get("messages", [])
            + [AIMessage(content="Evidence validation: no sources to assess.")],
        }

    formatted = _format_sources(results)
    llm = _get_llm().with_structured_output(EvidenceValidation)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"{_format_plan_context(query, plan)}\n\n"
                f"Retrieved sources ({len(assessed)} shown):\n\n"
                f"{formatted}"
            )
        ),
    ]

    validation: EvidenceValidation = await llm.ainvoke(messages)
    validated_results = _filter_validated(assessed, validation)
    used_fallback = False

    if not validated_results and validation.assessments:
        validated_results = _fallback_keep_top_scored(assessed, validation)
        used_fallback = bool(validated_results)
        if used_fallback:
            validation = validation.model_copy(
                update={
                    "validation_summary": (
                        f"{validation.validation_summary} "
                        f"Strict filtering removed all sources; kept "
                        f"{len(validated_results)} highest-scored source(s) as fallback."
                    ).strip()
                }
            )

    rejected = len(assessed) - len(validated_results)
    validation = validation.model_copy(update={"rejected_count": rejected})

    logger.info(
        "[EvidenceValidator] Kept %d / %d sources (%s), %d gaps identified",
        len(validated_results),
        len(results),
        "fallback" if used_fallback else "strict",
        len(validation.evidence_gaps),
    )

    step_entry = {
        "agent": "evidence_validator",
        "output": {
            "kept": len(validated_results),
            "rejected": rejected,
            "gaps": validation.evidence_gaps,
            "summary": validation.validation_summary,
            "used_fallback": used_fallback,
        },
    }

    return {
        "evidence_validation": validation,
        "search_results": validated_results,
        "current_step": "summarizer",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", [])
        + messages
        + [AIMessage(content=f"Validated {len(validated_results)} of {len(results)} sources.")],
    }
