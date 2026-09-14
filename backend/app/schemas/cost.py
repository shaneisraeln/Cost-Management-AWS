"""Cost schemas: the AWS-shaped raw line and the API response models.

`RawCostLine` is intentionally close to the Cost Explorer response so the
provider layer stays a thin adapter. Normalization into `CostRecord` happens
in a separate, testable engine. This keeps the raw AWS shape decoupled from
our canonical model so CUR/Data Exports can be added later.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RawCostLine(BaseModel):
    """One grouped cost line as returned by the cost provider (AWS-shaped)."""

    model_config = ConfigDict(frozen=True)

    period_start: date
    period_end: date
    service: str | None
    region: str | None
    usage_type: str | None
    operation: str | None
    amount: Decimal
    currency: str
    # Opaque reference describing the query that produced this line, for
    # traceability back to the exact AWS call.
    source_ref: dict


class CostSummary(BaseModel):
    """Totals for a selected date range."""

    period_start: date
    period_end: date
    total: Decimal
    currency: str
    record_count: int


class DailyCostPoint(BaseModel):
    date: date
    amount: Decimal


class ServiceBreakdownItem(BaseModel):
    service: str
    amount: Decimal


class CostBreakdown(BaseModel):
    period_start: date
    period_end: date
    currency: str
    by_service: list[ServiceBreakdownItem]


class CostSyncResult(BaseModel):
    """Outcome of a cost sync run."""

    account_id: str | None
    period_start: date
    period_end: date
    lines_fetched: int
    records_upserted: int
    total: Decimal
    currency: str
