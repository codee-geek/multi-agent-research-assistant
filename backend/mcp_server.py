"""
MCP Search Server
─────────────────
Exposes DuckDuckGo search as MCP tools that the retriever agent consumes.
Runs as a standalone HTTP service so it works in Docker and CI.

Start:  python mcp_server.py
Port:   8001  (configure via MCP_SERVER_PORT)
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from tools.search import search_web
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Server setup ─────────────────────────────────────────────────────────────

mcp = FastMCP(name="research-tools")


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
    region: str = "wt-wt",
) -> list[dict]:
    """Search the web using DuckDuckGo and return ranked results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (2-10).
        region: DuckDuckGo region code (default: worldwide).

    Returns:
        List of dicts with keys: title, url, snippet.
    """
    max_results = max(2, min(max_results, 10))
    results = search_web(query, max_results=max_results, region=region)
    logger.info("web_search(%r) → %d results", query, len(results))
    return results


@mcp.tool()
def news_search(
    query: str,
    max_results: int = 5,
) -> list[dict]:
    """Search recent news articles using DuckDuckGo News.

    Args:
        query: The news search query.
        max_results: Maximum number of articles to return.

    Returns:
        List of dicts with keys: title, url, snippet, date, source.
    """
    max_results = max(2, min(max_results, 10))
    results: list[dict] = []

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("body", ""),
                        "date": r.get("date", ""),
                        "source": r.get("source", ""),
                    }
                )
    except Exception as exc:
        logger.warning("DuckDuckGo news search failed for %r: %s", query, exc)

    logger.info("news_search(%r) → %d results", query, len(results))
    return results


@mcp.tool()
def batch_search(queries: list[str], max_results_per_query: int = 4) -> dict[str, list[dict]]:
    """Run multiple web searches in sequence and return results keyed by query.

    Args:
        queries: List of search queries (max 10).
        max_results_per_query: Results per query.

    Returns:
        Dict mapping each query to its list of search results.
    """
    queries = queries[:10]
    output: dict[str, list[dict]] = {}

    for q in queries:
        output[q] = web_search(q, max_results=max_results_per_query)

    return output


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    logger.info("Starting MCP research-tools server on %s:%d", host, port)
    mcp.run(transport="sse", host=host, port=port)
