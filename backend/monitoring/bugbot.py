"""
BugBot — pipeline monitor
──────────────────────────
Watches every research session: logs I/O, runs heuristic checks after each
agent step, flags issues in real time, and appends a human-readable verdict
to logs/bugbot_observations.txt.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from monitoring.session_trace import LOGS_DIR, SessionTrace

logger = logging.getLogger(__name__)

OBSERVATIONS_FILE = LOGS_DIR / "bugbot_observations.txt"
FLAGS_FILE = LOGS_DIR / "bugbot_flags.jsonl"

# Casual / non-research inputs the planner should clarify, not plan around.
_GREETING_ONLY_RE = re.compile(
    r"^(\s*(hi|hello|hey|howdy|greetings|yo|sup|thanks|thank you|good morning|"
    r"good afternoon|good evening)\b[!.?,]*\s*)+$",
    re.IGNORECASE,
)
_CHITCHAT_RE = re.compile(
    r"\b(how are you|how r u|what'?s up|whats up)\b",
    re.IGNORECASE,
)
_GREETING_START_RE = re.compile(
    r"^\s*(hi|hello|hey|howdy|greetings|yo|sup|thanks|thank you)\b",
    re.IGNORECASE,
)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class BugFlag:
    severity: Severity
    category: str
    agent: str
    message: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "agent": self.agent,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class SessionVerdict:
    session_id: str
    query: str
    verdict: Verdict
    flags: list[BugFlag] = field(default_factory=list)
    performed_well: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    agent_summary: list[str] = field(default_factory=list)
    elapsed_seconds: float | None = None
    clarification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "verdict": self.verdict.value,
            "flag_count": len(self.flags),
            "flags": [f.to_dict() for f in self.flags],
            "performed_well": self.performed_well,
            "failed": self.failed,
            "agent_summary": self.agent_summary,
            "elapsed_seconds": self.elapsed_seconds,
            "clarification": self.clarification,
            "observations_file": str(OBSERVATIONS_FILE),
        }


class BugBot:
    """Heuristic monitor for the multi-agent research pipeline."""

    QUALITY_WARN_THRESHOLD = float(os.getenv("BUGBOT_QUALITY_WARN", "6.0"))
    QUALITY_FAIL_THRESHOLD = float(os.getenv("BUGBOT_QUALITY_FAIL", "4.0"))

    @classmethod
    def is_likely_non_research(cls, query: str) -> bool:
        q = query.strip()
        if len(q) < 4:
            return True
        if _GREETING_ONLY_RE.match(q):
            return True
        if _CHITCHAT_RE.search(q) and len(q) < 80:
            return True
        if _GREETING_START_RE.match(q) and len(q) < 60:
            return True
        return False

    @classmethod
    def check_step(
        cls,
        node: str,
        patch: dict[str, Any],
        trace: SessionTrace,
        *,
        query: str,
    ) -> list[BugFlag]:
        """Run fast checks after an agent completes. Returns new flags."""
        flags: list[BugFlag] = []

        if node == "planner":
            flags.extend(cls._check_planner(patch, query))
        elif node == "retriever":
            flags.extend(cls._check_retriever(patch))
        elif node == "evidence_validator":
            flags.extend(cls._check_validator(patch, trace))
        elif node == "summarizer":
            flags.extend(cls._check_summarizer(patch, trace))
        elif node == "self_review":
            flags.extend(cls._check_self_review(patch))
        elif node == "citation_formatter":
            flags.extend(cls._check_citation_formatter(patch, trace))

        for flag in flags:
            trace.record_flag(flag.to_dict())

        return flags

    @classmethod
    def _check_planner(cls, patch: dict[str, Any], query: str) -> list[BugFlag]:
        flags: list[BugFlag] = []

        if patch.get("needs_clarification"):
            return flags  # correct behaviour

        plan = patch.get("plan")
        if plan and cls.is_likely_non_research(query):
            flags.append(
                BugFlag(
                    severity=Severity.HIGH,
                    category="query_mismatch",
                    agent="planner",
                    message="Non-research input was planned instead of asking for clarification",
                    detail=f"Query {query!r} looks like a greeting/chitchat.",
                )
            )

        if plan and len(plan.sub_queries) >= 9:
            flags.append(
                BugFlag(
                    severity=Severity.LOW,
                    category="plan_bloat",
                    agent="planner",
                    message=f"Planner generated {len(plan.sub_queries)} sub-queries (upper bound)",
                    detail="Many sub-queries increase retrieval cost and overlap risk.",
                )
            )

        return flags

    @classmethod
    def _check_retriever(cls, patch: dict[str, Any]) -> list[BugFlag]:
        flags: list[BugFlag] = []
        results = patch.get("search_results") or []
        count = patch.get("retrieved_count", len(results))

        if count == 0:
            flags.append(
                BugFlag(
                    severity=Severity.HIGH,
                    category="empty_retrieval",
                    agent="retriever",
                    message="Web retriever returned zero sources",
                    detail="Check MCP server connectivity or query phrasing.",
                )
            )
        elif count < 5:
            flags.append(
                BugFlag(
                    severity=Severity.MEDIUM,
                    category="sparse_retrieval",
                    agent="retriever",
                    message=f"Only {count} source(s) retrieved — thin evidence base",
                )
            )

        return flags

    @classmethod
    def _check_validator(
        cls, patch: dict[str, Any], trace: SessionTrace
    ) -> list[BugFlag]:
        flags: list[BugFlag] = []
        validated = patch.get("search_results") or []
        ev = patch.get("evidence_validation")

        retrieved = cls._retrieved_count(trace)
        kept = len(validated)
        rejected = ev.rejected_count if ev else 0

        if retrieved > 0 and kept == 0:
            flags.append(
                BugFlag(
                    severity=Severity.CRITICAL,
                    category="source_dropout",
                    agent="evidence_validator",
                    message=f"Retrieved {retrieved} sources but validator kept 0",
                    detail=(
                        "Likely query/plan scope mismatch or validator too strict. "
                        "User will see an empty report."
                    ),
                )
            )
        elif retrieved > 0 and kept < retrieved * 0.2:
            flags.append(
                BugFlag(
                    severity=Severity.HIGH,
                    category="heavy_filtering",
                    agent="evidence_validator",
                    message=f"Validator kept only {kept}/{retrieved} sources ({rejected} rejected)",
                )
            )

        # Detect fallback usage from step_log if present
        step_log = patch.get("step_log") or []
        for entry in reversed(step_log):
            if entry.get("agent") == "evidence_validator":
                output = entry.get("output") or {}
                if output.get("used_fallback"):
                    flags.append(
                        BugFlag(
                            severity=Severity.MEDIUM,
                            category="validator_fallback",
                            agent="evidence_validator",
                            message="Strict validation removed all sources; fallback sources were kept",
                        )
                    )
                break

        return flags

    @classmethod
    def _check_summarizer(cls, patch: dict[str, Any], trace: SessionTrace) -> list[BugFlag]:
        flags: list[BugFlag] = []
        summary = patch.get("summary")
        if not summary:
            return flags

        title = (summary.title or "").lower()
        if title in {"no sources found", "sources filtered out"}:
            retrieved = cls._retrieved_count(trace)
            severity = Severity.CRITICAL if retrieved > 0 else Severity.HIGH
            flags.append(
                BugFlag(
                    severity=severity,
                    category="empty_output",
                    agent="summarizer",
                    message=f"Summary title indicates failure: {summary.title!r}",
                    detail=f"Retrieved count was {retrieved}.",
                )
            )

        return flags

    @classmethod
    def _check_self_review(cls, patch: dict[str, Any]) -> list[BugFlag]:
        flags: list[BugFlag] = []
        review = patch.get("self_review")
        if not review:
            return flags

        score = review.quality_score
        if score < cls.QUALITY_FAIL_THRESHOLD:
            flags.append(
                BugFlag(
                    severity=Severity.HIGH,
                    category="low_quality",
                    agent="self_review",
                    message=f"Self-review score {score:.1f}/10 — report failed quality bar",
                    detail=review.overall_assessment[:200] if review.overall_assessment else "",
                )
            )
        elif score < cls.QUALITY_WARN_THRESHOLD or not review.approved:
            flags.append(
                BugFlag(
                    severity=Severity.MEDIUM,
                    category="quality_warning",
                    agent="self_review",
                    message=f"Self-review score {score:.1f}/10 — needs improvement",
                )
            )

        if review.hallucination_risks:
            flags.append(
                BugFlag(
                    severity=Severity.MEDIUM,
                    category="hallucination_risk",
                    agent="self_review",
                    message=f"{len(review.hallucination_risks)} hallucination risk(s) flagged",
                    detail="; ".join(review.hallucination_risks[:2]),
                )
            )

        return flags

    @classmethod
    def _check_citation_formatter(
        cls, patch: dict[str, Any], trace: SessionTrace
    ) -> list[BugFlag]:
        flags: list[BugFlag] = []
        citations = patch.get("citations")
        retrieved = cls._retrieved_count(trace)
        count = len(citations.citations) if citations else 0

        if retrieved == 0 and count > 0:
            flags.append(
                BugFlag(
                    severity=Severity.CRITICAL,
                    category="fabricated_citations",
                    agent="citation_formatter",
                    message=f"Generated {count} citation(s) with zero retrieved sources",
                    detail="Citations must only come from retrieved search results.",
                )
            )
        return flags

    @classmethod
    def _retrieved_count(cls, trace: SessionTrace) -> int:
        for entry in reversed(trace.nodes):
            if entry["node"] == "retriever":
                patch = entry.get("patch") or {}
                return patch.get("retrieved_count") or len(patch.get("search_results") or [])
        return 0

    @classmethod
    def finalize_session(
        cls,
        trace: SessionTrace,
        accumulated: dict[str, Any] | None = None,
        *,
        error: str | None = None,
        elapsed_seconds: float | None = None,
    ) -> SessionVerdict:
        """Build end-of-session verdict and append to observations file."""
        flags: list[BugFlag] = []
        for f in trace.flags:
            flags.append(
                BugFlag(
                    severity=Severity(f["severity"]),
                    category=f["category"],
                    agent=f["agent"],
                    message=f["message"],
                    detail=f.get("detail", ""),
                )
            )

        if error:
            flags.append(
                BugFlag(
                    severity=Severity.CRITICAL,
                    category="pipeline_error",
                    agent="pipeline",
                    message="Pipeline raised an exception",
                    detail=error[:500],
                )
            )

        agent_summary, performed_well, failed = cls._build_summaries(trace, accumulated)
        verdict = cls._compute_verdict(flags, trace.status, error)

        session_verdict = SessionVerdict(
            session_id=trace.session_id,
            query=trace.query,
            verdict=verdict,
            flags=flags,
            performed_well=performed_well,
            failed=failed,
            agent_summary=agent_summary,
            elapsed_seconds=elapsed_seconds,
            clarification=trace.clarification,
        )

        cls._append_observations(session_verdict)
        cls._append_flag_jsonl(session_verdict)
        trace.save()

        logger.info(
            "[BugBot] Session %s → %s (%d flags)",
            trace.session_id,
            verdict.value,
            len(flags),
        )
        return session_verdict

    @classmethod
    def _compute_verdict(
        cls, flags: list[BugFlag], status: str, error: str | None
    ) -> Verdict:
        if error or status == "error":
            return Verdict.FAIL
        severities = {f.severity for f in flags}
        if Severity.CRITICAL in severities or Severity.HIGH in severities:
            return Verdict.FAIL
        if Severity.MEDIUM in severities or flags:
            return Verdict.WARN
        return Verdict.OK

    @classmethod
    def _build_summaries(
        cls,
        trace: SessionTrace,
        accumulated: dict[str, Any] | None,
    ) -> tuple[list[str], list[str], list[str]]:
        agent_summary: list[str] = []
        performed_well: list[str] = []
        failed: list[str] = []

        for entry in trace.nodes:
            node = entry["node"]
            patch = entry.get("patch") or {}

            if node == "planner":
                if patch.get("needs_clarification"):
                    agent_summary.append("planner: requested user clarification")
                    if trace.status == "clarification":
                        performed_well.append("Planner correctly paused for clarification")
                elif plan := patch.get("plan"):
                    n = len(plan.sub_queries)
                    agent_summary.append(f"planner: generated {n} sub-queries")
                    if not cls.is_likely_non_research(trace.query):
                        performed_well.append(f"Planner decomposed query into {n} sub-queries")

            elif node == "retriever":
                count = patch.get("retrieved_count") or len(patch.get("search_results") or [])
                agent_summary.append(f"retriever: {count} sources fetched")
                if count >= 10:
                    performed_well.append(f"Retriever returned a healthy {count} sources")

            elif node == "evidence_validator":
                kept = len(patch.get("search_results") or [])
                ev = patch.get("evidence_validation")
                rejected = ev.rejected_count if ev else 0
                agent_summary.append(f"evidence_validator: kept {kept}, rejected {rejected}")
                if kept > 0:
                    performed_well.append(f"Validator kept {kept} relevant source(s)")
                elif cls._retrieved_count(trace) > 0:
                    failed.append("Validator rejected all retrieved sources")

            elif node == "summarizer":
                title = patch.get("summary").title if patch.get("summary") else "?"
                agent_summary.append(f"summarizer: {title!r}")
                if title.lower() not in {"no sources found", "sources filtered out"}:
                    performed_well.append("Summarizer produced a substantive report")
                else:
                    failed.append(f"Summarizer output unusable: {title}")

            elif node == "self_review":
                review = patch.get("self_review")
                if review:
                    agent_summary.append(
                        f"self_review: {review.quality_score:.1f}/10, "
                        f"{'approved' if review.approved else 'not approved'}"
                    )
                    if review.approved:
                        performed_well.append(
                            f"Self-review approved report ({review.quality_score:.1f}/10)"
                        )
                    else:
                        failed.append(
                            f"Self-review rejected report ({review.quality_score:.1f}/10)"
                        )

        if trace.status == "clarification":
            performed_well.append("Pipeline correctly paused awaiting user input")

        if cls.is_likely_non_research(trace.query) and trace.status == "complete":
            failed.append("Non-research query completed full pipeline — user likely got wrong output type")

        return agent_summary, performed_well, failed

    @classmethod
    def _append_observations(cls, verdict: SessionVerdict) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "=" * 80,
            f"[{ts}] SESSION: {verdict.session_id} | VERDICT: {verdict.verdict.value.upper()}",
            f"Query: {verdict.query!r}",
        ]
        if verdict.clarification:
            lines.append(f"Clarification: {verdict.clarification!r}")
        if verdict.elapsed_seconds is not None:
            lines.append(f"Elapsed: {verdict.elapsed_seconds:.2f}s")
        lines.append("")

        if verdict.flags:
            lines.append(f"FLAGS ({len(verdict.flags)}):")
            for f in verdict.flags:
                lines.append(
                    f"  [{f.severity.value.upper()}] {f.category} @ {f.agent} — {f.message}"
                )
                if f.detail:
                    lines.append(f"           {f.detail}")
        else:
            lines.append("FLAGS: none — clean run")

        lines.append("")
        lines.append("AGENT TRACE:")
        for s in verdict.agent_summary:
            lines.append(f"  {s}")

        if verdict.performed_well:
            lines.append("")
            lines.append("PERFORMED WELL:")
            for item in verdict.performed_well:
                lines.append(f"  + {item}")

        if verdict.failed:
            lines.append("")
            lines.append("FAILED / NEEDS ATTENTION:")
            for item in verdict.failed:
                lines.append(f"  - {item}")

        lines.append("")
        block = "\n".join(lines) + "\n"

        with OBSERVATIONS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(block)

    @classmethod
    def _append_flag_jsonl(cls, verdict: SessionVerdict) -> None:
        import json

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **verdict.to_dict(),
        }
        with FLAGS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    @classmethod
    def read_observations(cls, tail_lines: int = 200) -> str:
        if not OBSERVATIONS_FILE.exists():
            return "(No observations yet — run a research query to start monitoring.)\n"
        text = OBSERVATIONS_FILE.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) <= tail_lines:
            return text
        return "\n".join(lines[-tail_lines:]) + "\n"
