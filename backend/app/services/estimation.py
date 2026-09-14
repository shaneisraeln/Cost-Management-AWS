"""Estimation service: parse an IaC document, estimate cost, store the result.

The stored CostEstimate is a prediction to be compared with actual cost later.
It is explicitly an estimate and records the pricing source and any resources
that could not be estimated.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cost_estimate import CostEstimate
from app.engines.cost_estimation import EstimateResult, estimate
from app.engines.iac.terraform_plan import get_parser
from app.providers.pricing.static_cache import StaticPriceCacheProvider
from app.repositories.github import CostEstimateRepository
from app.services.guardrail import evaluate_and_store


def _line_item_dicts(result: EstimateResult) -> list[dict]:
    return [
        {
            "address": li.address,
            "iac_type": li.iac_type,
            "service": li.service,
            "action": li.action,
            "baseline_monthly": str(li.baseline_monthly),
            "proposed_monthly": str(li.proposed_monthly),
            "delta_monthly": str(li.delta_monthly),
            "estimated": li.estimated,
            "detail": li.detail,
        }
        for li in result.line_items
    ]


async def estimate_from_plan(
    db: AsyncSession,
    tenant_id: str,
    *,
    plan_document: dict,
    iac_format: str = "terraform_plan",
    repository_id: str | None = None,
    pr_number: int | None = None,
    base_commit: str | None = None,
    head_commit: str | None = None,
) -> CostEstimate:
    parser = get_parser(iac_format)
    parsed = parser.parse(plan_document)
    result = estimate(parsed, StaticPriceCacheProvider())

    record = CostEstimate(
        tenant_id=tenant_id,
        repository_id=repository_id,
        pr_number=pr_number,
        base_commit=base_commit,
        head_commit=head_commit,
        baseline_monthly=result.baseline_monthly,
        proposed_monthly=result.proposed_monthly,
        estimated_monthly_delta=result.delta_monthly,
        currency=result.currency,
        line_items=_line_item_dicts(result),
        unsupported=result.unsupported,
        iac_format=iac_format,
        pricing_source=result.pricing_source,
        status="estimated",
    )
    await CostEstimateRepository(db, tenant_id).add(record)
    # Evaluate the Cost Guardrail from the deterministic delta and persist it.
    await evaluate_and_store(db, tenant_id, record)
    await db.commit()
    await db.refresh(record)
    return record


def _summarize_for_explanation(record: CostEstimate) -> dict:
    """Facts-only payload for the LLM explanation (no computation allowed)."""
    priceable = [li for li in record.line_items if li.get("estimated")]
    return {
        "baseline_monthly": str(record.baseline_monthly),
        "proposed_monthly": str(record.proposed_monthly),
        "delta_monthly": str(record.estimated_monthly_delta),
        "currency": record.currency,
        "changed_resources": [
            {
                "address": li["address"],
                "action": li["action"],
                "delta_monthly": li["delta_monthly"],
            }
            for li in priceable
        ],
        "not_estimated": [
            li["address"] for li in record.line_items if not li.get("estimated")
        ],
        "unsupported_types": record.unsupported,
    }


def has_meaningful_estimate(record: CostEstimate) -> bool:
    return Decimal(str(record.estimated_monthly_delta)) != Decimal("0") or bool(
        [li for li in record.line_items if li.get("estimated")]
    )
