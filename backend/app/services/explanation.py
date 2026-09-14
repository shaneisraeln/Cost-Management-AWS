"""Explanation service: assemble derived facts and ask the LLM to phrase them.

Facts come only from stored, deterministically-derived records. The service
never passes raw AWS data or lets the model compute anything.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.llm.base import Explanation, ExplanationFacts
from app.providers.llm.groq import GroqLlmProvider
from app.repositories.investigation import CostChangeRepository


async def explain_cost_change(
    db: AsyncSession, tenant_id: str, cost_change_id: str
) -> Explanation | None:
    repo = CostChangeRepository(db, tenant_id)
    change = await repo.get(cost_change_id)
    if change is None:
        return None

    facts = ExplanationFacts(
        subject=f"{change.service or 'Account'} cost change on {change.period_date.isoformat()}",
        baseline=f"{change.baseline_cost}",
        observed=f"{change.observed_cost}",
        difference=f"{change.absolute_change}",
        classification=change.classification.value,
        confidence=float(change.confidence),
        evidence=list(change.evidence or []),
    )
    return GroqLlmProvider().explain(facts)
