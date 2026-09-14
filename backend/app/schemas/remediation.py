"""Remediation and audit schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.action_request import ActionStatus, ActionType


class PreviewRead(BaseModel):
    resource_id: str
    provider_resource_id: str | None
    service: str | None
    current_state: str | None
    proposed_action: str
    allowed: bool
    reasons: list[str]
    checks: list[dict]


class StopInstanceRequest(BaseModel):
    resource_id: str
    # Must be true; the explicit confirmation immediately before the AWS call.
    confirm: bool = False


class ActionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_type: ActionType
    resource_id: str | None
    provider_resource_id: str | None
    region: str | None
    requested_by: str
    status: ActionStatus
    policy_result: dict
    result: dict
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None
    action: str
    resource_id: str | None
    aws_api: str | None
    request_summary: str | None
    result: str
    detail: dict
    created_at: datetime
