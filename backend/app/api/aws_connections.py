"""AWS connection onboarding and validation endpoints.

Supports the production cross-account AssumeRole flow and the local-profile
development flow. Creating and validating connections is restricted to
OWNER/ADMIN roles. All queries are tenant-scoped server-side; a per-connection
External ID is derived server-side and never shared across tenants.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.external_id import derive_external_id
from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.aws_connection import (
    AwsConnection,
    ConnectionAuthMode,
    ConnectionStatus,
)
from app.db.models.user import UserRole
from app.db.session import get_db
from app.repositories.aws_connection import AwsConnectionRepository
from app.schemas.aws_connection import (
    AwsConnectionCreate,
    AwsConnectionRead,
    ConnectionSetupInfo,
    PermissionStatus,
    ValidationResult,
)
from app.services.aws_connection import (
    CAPABILITY_LABELS,
    friendly_error,
    validate_connection,
)
from app.services.connection_setup import build_setup_info

router = APIRouter(prefix="/aws/connections", tags=["aws"])


@router.get("", response_model=list[AwsConnectionRead])
async def list_connections(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[AwsConnection]:
    repo = AwsConnectionRepository(db, ctx.tenant_id)
    return await repo.list()


@router.get("/setup-info", response_model=ConnectionSetupInfo)
async def setup_info(
    region: str = Query(default="us-east-1"),
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ConnectionSetupInfo:
    """Return the IAM policy, trust policy, and External ID for the wizard.

    A tenant-scoped External ID is derived up front (bound to the tenant) so
    the user can create the role before the connection row exists. The same
    value is re-derived and stored when the connection is created.
    """
    external_id = derive_external_id(ctx.tenant_id, "pending")
    return ConnectionSetupInfo(**build_setup_info(external_id, region))


@router.post("", response_model=AwsConnectionRead, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: AwsConnectionCreate,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AwsConnection:
    if payload.auth_mode is ConnectionAuthMode.ASSUME_ROLE and not payload.role_arn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role_arn is required for AssumeRole connections",
        )

    repo = AwsConnectionRepository(db, ctx.tenant_id)
    connection = AwsConnection(
        auth_mode=payload.auth_mode,
        account_id=payload.account_id,
        profile_name=payload.profile_name,
        role_arn=payload.role_arn,
        region=payload.region,
        status=ConnectionStatus.PENDING,
        read_only=True,
        permission_status={},
    )
    await repo.add(connection)
    # Derive a stable External ID bound to this tenant + connection.
    connection.external_id = derive_external_id(ctx.tenant_id, connection.id)
    await db.commit()
    await db.refresh(connection)
    return connection


def _permission_rows(probes) -> list[PermissionStatus]:
    return [
        PermissionStatus(
            capability=p.capability,
            label=CAPABILITY_LABELS.get(p.capability, p.capability),
            available=p.available,
            detail=p.detail,
        )
        for p in probes
    ]


@router.post("/{connection_id}/validate", response_model=ValidationResult)
async def validate(
    connection_id: str,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ValidationResult:
    repo = AwsConnectionRepository(db, ctx.tenant_id)
    connection = await repo.get(connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    account_id, probes, new_status, assume_error = await validate_connection(connection)
    message = friendly_error(assume_error, probes)

    connection.account_id = account_id or connection.account_id
    connection.status = new_status
    connection.permission_status = {p.capability: p.available for p in probes}
    connection.last_error = message
    await db.commit()

    return ValidationResult(
        account_id=connection.account_id,
        status=new_status,
        permissions=_permission_rows(probes),
        error_message=message,
    )
