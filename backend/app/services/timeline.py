"""Timeline service: merge events, anomalies, and cost changes chronologically.

Produces a single evidence-first stream so a user can see what happened and
when. Each item is labeled by kind so facts (events, detected changes) are
never conflated with inference.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.anomaly import Anomaly
from app.db.models.cost_change import CostChange
from app.db.models.event import Event


async def build_timeline(
    db: AsyncSession, tenant_id: str, *, days: int = 30
) -> list[dict]:
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days)
    start_dt = datetime(start.year, start.month, start.day)

    items: list[dict] = []

    events = (
        await db.execute(
            select(Event).where(
                Event.tenant_id == tenant_id,
                Event.timestamp.isnot(None),
                Event.timestamp >= start_dt,
            )
        )
    ).scalars().all()
    for ev in events:
        items.append(
            {
                "kind": "event",
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                "title": ev.event_name or ev.event_type,
                "detail": {
                    "actor": ev.actor_principal_id,
                    "resource": ev.resource_provider_id,
                    "region": ev.region,
                },
            }
        )

    anomalies = (
        await db.execute(
            select(Anomaly).where(
                Anomaly.tenant_id == tenant_id,
                Anomaly.detected_for >= start,
            )
        )
    ).scalars().all()
    for a in anomalies:
        items.append(
            {
                "kind": "anomaly",
                "timestamp": datetime(
                    a.detected_for.year, a.detected_for.month, a.detected_for.day
                ).isoformat(),
                "title": f"Cost anomaly: {a.service or 'account'}",
                "detail": {
                    "baseline": str(a.baseline),
                    "observed": str(a.observed),
                    "severity": a.severity.value,
                    "confidence": float(a.confidence),
                    "id": a.id,
                },
            }
        )

    changes = (
        await db.execute(
            select(CostChange).where(
                CostChange.tenant_id == tenant_id,
                CostChange.period_date >= start,
            )
        )
    ).scalars().all()
    for c in changes:
        items.append(
            {
                "kind": "cost_change",
                "timestamp": datetime(
                    c.period_date.year, c.period_date.month, c.period_date.day
                ).isoformat(),
                "title": f"Cost change: {c.service or 'account'}",
                "detail": {
                    "classification": c.classification.value,
                    "absolute_change": str(c.absolute_change),
                    "confidence": float(c.confidence),
                    "id": c.id,
                },
            }
        )

    items.sort(key=lambda i: i["timestamp"] or "", reverse=True)
    return items
