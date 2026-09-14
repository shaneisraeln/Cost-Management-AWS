"""Unit tests for deterministic cost normalization and idempotency keys."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.engines.cost_normalization import (
    natural_key_hash,
    normalize_line,
    normalize_lines,
)
from app.schemas.cost import RawCostLine


def _line(service: str, day: str, amount: str) -> RawCostLine:
    return RawCostLine(
        period_start=date.fromisoformat(day),
        period_end=date.fromisoformat(day),
        service=service,
        region=None,
        usage_type=None,
        operation=None,
        amount=Decimal(amount),
        currency="USD",
        source_ref={"provider": "COST_EXPLORER"},
    )


def test_natural_key_is_deterministic() -> None:
    kwargs = dict(
        account_id="123",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 2),
        service="Amazon EC2",
        region=None,
        resource_id=None,
        usage_type=None,
        operation=None,
        source="COST_EXPLORER",
    )
    assert natural_key_hash(**kwargs) == natural_key_hash(**kwargs)


def test_natural_key_changes_with_inputs() -> None:
    base = dict(
        account_id="123",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 2),
        service="Amazon EC2",
        region=None,
        resource_id=None,
        usage_type=None,
        operation=None,
        source="COST_EXPLORER",
    )
    other = {**base, "service": "Amazon S3"}
    assert natural_key_hash(**base) != natural_key_hash(**other)


def test_normalize_preserves_amount_and_currency() -> None:
    line = _line("Amazon EC2", "2026-09-01", "12.34")
    n = normalize_line(line, account_id="123", source="COST_EXPLORER")
    assert n.cost == Decimal("12.34")
    assert n.currency == "USD"
    assert n.service == "Amazon EC2"
    assert n.account_id == "123"
    assert n.resource_id is None  # Cost Explorer service grouping has no resource


def test_normalize_allows_negative_credit() -> None:
    line = _line("AWS Data Transfer", "2026-09-01", "-0.000002")
    n = normalize_line(line, account_id="123", source="COST_EXPLORER")
    assert n.cost == Decimal("-0.000002")


def test_same_line_normalizes_to_same_key() -> None:
    line = _line("Amazon EC2", "2026-09-01", "1.00")
    a = normalize_line(line, account_id="123", source="COST_EXPLORER")
    b = normalize_line(line, account_id="123", source="COST_EXPLORER")
    assert a.natural_key == b.natural_key


def test_normalize_lines_count() -> None:
    lines = [_line("EC2", "2026-09-01", "1"), _line("S3", "2026-09-01", "2")]
    out = normalize_lines(lines, account_id="123", source="COST_EXPLORER")
    assert len(out) == 2
