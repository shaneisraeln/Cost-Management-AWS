"""Bedrock intelligence endpoints (read-only).

Answers: how much did Bedrock cost, how much was it used, which models, and is
anything worth investigating. Cost comes from Cost Explorer, usage from
CloudWatch. Groq only explains already-computed facts.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context
from app.db.session import get_db
from app.providers.llm.base import ExplanationFacts
from app.providers.llm.groq import GroqLlmProvider
from app.repositories.aws_connection import AwsConnectionRepository
from app.schemas.bedrock import BedrockExplanationRead, BedrockIntelligence
from app.services.bedrock import get_bedrock_intelligence

router = APIRouter(prefix="/bedrock", tags=["bedrock"])


def _resolve_range(from_: date | None, to: date | None) -> tuple[date, date]:
    if from_ and to:
        if from_ >= to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'from' must be before 'to'",
            )
        return from_, to
    end = date.today() + timedelta(days=1)  # include today (end exclusive)
    start = end - timedelta(days=30)
    return start, end


async def _get_connection(db: AsyncSession, tenant_id: str):
    conns = await AwsConnectionRepository(db, tenant_id).list()
    return conns[0] if conns else None


@router.get("/intelligence", response_model=BedrockIntelligence)
async def bedrock_intelligence(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> BedrockIntelligence:
    connection = await _get_connection(db, ctx.tenant_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AWS connection. Add one in Settings first.",
        )
    start, end = _resolve_range(from_, to)
    return await get_bedrock_intelligence(connection, start, end)


@router.post("/explain", response_model=BedrockExplanationRead)
async def explain_bedrock(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> BedrockExplanationRead:
    connection = await _get_connection(db, ctx.tenant_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No AWS connection."
        )
    start, end = _resolve_range(from_, to)
    intel = await get_bedrock_intelligence(connection, start, end)

    # Facts only. The model rephrases; it never computes or invents.
    evidence: list[dict] = [
        {
            "type": "usage",
            "detail": {
                "invocations": intel.usage.invocations,
                "input_tokens": intel.usage.input_tokens,
                "output_tokens": intel.usage.output_tokens,
                "metrics_present": intel.usage.metrics_present,
            },
        },
        {
            "type": "by_model",
            "detail": [
                {"model_id": m.model_id, "invocations": m.invocations}
                for m in intel.by_model
            ],
        },
    ]
    if intel.spike.detected:
        evidence.append(
            {
                "type": "spike",
                "detail": {
                    "metric": intel.spike.metric,
                    "day": intel.spike.day,
                    "baseline": str(intel.spike.baseline),
                    "observed": str(intel.spike.observed),
                    "associated_cost_change": str(intel.spike.associated_cost_change),
                },
            }
        )

    facts = ExplanationFacts(
        subject=f"Bedrock usage and cost, {intel.period_start} to {intel.period_end}",
        observed=(
            f"{intel.cost.total_cost} {intel.cost.currency}"
            if intel.cost.available
            else "cost unavailable"
        ),
        classification="MEASUREMENT (Bedrock cost from Cost Explorer, usage from CloudWatch)",
        evidence=evidence,
    )
    explanation = GroqLlmProvider().explain(facts)
    return BedrockExplanationRead(
        text=explanation.text, generated_by=explanation.generated_by
    )
