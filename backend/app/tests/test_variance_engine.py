"""Unit tests for the predicted-vs-actual variance engine."""
from __future__ import annotations

from decimal import Decimal

from app.engines.variance import (
    VarianceConfig,
    VarianceVerdict,
    compute_variance,
)


def test_insufficient_data_when_too_few_days() -> None:
    r = compute_variance(
        predicted_monthly=Decimal("120"),
        actual_monthly=Decimal("100"),
        actual_days_observed=1,
    )
    assert r.verdict is VarianceVerdict.INSUFFICIENT_DATA
    assert r.percentage_variance is None


def test_actual_higher_than_predicted() -> None:
    r = compute_variance(
        predicted_monthly=Decimal("100"),
        actual_monthly=Decimal("150"),
        actual_days_observed=10,
    )
    assert r.verdict is VarianceVerdict.HIGHER
    assert r.absolute_variance == Decimal("50")
    assert round(r.percentage_variance, 1) == 50.0
    assert r.is_causal_claim is False
    assert r.possible_reasons  # candidate reasons, not conclusions


def test_actual_lower_than_predicted() -> None:
    r = compute_variance(
        predicted_monthly=Decimal("100"),
        actual_monthly=Decimal("40"),
        actual_days_observed=10,
    )
    assert r.verdict is VarianceVerdict.LOWER
    assert r.absolute_variance == Decimal("-60")


def test_close_within_tolerance() -> None:
    r = compute_variance(
        predicted_monthly=Decimal("100"),
        actual_monthly=Decimal("108"),
        actual_days_observed=10,
    )
    # 8% within default 15% tolerance -> CLOSE
    assert r.verdict is VarianceVerdict.CLOSE


def test_near_zero_both_sides_is_close_not_huge_percentage() -> None:
    r = compute_variance(
        predicted_monthly=Decimal("0.0"),
        actual_monthly=Decimal("0.2"),
        actual_days_observed=10,
    )
    assert r.verdict is VarianceVerdict.CLOSE
    assert r.percentage_variance is None  # guarded against div-by-zero


def test_configurable_tolerance() -> None:
    cfg = VarianceConfig(tolerance_fraction=0.01)
    r = compute_variance(
        predicted_monthly=Decimal("100"),
        actual_monthly=Decimal("108"),
        actual_days_observed=10,
        config=cfg,
    )
    # With a strict 1% band, 8% is now HIGHER.
    assert r.verdict is VarianceVerdict.HIGHER
