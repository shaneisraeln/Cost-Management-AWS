"""Resource inventory schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str | None
    provider: str
    provider_resource_id: str
    arn: str | None
    service: str
    resource_type: str
    region: str | None
    state: str | None
    provider_created_at: datetime | None
    tags: dict
    resource_metadata: dict
    owner_id: str | None
    project_id: str | None
    environment: str | None
    attribution_status: str | None
    created_at: datetime
    updated_at: datetime


class ResourceSyncResult(BaseModel):
    account_id: str | None
    discovered: int
    upserted: int
    by_service: dict[str, int]
