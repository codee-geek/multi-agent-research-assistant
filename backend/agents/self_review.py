"""
Self-Review Agent
─────────────────
Critically reviews the completed research report — summary, citations, and
evidence quality — before delivery to the user.

Uses GPT-4o with structured output.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from models.schemas import SelfReview

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a rigorous research quality reviewer. You will receive a research question, \
a summary, citations, and evidence validation notes. Critically assess the report \
before it is delivered to the user.

Rules:
- quality_score: 0-10 (10 = publication-ready, 5 = acceptable, below 5 = poor).
- approved=true only if quality_score >= 6.0 AND no critical hallucination risks.
- hallucination_risks: flag claims in the summary not clearly supported by sources.
- weaknesses: be specific — vague summaries, missing perspectives, weak sources, etc.
- improvement_suggestions: actionable fixes (e.g. "Add a source on X", "Clarify claim Y").
- overall_assessment: honest 2-3 sentence verdict for the user.
"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.2, max_tokens=2048)


async def self_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: review the completed research report."""
    query: str = state["query"]
    summary = state.get("summary")
    citations = state.get("citations")
    validation = state.get("evidence_validation")

    logger.info("[SelfReview] Reviewing report for %r", query)

    summary_text = summary.summary if summary else "(no summary)"
    summary_title = summary.title if summary else "(untitled)"
    key_findings = summary.key_findings if summary else []

    citation_lines = []
    if citations:
        for c in citations.citations:
            citation_lines.append(f"  [{c.index}] {c.title} — {c.url}")

    validation_text = ""
    if validation:
        validation_text = (
            f"Validation summary: {validation.validation_summary}\n"
            f"Sources kept: {len(validation.assessments) - validation.rejected_count}\n"
            f"Evidence gaps: {', '.join(validation.evidence_gaps) or 'none'}"
        )

    llm = _get_llm().with_structured_output(SelfReview)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research question: {query}\n\n"
                f"Title: {summary_title}\n\n"
                f"Key findings:\n"
                + "\n".join(f"  - {f}" for f in key_findings)
                + f"\n\nSummary (first 1200 chars):\n{summary_text[:1200]}\n\n"
                f"Citations ({len(citation_lines)}):\n"
                + ("\n".join(citation_lines) or "  (none)")
                + f"\n\nEvidence validation:\n{validation_text or '  (not available)'}"
            )
        ),
    ]

    review: SelfReview = await llm.ainvoke(messages)

    logger.info(
        "[SelfReview] Score: %.1f/10 — approved=%s",
        review.quality_score,
        review.approved,
    )

    step_entry = {
        "agent": "self_review",
        "output": {
            "quality_score": review.quality_score,
            "approved": review.approved,
            "overall_assessment": review.overall_assessment,
            "hallucination_risks": review.hallucination_risks,
        },
    }

    return {
        "self_review": review,
        "current_step": "complete",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", [])
        + messages
        + [AIMessage(content=f"Self-review: {review.quality_score}/10 — {'approved' if review.approved else 'needs improvement'}")],
    }
