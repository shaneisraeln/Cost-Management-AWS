"""Focused tests for the Bedrock intelligence service (mocked AWS).

Verifies the honesty rules: missing metrics -> unavailable (not zero),
efficiency only when denominators exist, per-model breakdown, spike detection
via the reused anomaly engine, and permission-error handling. No real AWS.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.db.models.aws_connection import AwsConnection, ConnectionAuthMode
from app.providers.aws.bedrock import (
    BedrockCostResult,
    BedrockUsageResult,
    MetricSeries,
)
from app.services.bedrock import get_bedrock_intelligence


class _StubCost:
    def __init__(self, result: BedrockCostResult) -> None:
        self._r = result

    def get_cost(self, session, start, end) -> BedrockCostResult:
        return self._r


class _StubUsage:
    def __init__(self, result: BedrockUsageResult) -> None:
        self._r = result

    def get_usage(self, session, region, start, end) -> BedrockUsageResult:
        return self._r


def _conn() -> AwsConnection:
    return AwsConnection(
        tenant_id="t", account_id="acct",
        auth_mode=ConnectionAuthMode.LOCAL_PROFILE, region="us-east-1",
    )


async def _run(cost: BedrockCostResult, usage: BedrockUsageResult):
    start = date(2026, 9, 1)
    end = date(2026, 10, 1)
    return await get_bedrock_intelligence(
        _conn(), start, end,
        cost_provider=_StubCost(cost), usage_provider=_StubUsage(usage),
    )


@pytest.mark.asyncio
async def test_normal_usage_and_efficiency() -> None:
    cost = BedrockCostResult(available=True, total_cost=Decimal("100"), currency="USD",
                             daily=[("2026-09-01", Decimal("100"))])
    usage = BedrockUsageResult(
        available=True,
        series=[
            MetricSeries("Invocations", "anthropic.claude-v2", Decimal("1000"), []),
            MetricSeries("InputTokenCount", "anthropic.claude-v2", Decimal("500000"), []),
            MetricSeries("OutputTokenCount", "anthropic.claude-v2", Decimal("250000"), []),
        ],
        metrics_present=["InputTokenCount", "Invocations", "OutputTokenCount"],
    )
    intel = await _run(cost, usage)
    assert intel.usage.invocations == 1000
    assert intel.usage.input_tokens == 500000
    # cost per invocation = 100 / 1000 = 0.1
    assert intel.efficiency.cost_per_invocation == Decimal("0.100000")
    # tokens per invocation = 750000 / 1000 = 750
    assert intel.efficiency.tokens_per_invocation == Decimal("750.00")
    assert intel.by_model[0].model_id == "anthropic.claude-v2"
    assert intel.has_any_data is True


@pytest.mark.asyncio
async def test_no_usage_is_not_fake_zero() -> None:
    cost = BedrockCostResult(available=True, total_cost=Decimal("0"), currency="USD")
    usage = BedrockUsageResult(available=True, series=[], metrics_present=[],
                               reason="no Bedrock metrics published")
    intel = await _run(cost, usage)
    # No fabricated zeros: metrics are unavailable (None).
    assert intel.usage.invocations is None
    assert intel.efficiency.cost_per_invocation is None
    assert intel.has_any_data is False


@pytest.mark.asyncio
async def test_missing_token_metric_marked_unavailable() -> None:
    cost = BedrockCostResult(available=True, total_cost=Decimal("10"), currency="USD")
    usage = BedrockUsageResult(
        available=True,
        series=[MetricSeries("Invocations", None, Decimal("100"), [])],
        metrics_present=["Invocations"],
    )
    intel = await _run(cost, usage)
    assert intel.usage.invocations == 100
    assert intel.usage.input_tokens is None   # unavailable, not 0
    assert intel.usage.output_tokens is None
    # tokens/invocation can't be computed -> None
    assert intel.efficiency.tokens_per_invocation is None
    # cost/invocation still computable
    assert intel.efficiency.cost_per_invocation == Decimal("0.100000")


@pytest.mark.asyncio
async def test_usage_permission_error_is_unavailable() -> None:
    cost = BedrockCostResult(available=True, total_cost=Decimal("5"), currency="USD")
    usage = BedrockUsageResult(available=False, reason="AccessDenied")
    intel = await _run(cost, usage)
    assert intel.usage.available is False
    assert intel.usage.invocations is None
    assert any("unavailable" in n.lower() for n in intel.notes)


@pytest.mark.asyncio
async def test_cost_permission_error_does_not_fake_zero() -> None:
    cost = BedrockCostResult(available=False, total_cost=Decimal("0"), currency="USD",
                             reason="AccessDenied")
    usage = BedrockUsageResult(available=True,
                               series=[MetricSeries("Invocations", None, Decimal("50"), [])],
                               metrics_present=["Invocations"])
    intel = await _run(cost, usage)
    assert intel.cost.available is False
    # Efficiency cost ratio unavailable when cost is unavailable.
    assert intel.efficiency.cost_per_invocation is None


@pytest.mark.asyncio
async def test_invocation_spike_detected() -> None:
    # Flat ~5/day for a week, then a jump to 500 -> spike.
    base_day = date(2026, 9, 1)
    daily = [((base_day + timedelta(days=i)).isoformat(), Decimal("5")) for i in range(6)]
    daily.append(((base_day + timedelta(days=6)).isoformat(), Decimal("500")))
    cost_daily = [((base_day + timedelta(days=i)).isoformat(), Decimal("1")) for i in range(7)]
    cost = BedrockCostResult(available=True, total_cost=Decimal("7"), currency="USD",
                             daily=cost_daily)
    usage = BedrockUsageResult(
        available=True,
        series=[MetricSeries("Invocations", None, Decimal("530"), daily)],
        metrics_present=["Invocations"],
    )
    intel = await _run(cost, usage)
    assert intel.spike.detected is True
    assert intel.spike.metric == "invocations"
    assert intel.spike.associated_cost_change == Decimal("1")
    assert "investigating" in (intel.spike.message or "").lower()


@pytest.mark.asyncio
async def test_insufficient_history_no_spike() -> None:
    base_day = date(2026, 9, 1)
    daily = [((base_day + timedelta(days=i)).isoformat(), Decimal("5")) for i in range(2)]
    cost = BedrockCostResult(available=True, total_cost=Decimal("2"), currency="USD")
    usage = BedrockUsageResult(
        available=True,
        series=[MetricSeries("Invocations", None, Decimal("10"), daily)],
        metrics_present=["Invocations"],
    )
    intel = await _run(cost, usage)
    assert intel.spike.detected is False
    assert "insufficient" in (intel.spike.reason or "").lower()
