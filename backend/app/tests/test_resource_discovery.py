"""Lightweight tests for resource normalization, idempotent upsert, and tags."""
from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.engines.resource_normalization import normalize_resources
from app.providers.aws.resources import RawResource, _tags_to_dict
from app.repositories.resource import ResourceRepository


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _raw(rid: str, service: str, rtype: str, region: str, tags=None) -> RawResource:
    return RawResource(
        provider_resource_id=rid,
        service=service,
        resource_type=rtype,
        region=region,
        state="running",
        created_at=datetime(2026, 9, 1),
        tags=tags or {},
        metadata={"k": "v"},
    )


def test_tags_to_dict_handles_none_and_list() -> None:
    assert _tags_to_dict(None) == {}
    assert _tags_to_dict([{"Key": "Name", "Value": "web"}]) == {"Name": "web"}
    # Entries without a Key are ignored.
    assert _tags_to_dict([{"Value": "x"}]) == {}


def test_normalize_maps_fields() -> None:
    raw = _raw("i-1", "EC2", "instance", "us-east-1", {"Name": "web"})
    out = normalize_resources([raw], account_id="123")
    assert len(out) == 1
    n = out[0]
    assert n.provider_resource_id == "i-1"
    assert n.service == "EC2"
    assert n.tags == {"Name": "web"}
    assert n.account_id == "123"


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_updates(session: AsyncSession) -> None:
    repo = ResourceRepository(session, "t1")
    raws = [_raw("i-1", "EC2", "instance", "us-east-1")]

    await repo.upsert_many(normalize_resources(raws, account_id="123"))
    await session.commit()
    assert await repo.count() == 1

    # Same resource, changed state -> update, not duplicate.
    changed = [
        RawResource(
            provider_resource_id="i-1",
            service="EC2",
            resource_type="instance",
            region="us-east-1",
            state="stopped",
            created_at=datetime(2026, 9, 1),
            tags={},
            metadata={},
        )
    ]
    await repo.upsert_many(normalize_resources(changed, account_id="123"))
    await session.commit()

    resources = await repo.list_filtered()
    assert await repo.count() == 1
    assert resources[0].state == "stopped"


@pytest.mark.asyncio
async def test_list_filter_and_tenant_scoping(session: AsyncSession) -> None:
    repo_a = ResourceRepository(session, "a")
    repo_b = ResourceRepository(session, "b")
    await repo_a.upsert_many(
        normalize_resources(
            [
                _raw("i-1", "EC2", "instance", "us-east-1"),
                _raw("vol-1", "EBS", "volume", "us-west-2"),
            ],
            account_id="123",
        )
    )
    await repo_b.upsert_many(
        normalize_resources([_raw("i-99", "EC2", "instance", "us-east-1")], account_id="999")
    )
    await session.commit()

    ec2 = await repo_a.list_filtered(service="EC2")
    assert len(ec2) == 1 and ec2[0].provider_resource_id == "i-1"
    assert await repo_a.count() == 2
    assert await repo_b.count() == 1  # tenant isolation
