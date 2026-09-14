"""Detected cost change for a service over a period.

A cost change is a fact (baseline vs observed) plus a deterministic
classification. Classification confidence reflects how much correlating
evidence supports it, never a causal claim (Requirements 8.1, 8.2).
"""
from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import JSON, Date, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class ChangeClassification(str, enum.Enum):
    GROWTH = "GROWTH"
    ENGINEERING_CHANGE = "ENGINEERING_CHANGE"
    WASTE = "WASTE"
    SUSPICIOUS = "SUSPICIOUS"
    UNKNOWN = "UNKNOWN"


class CostChange(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "cost_changes"

    period_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    baseline_cost: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    observed_cost: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    absolute_change: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    percentage_change: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    classification: Mapped[ChangeClassification] = mapped_column(
        SAEnum(ChangeClassification, name="change_classification"),
        nullable=False,
        default=ChangeClassification.UNKNOWN,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)

    # Correlated evidence (event ids, resource ids, correlation types). Facts,
    # not proof of causality.
    evidence: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
