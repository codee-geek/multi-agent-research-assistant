"""
Citation Formatter Agent
────────────────────────
Selects the most relevant sources from the retrieved results and formats
them as structured citations with excerpts, relevance notes, and APA strings.

Uses GPT-4o with structured output; also generates APA-style reference strings
so the frontend can render a proper bibliography.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from models.schemas import CitationOutput, SearchResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an academic citation specialist. Given a list of web sources and a \
research summary, select the most relevant sources and format them as structured \
citations.

Rules:
- ONLY cite sources from the provided list — never invent URLs or titles.
- If no sources are provided, return empty citations and apa_references lists.
- Select 3-6 of the most informative / credible sources.
- For each citation, provide a short excerpt (1-2 sentences) directly from or \
  closely paraphrasing the source snippet.
- The relevance field should be 1 sentence explaining the source's specific \
  contribution to the research.
- For apa_references, generate APA 7th edition web citation strings in the form:
  Author or Site Name. (Year, Month Day). Title. Site. URL
  Use "n.d." for unknown dates. Use the domain name if no author is identifiable.
- Index citations starting at 1.
"""


def _format_sources(results: list[SearchResult]) -> str:
    lines: list[str] = []
    for i, r in enumerate(results[:15], 1):  # cap at 15 for context
        lines.append(
            f"[{i}] Title: {r.title}\n"
            f"    URL: {r.url}\n"
            f"    Snippet: {r.snippet[:300]}\n"
        )
    return "\n".join(lines)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.1, max_tokens=2048)


async def citation_formatter_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: select and format citations from search results."""
    query: str = state["query"]
    results: list[SearchResult] = state["search_results"]
    summary_text: str = state["summary"].summary if state.get("summary") else ""

    logger.info("[CitationFormatter] Formatting citations from %d sources", len(results))

    if not results:
        citations = CitationOutput(citations=[], apa_references=[])
        logger.info("[CitationFormatter] No sources available — skipping LLM citation step")
        return {
            "citations": citations,
            "current_step": "self_review",
            "step_log": state.get("step_log", []) + [{
                "agent": "citation_formatter",
                "output": {"citation_count": 0, "urls": []},
            }],
            "messages": state.get("messages", [])
            + [AIMessage(content="No sources to cite — skipped citation formatting.")],
        }

    formatted_sources = _format_sources(results)
    llm = _get_llm().with_structured_output(CitationOutput)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research question: {query}\n\n"
                f"Summary excerpt (first 600 chars):\n{summary_text[:600]}\n\n"
                f"Available sources:\n{formatted_sources}"
            )
        ),
    ]

    citations: CitationOutput = await llm.ainvoke(messages)

    logger.info(
        "[CitationFormatter] Formatted %d citations", len(citations.citations)
    )

    step_entry = {
        "agent": "citation_formatter",
        "output": {
            "citation_count": len(citations.citations),
            "urls": [c.url for c in citations.citations],
        },
    }

    return {
        "citations": citations,
        "current_step": "self_review",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", [])
        + messages
        + [AIMessage(content=f"Formatted {len(citations.citations)} citations.")],
    }
