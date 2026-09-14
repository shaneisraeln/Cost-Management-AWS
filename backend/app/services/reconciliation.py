"""Reconciliation service: bucket period cost into Attributed/Shared/Unknown.

Joins cost-by-service (from CostRecord) with the attribution states of the
resources discovered for each service. This is intentionally coarse: Cost
Explorer service grouping cannot resolve most spend to a single resource, so
we surface Attributed/Shared/Unknown honestly rather than faking resource-level
precision (Requirement 5, PRD P5).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attribution import AttributionStatus
from app.engines.allocation import (
    ReconciliationResult,
    ServiceAttributionSummary,
    reconcile,
)
from app.repositories.attribution import AttributionRepository
from app.repositories.cost_record import CostRecordRepository
from app.repositories.resource import ResourceRepository

# Cost Explorer service names differ from our internal service codes.
# Map internal resource services -> substrings found in Cost Explorer names.
SERVICE_NAME_HINTS = {
    "EC2": ["Elastic Compute Cloud", "EC2"],
    "EBS": ["EC2", "Elastic Block Store"],
    "S3": ["Simple Storage Service", "S3"],
    "RDS": ["Relational Database", "RDS"],
}


def _internal_service_for(ce_service: str) -> str | None:
    name = (ce_service or "").lower()
    for internal, hints in SERVICE_NAME_HINTS.items():
        if any(h.lower() in name for h in hints):
            return internal
    return None


async def reconcile_period(
    db: AsyncSession, tenant_id: str, start: date, end: date
) -> ReconciliationResult:
    cost_repo = CostRecordRepository(db, tenant_id)
    resource_repo = ResourceRepository(db, tenant_id)
    attribution_repo = AttributionRepository(db, tenant_id)

    by_service = await cost_repo.by_service(start, end)
    currency = await cost_repo.currency(start, end)

    # Build a map of internal service -> attribution statuses of its resources.
    resources = await resource_repo.list_filtered()
    statuses_by_service: dict[str, list[AttributionStatus]] = {}
    for r in resources:
        attribution = await attribution_repo.get_for_resource(r.id)
        status = attribution.status if attribution else AttributionStatus.UNKNOWN
        statuses_by_service.setdefault(r.service, []).append(status)

    summaries: list[ServiceAttributionSummary] = []
    for ce_service, cost in by_service:
        internal = _internal_service_for(ce_service or "")
        statuses = statuses_by_service.get(internal, []) if internal else []
        summaries.append(
            ServiceAttributionSummary(
                service=ce_service or "Unattributed",
                cost=cost,
                statuses=statuses,
            )
        )

    return reconcile(summaries, currency=currency)
