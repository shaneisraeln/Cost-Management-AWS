"""Cost overview, explorer, and sync endpoints.

Date ranges use an inclusive ``from`` and exclusive ``to`` (matching Cost
Explorer). All reads and the sync are tenant-scoped server-side.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.aws_connection import AwsConnectionRepository
from app.schemas.cost import (
    CostBreakdown,
    CostSummary,
    CostSyncResult,
    DailyCostPoint,
)
from app.services.cost_query import CostQueryService
from app.services.cost_sync import sync_costs

router = APIRouter(prefix="/costs", tags=["costs"])


def _default_range() -> tuple[date, date]:
    end = date.today() + timedelta(days=1)  # include today (end is exclusive)
    start = end - timedelta(days=31)
    return start, end


def _resolve_range(from_: date | None, to: date | None) -> tuple[date, date]:
    if from_ and to:
        if from_ >= to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'from' must be before 'to'",
            )
        return from_, to
    return _default_range()


@router.get("/summary", response_model=CostSummary)
async def cost_summary(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> CostSummary:
    start, end = _resolve_range(from_, to)
    return await CostQueryService(db, ctx.tenant_id).summary(start, end)


@router.get("", response_model=list[DailyCostPoint])
async def cost_daily(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[DailyCostPoint]:
    start, end = _resolve_range(from_, to)
    return await CostQueryService(db, ctx.tenant_id).daily(start, end)


@router.get("/breakdown", response_model=CostBreakdown)
async def cost_breakdown(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> CostBreakdown:
    start, end = _resolve_range(from_, to)
    return await CostQueryService(db, ctx.tenant_id).breakdown(start, end)


@router.post("/sync", response_model=CostSyncResult)
async def trigger_sync(
    connection_id: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CostSyncResult:
    conn_repo = AwsConnectionRepository(db, ctx.tenant_id)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    end = date.today() + timedelta(days=1)  # include today
    start = end - timedelta(days=days)
    return await sync_costs(db, ctx.tenant_id, connection, start, end)
