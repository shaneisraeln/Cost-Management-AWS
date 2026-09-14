"""Investigation endpoints: anomalies, cost changes, timeline, explanations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.anomaly import Anomaly
from app.db.models.cost_change import CostChange
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.investigation import AnomalyRepository, CostChangeRepository
from app.schemas.investigation import (
    AnomalyRead,
    CostChangeRead,
    DetectionResult,
    ExplanationRead,
    TimelineItem,
)
from app.services.detection import run_detection
from app.services.explanation import explain_cost_change
from app.services.timeline import build_timeline

router = APIRouter(tags=["investigation"])


@router.get("/anomalies", response_model=list[AnomalyRead])
async def list_anomalies(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[Anomaly]:
    return await AnomalyRepository(db, ctx.tenant_id).list_recent()


@router.get("/cost-changes", response_model=list[CostChangeRead])
async def list_cost_changes(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[CostChange]:
    return await CostChangeRepository(db, ctx.tenant_id).list_recent()


@router.get("/cost-changes/{change_id}", response_model=CostChangeRead)
async def get_cost_change(
    change_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> CostChange:
    change = await CostChangeRepository(db, ctx.tenant_id).get(change_id)
    if change is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost change not found")
    return change


@router.get("/timeline", response_model=list[TimelineItem])
async def timeline(
    days: int = Query(default=30, ge=1, le=365),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[TimelineItem]:
    items = await build_timeline(db, ctx.tenant_id, days=days)
    return [TimelineItem(**i) for i in items]


@router.post("/investigate/detect", response_model=DetectionResult)
async def detect(
    days: int = Query(default=30, ge=7, le=365),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> DetectionResult:
    result = await run_detection(db, ctx.tenant_id, days=days)
    return DetectionResult(**result)


@router.post("/cost-changes/{change_id}/explain", response_model=ExplanationRead)
async def explain(
    change_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ExplanationRead:
    explanation = await explain_cost_change(db, ctx.tenant_id, change_id)
    if explanation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost change not found")
    return ExplanationRead(text=explanation.text, generated_by=explanation.generated_by)
