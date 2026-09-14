"""Sample authenticated route confirming tenant context resolution."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import TenantContext, get_tenant_context

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(ctx: TenantContext = Depends(get_tenant_context)) -> dict:
    """Return the resolved tenant/user context for the caller."""
    return {
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
        "role": ctx.role.value,
    }
