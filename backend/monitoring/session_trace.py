"""Per-session I/O trace — records every agent input/output for BugBot analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
SESSIONS_DIR = LOGS_DIR / "sessions"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _serialize(value: Any) -> Any:
    """Convert Pydantic models and other objects to JSON-safe data."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class SessionTrace:
    """Accumulates agent-level inputs/outputs for one research session."""

    def __init__(
        self,
        session_id: str,
        query: str,
        *,
        clarification: str | None = None,
        max_sources: int = 5,
    ) -> None:
        self.session_id = session_id
        self.query = query
        self.clarification = clarification
        self.max_sources = max_sources
        self.started_at = _utc_now()
        self.ended_at: str | None = None
        self.status: str = "running"  # running | clarification | complete | error
        self.error: str | None = None
        self.elapsed_seconds: float | None = None
        self.nodes: list[dict[str, Any]] = []
        self.flags: list[dict[str, Any]] = []

    def record_node(self, node: str, patch: dict[str, Any]) -> None:
        entry = {
            "timestamp": _utc_now(),
            "node": node,
            "patch": _serialize(patch),
        }
        self.nodes.append(entry)

    def record_flag(self, flag: dict[str, Any]) -> None:
        self.flags.append({**flag, "timestamp": _utc_now()})

    def finalize(
        self,
        *,
        status: str,
        elapsed_seconds: float | None = None,
        error: str | None = None,
        accumulated: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.status = status
        self.ended_at = _utc_now()
        self.elapsed_seconds = elapsed_seconds
        self.error = error
        return self.to_dict(accumulated=accumulated)

    def to_dict(self, *, accumulated: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "clarification": self.clarification,
            "max_sources": self.max_sources,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
            "nodes": self.nodes,
            "flags": self.flags,
            "final_state": _serialize(accumulated) if accumulated else None,
        }

    def save(self) -> Path:
        """Persist full session trace as JSON."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = SESSIONS_DIR / f"{date_prefix}_{self.session_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
