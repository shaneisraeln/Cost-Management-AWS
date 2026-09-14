"""Tenant-scoped repository base.

All data access for tenant-owned models goes through this base, which
guarantees every query is filtered by the tenant_id taken from the
authenticated context - never from a request body (Requirement 18.2, 18.3).
"""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base, TenantMixin

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    """Base repository that scopes every operation to a single tenant."""

    model: type[ModelT]

    def __init__(self, db: AsyncSession, tenant_id: str) -> None:
        if not issubclass(self.model, TenantMixin):
            raise TypeError(
                f"{self.model.__name__} is not tenant-scoped; "
                "use a plain repository for global models."
            )
        self.db = db
        self.tenant_id = tenant_id

    def _base_query(self):
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def list(self) -> list[ModelT]:
        result = await self.db.execute(self._base_query())
        return list(result.scalars().all())

    async def get(self, id_: str) -> ModelT | None:
        result = await self.db.execute(
            self._base_query().where(self.model.id == id_)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def add(self, entity: ModelT) -> ModelT:
        # Force tenant ownership regardless of any tenant_id already set.
        entity.tenant_id = self.tenant_id  # type: ignore[attr-defined]
        self.db.add(entity)
        await self.db.flush()
        return entity
