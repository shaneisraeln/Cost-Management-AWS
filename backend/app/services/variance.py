"""Variance service: compare a stored estimate to actual Cost Explorer data.

Actual cost comes from the CostRecords ingested in Phase 2 (Cost Explorer),
never from CUR. We measure the post-deployment window, normalize the observed
daily spend to a monthly figure, and defer to the VarianceEngine — which
returns INSUFFICIENT_DATA when there isn't enough real data to compare.

The comparison is a measurement/correlation. It is scoped to the estimate's
account; it does NOT claim the PR caused the account-level spend, and this is
made explicit in the output.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cost_estimate import CostEstimate
from app.engines.variance import VarianceConfig, VarianceResult, compute_variance
from app.repositories.cost_record import CostRecordRepository

DAYS_PER_MONTH = Decimal("30")


@dataclass(frozen=True)
class VarianceReport:
    estimate_id: str
    result: VarianceResult
    window_start: date
    window_end: date
    account_scoped: bool
    service_breakdown: list[dict]
    note: str


async def compute_estimate_variance(
    db: AsyncSession,
    tenant_id: str,
    estimate: CostEstimate,
    *,
    config: VarianceConfig | None = None,
) -> VarianceReport:
    config = config or VarianceConfig()
    cost_repo = CostRecordRepository(db, tenant_id)

    # Comparison window: from deployment to now (capped to a sensible span).
    today = date.today()
    end = today + timedelta(days=1)  # end exclusive, include today
    if estimate.deployed_at is not None:
        start = estimate.deployed_at.date()
    else:
        # Not marked deployed: default to trailing 14 days as a best-effort
        # measurement window, but this will typically be INSUFFICIENT_DATA
        # unless data exists.
        start = end - timedelta(days=14)

    total, _records, distinct_days = await cost_repo.total_for_account(
        estimate.account_id, start, end
    )

    # Normalize observed spend over the window to a monthly figure.
    if distinct_days > 0:
        daily_avg = total / Decimal(distinct_days)
        actual_monthly = (daily_avg * DAYS_PER_MONTH).quantize(Decimal("0.0001"))
    else:
        actual_monthly = Decimal("0")

    predicted_monthly = Decimal(str(estimate.estimated_monthly_delta))

    result = compute_variance(
        predicted_monthly=predicted_monthly,
        actual_monthly=actual_monthly,
        actual_days_observed=distinct_days,
        config=config,
    )

    breakdown_rows = await cost_repo.by_service_for_account(estimate.account_id, start, end)
    def _monthly(amt: Decimal) -> str:
        if distinct_days <= 0:
            return "0"
        monthly = (amt / Decimal(distinct_days) * DAYS_PER_MONTH).quantize(Decimal("0.0001"))
        return str(monthly)

    service_breakdown = [
        {
            "service": svc or "Unattributed",
            "observed_window": str(amt),
            "observed_monthly": _monthly(amt),
        }
        for svc, amt in breakdown_rows
    ]

    note = (
        "Measurement, not causality. Actual is account-scoped Cost Explorer "
        "spend over the comparison window normalized to a monthly figure; it "
        "reflects all activity in the account, not only this PR."
    )

    return VarianceReport(
        estimate_id=estimate.id,
        result=result,
        window_start=start,
        window_end=end,
        account_scoped=estimate.account_id is not None,
        service_breakdown=service_breakdown,
        note=note,
    )


def mark_deployed_now(estimate: CostEstimate) -> datetime:
    dt = datetime.now(UTC)
    estimate.deployed_at = dt
    estimate.status = "deployed"
    return dt
