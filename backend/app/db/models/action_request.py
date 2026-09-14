"""Executed (or attempted) write action against AWS.

Distinct from a recommendation: a recommendation is advice; an ActionRequest
is a user-approved attempt to change infrastructure. Phase 8 supports exactly
one action type: STOP_INSTANCE. Every attempt records who, what, when, and the
outcome (Requirements 16, 21).
"""
from __future__ import annotations

import enum

from sqlalchemy import JSON, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class ActionType(str, enum.Enum):
    # Intentionally the only supported write action in this phase.
    STOP_INSTANCE = "STOP_INSTANCE"


class ActionStatus(str, enum.Enum):
    PENDING = "PENDING"        # created, not yet executed
    BLOCKED = "BLOCKED"        # policy denied it
    FAILED = "FAILED"          # AWS call failed / not confirmed
    EXECUTED = "EXECUTED"      # AWS confirmed the action


class ActionRequest(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "action_requests"

    action_type: Mapped[ActionType] = mapped_column(
        SAEnum(ActionType, name="action_type"), nullable=False
    )
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider_resource_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)

    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)  # app user id
    status: Mapped[ActionStatus] = mapped_column(
        SAEnum(ActionStatus, name="action_status"),
        nullable=False,
        default=ActionStatus.PENDING,
    )
    policy_result: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
