"""Detection service: run deterministic detection over stored cost records.

Builds per-service daily series from CostRecords, detects anomalies, records
a CostChange per anomaly, and correlates each with nearby CloudTrail creation
events (temporal + resource/service match). Correlations are evidence, not
proof of causality (Requirements 8, 7.4, 7.5). Idempotent per (service, day,
algorithm).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.anomaly import Anomaly
from app.db.models.cost_change import CostChange
from app.db.models.cost_record import CostRecord
from app.db.models.event import Event
from app.engines.anomaly import (
    DailyPoint,
    DetectionConfig,
    classify_change,
    detect_service_anomalies,
)
from app.repositories.investigation import AnomalyRepository

# How close (in days) an event must be to a cost change to count as temporal.
CORRELATION_WINDOW_DAYS = 2


async def _daily_by_service(
    db: AsyncSession, tenant_id: str, start: date, end: date
) -> dict[str | None, list[DailyPoint]]:
    stmt = (
        select(CostRecord.service, CostRecord.period_start, CostRecord.cost)
        .where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.period_start >= start,
            CostRecord.period_start < end,
        )
        .order_by(CostRecord.period_start)
    )
    rows = (await db.execute(stmt)).all()
    grouped: dict[str | None, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for service, day, cost in rows:
        grouped[service][day] += Decimal(str(cost))
    return {
        service: [DailyPoint(day=d, amount=a) for d, a in sorted(days.items())]
        for service, days in grouped.items()
    }


async def _events_near(
    db: AsyncSession, tenant_id: str, day: date
) -> list[Event]:
    lo = day - timedelta(days=CORRELATION_WINDOW_DAYS)
    hi = day + timedelta(days=CORRELATION_WINDOW_DAYS + 1)
    stmt = select(Event).where(
        Event.tenant_id == tenant_id,
        Event.timestamp.isnot(None),
        Event.timestamp >= _as_dt(lo),
        Event.timestamp < _as_dt(hi),
    )
    return list((await db.execute(stmt)).scalars().all())


def _as_dt(d: date):
    from datetime import datetime

    return datetime(d.year, d.month, d.day)


async def run_detection(
    db: AsyncSession,
    tenant_id: str,
    *,
    days: int = 30,
    config: DetectionConfig | None = None,
) -> dict:
    config = config or DetectionConfig()
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days)

    series_by_service = await _daily_by_service(db, tenant_id, start, end)
    anomaly_repo = AnomalyRepository(db, tenant_id)
    existing = await anomaly_repo.existing_keys()

    created_anomalies = 0
    created_changes = 0

    for service, series in series_by_service.items():
        detected = detect_service_anomalies(service, series, config)
        for det in detected:
            key = (det.service, det.day, det.algorithm)
            if key in existing:
                continue

            # Correlate with nearby events (temporal + service/resource match).
            events = await _events_near(db, tenant_id, det.day)
            evidence = list(det.evidence)
            correlations = []
            has_creation = False
            for ev in events:
                corr = {
                    "type": "TEMPORAL",
                    "event_id": ev.provider_event_id,
                    "event_name": ev.event_name,
                    "actor": ev.actor_principal_id,
                    "resource": ev.resource_provider_id,
                }
                if ev.event_type == "RESOURCE_CREATED":
                    corr["type"] = "DEPLOYMENT_MATCH"
                    has_creation = True
                correlations.append(corr)
            if correlations:
                evidence.append({"type": "correlated_events", "detail": correlations})

            db.add(
                Anomaly(
                    tenant_id=tenant_id,
                    service=det.service,
                    detected_for=det.day,
                    severity=det.severity,
                    baseline=det.baseline,
                    observed=det.observed,
                    difference=det.difference,
                    algorithm=det.algorithm,
                    confidence=det.confidence,
                    evidence=evidence,
                )
            )
            created_anomalies += 1

            classification, conf = classify_change(
                difference=det.difference,
                has_recent_creation_event=has_creation,
                unusual_identity=False,
            )
            pct = (
                float(det.difference / det.baseline)
                if det.baseline and det.baseline != 0
                else None
            )
            db.add(
                CostChange(
                    tenant_id=tenant_id,
                    period_date=det.day,
                    service=det.service,
                    baseline_cost=det.baseline,
                    observed_cost=det.observed,
                    absolute_change=det.difference,
                    percentage_change=pct,
                    classification=classification,
                    confidence=conf,
                    evidence=evidence,
                )
            )
            created_changes += 1

    await db.commit()
    return {
        "anomalies_created": created_anomalies,
        "cost_changes_created": created_changes,
        "services_analyzed": len(series_by_service),
    }
