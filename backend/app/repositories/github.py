"""Tenant-scoped repositories for GitHub entities and cost estimates."""
from __future__ import annotations

from app.db.models.cost_estimate import CostEstimate
from app.db.models.github import GithubPullRequest, GithubRepository
from app.repositories.base import TenantScopedRepository


class GithubRepositoryRepo(TenantScopedRepository[GithubRepository]):
    model = GithubRepository

    async def get_by_full_name(self, full_name: str) -> GithubRepository | None:
        result = await self.db.execute(
            self._base_query().where(GithubRepository.full_name == full_name)
        )
        return result.scalar_one_or_none()


class GithubPullRequestRepo(TenantScopedRepository[GithubPullRequest]):
    model = GithubPullRequest


class CostEstimateRepository(TenantScopedRepository[CostEstimate]):
    model = CostEstimate

    async def list_recent(self) -> list[CostEstimate]:
        from sqlalchemy import desc

        stmt = self._base_query().order_by(desc(CostEstimate.created_at))
        return list((await self.db.execute(stmt)).scalars().all())
