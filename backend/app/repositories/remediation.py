"""Tenant-scoped repositories for action requests and audit logs."""
from __future__ import annotations

from sqlalchemy import desc

from app.db.models.action_request import ActionRequest
from app.db.models.audit_log import AuditLog
from app.repositories.base import TenantScopedRepository


class ActionRequestRepository(TenantScopedRepository[ActionRequest]):
    model = ActionRequest

    async def list_recent(self) -> list[ActionRequest]:
        stmt = self._base_query().order_by(desc(ActionRequest.created_at))
        return list((await self.db.execute(stmt)).scalars().all())


class AuditLogRepository(TenantScopedRepository[AuditLog]):
    model = AuditLog

    async def list_recent(self) -> list[AuditLog]:
        stmt = self._base_query().order_by(desc(AuditLog.created_at))
        return list((await self.db.execute(stmt)).scalars().all())
