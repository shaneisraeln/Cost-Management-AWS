"""Resource inventory, detail, and discovery-sync endpoints (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.resource import Resource
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.aws_connection import AwsConnectionRepository
from app.repositories.resource import ResourceRepository
from app.schemas.resource import ResourceRead, ResourceSyncResult
from app.services.resource_sync import sync_resources

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceRead])
async def list_resources(
    service: str | None = Query(default=None),
    region: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[Resource]:
    repo = ResourceRepository(db, ctx.tenant_id)
    return await repo.list_filtered(service=service, region=region)


@router.get("/{resource_id}", response_model=ResourceRead)
async def get_resource(
    resource_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Resource:
    repo = ResourceRepository(db, ctx.tenant_id)
    resource = await repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return resource


@router.post("/sync", response_model=ResourceSyncResult)
async def trigger_resource_sync(
    connection_id: str = Query(...),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResourceSyncResult:
    conn_repo = AwsConnectionRepository(db, ctx.tenant_id)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    result = await sync_resources(db, ctx.tenant_id, connection)
    return ResourceSyncResult(**result)
