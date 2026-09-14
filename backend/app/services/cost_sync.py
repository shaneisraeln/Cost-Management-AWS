"""Cost synchronization: provider -> normalize -> idempotent upsert.

Updates the connection's sync state and records errors without corrupting
existing data. On failure the last successful sync timestamp is preserved and
the error is surfaced, so the UI never shows a false zero (Requirements 2.5,
2.6, 20.3, 20.4, 20.5).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.aws_connection import AwsConnection
from app.engines.cost_normalization import normalize_lines
from app.providers.aws.cost_explorer import CostExplorerProvider, CostProvider
from app.providers.aws.credentials import get_credential_provider
from app.repositories.cost_record import CostRecordRepository
from app.schemas.cost import CostSyncResult

logger = logging.getLogger(__name__)


def _fetch_lines(connection: AwsConnection, provider: CostProvider, start: date, end: date):
    """Synchronous boto3 fetch, executed off the event loop by the caller."""
    cred = get_credential_provider(
        connection.auth_mode,
        profile_name=connection.profile_name,
        role_arn=connection.role_arn,
        region=connection.region,
    )
    session = cred.get_session(region=connection.region)
    return provider.get_daily_cost_by_service(session, start, end)


async def sync_costs(
    db: AsyncSession,
    tenant_id: str,
    connection: AwsConnection,
    start: date,
    end: date,
    *,
    provider: CostProvider | None = None,
) -> CostSyncResult:
    """Fetch, normalize, and idempotently upsert cost records for a range.

    ``end`` is exclusive (matches Cost Explorer). Raises on hard failure after
    recording the error on the connection; the caller/job handles retry.
    """
    provider = provider or CostExplorerProvider()

    try:
        lines = await asyncio.to_thread(_fetch_lines, connection, provider, start, end)
    except Exception as exc:  # noqa: BLE001 - record and re-raise for retry
        connection.last_error = f"cost_sync: {exc.__class__.__name__}: {exc}"
        await db.commit()
        logger.exception(
            "cost sync failed",
            extra={"tenant_id": tenant_id, "account_id": connection.account_id},
        )
        raise

    normalized = normalize_lines(lines, account_id=connection.account_id, source=provider.source)
    repo = CostRecordRepository(db, tenant_id)
    upserted = await repo.upsert_many(normalized)

    total = sum((n.cost for n in normalized), Decimal("0"))
    currency = normalized[0].currency if normalized else "USD"

    connection.last_cost_sync = datetime.now(UTC)
    connection.last_error = None
    await db.commit()

    logger.info(
        "cost sync complete",
        extra={
            "tenant_id": tenant_id,
            "account_id": connection.account_id,
            "lines_fetched": len(lines),
            "records_upserted": upserted,
        },
    )

    return CostSyncResult(
        account_id=connection.account_id,
        period_start=start,
        period_end=end,
        lines_fetched=len(lines),
        records_upserted=upserted,
        total=total,
        currency=currency,
    )
