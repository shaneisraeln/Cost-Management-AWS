"""AWS identity model.

Represents an AWS principal (IAM user, assumed role, Identity Center identity,
service principal) seen in activity. Distinct from application Users.
"""
from __future__ import annotations

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB, "postgresql")


class AwsIdentity(Base, IdMixin, TenantMixin, TimestampMixin):
    __tablename__ = "aws_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", "principal_id", name="uq_aws_identity"),
    )

    account_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    principal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    principal_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    arn: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identity_metadata: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
