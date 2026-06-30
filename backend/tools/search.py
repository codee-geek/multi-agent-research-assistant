"""Shared web search helper — prefers the `ddgs` package over deprecated duckduckgo_search."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5, region: str = "wt-wt") -> list[dict]:
    """Run a web search and return list of {title, url, snippet} dicts."""
    max_results = max(1, min(max_results, 10))
    results: list[dict] = []

    try:
        from ddgs import DDGS

        ddgs = DDGS()
        for r in ddgs.text(query, region=region, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                }
            )
        if results:
            return results
    except ImportError:
        logger.debug("ddgs not installed, falling back to duckduckgo_search")
    except Exception as exc:
        logger.warning("ddgs search failed for %r: %s", query, exc)

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for r in ddgs.text(query, region=region, max_results=max_results):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                )
    except Exception as exc:
        logger.warning("duckduckgo_search failed for %r: %s", query, exc)

    logger.info("search_web(%r) → %d results", query, len(results))
    return results
