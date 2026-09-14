"""Pricing provider abstraction.

The cost engine depends only on this interface, never on hard-coded numbers in
business logic (Requirement 13). A `PriceResult` always records its source and
whether a rate was actually found — a missing rate yields ``found=False`` so
the estimator can mark the item "not estimated" rather than guessing.

For this phase the concrete implementation is a small, transparent internal
price cache. The AWS Price List API can be added behind the same interface
later without touching the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PriceResult:
    found: bool
    # Monthly unit price in `currency`. Meaningless when found is False.
    monthly_unit_price: Decimal
    unit: str
    currency: str
    source: str
    retrieved_at: str
    note: str | None = None


@runtime_checkable
class PricingProvider(Protocol):
    source: str

    def get_monthly_price(
        self, *, service: str, region: str, attributes: dict
    ) -> PriceResult: ...
