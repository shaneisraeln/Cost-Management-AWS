"""Tenant-scoped repository for resources: idempotent upsert + queries."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models.resource import Resource
from app.engines.resource_normalization import NormalizedResource
from app.repositories.base import TenantScopedRepository


class ResourceRepository(TenantScopedRepository[Resource]):
    model = Resource

    async def upsert_many(self, normalized: list[NormalizedResource]) -> int:
        """Insert or update resources by (account, provider_resource_id).

        Idempotent: re-running discovery updates mutable fields (state, tags,
        metadata, region) rather than duplicating rows.
        """
        if not normalized:
            return 0

        by_id: dict[str, NormalizedResource] = {}
        for item in normalized:
            by_id[item.provider_resource_id] = item

        ids = list(by_id.keys())
        existing = {
            rec.provider_resource_id: rec
            for rec in (
                await self.db.execute(
                    self._base_query().where(Resource.provider_resource_id.in_(ids))
                )
            )
            .scalars()
            .all()
        }

        for pid, item in by_id.items():
            rec = existing.get(pid)
            if rec is None:
                self.db.add(
                    Resource(
                        tenant_id=self.tenant_id,
                        account_id=item.account_id,
                        provider=item.provider,
                        provider_resource_id=item.provider_resource_id,
                        arn=item.arn,
                        service=item.service,
                        resource_type=item.resource_type,
                        region=item.region,
                        state=item.state,
                        provider_created_at=item.provider_created_at,
                        tags=item.tags,
                        resource_metadata=item.resource_metadata,
                    )
                )
            else:
                rec.arn = item.arn
                rec.region = item.region
                rec.state = item.state
                rec.provider_created_at = item.provider_created_at
                rec.tags = item.tags
                rec.resource_metadata = item.resource_metadata
                rec.account_id = item.account_id

        await self.db.flush()
        return len(by_id)

    async def list_filtered(
        self, *, service: str | None = None, region: str | None = None
    ) -> list[Resource]:
        stmt = self._base_query()
        if service:
            stmt = stmt.where(Resource.service == service)
        if region:
            stmt = stmt.where(Resource.region == region)
        stmt = stmt.order_by(Resource.service, Resource.region)
        return list((await self.db.execute(stmt)).scalars().all())

    async def count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count(Resource.id)).where(Resource.tenant_id == self.tenant_id)
        return int((await self.db.execute(stmt)).scalar_one())
