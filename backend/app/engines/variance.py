"""Predicted-vs-actual variance engine (pure).

Compares a predicted monthly cost delta (from a stored estimate) with an
actual monthly cost measured from Cost Explorer data. Deliberately careful:

- If there isn't enough actual data yet, return INSUFFICIENT_DATA rather than
  forcing a misleading comparison (Requirement 15, "don't force a comparison").
- Percentage variance guards against a near-zero predicted baseline.
- The result is a MEASUREMENT/CORRELATION. It never asserts the PR caused the
  difference; possible_reasons are framed as candidates, not conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class VarianceVerdict(str, Enum):
    HIGHER = "HIGHER"                    # actual meaningfully above predicted
    LOWER = "LOWER"                      # actual meaningfully below predicted
    CLOSE = "CLOSE"                      # within tolerance
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class VarianceConfig:
    # Minimum days of post-deployment actual data required to compare.
    min_actual_days: int = 3
    # Within this fraction of predicted (or of the abs floor) -> CLOSE.
    tolerance_fraction: float = 0.15
    # Absolute floor: if both predicted and actual are under this, treat as
    # near-zero and report CLOSE rather than a huge percentage swing.
    near_zero_floor: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class VarianceResult:
    predicted_monthly: Decimal
    actual_monthly: Decimal
    absolute_variance: Decimal          # actual - predicted
    percentage_variance: float | None   # None when predicted ~ 0
    verdict: VarianceVerdict
    actual_days_observed: int
    possible_reasons: list[str] = field(default_factory=list)
    # Always a measurement; never a causal claim.
    is_causal_claim: bool = False


def compute_variance(
    *,
    predicted_monthly: Decimal,
    actual_monthly: Decimal,
    actual_days_observed: int,
    config: VarianceConfig | None = None,
) -> VarianceResult:
    config = config or VarianceConfig()

    # Not enough real billing data yet -> refuse to force a comparison.
    if actual_days_observed < config.min_actual_days:
        return VarianceResult(
            predicted_monthly=predicted_monthly,
            actual_monthly=actual_monthly,
            absolute_variance=Decimal("0"),
            percentage_variance=None,
            verdict=VarianceVerdict.INSUFFICIENT_DATA,
            actual_days_observed=actual_days_observed,
            possible_reasons=[
                f"Only {actual_days_observed} day(s) of actual data since "
                f"deployment; need at least {config.min_actual_days}."
            ],
        )

    absolute = actual_monthly - predicted_monthly

    # Percentage variance relative to predicted, guarding near-zero.
    pct: float | None
    if abs(predicted_monthly) < config.near_zero_floor:
        pct = None
    else:
        pct = float(absolute / predicted_monthly) * 100.0

    # Verdict: near-zero on both sides -> CLOSE; else compare to tolerance band.
    if (
        abs(predicted_monthly) < config.near_zero_floor
        and abs(actual_monthly) < config.near_zero_floor
    ):
        verdict = VarianceVerdict.CLOSE
    else:
        band = (
            abs(predicted_monthly) * Decimal(str(config.tolerance_fraction))
            if abs(predicted_monthly) >= config.near_zero_floor
            else config.near_zero_floor
        )
        if abs(absolute) <= band:
            verdict = VarianceVerdict.CLOSE
        elif absolute > 0:
            verdict = VarianceVerdict.HIGHER
        else:
            verdict = VarianceVerdict.LOWER

    reasons: list[str] = []
    if verdict == VarianceVerdict.HIGHER:
        reasons = [
            "Actual usage may exceed the estimate's assumptions.",
            "Additional resources or higher runtime than modeled.",
            "Other unrelated spend changed in the same account/period.",
        ]
    elif verdict == VarianceVerdict.LOWER:
        reasons = [
            "Resources may run less than the modeled 730 hours/month.",
            "Some predicted resources may not have been deployed.",
        ]

    return VarianceResult(
        predicted_monthly=predicted_monthly,
        actual_monthly=actual_monthly,
        absolute_variance=absolute,
        percentage_variance=pct,
        verdict=verdict,
        actual_days_observed=actual_days_observed,
        possible_reasons=reasons,
    )
