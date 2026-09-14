"""Guardrail service: resolve policy, evaluate against a stored estimate.

Bridges the persisted CostEstimate (the deterministic source of truth) and the
pure GuardrailEngine. Resolves thresholds from the estimate's project (if any)
falling back to engine defaults. Persists the guardrail decision onto the
CostEstimate so it is reproducible and returned with the estimate.

No cost or pricing is computed here; the delta and line items already exist.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cost_estimate import CostEstimate
from app.engines.guardrail import (
    CostDriver,
    GuardrailPolicy,
    GuardrailResult,
    evaluate,
)
from app.repositories.attribution import ProjectRepository


async def resolve_policy(
    db: AsyncSession, tenant_id: str, project_id: str | None
) -> GuardrailPolicy:
    """Project-scoped policy with engine defaults as fallback (tenant-safe)."""
    if project_id:
        project = await ProjectRepository(db, tenant_id).get(project_id)
        if project is not None and (
            project.guardrail_warning_threshold is not None
            or project.guardrail_review_threshold is not None
        ):
            defaults = GuardrailPolicy()
            warning = (
                Decimal(str(project.guardrail_warning_threshold))
                if project.guardrail_warning_threshold is not None
                else defaults.warning_threshold_monthly
            )
            review = (
                Decimal(str(project.guardrail_review_threshold))
                if project.guardrail_review_threshold is not None
                else defaults.review_threshold_monthly
            )
            return GuardrailPolicy(
                warning_threshold_monthly=warning,
                review_threshold_monthly=review,
            )
    return GuardrailPolicy()


def _cost_drivers_from_estimate(record: CostEstimate) -> list[CostDriver]:
    """Build cost drivers from existing line items (priceable, non-zero delta)."""
    drivers: list[CostDriver] = []
    for li in record.line_items or []:
        if not li.get("estimated"):
            continue
        try:
            delta = Decimal(str(li.get("delta_monthly", "0")))
        except (ValueError, TypeError):
            continue
        if delta == 0:
            continue
        drivers.append(
            CostDriver(
                address=li.get("address", ""),
                detail=li.get("detail", ""),
                delta_monthly=delta,
            )
        )
    # Largest contributors first.
    drivers.sort(key=lambda d: d.delta_monthly, reverse=True)
    return drivers


def _completeness(record: CostEstimate) -> tuple[bool, int, int]:
    unsupported_count = len(record.unsupported or [])
    not_estimated_count = sum(
        1 for li in (record.line_items or []) if not li.get("estimated")
    )
    complete = unsupported_count == 0 and not_estimated_count == 0
    return complete, unsupported_count, not_estimated_count


def evaluate_estimate(record: CostEstimate, policy: GuardrailPolicy) -> GuardrailResult:
    """Pure-ish wrapper: derive engine inputs from the stored estimate."""
    complete, unsupported_count, not_estimated_count = _completeness(record)
    return evaluate(
        monthly_delta=Decimal(str(record.estimated_monthly_delta)),
        policy=policy,
        currency=record.currency,
        estimate_complete=complete,
        unsupported_count=unsupported_count,
        not_estimated_count=not_estimated_count,
        cost_drivers=_cost_drivers_from_estimate(record),
    )


async def evaluate_and_store(
    db: AsyncSession, tenant_id: str, record: CostEstimate
) -> GuardrailResult:
    """Evaluate the guardrail for an estimate and persist the decision."""
    policy = await resolve_policy(db, tenant_id, record.project_id)
    result = evaluate_estimate(record, policy)

    record.guardrail_status = result.status.value
    record.guardrail_warning_threshold = result.warning_threshold
    record.guardrail_review_threshold = result.review_threshold
    record.guardrail_evaluated_at = result.evaluated_at
    return result
