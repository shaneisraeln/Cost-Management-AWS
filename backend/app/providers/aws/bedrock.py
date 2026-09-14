"""Bedrock cost + usage providers (read-only).

Two distinct AWS sources, kept separate on purpose:

- Cost: AWS Cost Explorer (``GetCostAndUsage``) filtered to the Bedrock
  service. This is the authoritative source for cost, consistent with the
  rest of the product.
- Usage: CloudWatch ``AWS/Bedrock`` metrics (Invocations, InputTokenCount,
  OutputTokenCount), discovered/dimensioned by ModelId where AWS exposes it.
  This is the authoritative source for usage.

We never fabricate a metric. If AWS does not return a value, or a permission
is missing, the corresponding field is reported as unavailable (None) with a
reason — never a fake zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

BEDROCK_NAMESPACE = "AWS/Bedrock"
# Cost Explorer service dimension values that represent Bedrock.
BEDROCK_CE_SERVICE_VALUES = ["Amazon Bedrock", "Bedrock"]
# CloudWatch metrics we read (only those AWS actually publishes for Bedrock).
USAGE_METRICS = ["Invocations", "InputTokenCount", "OutputTokenCount"]


@dataclass(frozen=True)
class BedrockCostResult:
    available: bool
    total_cost: Decimal
    currency: str
    # Daily cost points as (iso date, amount) for spike detection / trend.
    daily: list[tuple[str, Decimal]] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True)
class MetricSeries:
    """One CloudWatch metric, optionally scoped to a model."""

    metric: str
    model_id: str | None
    total: Decimal
    daily: list[tuple[str, Decimal]] = field(default_factory=list)


@dataclass(frozen=True)
class BedrockUsageResult:
    available: bool
    # Per (metric, model) series. Empty when unavailable.
    series: list[MetricSeries] = field(default_factory=list)
    # Which metrics were actually returned by AWS (present != necessarily >0).
    metrics_present: list[str] = field(default_factory=list)
    reason: str | None = None


def _reason(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", "ClientError")
    return exc.__class__.__name__


class BedrockCostProvider:
    """Bedrock cost from Cost Explorer, filtered to the Bedrock service."""

    source = "COST_EXPLORER"

    def get_cost(
        self, session: boto3.Session, start: date, end: date
    ) -> BedrockCostResult:
        client = session.client("ce")
        try:
            resp = client.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": BEDROCK_CE_SERVICE_VALUES,
                    }
                },
            )
        except (ClientError, BotoCoreError) as exc:
            return BedrockCostResult(
                available=False,
                total_cost=Decimal("0"),
                currency="USD",
                reason=_reason(exc),
            )

        daily: list[tuple[str, Decimal]] = []
        total = Decimal("0")
        currency = "USD"
        for result in resp.get("ResultsByTime", []):
            amount_obj = result.get("Total", {}).get("UnblendedCost")
            if not amount_obj:
                continue
            amt = Decimal(str(amount_obj["Amount"]))
            currency = amount_obj.get("Unit", currency)
            daily.append((result["TimePeriod"]["Start"], amt))
            total += amt

        return BedrockCostResult(
            available=True,
            total_cost=total,
            currency=currency,
            daily=daily,
        )


class BedrockUsageProvider:
    """Bedrock usage from CloudWatch AWS/Bedrock metrics.

    Discovers ModelId dimensions via ListMetrics, then pulls daily sums via
    GetMetricData. If ListMetrics/GetMetricData is denied or returns nothing,
    the result is marked unavailable rather than zero.
    """

    source = "CLOUDWATCH"

    def get_usage(
        self, session: boto3.Session, region: str, start: date, end: date
    ) -> BedrockUsageResult:
        cw = session.client("cloudwatch", region_name=region)

        # 1. Discover which (metric, ModelId) combinations AWS publishes.
        try:
            discovered = self._discover(cw)
        except (ClientError, BotoCoreError) as exc:
            return BedrockUsageResult(available=False, reason=_reason(exc))

        if not discovered:
            # No Bedrock metrics published (likely no usage / not enabled).
            return BedrockUsageResult(
                available=True,
                series=[],
                metrics_present=[],
                reason="no Bedrock metrics published",
            )

        # 2. Pull daily sums for each discovered metric/model.
        try:
            series = self._fetch(cw, discovered, start, end)
        except (ClientError, BotoCoreError) as exc:
            return BedrockUsageResult(available=False, reason=_reason(exc))

        metrics_present = sorted({s.metric for s in series})
        return BedrockUsageResult(
            available=True,
            series=series,
            metrics_present=metrics_present,
        )

    @staticmethod
    def _discover(cw) -> list[tuple[str, str | None]]:
        """Return list of (metric_name, model_id|None) present in AWS/Bedrock."""
        found: list[tuple[str, str | None]] = []
        seen: set[tuple[str, str | None]] = set()
        paginator = cw.get_paginator("list_metrics")
        for metric in USAGE_METRICS:
            for page in paginator.paginate(
                Namespace=BEDROCK_NAMESPACE, MetricName=metric
            ):
                for m in page.get("Metrics", []):
                    model_id = None
                    for dim in m.get("Dimensions", []):
                        if dim.get("Name") == "ModelId":
                            model_id = dim.get("Value")
                    key = (metric, model_id)
                    if key not in seen:
                        seen.add(key)
                        found.append(key)
        return found

    @staticmethod
    def _fetch(
        cw, combos: list[tuple[str, str | None]], start: date, end: date
    ) -> list[MetricSeries]:
        # Build GetMetricData queries (daily period = 86400s, Sum statistic).
        queries = []
        index: dict[str, tuple[str, str | None]] = {}
        for i, (metric, model_id) in enumerate(combos):
            qid = f"q{i}"
            index[qid] = (metric, model_id)
            dims = [{"Name": "ModelId", "Value": model_id}] if model_id else []
            queries.append(
                {
                    "Id": qid,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": BEDROCK_NAMESPACE,
                            "MetricName": metric,
                            "Dimensions": dims,
                        },
                        "Period": 86400,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )

        start_dt = datetime.combine(start, time.min, tzinfo=UTC)
        end_dt = datetime.combine(end, time.min, tzinfo=UTC)

        results: dict[str, MetricSeries] = {}
        next_token: str | None = None
        # GetMetricData caps at 500 queries per call; our combo count is small.
        while True:
            kwargs = {
                "MetricDataQueries": queries,
                "StartTime": start_dt,
                "EndTime": end_dt,
                "ScanBy": "TimestampAscending",
            }
            if next_token:
                kwargs["NextToken"] = next_token
            resp = cw.get_metric_data(**kwargs)

            for r in resp.get("MetricDataResults", []):
                qid = r.get("Id")
                metric, model_id = index.get(qid, (qid, None))
                timestamps = r.get("Timestamps", [])
                values = r.get("Values", [])
                daily = [
                    (ts.date().isoformat(), Decimal(str(v)))
                    for ts, v in zip(timestamps, values, strict=False)
                ]
                total = sum((d[1] for d in daily), Decimal("0"))
                key = f"{metric}|{model_id or ''}"
                if key in results:
                    prev = results[key]
                    results[key] = MetricSeries(
                        metric=metric,
                        model_id=model_id,
                        total=prev.total + total,
                        daily=prev.daily + daily,
                    )
                else:
                    results[key] = MetricSeries(
                        metric=metric, model_id=model_id, total=total, daily=daily
                    )

            next_token = resp.get("NextToken")
            if not next_token:
                break

        return list(results.values())
