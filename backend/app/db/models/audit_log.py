"""Audit log for every sensitive/attempted action.

Written on EVERY attempt — requested, blocked, failed, or executed — so there
is an accountable record. Never stores secrets (Requirement 21).
"""
from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class AuditLog(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    aws_api: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. EXECUTED/BLOCKED
    detail: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
