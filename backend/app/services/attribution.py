"""Attribution service: run the engine over resources and persist results.

Combines resource tags with CloudTrail creator evidence and any manual
mapping, then writes an Attribution row per resource and mirrors the summary
fields onto the Resource. Manual mappings are preserved and never overwritten
by inferred attribution (Requirements 4.1-4.8).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attribution import Attribution, AttributionStatus
from app.engines.attribution import (
    AttributionConfig,
    AttributionInputs,
    attribute,
)
from app.repositories.attribution import AttributionRepository, EventRepository
from app.repositories.resource import ResourceRepository


async def run_attribution(
    db: AsyncSession,
    tenant_id: str,
    *,
    config: AttributionConfig | None = None,
) -> dict:
    """(Re)compute attribution for all resources in the tenant."""
    resource_repo = ResourceRepository(db, tenant_id)
    attribution_repo = AttributionRepository(db, tenant_id)
    event_repo = EventRepository(db, tenant_id)

    resources = await resource_repo.list_filtered()
    creators = await event_repo.creators_by_resource()

    counts = {s.value: 0 for s in AttributionStatus}

    for resource in resources:
        existing = await attribution_repo.get_for_resource(resource.id)

        # Preserve manual mappings; do not overwrite them with inference.
        if existing and existing.is_manual:
            counts[existing.status.value] += 1
            continue

        inputs = AttributionInputs(
            tags=resource.tags or {},
            creator_principal=creators.get(resource.provider_resource_id),
        )
        result = attribute(inputs, config)

        if existing is None:
            existing = Attribution(
                tenant_id=tenant_id,
                resource_id=resource.id,
                valid_from=datetime.now(UTC),
            )
            db.add(existing)

        existing.owner_label = result.owner_label
        existing.project_id = None  # project tag is a label until linked in a later step
        existing.environment = result.environment
        existing.status = result.status
        existing.confidence = result.confidence
        existing.source = result.source
        existing.evidence = result.evidence_as_dicts()

        # Mirror summary onto the resource for quick listing/filtering.
        resource.attribution_status = result.status.value
        resource.attribution_confidence = result.confidence
        resource.environment = result.environment

        counts[result.status.value] += 1

    await db.commit()
    return {"resources": len(resources), "by_status": counts}


async def set_manual_attribution(
    db: AsyncSession,
    tenant_id: str,
    resource_id: str,
    *,
    owner_label: str | None,
    project_id: str | None,
    environment: str | None,
) -> Attribution:
    """Create/replace a manual attribution mapping for a resource."""
    resource_repo = ResourceRepository(db, tenant_id)
    attribution_repo = AttributionRepository(db, tenant_id)

    resource = await resource_repo.get(resource_id)
    if resource is None:
        raise ValueError("resource_not_found")

    existing = await attribution_repo.get_for_resource(resource_id)
    if existing is None:
        existing = Attribution(
            tenant_id=tenant_id,
            resource_id=resource_id,
            valid_from=datetime.now(UTC),
        )
        db.add(existing)

    existing.owner_label = owner_label
    existing.project_id = project_id
    existing.environment = environment
    existing.status = AttributionStatus.ATTRIBUTED
    existing.confidence = 1.0
    existing.source = "manual_mapping"
    existing.evidence = [{"type": "manual_mapping", "weight": 1.0, "detail": "user-provided"}]
    existing.is_manual = True

    resource.attribution_status = AttributionStatus.ATTRIBUTED.value
    resource.attribution_confidence = 1.0
    resource.environment = environment

    await db.commit()
    return existing
