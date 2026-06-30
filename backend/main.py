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
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from graph.research_graph import stream_research
from models.schemas import AgentEvent, ResearchRequest
from monitoring.bugbot import BugBot
from monitoring.session_trace import SessionTrace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Research Assistant",
    description=(
        "6-agent LangGraph pipeline (Planner → Retriever → Evidence Validator → "
        "Summarizer → Citation Formatter → Self-Review) with MCP tool integration, "
        "streaming SSE output, and structured GPT-4o responses."
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
    "evidence_validator": {
        "label": "Evidence Validator",
        "icon": "✅",
        "start_msg": "Assessing source relevance and credibility…",
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
    "self_review": {
        "label": "Self-Review",
        "icon": "🔎",
        "start_msg": "Critically reviewing report quality and accuracy…",
    },
}

_NODE_ORDER = [
    "planner",
    "retriever",
    "evidence_validator",
    "summarizer",
    "citation_formatter",
    "self_review",
]


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
      bugbot_flag  — real-time quality/behaviour flag from BugBot monitor
      bugbot_report — end-of-session verdict (ok | warn | fail)
      complete     — final accumulated research result
      error        — pipeline error (recoverable or fatal)
    """
    session_id = str(uuid.uuid4())
    start_time = time.monotonic()

    logger.info(
        "[Session %s] Query: %r%s",
        session_id,
        request.query,
        f" (clarification: {request.clarification!r})" if request.clarification else "",
    )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        # Send session metadata immediately
        yield _sse(
            "session",
            {"session_id": session_id, "query": request.query},
        )

        accumulated: dict[str, Any] = {}
        prev_node: str | None = None
        trace = SessionTrace(
            session_id,
            request.query,
            clarification=request.clarification,
            max_sources=request.max_sources,
        )

        try:
            async for chunk in stream_research(
                request.query,
                request.max_sources,
                request.clarification,
            ):
                node: str = chunk["node"]
                patch: dict[str, Any] = chunk["state_patch"]

                # Emit step_start once per node transition
                if node != prev_node:
                    yield _step_start_event(node)
                    prev_node = node
                    await asyncio.sleep(0)  # yield control to event loop

                accumulated.update(patch)
                trace.record_node(node, patch)

                # BugBot: real-time checks after each agent step
                for flag in BugBot.check_step(node, patch, trace, query=request.query):
                    payload = {
                        "session_id": session_id,
                        **flag.to_dict(),
                    }
                    yield _sse("bugbot_flag", payload)
                    logger.warning(
                        "[BugBot][Session %s] %s @ %s: %s",
                        session_id,
                        flag.severity.value,
                        flag.agent,
                        flag.message,
                    )

                # Planner may request user clarification instead of a plan
                if node == "planner" and patch.get("needs_clarification"):
                    yield _sse(
                        "clarification_needed",
                        {
                            "agent": "planner",
                            "query": request.query,
                            "clarification_question": patch.get("clarification_question", ""),
                            "ambiguities": patch.get("ambiguities") or [],
                            "session_id": session_id,
                        },
                    )
                    yield _sse(
                        "step_output",
                        {
                            "agent": "planner",
                            "action": "clarify",
                            "clarification_question": patch.get("clarification_question", ""),
                            "ambiguities": patch.get("ambiguities") or [],
                        },
                    )
                    logger.info(
                        "[Session %s] Awaiting user clarification: %r",
                        session_id,
                        patch.get("clarification_question"),
                    )
                    await asyncio.sleep(0)
                    continue

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

                elif node == "evidence_validator" and patch.get("evidence_validation"):
                    ev = patch["evidence_validation"]
                    validated = patch.get("search_results") or []
                    yield _sse(
                        "step_output",
                        {
                            "agent": "evidence_validator",
                            "kept": len(validated),
                            "rejected": ev.rejected_count,
                            "validation_summary": ev.validation_summary,
                            "evidence_gaps": ev.evidence_gaps,
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

                elif node == "self_review" and patch.get("self_review"):
                    sr = patch["self_review"]
                    yield _sse(
                        "step_output",
                        {
                            "agent": "self_review",
                            "quality_score": sr.quality_score,
                            "approved": sr.approved,
                            "overall_assessment": sr.overall_assessment,
                            "strengths": sr.strengths,
                            "weaknesses": sr.weaknesses,
                            "hallucination_risks": sr.hallucination_risks,
                            "improvement_suggestions": sr.improvement_suggestions,
                        },
                    )

                await asyncio.sleep(0)

            if accumulated.get("needs_clarification"):
                elapsed = round(time.monotonic() - start_time, 2)
                trace.finalize(status="clarification", elapsed_seconds=elapsed, accumulated=accumulated)
                report = BugBot.finalize_session(
                    trace, accumulated, elapsed_seconds=elapsed
                )
                yield _sse("bugbot_report", report.to_dict())
                logger.info("[Session %s] Paused for user clarification", session_id)
                return

            # ── Assemble and emit final result ───────────────────────────────
            elapsed = round(time.monotonic() - start_time, 2)
            final_summary = accumulated.get("summary")
            final_citations = accumulated.get("citations")
            final_plan = accumulated.get("plan")
            final_validation = accumulated.get("evidence_validation")
            final_review = accumulated.get("self_review")
            validated_results = accumulated.get("search_results") or []

            final_payload: dict[str, Any] = {
                "session_id": session_id,
                "query": request.query,
                "elapsed_seconds": elapsed,
                "plan": {
                    "sub_queries": final_plan.sub_queries if final_plan else [],
                    "reasoning": final_plan.reasoning if final_plan else "",
                },
                "evidence_validation": {
                    "validation_summary": final_validation.validation_summary if final_validation else "",
                    "rejected_count": final_validation.rejected_count if final_validation else 0,
                    "evidence_gaps": final_validation.evidence_gaps if final_validation else [],
                    "assessments": [
                        {
                            "source_index": a.source_index,
                            "relevance_score": a.relevance_score,
                            "credibility_note": a.credibility_note,
                            "is_relevant": a.is_relevant,
                        }
                        for a in (final_validation.assessments if final_validation else [])
                    ],
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
                "self_review": {
                    "quality_score": final_review.quality_score if final_review else 0,
                    "approved": final_review.approved if final_review else False,
                    "strengths": final_review.strengths if final_review else [],
                    "weaknesses": final_review.weaknesses if final_review else [],
                    "hallucination_risks": final_review.hallucination_risks if final_review else [],
                    "improvement_suggestions": final_review.improvement_suggestions if final_review else [],
                    "overall_assessment": final_review.overall_assessment if final_review else "",
                },
                "total_sources": accumulated.get("retrieved_count", len(validated_results)),
                "validated_sources": len(validated_results),
            }

            _result_cache[session_id] = {
                "result": final_payload,
                "cached_at": time.time(),
            }

            yield _sse("complete", final_payload)

            trace.finalize(status="complete", elapsed_seconds=elapsed, accumulated=accumulated)
            report = BugBot.finalize_session(
                trace, accumulated, elapsed_seconds=elapsed
            )
            yield _sse("bugbot_report", report.to_dict())

            logger.info(
                "[Session %s] Completed in %.2fs — %d sources",
                session_id,
                elapsed,
                final_payload["total_sources"],
            )

        except Exception as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            logger.exception("[Session %s] Pipeline error: %s", session_id, exc)
            trace.finalize(
                status="error",
                elapsed_seconds=elapsed,
                error=str(exc),
                accumulated=accumulated,
            )
            report = BugBot.finalize_session(
                trace, accumulated, error=str(exc), elapsed_seconds=elapsed
            )
            yield _sse("bugbot_report", report.to_dict())
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


@app.get("/api/bugbot/observations")
async def bugbot_observations(tail: int = 200) -> JSONResponse:
    """Return the tail of BugBot's rolling observations log."""
    text = BugBot.read_observations(tail_lines=min(tail, 2000))
    return JSONResponse({"observations": text, "path": "backend/logs/bugbot_observations.txt"})


@app.get("/api/bugbot/sessions/{session_id}")
async def bugbot_session_trace(session_id: str) -> JSONResponse:
    """Return the JSON trace for a monitored session."""
    sessions_dir = Path(__file__).resolve().parent / "logs" / "sessions"
    matches = sorted(sessions_dir.glob(f"*_{session_id}.json"), reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail="Session trace not found")
    return JSONResponse(json.loads(matches[0].read_text(encoding="utf-8")))


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
