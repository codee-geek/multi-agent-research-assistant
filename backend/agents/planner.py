"""
Planner Agent
─────────────
Receives the user query and produces a structured research plan:
  - 3-5 targeted sub-queries that together cover the topic
  - Brief reasoning for the decomposition strategy

Uses GPT-4o with structured output (Pydantic schema enforcement).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from models.schemas import ResearchPlan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research planning specialist. Your job is to decompose a user's research \
question into a set of precise, targeted web search queries.

Rules:
- Generate 3-5 sub-queries that together provide comprehensive coverage.
- Each sub-query should be specific enough to return high-quality results.
- Avoid overlap between sub-queries.
- Use natural language search phrasing (not boolean operators).
- The sub-queries should progress logically: background → current state → implications.
"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", temperature=0.2, max_tokens=1024)


async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: decompose the query into a research plan."""
    query = state["query"]
    logger.info("[Planner] Planning research for: %r", query)

    llm = _get_llm().with_structured_output(ResearchPlan)

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Research question: {query}"),
    ]

    plan: ResearchPlan = await llm.ainvoke(messages)

    logger.info(
        "[Planner] Generated %d sub-queries: %s",
        len(plan.sub_queries),
        plan.sub_queries,
    )

    step_entry = {
        "agent": "planner",
        "output": {
            "sub_queries": plan.sub_queries,
            "reasoning": plan.reasoning,
        },
    }

    return {
        "plan": plan,
        "current_step": "retriever",
        "step_log": state.get("step_log", []) + [step_entry],
        "messages": state.get("messages", []) + messages,
    }
