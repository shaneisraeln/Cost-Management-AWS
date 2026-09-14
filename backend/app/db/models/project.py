"""Project model. Resources/costs can be attributed to a project."""
from __future__ import annotations

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Project(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    # Optional per-project Cost Guardrail overrides. Null -> fall back to the
    # engine defaults ($25 / $100). Leaves room for environment-level policy
    # later without a schema rewrite.
    guardrail_warning_threshold: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    guardrail_review_threshold: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
