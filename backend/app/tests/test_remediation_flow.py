"""Integration test for the remediation execute flow (fully mocked AWS).

Verifies EXECUTED (confirmed), BLOCKED (production), FAILED (AWS not confirmed),
and that an AuditLog is written on every attempt. No real AWS calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import TenantContext
from app.db.base import Base
from app.db.models.action_request import ActionStatus
from app.db.models.aws_connection import AwsConnection, ConnectionAuthMode
from app.db.models.resource import Resource
from app.db.models.user import UserRole
from app.providers.aws.actions import ActionOutcome, Ec2ActionExecutor
from app.repositories.remediation import AuditLogRepository
from app.services import remediation


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _ctx() -> TenantContext:
    return TenantContext(tenant_id="t1", user_id="u1", role=UserRole.ADMIN)


async def _seed(session, *, tags) -> Resource:
    session.add(
        AwsConnection(
            tenant_id="t1", account_id="acct1",
            auth_mode=ConnectionAuthMode.LOCAL_PROFILE, region="us-east-1",
        )
    )
    resource = Resource(
        tenant_id="t1", account_id="acct1", provider="AWS",
        provider_resource_id="i-123", service="EC2", resource_type="instance",
        region="us-east-1", state="running", tags=tags, resource_metadata={},
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


def _confirmed_executor() -> Ec2ActionExecutor:
    ex = MagicMock(spec=Ec2ActionExecutor)
    ex.stop_instance.return_value = ActionOutcome(
        confirmed=True, aws_api="ec2:StopInstances", detail="confirmed stopping", raw={}
    )
    return ex


@pytest.mark.asyncio
async def test_executes_on_confirmation(session, monkeypatch) -> None:
    resource = await _seed(session, tags={"environment": "dev"})
    # Live state check returns running (mock, no real AWS).
    monkeypatch.setattr(remediation, "_live_ec2_state", _async_return("running"))

    action = await remediation.execute_stop_instance(
        session, _ctx(), resource_id=resource.id, confirmed=True,
        executor=_confirmed_executor(),
    )
    assert action.status is ActionStatus.EXECUTED
    audits = await AuditLogRepository(session, "t1").list_recent()
    assert len(audits) == 1 and audits[0].result == "EXECUTED"


@pytest.mark.asyncio
async def test_blocks_production_and_audits(session, monkeypatch) -> None:
    resource = await _seed(session, tags={"environment": "production"})
    monkeypatch.setattr(remediation, "_live_ec2_state", _async_return("running"))

    action = await remediation.execute_stop_instance(
        session, _ctx(), resource_id=resource.id, confirmed=True,
        executor=_confirmed_executor(),
    )
    assert action.status is ActionStatus.BLOCKED
    audits = await AuditLogRepository(session, "t1").list_recent()
    assert audits[0].result == "BLOCKED"


@pytest.mark.asyncio
async def test_blocks_without_confirmation(session, monkeypatch) -> None:
    resource = await _seed(session, tags={"environment": "dev"})
    monkeypatch.setattr(remediation, "_live_ec2_state", _async_return("running"))

    action = await remediation.execute_stop_instance(
        session, _ctx(), resource_id=resource.id, confirmed=False,
        executor=_confirmed_executor(),
    )
    assert action.status is ActionStatus.BLOCKED


@pytest.mark.asyncio
async def test_failed_when_aws_not_confirmed(session, monkeypatch) -> None:
    resource = await _seed(session, tags={"environment": "dev"})
    monkeypatch.setattr(remediation, "_live_ec2_state", _async_return("running"))

    ex = MagicMock(spec=Ec2ActionExecutor)
    ex.stop_instance.return_value = ActionOutcome(
        confirmed=False, aws_api="ec2:StopInstances", detail="not confirmed", raw={}
    )
    action = await remediation.execute_stop_instance(
        session, _ctx(), resource_id=resource.id, confirmed=True, executor=ex,
    )
    assert action.status is ActionStatus.FAILED
    audits = await AuditLogRepository(session, "t1").list_recent()
    assert audits[0].result == "FAILED"


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn
