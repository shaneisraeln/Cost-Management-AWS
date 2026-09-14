"""Attribution record: who/what owns a resource, with evidence and confidence.

Kept separate from Resource so attribution history is preserved and evidence
is auditable. Never fabricates an owner: absence of evidence yields UNKNOWN;
conflicting owners yield DISPUTED; multiple co-owners yield SHARED
(Requirements 4.4, 4.5, 4.6, 4.8).
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class AttributionStatus(str, enum.Enum):
    ATTRIBUTED = "ATTRIBUTED"
    SHARED = "SHARED"
    UNKNOWN = "UNKNOWN"
    DISPUTED = "DISPUTED"


class Attribution(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "attributions"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_attribution_confidence_range"
        ),
    )

    resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Free-form owner label when we know an identity but not an app user
    # (e.g. an IAM principal or a tag value). Keeps evidence honest.
    owner_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[AttributionStatus] = mapped_column(
        SAEnum(AttributionStatus, name="attribution_status"),
        nullable=False,
        default=AttributionStatus.UNKNOWN,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Manual mappings override inferred attribution and are never auto-replaced.
    is_manual: Mapped[bool] = mapped_column(nullable=False, default=False)
