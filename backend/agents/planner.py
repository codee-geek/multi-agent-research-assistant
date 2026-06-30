"""
Planner Agent
─────────────
Receives the user query and either:
  - asks for clarification when the topic is ambiguous or underspecified, or
  - produces a structured research plan with targeted sub-queries.

Uses GPT-4o with structured output (Pydantic schema enforcement).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from models.schemas import PlannerDecision, ResearchPlan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research planning specialist. Your job is to decide whether a user's \
research question is clear enough to decompose into web search queries, or \
whether you need to ask the user for clarification first.

## When to ask for clarification (action = "clarify")
Ask before planning when ANY of these apply:
- The query uses jargon, acronyms, or niche terms with multiple valid meanings.
- The topic could reasonably be interpreted in several different ways.
- Key scope is missing: timeframe, geography, audience, technology stack, or \
  which variant/approach the user cares about.
- You are not confident what the user actually wants researched.
- The input is a greeting, small talk, or not a research question \
  (e.g. "hi", "hello", "how are you", "thanks").

When clarifying:
- Ask focused questions that resolves the main ambiguity.
- List the specific ambiguities or interpretations you see in `ambiguities`.
- Do NOT guess or pick an interpretation — let the user decide.
- For non-research inputs, ask what topic the user wants researched.

Example: query "hi, how are you?"
→ action: clarify
→ ambiguities: ["Not a research question — casual greeting"]
→ clarification_question: "That's a greeting, not a research topic. What would you \
like me to research? For example: the history of greetings, conversational AI, etc."

Example: query "vectorless rag"
→ action: clarify
→ ambiguities: ["TF-IDF / BM25 keyword-based retrieval without embeddings", \
"PageIndex tree-based document navigation without vector stores"]
→ clarification_question: "Which approach do you mean — keyword-based retrieval \
(TF-IDF/BM25) or PageIndex-style tree navigation? Or are you interested in both?"

## When to plan (action = "plan")
Proceed only when the research scope is unambiguous, or the user has already \
provided clarification that resolves prior doubts.

Rules for sub-queries:
- Generate 5-10 sub-queries that together provide comprehensive coverage.
- Each sub-query should be specific enough to return high-quality results.
- Avoid overlap between sub-queries.
- Use natural language search phrasing (not boolean operators).
- The sub-queries should progress logically: background → current state → implications.
"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.2, max_tokens=1024)


def _build_user_message(query: str, clarification: str | None) -> str:
    if clarification:
        return (
            f"Research question: {query}\n\n"
            f"User clarification (resolves prior ambiguity): {clarification}\n\n"
            "The user has answered your clarification question. Proceed with planning "
            "unless significant ambiguity remains."
        )
    return f"Research question: {query}"


async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: clarify ambiguous queries or decompose into a research plan."""
    query = state["query"]
    clarification = state.get("clarification")
    logger.info("[Planner] Planning research for: %r (clarification=%r)", query, clarification)

    llm = _get_llm().with_structured_output(PlannerDecision)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_message(query, clarification)),
    ]

    decision: PlannerDecision = await llm.ainvoke(messages)

    if decision.action == "clarify":
        logger.info(
            "[Planner] Clarification needed: %r (ambiguities=%s)",
            decision.clarification_question,
            decision.ambiguities,
        )
        step_entry = {
            "agent": "planner",
            "output": {
                "action": "clarify",
                "clarification_question": decision.clarification_question,
                "ambiguities": decision.ambiguities or [],
                "reasoning": decision.reasoning,
            },
        }
        return {
            "needs_clarification": True,
            "clarification_question": decision.clarification_question,
            "ambiguities": decision.ambiguities or [],
            "current_step": "awaiting_clarification",
            "step_log": state.get("step_log", []) + [step_entry],
            "messages": state.get("messages", []) + messages,
        }

    plan = ResearchPlan(
        sub_queries=decision.sub_queries or [],
        reasoning=decision.reasoning,
    )

    logger.info(
        "[Planner] Generated %d sub-queries: %s",
        len(plan.sub_queries),
        plan.sub_queries,
    )

    step_entry = {
        "agent": "planner",
        "output": {
            "action": "plan",
            "sub_queries": plan.sub_queries,
            "reasoning": plan.reasoning,
        },
    }

    return {
        "plan": plan,
        "needs_clarification": False,
        "current_step": "retriever",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", []) + messages,
    }
