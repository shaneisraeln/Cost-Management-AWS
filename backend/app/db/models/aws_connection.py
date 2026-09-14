"""AWS account connection and its synchronization state.

A connection is read-only by default. Credentials are never stored here;
in local mode we rely on the host profile, and in the future AssumeRole
mode only a role ARN (not secrets) is persisted (Requirements 1, 20.1).
"""
from __future__ import annotations

import enum

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

# JSONB on PostgreSQL (production), plain JSON on SQLite (unit tests).
JsonType = JSON().with_variant(JSONB, "postgresql")


class ConnectionStatus(str, enum.Enum):
    PENDING = "PENDING"          # created, not yet validated
    CONNECTED = "CONNECTED"      # permissions validated, ready to sync
    DEGRADED = "DEGRADED"        # some capabilities unavailable
    ERROR = "ERROR"              # validation/sync failing


class ConnectionAuthMode(str, enum.Enum):
    LOCAL_PROFILE = "LOCAL_PROFILE"
    ASSUME_ROLE = "ASSUME_ROLE"


class AwsConnection(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "aws_connections"
    __table_args__ = (
        # One connection per (tenant, account) as recommended by the TRD.
        UniqueConstraint("tenant_id", "account_id", name="uq_aws_connection_tenant_account"),
    )

    # Populated after successful validation (STS get-caller-identity).
    account_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    auth_mode: Mapped[ConnectionAuthMode] = mapped_column(
        SAEnum(ConnectionAuthMode, name="connection_auth_mode"),
        nullable=False,
        default=ConnectionAuthMode.LOCAL_PROFILE,
    )
    # LOCAL_PROFILE: which host profile to use (nullable = default chain).
    profile_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ASSUME_ROLE: the customer role ARN (no secrets ever stored).
    role_arn: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Per-connection External ID for the cross-account trust policy. This is
    # connection metadata (used in the customer's trust relationship), NOT an
    # AWS credential. Deterministically derived; safe to display to the tenant.
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    region: Mapped[str] = mapped_column(String(32), nullable=False, default="us-east-1")

    status: Mapped[ConnectionStatus] = mapped_column(
        SAEnum(ConnectionStatus, name="connection_status"),
        nullable=False,
        default=ConnectionStatus.PENDING,
    )
    # Read-only mode is the default and only mode in the MVP.
    read_only: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Per-capability validation results, e.g. {"sts": true, "cost_explorer": true}.
    permission_status: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    # Sync state (populated by background jobs in later phases).
    last_cost_sync: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_resource_sync: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_sync: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_metrics_sync: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
