"""Tests for idempotent upsert and tenant-scoped aggregations (SQLite)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.engines.cost_normalization import normalize_lines
from app.repositories.cost_record import CostRecordRepository
from app.schemas.cost import RawCostLine


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _line(service: str, day: str, amount: str) -> RawCostLine:
    return RawCostLine(
        period_start=date.fromisoformat(day),
        period_end=date.fromisoformat(day),
        service=service,
        region=None,
        usage_type=None,
        operation=None,
        amount=Decimal(amount),
        currency="USD",
        source_ref={"provider": "COST_EXPLORER"},
    )


def _normalized(lines, account="123"):
    return normalize_lines(lines, account_id=account, source="COST_EXPLORER")


@pytest.mark.asyncio
async def test_upsert_is_idempotent(session: AsyncSession) -> None:
    repo = CostRecordRepository(session, "t1")
    lines = [_line("EC2", "2026-09-01", "10"), _line("S3", "2026-09-01", "5")]

    await repo.upsert_many(_normalized(lines))
    await session.commit()
    first = await repo.list()

    # Re-run the same sync: no duplicates.
    await repo.upsert_many(_normalized(lines))
    await session.commit()
    second = await repo.list()

    assert len(first) == 2
    assert len(second) == 2


@pytest.mark.asyncio
async def test_upsert_updates_amount_on_rerun(session: AsyncSession) -> None:
    repo = CostRecordRepository(session, "t1")
    await repo.upsert_many(_normalized([_line("EC2", "2026-09-01", "10")]))
    await session.commit()

    # AWS revises the same line's amount; upsert updates in place.
    await repo.upsert_many(_normalized([_line("EC2", "2026-09-01", "12.50")]))
    await session.commit()

    total, count = await repo.total(date(2026, 9, 1), date(2026, 9, 2))
    assert count == 1
    assert total == Decimal("12.50")


@pytest.mark.asyncio
async def test_aggregations_and_tenant_scoping(session: AsyncSession) -> None:
    repo_a = CostRecordRepository(session, "tenant-a")
    repo_b = CostRecordRepository(session, "tenant-b")

    await repo_a.upsert_many(
        _normalized(
            [
                _line("EC2", "2026-09-01", "10"),
                _line("EC2", "2026-09-02", "20"),
                _line("S3", "2026-09-01", "5"),
            ]
        )
    )
    await repo_b.upsert_many(_normalized([_line("EC2", "2026-09-01", "999")]))
    await session.commit()

    start, end = date(2026, 9, 1), date(2026, 9, 3)

    total_a, count_a = await repo_a.total(start, end)
    assert total_a == Decimal("35")
    assert count_a == 3

    # Tenant b's data must not leak into tenant a.
    total_b, _ = await repo_b.total(start, end)
    assert total_b == Decimal("999")

    daily = await repo_a.daily_totals(start, end)
    assert daily == [(date(2026, 9, 1), Decimal("15")), (date(2026, 9, 2), Decimal("20"))]

    by_service = await repo_a.by_service(start, end)
    assert by_service[0] == ("EC2", Decimal("30"))
