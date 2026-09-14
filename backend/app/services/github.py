"""Lightweight GitHub foundation: register repos, link project/env, record PRs."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.github import GithubPullRequest, GithubRepository
from app.repositories.github import GithubRepositoryRepo


async def register_repository(
    db: AsyncSession,
    tenant_id: str,
    *,
    full_name: str,
    project_id: str | None = None,
    environment: str | None = None,
) -> GithubRepository:
    repo_store = GithubRepositoryRepo(db, tenant_id)
    existing = await repo_store.get_by_full_name(full_name)
    if existing:
        existing.project_id = project_id
        existing.environment = environment
        await db.commit()
        return existing
    repo = GithubRepository(
        tenant_id=tenant_id,
        full_name=full_name,
        project_id=project_id,
        environment=environment,
    )
    await repo_store.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


async def record_pull_request(
    db: AsyncSession,
    tenant_id: str,
    *,
    repository_id: str,
    pr_number: int,
    title: str | None = None,
    base_commit: str | None = None,
    head_commit: str | None = None,
) -> GithubPullRequest:
    pr = GithubPullRequest(
        tenant_id=tenant_id,
        repository_id=repository_id,
        pr_number=pr_number,
        title=title,
        base_commit=base_commit,
        head_commit=head_commit,
    )
    db.add(pr)
    await db.commit()
    await db.refresh(pr)
    return pr
