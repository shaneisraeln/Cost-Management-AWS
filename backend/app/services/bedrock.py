"""Bedrock intelligence service.

Combines the separate cost (Cost Explorer) and usage (CloudWatch) facts,
computes efficiency ratios as OUR calculation (only when the denominators
exist), builds a per-model usage breakdown, and reuses the existing
deterministic anomaly engine to flag a meaningful usage/cost increase.

Honesty rules enforced here:
- Missing AWS metric -> None (unavailable), never zero.
- Efficiency only computed when invocations > 0 and the numerator exists.
- Spike statements are associative ("associated with"), never causal.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

from app.db.models.aws_connection import AwsConnection
from app.engines.anomaly import DailyPoint, DetectionConfig, detect_service_anomalies
from app.providers.aws.bedrock import (
    BedrockCostProvider,
    BedrockCostResult,
    BedrockUsageProvider,
    BedrockUsageResult,
)
from app.providers.aws.credentials import get_credential_provider
from app.schemas.bedrock import (
    BedrockCostFacts,
    BedrockIntelligence,
    BedrockSpike,
    BedrockUsageFacts,
    EfficiencyFacts,
    ModelUsage,
)


def _int_or_none(value: Decimal | None) -> int | None:
    return int(value) if value is not None else None


def _sum_metric(usage: BedrockUsageResult, metric: str) -> Decimal | None:
    """Total for a metric across all models. None if the metric is absent."""
    matching = [s for s in usage.series if s.metric == metric]
    if not matching:
        return None
    return sum((s.total for s in matching), Decimal("0"))


def _daily_metric(usage: BedrockUsageResult, metric: str) -> dict[str, Decimal]:
    daily: dict[str, Decimal] = {}
    for s in usage.series:
        if s.metric != metric:
            continue
        for day, val in s.daily:
            daily[day] = daily.get(day, Decimal("0")) + val
    return daily


def _by_model(usage: BedrockUsageResult) -> list[ModelUsage]:
    models: dict[str, dict[str, Decimal]] = {}
    for s in usage.series:
        if s.model_id is None:
            continue
        bucket = models.setdefault(s.model_id, {})
        bucket[s.metric] = bucket.get(s.metric, Decimal("0")) + s.total
    out: list[ModelUsage] = []
    for model_id, metrics in models.items():
        out.append(
            ModelUsage(
                model_id=model_id,
                invocations=_int_or_none(metrics.get("Invocations")),
                input_tokens=_int_or_none(metrics.get("InputTokenCount")),
                output_tokens=_int_or_none(metrics.get("OutputTokenCount")),
            )
        )
    # Sort by invocations desc (None last).
    out.sort(key=lambda m: (m.invocations is None, -(m.invocations or 0)))
    return out


def _efficiency(
    total_cost: Decimal | None,
    invocations: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> EfficiencyFacts:
    if not invocations:
        return EfficiencyFacts(
            cost_per_invocation=None,
            tokens_per_invocation=None,
            note=(
                "Invocation count unavailable or zero; efficiency ratios cannot "
                "be computed."
            ),
        )
    cost_per_inv = (
        (total_cost / Decimal(invocations)).quantize(Decimal("0.000001"))
        if total_cost is not None
        else None
    )
    total_tokens = (input_tokens or 0) + (output_tokens or 0)
    tokens_per_inv = (
        (Decimal(total_tokens) / Decimal(invocations)).quantize(Decimal("0.01"))
        if (input_tokens is not None or output_tokens is not None)
        else None
    )
    return EfficiencyFacts(
        cost_per_invocation=cost_per_inv,
        tokens_per_invocation=tokens_per_inv,
        note=(
            "Calculated by this tool from separate Cost Explorer cost and "
            "CloudWatch usage data. Not an AWS-provided metric."
        ),
    )


def _detect_spike(
    invocations_daily: dict[str, Decimal],
    cost_daily: list[tuple[str, Decimal]],
) -> BedrockSpike:
    """Reuse the deterministic anomaly engine on the invocation series."""
    if len(invocations_daily) < 4:
        return BedrockSpike(
            detected=False,
            reason="Insufficient usage history to assess a meaningful increase.",
        )

    points = [
        DailyPoint(day=date.fromisoformat(d), amount=v)
        for d, v in sorted(invocations_daily.items())
    ]
    # Usage units are invocations, not dollars: require a non-trivial jump.
    config = DetectionConfig(min_absolute=Decimal("10"))
    anomalies = detect_service_anomalies("Bedrock invocations", points, config)
    if not anomalies:
        return BedrockSpike(
            detected=False,
            message="Bedrock invocation volume is within its recent baseline.",
        )

    top = max(anomalies, key=lambda a: a.difference)
    cost_map = {d: v for d, v in cost_daily}
    associated = cost_map.get(top.day.isoformat())

    return BedrockSpike(
        detected=True,
        metric="invocations",
        day=top.day.isoformat(),
        baseline=top.baseline,
        observed=top.observed,
        difference=top.difference,
        associated_cost_change=associated,
        message=(
            "Bedrock invocation volume increased significantly compared with the "
            "recent baseline. Worth investigating."
        ),
    )


def _fetch(
    connection: AwsConnection,
    start: date,
    end: date,
    cost_provider: BedrockCostProvider,
    usage_provider: BedrockUsageProvider,
) -> tuple[BedrockCostResult, BedrockUsageResult]:
    cred = get_credential_provider(
        connection.auth_mode,
        profile_name=connection.profile_name,
        role_arn=connection.role_arn,
        region=connection.region,
    )
    session = cred.get_session(region=connection.region)
    cost = cost_provider.get_cost(session, start, end)
    usage = usage_provider.get_usage(session, connection.region, start, end)
    return cost, usage


async def get_bedrock_intelligence(
    connection: AwsConnection,
    start: date,
    end: date,
    *,
    cost_provider: BedrockCostProvider | None = None,
    usage_provider: BedrockUsageProvider | None = None,
) -> BedrockIntelligence:
    cost_provider = cost_provider or BedrockCostProvider()
    usage_provider = usage_provider or BedrockUsageProvider()

    cost_res, usage_res = await asyncio.to_thread(
        _fetch, connection, start, end, cost_provider, usage_provider
    )

    notes: list[str] = []

    # --- Cost facts (authoritative for cost) ---
    cost_facts = BedrockCostFacts(
        available=cost_res.available,
        total_cost=cost_res.total_cost if cost_res.available else Decimal("0"),
        currency=cost_res.currency,
        reason=cost_res.reason,
    )
    if not cost_res.available:
        notes.append(f"Bedrock cost unavailable ({cost_res.reason}).")

    # --- Usage facts (authoritative for usage) ---
    invocations = _sum_metric(usage_res, "Invocations") if usage_res.available else None
    input_tokens = _sum_metric(usage_res, "InputTokenCount") if usage_res.available else None
    output_tokens = _sum_metric(usage_res, "OutputTokenCount") if usage_res.available else None

    usage_facts = BedrockUsageFacts(
        available=usage_res.available,
        invocations=_int_or_none(invocations),
        input_tokens=_int_or_none(input_tokens),
        output_tokens=_int_or_none(output_tokens),
        metrics_present=usage_res.metrics_present,
        reason=usage_res.reason,
    )
    if not usage_res.available:
        notes.append(f"Bedrock usage unavailable ({usage_res.reason}).")
    elif not usage_res.series:
        notes.append("No Bedrock usage metrics were published for this period.")
    else:
        missing = [m for m in ("Invocations", "InputTokenCount", "OutputTokenCount")
                   if m not in usage_res.metrics_present]
        if missing:
            notes.append(f"Some usage metrics unavailable: {', '.join(missing)}.")

    # --- Per-model breakdown ---
    by_model = _by_model(usage_res) if usage_res.available else []

    # --- Efficiency (our calculation) ---
    efficiency = _efficiency(
        cost_res.total_cost if cost_res.available else None,
        _int_or_none(invocations),
        _int_or_none(input_tokens),
        _int_or_none(output_tokens),
    )

    # --- Spike detection (deterministic, reuses anomaly engine) ---
    spike = _detect_spike(
        _daily_metric(usage_res, "Invocations") if usage_res.available else {},
        cost_res.daily if cost_res.available else [],
    )

    has_any_data = bool(
        (cost_res.available and cost_res.total_cost != 0)
        or (usage_res.available and usage_res.series)
    )
    if not has_any_data and not notes:
        notes.append("No Bedrock cost or usage found for this period.")

    return BedrockIntelligence(
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        cost=cost_facts,
        usage=usage_facts,
        by_model=by_model,
        efficiency=efficiency,
        spike=spike,
        has_any_data=has_any_data,
        notes=notes,
    )
