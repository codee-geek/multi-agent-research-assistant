"""
Summarizer Agent
────────────────
Receives the full set of search results and synthesizes them into a
well-structured markdown research summary with key findings.

Uses GPT-4o with structured output and a context-window-aware truncation
strategy so token limits never crash the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from models.schemas import ResearchSummary, SearchResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert research analyst. You will receive a set of web search results \
and must synthesize them into a high-quality research summary.

Requirements:
- Write in clear, authoritative prose.
- Structure the summary with ## section headings.
- Use bullet points only for lists of distinct items (pros/cons, features, etc.).
- Do NOT simply concatenate snippets — synthesize, compare, and analyse.
- Identify agreements and contradictions across sources.
- The summary field must be valid Markdown.
- key_findings should be concise, standalone sentences a reader can skim.
- Title should be 5-10 words, descriptive, not generic.
"""

# Keep to ~6 000 chars to stay well within context window
_MAX_SNIPPET_CHARS = 500
_MAX_TOTAL_CHARS = 12_000


def _format_results(results: list[SearchResult]) -> str:
    chunks: list[str] = []
    total = 0

    for i, r in enumerate(results, 1):
        snippet = r.snippet[:_MAX_SNIPPET_CHARS]
        block = (
            f"[{i}] {r.title}\n"
            f"URL: {r.url}\n"
            f"Query: {r.query}\n"
            f"Snippet: {snippet}\n"
        )
        total += len(block)
        if total > _MAX_TOTAL_CHARS:
            break
        chunks.append(block)

    return "\n".join(chunks)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.3, max_tokens=2048)


async def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: synthesize search results into a structured summary."""
    query: str = state["query"]
    results: list[SearchResult] = state["search_results"]

    logger.info("[Summarizer] Synthesizing %d sources for %r", len(results), query)

    formatted = _format_results(results)

    llm = _get_llm().with_structured_output(ResearchSummary)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Original research question: {query}\n\n"
                f"Search results ({len(results)} sources):\n\n"
                f"{formatted}"
            )
        ),
    ]

    summary: ResearchSummary = await llm.ainvoke(messages)

    logger.info("[Summarizer] Summary generated: %r (%d chars)", summary.title, len(summary.summary))

    step_entry = {
        "agent": "summarizer",
        "output": {
            "title": summary.title,
            "key_findings": summary.key_findings,
            "summary_length": len(summary.summary),
        },
    }

    return {
        "summary": summary,
        "current_step": "citation_formatter",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", [])
        + messages
        + [AIMessage(content=f"Summary: {summary.title}")],
    }
