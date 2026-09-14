"""Detected cost anomaly (deterministic/statistical, no ML).

Stores the baseline the detector used, the observed value, the algorithm, and
the evidence, so the anomaly is fully explainable (Requirements 8.3-8.6).
"""
from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import JSON, CheckConstraint, Date, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class AnomalySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalyStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


class Anomaly(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_anomaly_confidence"),
        # One anomaly per (tenant, service, day, algorithm) - idempotent detection.
        UniqueConstraint(
            "tenant_id", "service", "detected_for", "algorithm", name="uq_anomaly_dedupe"
        ),
    )

    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    detected_for: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    severity: Mapped[AnomalySeverity] = mapped_column(
        SAEnum(AnomalySeverity, name="anomaly_severity"),
        nullable=False,
        default=AnomalySeverity.LOW,
    )
    baseline: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    observed: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    difference: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    status: Mapped[AnomalyStatus] = mapped_column(
        SAEnum(AnomalyStatus, name="anomaly_status"),
        nullable=False,
        default=AnomalyStatus.OPEN,
    )
    evidence: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
