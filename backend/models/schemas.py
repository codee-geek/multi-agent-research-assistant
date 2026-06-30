"""Pydantic schemas for structured LLM output and API contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Structured LLM outputs ──────────────────────────────────────────────────

class PlannerDecision(BaseModel):
    """Output of the Planner agent — either a research plan or a clarification request."""
    action: Literal["plan", "clarify"] = Field(
        description=(
            "Use 'clarify' when the query is ambiguous, underspecified, or has multiple "
            "valid interpretations. Use 'plan' only when the research scope is clear."
        )
    )
    reasoning: str = Field(description="Brief explanation of the decision")
    sub_queries: list[str] | None = Field(
        default=None,
        description="When action=plan: 5-10 specific search queries covering the topic",
        min_length=2,
        max_length=10,
    )
    clarification_question: str | None = Field(
        default=None,
        description="When action=clarify: a concise question for the user",
    )
    ambiguities: list[str] | None = Field(
        default=None,
        description="When action=clarify: possible interpretations or unknowns driving the question",
    )

    @model_validator(mode="after")
    def _validate_action_fields(self) -> PlannerDecision:
        if self.action == "plan":
            if not self.sub_queries or len(self.sub_queries) < 2:
                raise ValueError("plan action requires at least 2 sub_queries")
        elif self.action == "clarify":
            if not self.clarification_question:
                raise ValueError("clarify action requires clarification_question")
        return self


class ResearchPlan(BaseModel):
    """Output of the Planner agent."""
    sub_queries: list[str] = Field(
        description="5-10 specific search queries that together cover the research topic",
        min_length=2,
        max_length=10,
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


class SourceAssessment(BaseModel):
    """Per-source assessment from the Evidence Validator."""
    source_index: int = Field(description="1-based index into the retrieved source list")
    relevance_score: float = Field(ge=0.0, le=1.0, description="Relevance to the research question")
    credibility_note: str = Field(description="Brief note on source credibility and trustworthiness")
    is_relevant: bool = Field(description="Whether this source should be kept for synthesis")


class EvidenceValidation(BaseModel):
    """Output of the Evidence Validator agent."""
    assessments: list[SourceAssessment]
    rejected_count: int = Field(description="Number of sources filtered out")
    validation_summary: str = Field(description="Summary of the validation process and criteria applied")
    evidence_gaps: list[str] = Field(description="Topics or angles not well covered by the validated sources")


class SelfReview(BaseModel):
    """Output of the Self-Review agent."""
    quality_score: float = Field(ge=0.0, le=10.0, description="Overall report quality score out of 10")
    strengths: list[str] = Field(description="2-4 strengths of the research report")
    weaknesses: list[str] = Field(description="2-4 weaknesses or limitations")
    hallucination_risks: list[str] = Field(description="Claims that may lack sufficient source support")
    improvement_suggestions: list[str] = Field(description="Actionable suggestions to improve the report")
    overall_assessment: str = Field(description="2-3 sentence final assessment")
    approved: bool = Field(description="Whether the report meets a minimum quality bar")


# ── API request / response models ───────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500, description="Research question or topic")
    max_sources: int = Field(default=5, ge=2, le=10)
    clarification: str | None = Field(
        default=None,
        max_length=500,
        description="User's answer to a prior planner clarification question",
    )


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
    evidence_validation: EvidenceValidation | None = None
    summary: ResearchSummary
    citations: CitationOutput
    self_review: SelfReview | None = None
    total_sources: int
    validated_sources: int = 0
