"""Clerk authentication, tenant resolution, and role-based authorization.

Application identity (Clerk) is kept strictly separate from AWS identity.
Every authenticated request resolves a TenantContext that the repository
layer uses to scope all queries (Requirements 18, 19).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.session import get_db

settings = get_settings()
_bearer = HTTPBearer(auto_error=True)

# Simple in-process JWKS cache. Replace with a TTL cache in production.
_jwks_cache: dict[str, object] = {}


@dataclass
class TenantContext:
    """Resolved per-request identity and tenant scope."""

    tenant_id: str
    user_id: str
    role: UserRole


async def _get_jwks() -> dict:
    if "keys" not in _jwks_cache and settings.clerk_jwks_url:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.clerk_jwks_url)
            resp.raise_for_status()
            _jwks_cache["keys"] = resp.json()
    return _jwks_cache.get("keys", {"keys": []})  # type: ignore[return-value]


async def _verify_token(token: str) -> dict:
    """Verify a Clerk-issued JWT and return its claims."""
    try:
        jwks = await _get_jwks()
        header = jwt.get_unverified_header(token)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
        if key is None:
            raise ValueError("signing key not found")
        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            issuer=settings.clerk_issuer or None,
            options={"verify_aud": False},
        )
        return claims
    except Exception as exc:  # noqa: BLE001 - normalize to 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


async def _provision(claims: dict, db: AsyncSession) -> TenantContext:
    """Lazily resolve/create the Tenant and User from Clerk claims."""
    # Clerk may expose org context under different keys depending on the token
    # template / SDK version: top-level `org_id`/`org_role`/`org_slug`, or
    # nested under an `o` object ({"id","rol","slg"}), or under `organizations`.
    org_id = claims.get("org_id")
    org_role = claims.get("org_role")
    org_slug = claims.get("org_slug")
    if not org_id and isinstance(claims.get("o"), dict):
        o = claims["o"]
        org_id = o.get("id")
        org_role = org_role or o.get("rol")
        org_slug = org_slug or o.get("slg")

    user_id = claims.get("sub")
    if not org_id or not user_id:
        import logging

        logging.getLogger(__name__).warning(
            "auth: missing org in token", extra={"claim_keys": sorted(claims.keys())}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active organization is required",
        )

    tenant = (
        await db.execute(select(Tenant).where(Tenant.clerk_org_id == org_id))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(clerk_org_id=org_id, name=org_slug or org_id)
        db.add(tenant)
        await db.flush()

    user = (
        await db.execute(select(User).where(User.clerk_user_id == user_id))
    ).scalar_one_or_none()
    role = _map_role(org_role)
    if user is None:
        user = User(
            tenant_id=tenant.id,
            clerk_user_id=user_id,
            name=claims.get("name", ""),
            email=claims.get("email", ""),
            role=role,
        )
        db.add(user)
        await db.flush()
    elif user.role != role:
        user.role = role
    await db.commit()

    return TenantContext(tenant_id=tenant.id, user_id=user.id, role=user.role)


def _map_role(clerk_role: str | None) -> UserRole:
    mapping = {
        "org:admin": UserRole.ADMIN,
        "admin": UserRole.ADMIN,
        "org:owner": UserRole.OWNER,
        "owner": UserRole.OWNER,
        "org:member": UserRole.MEMBER,
        "member": UserRole.MEMBER,
    }
    return mapping.get((clerk_role or "").lower(), UserRole.MEMBER)


async def get_tenant_context(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """FastAPI dependency: verify JWT and resolve the tenant context."""
    claims = await _verify_token(credentials.credentials)
    return await _provision(claims, db)


def require_role(*allowed: UserRole):
    """Dependency factory enforcing that the caller has one of the roles."""

    async def _guard(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return ctx

    return _guard
