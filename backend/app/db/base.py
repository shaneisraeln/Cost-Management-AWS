"""SQLAlchemy declarative base and common mixins.

Every business table inherits `TenantMixin` so multi-tenancy is uniform
(Requirement 18.1). The repository layer is responsible for always filtering
by `tenant_id` from the authenticated context.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base for all models."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TenantMixin:
    """Adds a required tenant_id to a model (Requirement 18.1)."""

    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
