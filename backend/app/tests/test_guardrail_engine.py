"""Unit tests for the Cost Guardrail engine (deterministic, pure)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.engines.guardrail import (
    GuardrailPolicy,
    GuardrailStatus,
    evaluate,
)


def _status(delta: str, **kwargs) -> GuardrailStatus:
    return evaluate(monthly_delta=Decimal(delta), **kwargs).status


# --- The 10 required cases ---


def test_zero_delta_is_pass() -> None:
    assert _status("0") is GuardrailStatus.PASS


def test_ten_dollar_delta_is_pass() -> None:
    assert _status("10") is GuardrailStatus.PASS


def test_twenty_five_is_warning() -> None:
    # Boundary: >= 25 -> WARNING
    assert _status("25") is GuardrailStatus.WARNING


def test_fifty_is_warning() -> None:
    assert _status("50") is GuardrailStatus.WARNING


def test_ninety_nine_ninety_nine_is_warning() -> None:
    assert _status("99.99") is GuardrailStatus.WARNING


def test_one_hundred_is_review_required() -> None:
    # Boundary: >= 100 -> REVIEW_REQUIRED
    assert _status("100") is GuardrailStatus.REVIEW_REQUIRED


def test_one_fifty_is_review_required() -> None:
    assert _status("150") is GuardrailStatus.REVIEW_REQUIRED


def test_negative_delta_is_pass_and_savings() -> None:
    r = evaluate(monthly_delta=Decimal("-30"))
    assert r.status is GuardrailStatus.PASS
    assert r.is_savings is True
    assert "savings" in r.message.lower()


def test_unsupported_resource_marks_incomplete_without_fabrication() -> None:
    # Delta is only what could be priced; completeness flag surfaces the gap.
    r = evaluate(
        monthly_delta=Decimal("10"),
        estimate_complete=False,
        unsupported_count=1,
        not_estimated_count=0,
    )
    assert r.status is GuardrailStatus.PASS  # decided only on the known delta
    assert r.estimate_complete is False
    assert r.incomplete_note is not None
    assert "incomplete" in r.incomplete_note.lower()


def test_configurable_thresholds() -> None:
    strict = GuardrailPolicy(
        warning_threshold_monthly=Decimal("5"),
        review_threshold_monthly=Decimal("10"),
    )
    assert _status("6", policy=strict) is GuardrailStatus.WARNING
    assert _status("12", policy=strict) is GuardrailStatus.REVIEW_REQUIRED
    # Same delta under default policy is a PASS.
    assert _status("6") is GuardrailStatus.PASS


# --- A couple of extra guards ---


def test_invalid_policy_rejected() -> None:
    with pytest.raises(ValueError):
        GuardrailPolicy(
            warning_threshold_monthly=Decimal("100"),
            review_threshold_monthly=Decimal("25"),
        )


def test_threshold_reported_matches_decision() -> None:
    warn = evaluate(monthly_delta=Decimal("50"))
    assert warn.threshold == Decimal("25")
    review = evaluate(monthly_delta=Decimal("150"))
    assert review.threshold == Decimal("100")
    savings = evaluate(monthly_delta=Decimal("-5"))
    assert savings.threshold is None
