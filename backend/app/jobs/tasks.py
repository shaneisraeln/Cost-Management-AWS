"""Celery background jobs.

CostSyncJob fetches and upserts cost data for a connection. It retries
transient failures with exponential backoff and is idempotent, so a retry
never duplicates records (Requirements 20.2, 20.3, 20.4).
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models.aws_connection import AwsConnection
from app.db.session import SessionLocal
from app.jobs.celery_app import celery_app
from app.services.attribution import run_attribution
from app.services.cloudtrail_sync import sync_cloudtrail
from app.services.cost_sync import sync_costs
from app.services.resource_sync import sync_resources


async def _run_cost_sync(tenant_id: str, connection_id: str, days: int) -> dict:
    async with SessionLocal() as db:
        connection = (
            await db.execute(
                select(AwsConnection).where(
                    AwsConnection.id == connection_id,
                    AwsConnection.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            return {"error": "connection_not_found"}

        end = date.today()
        start = end - timedelta(days=days)
        result = await sync_costs(db, tenant_id, connection, start, end)
        return result.model_dump(mode="json")


@celery_app.task(
    name="cost.sync",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    retry_backoff=True,
    retry_backoff_max=300,
)
def cost_sync_task(self, tenant_id: str, connection_id: str, days: int = 30) -> dict:
    """Run a cost sync for a connection over the trailing ``days`` window."""
    try:
        return asyncio.run(_run_cost_sync(tenant_id, connection_id, days))
    except Exception as exc:  # noqa: BLE001 - Celery handles retry/backoff
        raise self.retry(exc=exc) from exc


async def _run_resource_sync(tenant_id: str, connection_id: str) -> dict:
    async with SessionLocal() as db:
        connection = (
            await db.execute(
                select(AwsConnection).where(
                    AwsConnection.id == connection_id,
                    AwsConnection.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            return {"error": "connection_not_found"}
        return await sync_resources(db, tenant_id, connection)


@celery_app.task(
    name="resource.sync",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    retry_backoff=True,
    retry_backoff_max=300,
)
def resource_sync_task(self, tenant_id: str, connection_id: str) -> dict:
    """Discover and upsert resources for a connection."""
    try:
        return asyncio.run(_run_resource_sync(tenant_id, connection_id))
    except Exception as exc:  # noqa: BLE001 - Celery handles retry/backoff
        raise self.retry(exc=exc) from exc


async def _run_cloudtrail_and_attribution(tenant_id: str, connection_id: str, days: int) -> dict:
    async with SessionLocal() as db:
        connection = (
            await db.execute(
                select(AwsConnection).where(
                    AwsConnection.id == connection_id,
                    AwsConnection.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            return {"error": "connection_not_found"}
        ct = await sync_cloudtrail(db, tenant_id, connection, days=days)
        attr = await run_attribution(db, tenant_id)
        return {"cloudtrail": ct, "attribution": attr}


@celery_app.task(
    name="attribution.sync",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    retry_backoff=True,
    retry_backoff_max=300,
)
def attribution_sync_task(self, tenant_id: str, connection_id: str, days: int = 90) -> dict:
    """Ingest CloudTrail creation events, then run attribution."""
    try:
        return asyncio.run(_run_cloudtrail_and_attribution(tenant_id, connection_id, days))
    except Exception as exc:  # noqa: BLE001 - Celery handles retry/backoff
        raise self.retry(exc=exc) from exc
