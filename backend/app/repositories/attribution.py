"""Tenant-scoped repositories for attribution, projects, identities, events."""
from __future__ import annotations

from app.db.models.attribution import Attribution
from app.db.models.aws_identity import AwsIdentity
from app.db.models.event import Event
from app.db.models.project import Project
from app.repositories.base import TenantScopedRepository


class AttributionRepository(TenantScopedRepository[Attribution]):
    model = Attribution

    async def get_for_resource(self, resource_id: str) -> Attribution | None:
        result = await self.db.execute(
            self._base_query().where(Attribution.resource_id == resource_id)
        )
        return result.scalar_one_or_none()


class ProjectRepository(TenantScopedRepository[Project]):
    model = Project


class AwsIdentityRepository(TenantScopedRepository[AwsIdentity]):
    model = AwsIdentity

    async def upsert(self, account_id: str | None, principal_id: str, **fields) -> AwsIdentity:
        existing = (
            await self.db.execute(
                self._base_query().where(
                    AwsIdentity.account_id == account_id,
                    AwsIdentity.principal_id == principal_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            return existing
        identity = AwsIdentity(
            tenant_id=self.tenant_id,
            account_id=account_id,
            principal_id=principal_id,
            **fields,
        )
        self.db.add(identity)
        await self.db.flush()
        return identity


class EventRepository(TenantScopedRepository[Event]):
    model = Event

    async def upsert_many(self, events: list[Event]) -> int:
        """Idempotent by (tenant, provider_event_id)."""
        if not events:
            return 0
        by_id = {e.provider_event_id: e for e in events if e.provider_event_id}
        ids = list(by_id.keys())
        existing = {
            e.provider_event_id
            for e in (
                await self.db.execute(
                    self._base_query().where(Event.provider_event_id.in_(ids))
                )
            )
            .scalars()
            .all()
        }
        added = 0
        for pid, ev in by_id.items():
            if pid not in existing:
                ev.tenant_id = self.tenant_id
                self.db.add(ev)
                added += 1
        await self.db.flush()
        return added

    async def creators_by_resource(self) -> dict[str, str]:
        """Map resource_provider_id -> earliest known creator principal."""
        rows = (
            await self.db.execute(
                self._base_query()
                .where(Event.event_type == "RESOURCE_CREATED")
                .order_by(Event.timestamp)
            )
        ).scalars().all()
        creators: dict[str, str] = {}
        for ev in rows:
            if ev.resource_provider_id and ev.actor_principal_id:
                creators.setdefault(ev.resource_provider_id, ev.actor_principal_id)
        return creators
