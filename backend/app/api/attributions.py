"""Attribution, reconciliation, and people/owner endpoints (read-only)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.attribution import Attribution, AttributionStatus
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.attribution import AttributionRepository
from app.repositories.aws_connection import AwsConnectionRepository
from app.schemas.attribution import (
    AttributionRead,
    AttributionRunResult,
    CloudTrailSyncResult,
    ManualAttributionRequest,
    OwnerSpendItem,
    OwnerSummary,
    ReconciliationRead,
)
from app.services.attribution import run_attribution, set_manual_attribution
from app.services.cloudtrail_sync import sync_cloudtrail
from app.services.reconciliation import reconcile_period

router = APIRouter(tags=["attribution"])


@router.get("/attributions", response_model=list[AttributionRead])
async def list_attributions(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[Attribution]:
    return await AttributionRepository(db, ctx.tenant_id).list()


@router.post("/attributions/manual", response_model=AttributionRead)
async def manual_attribution(
    payload: ManualAttributionRequest,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Attribution:
    try:
        return await set_manual_attribution(
            db,
            ctx.tenant_id,
            payload.resource_id,
            owner_label=payload.owner_label,
            project_id=payload.project_id,
            environment=payload.environment,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        ) from exc


@router.post("/attributions/run", response_model=AttributionRunResult)
async def run(
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AttributionRunResult:
    result = await run_attribution(db, ctx.tenant_id)
    return AttributionRunResult(**result)


@router.post("/attributions/sync-activity", response_model=CloudTrailSyncResult)
async def sync_activity(
    connection_id: str = Query(...),
    days: int = Query(default=90, ge=1, le=365),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CloudTrailSyncResult:
    connection = await AwsConnectionRepository(db, ctx.tenant_id).get(connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    result = await sync_cloudtrail(db, ctx.tenant_id, connection, days=days)
    return CloudTrailSyncResult(**result)


@router.get("/costs/reconciliation", response_model=ReconciliationRead)
async def reconciliation(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ReconciliationRead:
    if not (from_ and to):
        to = date.today() + timedelta(days=1)
        from_ = to - timedelta(days=31)
    result = await reconcile_period(db, ctx.tenant_id, from_, to)
    return ReconciliationRead(
        total=result.total,
        attributed=result.attributed,
        shared=result.shared,
        unknown=result.unknown,
        currency=result.currency,
        coverage=round(result.coverage, 4),
        reconciles=result.reconciles,
    )


@router.get("/people", response_model=OwnerSummary)
async def people(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> OwnerSummary:
    attributions = await AttributionRepository(db, ctx.tenant_id).list()
    owners: dict[str, int] = {}
    unknown = 0
    shared = 0
    for a in attributions:
        if a.status == AttributionStatus.UNKNOWN:
            unknown += 1
        elif a.status == AttributionStatus.SHARED:
            shared += 1
        elif a.owner_label:
            owners[a.owner_label] = owners.get(a.owner_label, 0) + 1
    return OwnerSummary(
        owners=[
            OwnerSpendItem(owner_label=k, resource_count=v)
            for k, v in sorted(owners.items(), key=lambda kv: kv[1], reverse=True)
        ],
        unknown_count=unknown,
        shared_count=shared,
    )
