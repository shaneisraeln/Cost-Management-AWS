"""Tenant-scoped repository for AWS connections."""
from __future__ import annotations

from app.db.models.aws_connection import AwsConnection
from app.repositories.base import TenantScopedRepository


class AwsConnectionRepository(TenantScopedRepository[AwsConnection]):
    model = AwsConnection

    async def get_by_account(self, account_id: str) -> AwsConnection | None:
        result = await self.db.execute(
            self._base_query().where(AwsConnection.account_id == account_id)
        )
        return result.scalar_one_or_none()
