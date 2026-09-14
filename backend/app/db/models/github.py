"""GitHub integration foundation: repositories and pull requests.

Lightweight for this phase: enough to link a repo to a project/environment and
identify a PR that a cost estimate belongs to. No GitHub App/webhook machinery.
"""
from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class GithubRepository(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "github_repositories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "full_name", name="uq_github_repo_fullname"),
    )

    # e.g. "owner/repo"
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # Link to a project/environment so cost is attributable later.
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)


class GithubPullRequest(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "github_pull_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "repository_id", "pr_number", name="uq_github_pr"
        ),
    )

    repository_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
