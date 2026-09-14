"""Deterministic normalization of raw cost lines into CostRecord values.

Pure functions only: no I/O, no DB. This is the tested boundary between the
AWS-shaped provider output and our canonical model (Requirement 25.3, 25.4).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.schemas.cost import RawCostLine


@dataclass(frozen=True)
class NormalizedCost:
    """Canonical cost values ready to persist as a CostRecord."""

    account_id: str | None
    period_start: date
    period_end: date
    service: str | None
    region: str | None
    resource_id: str | None
    resource_arn: str | None
    usage_type: str | None
    operation: str | None
    cost: Decimal
    currency: str
    source: str
    source_ref: dict
    natural_key: str


def natural_key_hash(
    *,
    account_id: str | None,
    period_start: date,
    period_end: date,
    service: str | None,
    region: str | None,
    resource_id: str | None,
    usage_type: str | None,
    operation: str | None,
    source: str,
) -> str:
    """Deterministic idempotency key for a cost line.

    Same inputs always yield the same key, so re-running a sync upserts the
    same row instead of duplicating it.
    """
    parts = [
        account_id or "",
        period_start.isoformat(),
        period_end.isoformat(),
        service or "",
        region or "",
        resource_id or "",
        usage_type or "",
        operation or "",
        source,
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest


def normalize_line(line: RawCostLine, *, account_id: str | None, source: str) -> NormalizedCost:
    """Convert one raw provider line into canonical cost values."""
    key = natural_key_hash(
        account_id=account_id,
        period_start=line.period_start,
        period_end=line.period_end,
        service=line.service,
        region=line.region,
        resource_id=None,
        usage_type=line.usage_type,
        operation=line.operation,
        source=source,
    )
    return NormalizedCost(
        account_id=account_id,
        period_start=line.period_start,
        period_end=line.period_end,
        service=line.service,
        region=line.region,
        resource_id=None,
        resource_arn=None,
        usage_type=line.usage_type,
        operation=line.operation,
        cost=line.amount,
        currency=line.currency,
        source=source,
        source_ref=dict(line.source_ref),
        natural_key=key,
    )


def normalize_lines(
    lines: list[RawCostLine], *, account_id: str | None, source: str
) -> list[NormalizedCost]:
    return [normalize_line(line, account_id=account_id, source=source) for line in lines]
