"""Remediation endpoints: preview, confirmed execute, action list, audit log.

Only OWNER/ADMIN may preview or execute. Execution requires an explicit
confirmation flag. The single supported action is stopping an EC2 instance.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.action_request import ActionRequest
from app.db.models.audit_log import AuditLog
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.remediation import (
    ActionRequestRepository,
    AuditLogRepository,
)
from app.schemas.remediation import (
    ActionRequestRead,
    AuditLogRead,
    PreviewRead,
    StopInstanceRequest,
)
from app.services.remediation import execute_stop_instance, preview_stop_instance

router = APIRouter(tags=["remediation"])


@router.get("/remediation/preview", response_model=PreviewRead)
async def preview(
    resource_id: str = Query(...),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> PreviewRead:
    result = await preview_stop_instance(db, ctx, resource_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return PreviewRead(**result.__dict__)


@router.post("/remediation/stop-instance", response_model=ActionRequestRead)
async def stop_instance(
    payload: StopInstanceRequest,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ActionRequest:
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit confirmation (confirm=true) is required",
        )
    return await execute_stop_instance(
        db, ctx, resource_id=payload.resource_id, confirmed=payload.confirm
    )


@router.get("/remediation/actions", response_model=list[ActionRequestRead])
async def list_actions(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[ActionRequest]:
    return await ActionRequestRepository(db, ctx.tenant_id).list_recent()


@router.get("/audit-logs", response_model=list[AuditLogRead])
async def audit_logs(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    return await AuditLogRepository(db, ctx.tenant_id).list_recent()
