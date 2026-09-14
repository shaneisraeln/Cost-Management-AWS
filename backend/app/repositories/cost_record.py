"""Tenant-scoped repository for cost records: idempotent upsert + aggregations."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models.cost_record import CostRecord
from app.engines.cost_normalization import NormalizedCost
from app.repositories.base import TenantScopedRepository


class CostRecordRepository(TenantScopedRepository[CostRecord]):
    model = CostRecord

    async def upsert_many(self, normalized: list[NormalizedCost]) -> int:
        """Insert or update records by (tenant, natural_key). Idempotent.

        Returns the number of rows processed. Uses a lookup-then-write per
        natural key so it is portable across PostgreSQL and SQLite (tests).
        Duplicate keys within a single batch are merged (last value wins) so a
        batch is internally idempotent too.
        """
        if not normalized:
            return 0

        # Collapse in-batch duplicates by natural_key.
        by_key: dict[str, NormalizedCost] = {}
        for item in normalized:
            by_key[item.natural_key] = item

        keys = list(by_key.keys())
        existing = {
            rec.natural_key: rec
            for rec in (
                await self.db.execute(
                    self._base_query().where(CostRecord.natural_key.in_(keys))
                )
            )
            .scalars()
            .all()
        }

        for key, item in by_key.items():
            rec = existing.get(key)
            if rec is None:
                self.db.add(
                    CostRecord(
                        tenant_id=self.tenant_id,
                        account_id=item.account_id,
                        period_start=item.period_start,
                        period_end=item.period_end,
                        service=item.service,
                        region=item.region,
                        resource_id=item.resource_id,
                        resource_arn=item.resource_arn,
                        usage_type=item.usage_type,
                        operation=item.operation,
                        cost=item.cost,
                        currency=item.currency,
                        source=item.source,
                        source_ref=item.source_ref,
                        natural_key=item.natural_key,
                    )
                )
            else:
                # Update mutable fields; the natural key is stable by design.
                rec.cost = item.cost
                rec.currency = item.currency
                rec.source_ref = item.source_ref
                rec.account_id = item.account_id

        await self.db.flush()
        return len(by_key)

    # --- Aggregations (all tenant-scoped; end date is exclusive) ---

    def _range_filter(self, start: date, end: date):
        return self._base_query().where(
            CostRecord.period_start >= start,
            CostRecord.period_start < end,
        )

    async def total(self, start: date, end: date) -> tuple[Decimal, int]:
        stmt = select(
            func.coalesce(func.sum(CostRecord.cost), 0),
            func.count(CostRecord.id),
        ).where(
            CostRecord.tenant_id == self.tenant_id,
            CostRecord.period_start >= start,
            CostRecord.period_start < end,
        )
        row = (await self.db.execute(stmt)).one()
        return Decimal(str(row[0])), int(row[1])

    async def daily_totals(self, start: date, end: date) -> list[tuple[date, Decimal]]:
        stmt = (
            select(CostRecord.period_start, func.sum(CostRecord.cost))
            .where(
                CostRecord.tenant_id == self.tenant_id,
                CostRecord.period_start >= start,
                CostRecord.period_start < end,
            )
            .group_by(CostRecord.period_start)
            .order_by(CostRecord.period_start)
        )
        rows = (await self.db.execute(stmt)).all()
        return [(r[0], Decimal(str(r[1]))) for r in rows]

    async def by_service(self, start: date, end: date) -> list[tuple[str | None, Decimal]]:
        stmt = (
            select(CostRecord.service, func.sum(CostRecord.cost))
            .where(
                CostRecord.tenant_id == self.tenant_id,
                CostRecord.period_start >= start,
                CostRecord.period_start < end,
            )
            .group_by(CostRecord.service)
            .order_by(func.sum(CostRecord.cost).desc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [(r[0], Decimal(str(r[1]))) for r in rows]

    async def total_for_account(
        self, account_id: str | None, start: date, end: date
    ) -> tuple[Decimal, int, int]:
        """Sum cost and count distinct days for an account over [start, end).

        Returns (total, record_count, distinct_days). When account_id is None,
        sums across the whole tenant (single-account MVP friendly).
        """
        conditions = [
            CostRecord.tenant_id == self.tenant_id,
            CostRecord.period_start >= start,
            CostRecord.period_start < end,
        ]
        if account_id is not None:
            conditions.append(CostRecord.account_id == account_id)

        stmt = select(
            func.coalesce(func.sum(CostRecord.cost), 0),
            func.count(CostRecord.id),
            func.count(func.distinct(CostRecord.period_start)),
        ).where(*conditions)
        row = (await self.db.execute(stmt)).one()
        return Decimal(str(row[0])), int(row[1]), int(row[2])

    async def by_service_for_account(
        self, account_id: str | None, start: date, end: date
    ) -> list[tuple[str | None, Decimal]]:
        conditions = [
            CostRecord.tenant_id == self.tenant_id,
            CostRecord.period_start >= start,
            CostRecord.period_start < end,
        ]
        if account_id is not None:
            conditions.append(CostRecord.account_id == account_id)
        stmt = (
            select(CostRecord.service, func.sum(CostRecord.cost))
            .where(*conditions)
            .group_by(CostRecord.service)
            .order_by(func.sum(CostRecord.cost).desc())
        )
        rows = (await self.db.execute(stmt)).all()
        return [(r[0], Decimal(str(r[1]))) for r in rows]

    async def currency(self, start: date, end: date) -> str:
        stmt = (
            select(CostRecord.currency)
            .where(
                CostRecord.tenant_id == self.tenant_id,
                CostRecord.period_start >= start,
                CostRecord.period_start < end,
            )
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return row or "USD"
