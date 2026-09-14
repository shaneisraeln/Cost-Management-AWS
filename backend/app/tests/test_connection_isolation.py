"""Tenant isolation for AWS connections (repository-level, SQLite)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.aws_connection import AwsConnection, ConnectionAuthMode
from app.repositories.aws_connection import AwsConnectionRepository


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
async def test_connection_is_not_visible_across_tenants(session: AsyncSession) -> None:
    repo_a = AwsConnectionRepository(session, "tenant-a")
    repo_b = AwsConnectionRepository(session, "tenant-b")

    conn = AwsConnection(
        auth_mode=ConnectionAuthMode.ASSUME_ROLE,
        account_id="111111111111",
        role_arn="arn:aws:iam::111111111111:role/CloudCostControlReadOnly",
        region="us-east-1",
    )
    await repo_a.add(conn)
    await session.commit()

    # Tenant B cannot list or get tenant A's connection.
    assert await repo_b.list() == []
    assert await repo_b.get(conn.id) is None
    # Tenant A can.
    assert len(await repo_a.list()) == 1
    assert (await repo_a.get(conn.id)) is not None


@pytest.mark.asyncio
async def test_add_forces_owning_tenant(session: AsyncSession) -> None:
    repo_a = AwsConnectionRepository(session, "tenant-a")
    smuggled = AwsConnection(
        auth_mode=ConnectionAuthMode.ASSUME_ROLE,
        account_id="222222222222",
        role_arn="arn:aws:iam::222222222222:role/X",
        region="us-east-1",
    )
    smuggled.tenant_id = "tenant-b"  # attempt to smuggle a foreign tenant
    await repo_a.add(smuggled)
    await session.commit()
    # The repository forces the owning tenant.
    assert smuggled.tenant_id == "tenant-a"
