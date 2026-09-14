"""Attribution and reconciliation schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.attribution import AttributionStatus


class AttributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    resource_id: str
    owner_label: str | None
    project_id: str | None
    environment: str | None
    status: AttributionStatus
    confidence: float
    source: str | None
    evidence: list
    is_manual: bool
    valid_from: datetime | None
    created_at: datetime


class ManualAttributionRequest(BaseModel):
    resource_id: str
    owner_label: str | None = None
    project_id: str | None = None
    environment: str | None = None


class AttributionRunResult(BaseModel):
    resources: int
    by_status: dict[str, int]


class CloudTrailSyncResult(BaseModel):
    account_id: str | None
    events_fetched: int
    events_added: int
    identities_seen: int


class ReconciliationRead(BaseModel):
    total: Decimal
    attributed: Decimal
    shared: Decimal
    unknown: Decimal
    currency: str
    coverage: float
    reconciles: bool


class OwnerSpendItem(BaseModel):
    owner_label: str
    resource_count: int


class OwnerSummary(BaseModel):
    owners: list[OwnerSpendItem]
    unknown_count: int
    shared_count: int
