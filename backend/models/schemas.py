"""Pydantic schemas for structured LLM output and API contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Structured LLM outputs ──────────────────────────────────────────────────

class ResearchPlan(BaseModel):
    """Output of the Planner agent."""
    sub_queries: list[str] = Field(
        description="3-5 specific search queries that together cover the research topic",
        min_length=2,
        max_length=6,
    )
    reasoning: str = Field(description="Brief explanation of why these queries cover the topic")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    query: str  # which sub-query produced this result


class RetrievalOutput(BaseModel):
    """Output of the Retriever agent."""
    results: list[SearchResult]
    total_sources: int


class ResearchSummary(BaseModel):
    """Output of the Summarizer agent."""
    title: str = Field(description="Concise, descriptive title for the research output")
    summary: str = Field(description="Well-structured markdown summary of findings (use ## headings, bullet points where appropriate)")
    key_findings: list[str] = Field(description="3-6 one-sentence key findings extracted from the research")


class Citation(BaseModel):
    index: int
    title: str
    url: str
    excerpt: str = Field(description="Most relevant quote or paraphrase from this source")
    relevance: str = Field(description="One sentence explaining why this source is relevant")


class CitationOutput(BaseModel):
    """Output of the Citation Formatter agent."""
    citations: list[Citation]
    apa_references: list[str] = Field(description="APA-style reference strings for each citation")


# ── API request / response models ───────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500, description="Research question or topic")
    max_sources: int = Field(default=5, ge=2, le=10)


class AgentEvent(BaseModel):
    """SSE event payload emitted for each agent step."""
    type: str  # "step_start" | "step_output" | "error" | "complete"
    agent: str  # "planner" | "retriever" | "summarizer" | "citation_formatter"
    message: str | None = None
    data: dict | None = None


class ResearchResponse(BaseModel):
    """Final accumulated result (also sent as the 'complete' SSE event)."""
    query: str
    plan: ResearchPlan
    summary: ResearchSummary
    citations: CitationOutput
    total_sources: int
