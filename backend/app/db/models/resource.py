"""Canonical discovered resource.

Optional fields are nullable rather than fabricated when AWS does not provide
them. Ownership/attribution columns are placeholders populated in Phase 4.
Uniqueness is enforced per (account, provider_resource_id) (Requirements 3.2,
3.3, 3.5, 24.2).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class Resource(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "provider_resource_id",
            name="uq_resource_account_provider_id",
        ),
    )

    account_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="AWS")
    provider_resource_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    arn: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tags: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    resource_metadata: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    # Ownership / attribution (populated in Phase 4; kept here per the data model).
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attribution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attribution_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
