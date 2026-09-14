"""Stored PR cost estimate (a prediction, not actual billing).

Persisted so we can later compare predicted vs actual (Phase 7). Every
estimate records its pricing source and which resources could not be estimated
so we never present a guessed figure as fact (Requirements 14, 15).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class CostEstimate(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "cost_estimates"

    repository_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Deployment link: where/when the predicted cost should start accruing.
    # Populated when the estimate is marked deployed, enabling predicted-vs-actual.
    account_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Monthly figures. All are ESTIMATES, never actual billing.
    baseline_monthly: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    proposed_monthly: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    estimated_monthly_delta: Mapped[float] = mapped_column(
        Numeric(18, 4), nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    # Per-resource breakdown and the list of resources we could not estimate.
    line_items: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    unsupported: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)

    iac_format: Mapped[str] = mapped_column(String(32), nullable=False, default="terraform_plan")
    pricing_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="estimated")

    # Cost Guardrail evaluation (deterministic; computed from the delta above and
    # the resolved policy thresholds). Stored so the decision is reproducible.
    guardrail_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guardrail_warning_threshold: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    guardrail_review_threshold: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    guardrail_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
