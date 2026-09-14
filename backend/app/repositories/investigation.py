"""Tenant-scoped repositories for anomalies and cost changes."""
from __future__ import annotations

from datetime import date

from app.db.models.anomaly import Anomaly
from app.db.models.cost_change import CostChange
from app.repositories.base import TenantScopedRepository


class AnomalyRepository(TenantScopedRepository[Anomaly]):
    model = Anomaly

    async def existing_keys(self) -> set[tuple]:
        rows = (await self.db.execute(self._base_query())).scalars().all()
        return {(a.service, a.detected_for, a.algorithm) for a in rows}

    async def list_recent(self) -> list[Anomaly]:
        stmt = self._base_query().order_by(Anomaly.detected_for.desc())
        return list((await self.db.execute(stmt)).scalars().all())


class CostChangeRepository(TenantScopedRepository[CostChange]):
    model = CostChange

    async def list_recent(self) -> list[CostChange]:
        stmt = self._base_query().order_by(CostChange.period_date.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def in_range(self, start: date, end: date) -> list[CostChange]:
        stmt = (
            self._base_query()
            .where(CostChange.period_date >= start, CostChange.period_date < end)
            .order_by(CostChange.period_date)
        )
        return list((await self.db.execute(stmt)).scalars().all())
