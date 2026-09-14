"""Cost reconciliation into Attributed / Shared / Unknown buckets (pure).

Honesty first: Cost Explorer grouped by SERVICE cannot map most spend to an
individual resource, so we do not pretend to. We bucket each service's cost by
the attribution state of the resources we discovered for that service:

- If a service has resources that are all ATTRIBUTED -> Attributed.
- If a service's resources are SHARED/DISPUTED (or mixed owners) -> Shared.
- If a service has no discovered resources or all UNKNOWN -> Unknown.

The invariant Total == Attributed + Shared + Unknown is always preserved; any
residual is placed in Unknown rather than dropped (Requirements 5.1-5.5, P5).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models.attribution import AttributionStatus


@dataclass(frozen=True)
class ServiceAttributionSummary:
    """For one service: total cost and the attribution states of its resources."""

    service: str
    cost: Decimal
    statuses: list[AttributionStatus]


@dataclass(frozen=True)
class ReconciliationResult:
    total: Decimal
    attributed: Decimal
    shared: Decimal
    unknown: Decimal
    currency: str

    @property
    def reconciles(self) -> bool:
        return self.attributed + self.shared + self.unknown == self.total

    @property
    def coverage(self) -> float:
        """Fraction of total that is attributed (0..1). 0 when total is 0."""
        if self.total == 0:
            return 0.0
        return float(self.attributed / self.total)


def _bucket_for(statuses: list[AttributionStatus]) -> str:
    if not statuses:
        return "unknown"
    distinct = set(statuses)
    if distinct == {AttributionStatus.ATTRIBUTED}:
        return "attributed"
    if distinct <= {AttributionStatus.UNKNOWN}:
        return "unknown"
    # Any mix, shared, or disputed -> shared bucket (co-owned / ambiguous).
    return "shared"


def reconcile(
    summaries: list[ServiceAttributionSummary], *, currency: str = "USD"
) -> ReconciliationResult:
    total = Decimal("0")
    attributed = Decimal("0")
    shared = Decimal("0")
    unknown = Decimal("0")

    for s in summaries:
        total += s.cost
        bucket = _bucket_for(s.statuses)
        if bucket == "attributed":
            attributed += s.cost
        elif bucket == "shared":
            shared += s.cost
        else:
            unknown += s.cost

    # Preserve the invariant explicitly; any floating residual falls to unknown.
    residual = total - (attributed + shared + unknown)
    if residual != 0:
        unknown += residual

    return ReconciliationResult(
        total=total,
        attributed=attributed,
        shared=shared,
        unknown=unknown,
        currency=currency,
    )
