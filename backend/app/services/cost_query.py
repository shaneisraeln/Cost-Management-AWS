"""Read-side cost aggregations built on the tenant-scoped repository."""
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cost_record import CostRecordRepository
from app.schemas.cost import (
    CostBreakdown,
    CostSummary,
    DailyCostPoint,
    ServiceBreakdownItem,
)


class CostQueryService:
    def __init__(self, db: AsyncSession, tenant_id: str) -> None:
        self.repo = CostRecordRepository(db, tenant_id)

    async def summary(self, start: date, end: date) -> CostSummary:
        total, count = await self.repo.total(start, end)
        currency = await self.repo.currency(start, end)
        return CostSummary(
            period_start=start,
            period_end=end,
            total=total,
            currency=currency,
            record_count=count,
        )

    async def daily(self, start: date, end: date) -> list[DailyCostPoint]:
        rows = await self.repo.daily_totals(start, end)
        return [DailyCostPoint(date=d, amount=amt) for d, amt in rows]

    async def breakdown(self, start: date, end: date) -> CostBreakdown:
        rows = await self.repo.by_service(start, end)
        currency = await self.repo.currency(start, end)
        return CostBreakdown(
            period_start=start,
            period_end=end,
            currency=currency,
            by_service=[
                ServiceBreakdownItem(service=service or "Unattributed", amount=amt)
                for service, amt in rows
            ],
        )
