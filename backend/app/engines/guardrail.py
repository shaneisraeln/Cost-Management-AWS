"""Cost Guardrail engine (pure, deterministic).

Consumes the ALREADY-COMPUTED monthly cost delta from the deterministic cost
estimator and a policy, and produces a PASS / WARNING / REVIEW_REQUIRED result.

This engine performs NO cost or pricing calculation of its own. It never
fabricates numbers, never calls an LLM, and never inspects AWS. It is the
authoritative, reproducible decision layer that sits after the estimator:

    monthly delta (deterministic) + policy thresholds  ->  guardrail status

Rules:
- delta < warning_threshold           -> PASS
- warning <= delta < review           -> WARNING
- delta >= review_threshold           -> REVIEW_REQUIRED
- delta <= 0 (savings or no change)   -> PASS (savings communicated separately)

Estimate completeness is passed through: if the underlying estimate skipped
resources (unknown pricing / unsupported types), the guardrail says so rather
than pretending the number is complete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

# Default thresholds. Not hardcoded across the app - resolved via GuardrailPolicy
# so they can be overridden per project/environment later.
DEFAULT_WARNING_THRESHOLD = Decimal("25.00")
DEFAULT_REVIEW_THRESHOLD = Decimal("100.00")


class GuardrailStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class GuardrailPolicy:
    """Configurable thresholds. Defaults preserve the required values."""

    warning_threshold_monthly: Decimal = DEFAULT_WARNING_THRESHOLD
    review_threshold_monthly: Decimal = DEFAULT_REVIEW_THRESHOLD

    def __post_init__(self) -> None:
        if self.review_threshold_monthly < self.warning_threshold_monthly:
            raise ValueError(
                "review_threshold_monthly must be >= warning_threshold_monthly"
            )


@dataclass(frozen=True)
class CostDriver:
    """A resource that contributed to the change (from existing line items)."""

    address: str
    detail: str
    delta_monthly: Decimal


@dataclass(frozen=True)
class GuardrailResult:
    status: GuardrailStatus
    monthly_delta: Decimal
    currency: str
    warning_threshold: Decimal
    review_threshold: Decimal
    # The threshold that the decision hinged on (the one crossed, or the
    # warning threshold for a PASS). None for savings/zero.
    threshold: Decimal | None
    message: str
    is_savings: bool
    estimate_complete: bool
    incomplete_note: str | None
    cost_drivers: list[CostDriver] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def evaluate(
    *,
    monthly_delta: Decimal,
    policy: GuardrailPolicy | None = None,
    currency: str = "USD",
    estimate_complete: bool = True,
    unsupported_count: int = 0,
    not_estimated_count: int = 0,
    cost_drivers: list[CostDriver] | None = None,
) -> GuardrailResult:
    """Deterministically evaluate the guardrail from a computed delta."""
    policy = policy or GuardrailPolicy()
    drivers = cost_drivers or []

    incomplete_note: str | None = None
    if not estimate_complete:
        bits = []
        if unsupported_count:
            bits.append(f"{unsupported_count} unsupported resource type(s)")
        if not_estimated_count:
            bits.append(f"{not_estimated_count} resource(s) with unknown pricing")
        detail = " and ".join(bits) if bits else "some resources could not be priced"
        incomplete_note = (
            f"Estimate may be incomplete: {detail}. "
            "The guardrail reflects only the deterministically estimated delta."
        )

    # Savings or no change -> always PASS.
    if monthly_delta <= 0:
        is_savings = monthly_delta < 0
        if is_savings:
            message = (
                f"Estimated savings of {abs(monthly_delta)} {currency}/month. "
                "The proposed infrastructure is estimated to reduce monthly cost."
            )
        else:
            message = "No estimated monthly cost change. Within the configured cost policy."
        return GuardrailResult(
            status=GuardrailStatus.PASS,
            monthly_delta=monthly_delta,
            currency=currency,
            warning_threshold=policy.warning_threshold_monthly,
            review_threshold=policy.review_threshold_monthly,
            threshold=None,
            message=message,
            is_savings=is_savings,
            estimate_complete=estimate_complete,
            incomplete_note=incomplete_note,
            cost_drivers=drivers,
        )

    # Positive delta -> compare against thresholds.
    if monthly_delta >= policy.review_threshold_monthly:
        status = GuardrailStatus.REVIEW_REQUIRED
        threshold = policy.review_threshold_monthly
        message = (
            f"Estimated monthly increase of {monthly_delta} {currency} exceeds the "
            f"configured review threshold of {threshold} {currency}. "
            "Manual review is required before proceeding."
        )
    elif monthly_delta >= policy.warning_threshold_monthly:
        status = GuardrailStatus.WARNING
        threshold = policy.warning_threshold_monthly
        message = (
            f"Estimated monthly increase of {monthly_delta} {currency} exceeds the "
            f"configured warning threshold of {threshold} {currency}."
        )
    else:
        status = GuardrailStatus.PASS
        threshold = policy.warning_threshold_monthly
        message = (
            f"Estimated monthly increase of {monthly_delta} {currency} is within the "
            f"configured cost policy (warning at {threshold} {currency})."
        )

    return GuardrailResult(
        status=status,
        monthly_delta=monthly_delta,
        currency=currency,
        warning_threshold=policy.warning_threshold_monthly,
        review_threshold=policy.review_threshold_monthly,
        threshold=threshold,
        message=message,
        is_savings=False,
        estimate_complete=estimate_complete,
        incomplete_note=incomplete_note,
        cost_drivers=drivers,
    )
