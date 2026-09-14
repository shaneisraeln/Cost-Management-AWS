"""Pydantic schemas for AWS connection onboarding and status."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.aws_connection import ConnectionAuthMode, ConnectionStatus


class AwsConnectionCreate(BaseModel):
    """Request body to create a connection.

    Production/default: ASSUME_ROLE with the customer's role ARN + account id.
    Local development: LOCAL_PROFILE with an optional host profile name.
    Credentials are never accepted or stored.
    """

    auth_mode: ConnectionAuthMode = ConnectionAuthMode.ASSUME_ROLE
    label: str | None = Field(default=None, max_length=255)
    account_id: str | None = Field(default=None, max_length=20)
    role_arn: str | None = Field(default=None, max_length=2048)
    profile_name: str | None = Field(default=None, max_length=255)
    region: str = Field(default="us-east-1", max_length=32)


class PermissionStatus(BaseModel):
    """Result of probing a single capability during validation."""

    capability: str
    label: str
    available: bool
    detail: str | None = None


class AwsConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str | None
    auth_mode: ConnectionAuthMode
    profile_name: str | None
    role_arn: str | None
    external_id: str | None
    region: str
    status: ConnectionStatus
    read_only: bool
    permission_status: dict
    last_cost_sync: datetime | None
    last_resource_sync: datetime | None
    last_event_sync: datetime | None
    last_metrics_sync: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ValidationResult(BaseModel):
    """Outcome of validating a connection's read-only permissions."""

    account_id: str | None
    status: ConnectionStatus
    permissions: list[PermissionStatus]
    error_message: str | None = None


class ConnectionSetupInfo(BaseModel):
    """Everything the wizard needs to guide the customer through IAM setup.

    Contains no secrets. The read policy and trust policy are exact JSON the
    customer attaches in their own AWS account.
    """

    # Whether the deployment can actually accept AssumeRole connections.
    assume_role_available: bool
    # The application principal the customer's role must trust. None when the
    # deployment has not yet configured a stable app principal.
    app_principal_arn: str | None
    external_id: str
    region: str
    read_policy: dict
    trust_policy: dict | None
    prerequisite_note: str | None = None
