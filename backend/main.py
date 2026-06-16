"""
Multi-Agent Research Assistant — FastAPI Backend
─────────────────────────────────────────────────
Endpoints:
  POST /api/research       → SSE stream of agent updates + final result
  GET  /api/research/{id}  → fetch cached result by session ID
  GET  /api/health         → liveness probe
  GET  /api/docs           → Swagger UI (auto-generated)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from graph.research_graph import stream_research
from models.schemas import AgentEvent, ResearchRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Research Assistant",
    description=(
        "4-agent LangGraph pipeline (Planner → Retriever → Summarizer → "
        "Citation Formatter) with MCP tool integration, streaming SSE output, "
        "and structured GPT-4o responses."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory result cache  {session_id: result_dict}
_result_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


# ── Agent display metadata ────────────────────────────────────────────────────

_AGENT_META = {
    "planner": {
        "label": "Research Planner",
        "icon": "🗺️",
        "start_msg": "Decomposing your query into targeted sub-questions…",
    },
    "retriever": {
        "label": "Web Retriever",
        "icon": "🔍",
        "start_msg": "Searching the web for each sub-query via MCP tools…",
    },
    "summarizer": {
        "label": "Research Synthesizer",
        "icon": "📝",
        "start_msg": "Synthesizing findings into a structured summary…",
    },
    "citation_formatter": {
        "label": "Citation Formatter",
        "icon": "📚",
        "start_msg": "Selecting and formatting citations…",
    },
}

_NODE_ORDER = ["planner", "retriever", "summarizer", "citation_formatter"]


# ── SSE event helpers ─────────────────────────────────────────────────────────

def _sse(event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": event_type, "data": json.dumps(payload)}


def _step_start_event(node: str) -> dict[str, str]:
    meta = _AGENT_META.get(node, {"label": node, "icon": "🤖", "start_msg": "Working…"})
    return _sse(
        "step_start",
        {
            "agent": node,
            "label": meta["label"],
            "icon": meta["icon"],
            "message": meta["start_msg"],
            "step": _NODE_ORDER.index(node) + 1 if node in _NODE_ORDER else 0,
            "total_steps": len(_NODE_ORDER),
        },
    )


# ── Research endpoint ──────────────────────────────────────────────────────────

@app.post("/api/research")
async def research(request: ResearchRequest) -> EventSourceResponse:
    """
    Start a research session and stream agent updates via SSE.

    Event types emitted:
      step_start   — agent is beginning its work
      step_output  — agent produced results
      complete     — final accumulated research result
      error        — pipeline error (recoverable or fatal)
    """
    session_id = str(uuid.uuid4())
    start_time = time.monotonic()

    logger.info("[Session %s] Query: %r", session_id, request.query)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        # Send session metadata immediately
        yield _sse(
            "session",
            {"session_id": session_id, "query": request.query},
        )

        accumulated: dict[str, Any] = {}
        prev_node: str | None = None

        try:
            async for chunk in stream_research(request.query, request.max_sources):
                node: str = chunk["node"]
                patch: dict[str, Any] = chunk["state_patch"]

                # Emit step_start once per node transition
                if node != prev_node:
                    yield _step_start_event(node)
                    prev_node = node
                    await asyncio.sleep(0)  # yield control to event loop

                accumulated.update(patch)

                # Build step_output payload based on the node
                if node == "planner" and patch.get("plan"):
                    plan = patch["plan"]
                    yield _sse(
                        "step_output",
                        {
                            "agent": "planner",
                            "sub_queries": plan.sub_queries,
                            "reasoning": plan.reasoning,
                        },
                    )

                elif node == "retriever" and patch.get("search_results") is not None:
                    results = patch["search_results"]
                    yield _sse(
                        "step_output",
                        {
                            "agent": "retriever",
                            "total_results": len(results),
                            "sources": [
                                {"title": r.title, "url": r.url, "query": r.query}
                                for r in results[:10]
                            ],
                        },
                    )

                elif node == "summarizer" and patch.get("summary"):
                    s = patch["summary"]
                    yield _sse(
                        "step_output",
                        {
                            "agent": "summarizer",
                            "title": s.title,
                            "key_findings": s.key_findings,
                            "summary": s.summary,
                        },
                    )

                elif node == "citation_formatter" and patch.get("citations"):
                    c = patch["citations"]
                    yield _sse(
                        "step_output",
                        {
                            "agent": "citation_formatter",
                            "citations": [
                                {
                                    "index": cit.index,
                                    "title": cit.title,
                                    "url": cit.url,
                                    "excerpt": cit.excerpt,
                                    "relevance": cit.relevance,
                                }
                                for cit in c.citations
                            ],
                            "apa_references": c.apa_references,
                        },
                    )

                await asyncio.sleep(0)

            # ── Assemble and emit final result ───────────────────────────────
            elapsed = round(time.monotonic() - start_time, 2)
            final_summary = accumulated.get("summary")
            final_citations = accumulated.get("citations")
            final_plan = accumulated.get("plan")

            final_payload: dict[str, Any] = {
                "session_id": session_id,
                "query": request.query,
                "elapsed_seconds": elapsed,
                "plan": {
                    "sub_queries": final_plan.sub_queries if final_plan else [],
                    "reasoning": final_plan.reasoning if final_plan else "",
                },
                "summary": {
                    "title": final_summary.title if final_summary else "",
                    "summary": final_summary.summary if final_summary else "",
                    "key_findings": final_summary.key_findings if final_summary else [],
                },
                "citations": {
                    "citations": [
                        {
                            "index": c.index,
                            "title": c.title,
                            "url": c.url,
                            "excerpt": c.excerpt,
                            "relevance": c.relevance,
                        }
                        for c in (final_citations.citations if final_citations else [])
                    ],
                    "apa_references": final_citations.apa_references if final_citations else [],
                },
                "total_sources": len(accumulated.get("search_results", [])),
            }

            _result_cache[session_id] = {
                "result": final_payload,
                "cached_at": time.time(),
            }

            yield _sse("complete", final_payload)
            logger.info(
                "[Session %s] Completed in %.2fs — %d sources",
                session_id,
                elapsed,
                final_payload["total_sources"],
            )

        except Exception as exc:
            logger.exception("[Session %s] Pipeline error: %s", session_id, exc)
            yield _sse("error", {"message": str(exc), "session_id": session_id})

    return EventSourceResponse(event_generator())


# ── Cached result retrieval ───────────────────────────────────────────────────

@app.get("/api/research/{session_id}")
async def get_research_result(session_id: str) -> JSONResponse:
    """Retrieve a previously completed research result by session ID."""
    entry = _result_cache.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    age = time.time() - entry["cached_at"]
    if age > _CACHE_TTL_SECONDS:
        del _result_cache[session_id]
        raise HTTPException(status_code=404, detail="Session expired")

    return JSONResponse(entry["result"])


# ── Health probe ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "multi-agent-research-assistant"}


# ── Dev entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENV", "production") == "development",
        log_level="info",
    )
