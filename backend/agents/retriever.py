"""
Retriever Agent
───────────────
Consumes the research plan produced by the Planner, then calls the MCP
`web_search` tool for each sub-query via the langchain-mcp-adapters client.

Falls back to a direct DuckDuckGo call if the MCP server is unreachable,
so the pipeline remains functional in local dev without Docker.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import AIMessage

from models.schemas import ResearchPlan, SearchResult
from tools.search import search_web

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8001/sse")


async def _search_via_mcp(sub_queries: list[str], max_results: int) -> list[SearchResult]:
    """Use the MCP research-tools server to run batch search."""
    results: list[SearchResult] = []

    client = MultiServerMCPClient(
        {
            "research-tools": {
                "url": MCP_SERVER_URL,
                "transport": "sse",
            }
        }
    )
    tools = await client.get_tools()
    batch_tool = next((t for t in tools if t.name == "batch_search"), None)

    if batch_tool is None:
        raise RuntimeError("batch_search tool not found on MCP server")

    raw: dict[str, list[dict]] = await batch_tool.ainvoke(
        {"queries": sub_queries, "max_results_per_query": max_results}
    )

    for query, hits in raw.items():
        for hit in hits:
            results.append(
                SearchResult(
                    title=hit.get("title", ""),
                    url=hit.get("url", ""),
                    snippet=hit.get("snippet", ""),
                    query=query,
                )
            )

    return results


async def _search_direct_fallback(
    sub_queries: list[str], max_results: int
) -> list[SearchResult]:
    """Direct web search fallback when the MCP server is unavailable or empty."""
    results: list[SearchResult] = []
    for query in sub_queries:
        try:
            for hit in search_web(query, max_results=max_results):
                results.append(
                    SearchResult(
                        title=hit.get("title", ""),
                        url=hit.get("url", ""),
                        snippet=hit.get("snippet", ""),
                        query=query,
                    )
                )
        except Exception as exc:
            logger.warning("Fallback search failed for %r: %s", query, exc)

    return results


async def retriever_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: execute web searches for each sub-query."""
    plan: ResearchPlan = state["plan"]
    max_sources: int = state.get("max_sources", 5)

    logger.info("[Retriever] Running %d sub-queries via MCP", len(plan.sub_queries))

    try:
        results = await _search_via_mcp(plan.sub_queries, max_sources)
        source = "mcp"
    except Exception as exc:
        logger.warning("[Retriever] MCP unavailable (%s), using direct fallback", exc)
        results = await _search_direct_fallback(plan.sub_queries, max_sources)
        source = "direct"

    if not results:
        logger.warning("[Retriever] MCP returned 0 results, trying direct fallback")
        results = await _search_direct_fallback(plan.sub_queries, max_sources)
        source = "direct"

    logger.info("[Retriever] Retrieved %d total results via %s", len(results), source)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_results: list[SearchResult] = []
    for r in results:
        if r.url and r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_results.append(r)

    step_entry = {
        "agent": "retriever",
        "output": {
            "total": len(unique_results),
            "source": source,
            "queries_run": plan.sub_queries,
        },
    }

    return {
        "search_results": unique_results,
        "retrieved_count": len(unique_results),
        "current_step": "evidence_validator",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", [])
        + [AIMessage(content=f"Retrieved {len(unique_results)} sources via {source}.")],
    }
