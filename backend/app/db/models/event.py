"""Normalized activity event (initially from CloudTrail).

Phase 4 focuses on resource-creation events that establish ownership. The
model is general enough to hold PR/deployment/anomaly events in later phases.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class Event(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (
        # Idempotency: a provider event id is unique within a tenant.
        UniqueConstraint("tenant_id", "provider_event_id", name="uq_event_provider_id"),
    )

    account_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="CLOUDTRAIL")

    actor_principal_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    actor_arn: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # The resource this event created/affected, when determinable.
    resource_provider_id: Mapped[str | None] = mapped_column(
        String(512), nullable=True, index=True
    )
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)

    normalized_data: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
