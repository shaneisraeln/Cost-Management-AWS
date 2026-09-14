"""Deterministic PR cost estimation (pure).

For each resource change, resolve pricing via the PricingProvider and compute a
monthly baseline (before) and proposed (after) cost, then a delta. Rules:

- All numbers come from the deterministic PricingProvider, never guessed.
- When no rate is available, the line is marked ``estimated=False`` and
  contributes 0 to totals; it is surfaced so the user knows it was skipped.
- "create" has no baseline; "delete" has no proposed; "update" has both.

Output is explicitly an ESTIMATE and is never conflated with actual billing
(Requirements 13, 14.3, 14.6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.engines.iac.base import ParseResult, ResourceChange
from app.providers.pricing.base import PricingProvider

# Region is fixed for the MVP static cache; kept as a parameter for future use.
DEFAULT_REGION = "us-east-1"


@dataclass(frozen=True)
class LineItem:
    address: str
    iac_type: str
    service: str
    action: str
    baseline_monthly: Decimal
    proposed_monthly: Decimal
    delta_monthly: Decimal
    estimated: bool
    detail: str
    pricing_source: str | None


@dataclass(frozen=True)
class EstimateResult:
    baseline_monthly: Decimal
    proposed_monthly: Decimal
    delta_monthly: Decimal
    currency: str
    line_items: list[LineItem] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    pricing_source: str | None = None


def _price_for(
    pricing: PricingProvider, service: str, attributes: dict, region: str
):
    if not attributes:
        return None
    result = pricing.get_monthly_price(service=service, region=region, attributes=attributes)
    return result if result.found else None


def _estimate_change(
    change: ResourceChange, pricing: PricingProvider, region: str
) -> LineItem:
    baseline = Decimal("0")
    proposed = Decimal("0")
    notes: list[str] = []
    estimated = True
    pricing_source: str | None = None

    # Baseline (before) applies to update/delete.
    if change.action in ("update", "delete"):
        before_price = _price_for(pricing, change.service, change.before, region)
        if before_price is None:
            estimated = False
            notes.append("baseline not priceable")
        else:
            baseline = before_price.monthly_unit_price
            pricing_source = before_price.source
            notes.append(f"baseline: {before_price.note}")

    # Proposed (after) applies to create/update.
    if change.action in ("create", "update"):
        after_price = _price_for(pricing, change.service, change.after, region)
        if after_price is None:
            estimated = False
            notes.append("proposed not priceable")
        else:
            proposed = after_price.monthly_unit_price
            pricing_source = after_price.source
            notes.append(f"proposed: {after_price.note}")

    # If we could not price the side(s) relevant to this action, mark not-estimated
    # and contribute nothing to totals rather than guessing.
    if not estimated:
        baseline = Decimal("0")
        proposed = Decimal("0")

    return LineItem(
        address=change.address,
        iac_type=change.iac_type,
        service=change.service or "",
        action=change.action,
        baseline_monthly=baseline,
        proposed_monthly=proposed,
        delta_monthly=proposed - baseline,
        estimated=estimated,
        detail="; ".join(notes) if notes else "no priceable attributes",
        pricing_source=pricing_source,
    )


def estimate(
    parsed: ParseResult,
    pricing: PricingProvider,
    *,
    region: str = DEFAULT_REGION,
    currency: str = "USD",
) -> EstimateResult:
    line_items = [_estimate_change(c, pricing, region) for c in parsed.changes]

    baseline_total = sum((li.baseline_monthly for li in line_items), Decimal("0"))
    proposed_total = sum((li.proposed_monthly for li in line_items), Decimal("0"))
    pricing_source = next(
        (li.pricing_source for li in line_items if li.pricing_source), pricing.source
    )

    return EstimateResult(
        baseline_monthly=baseline_total,
        proposed_monthly=proposed_total,
        delta_monthly=proposed_total - baseline_total,
        currency=currency,
        line_items=line_items,
        unsupported=parsed.unsupported,
        pricing_source=pricing_source,
    )
