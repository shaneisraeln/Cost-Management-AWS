"""Canonical normalized cost record.

Not every AWS cost line maps to a resource, so ``resource_id`` is nullable.
Idempotency is enforced by a deterministic ``natural_key`` hash unique per
tenant, so re-running a sync updates rather than duplicates (Requirements
2.3, 2.4, 2.5, 2.7, 24.2).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    Date,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class CostRecord(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "cost_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "natural_key", name="uq_cost_record_tenant_naturalkey"),
        # NOTE: individual cost lines may legitimately be negative (AWS credits,
        # refunds, rounding adjustments). Non-negativity is enforced on
        # aggregated totals, not raw line items.
    )

    account_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    resource_arn: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    usage_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation: Mapped[str | None] = mapped_column(String(255), nullable=True)

    cost: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    # Provenance for traceability back to the exact AWS query.
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_ref: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    # Deterministic idempotency key (see cost_normalization.natural_key_hash).
    natural_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
