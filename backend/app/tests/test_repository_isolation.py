"""Tests proving the tenant-scoped repository isolates tenants.

Uses an in-memory SQLite database so the test runs without external
infrastructure (Requirement 18.2, 18.3, 18.4).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.user import User, UserRole
from app.repositories.base import TenantScopedRepository


class UserRepository(TenantScopedRepository[User]):
    model = User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_scopes_to_tenant(session: AsyncSession) -> None:
    repo_a = UserRepository(session, tenant_id="tenant-a")
    repo_b = UserRepository(session, tenant_id="tenant-b")

    await repo_a.add(User(clerk_user_id="u1", name="A user", role=UserRole.MEMBER))
    await repo_b.add(User(clerk_user_id="u2", name="B user", role=UserRole.MEMBER))
    await session.commit()

    a_users = await repo_a.list()
    b_users = await repo_b.list()

    assert len(a_users) == 1
    assert len(b_users) == 1
    assert a_users[0].clerk_user_id == "u1"
    assert b_users[0].clerk_user_id == "u2"


@pytest.mark.asyncio
async def test_add_forces_tenant_ownership(session: AsyncSession) -> None:
    """A caller cannot smuggle another tenant's id into a new row."""
    repo_a = UserRepository(session, tenant_id="tenant-a")

    # Attempt to set a foreign tenant_id; the repository must override it.
    smuggled = User(clerk_user_id="u3", name="Sneaky", role=UserRole.MEMBER)
    smuggled.tenant_id = "tenant-b"
    await repo_a.add(smuggled)
    await session.commit()

    assert smuggled.tenant_id == "tenant-a"
    # And it is not visible to tenant-b.
    repo_b = UserRepository(session, tenant_id="tenant-b")
    assert await repo_b.list() == []
