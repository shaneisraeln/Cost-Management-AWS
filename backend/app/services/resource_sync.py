"""Resource discovery synchronization: providers -> normalize -> upsert.

Runs regional providers across all enabled regions and global providers once,
then idempotently upserts. Updates the connection's resource sync state and
records errors without corrupting existing data (Requirements 3.4, 20.3, 20.5).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.aws_connection import AwsConnection
from app.engines.resource_normalization import normalize_resources
from app.providers.aws.credentials import get_credential_provider
from app.providers.aws.resources import (
    GLOBAL_PROVIDERS,
    REGIONAL_PROVIDERS,
    RawResource,
    list_regions,
)
from app.repositories.resource import ResourceRepository

logger = logging.getLogger(__name__)


def _discover_all(connection: AwsConnection) -> list[RawResource]:
    """Synchronous boto3 discovery; executed off the event loop by the caller."""
    cred = get_credential_provider(
        connection.auth_mode,
        profile_name=connection.profile_name,
        role_arn=connection.role_arn,
        region=connection.region,
    )
    session = cred.get_session(region=connection.region)

    raws: list[RawResource] = []

    # Global services (e.g. S3) run once.
    for provider in GLOBAL_PROVIDERS:
        try:
            raws.extend(provider.discover(session, connection.region))
        except Exception:  # noqa: BLE001 - one service failing must not abort others
            logger.exception("global discovery failed", extra={"service": provider.service})

    # Regional services run per enabled region.
    regions = list_regions(session, connection.region)
    for region in regions:
        for provider in REGIONAL_PROVIDERS:
            try:
                raws.extend(provider.discover(session, region))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "regional discovery failed",
                    extra={"service": provider.service, "region": region},
                )
    return raws


async def sync_resources(
    db: AsyncSession, tenant_id: str, connection: AwsConnection
) -> dict:
    """Discover and idempotently upsert resources for a connection."""
    import asyncio

    try:
        raws = await asyncio.to_thread(_discover_all, connection)
    except Exception as exc:  # noqa: BLE001
        connection.last_error = f"resource_sync: {exc.__class__.__name__}: {exc}"
        await db.commit()
        logger.exception("resource sync failed", extra={"tenant_id": tenant_id})
        raise

    normalized = normalize_resources(raws, account_id=connection.account_id)
    repo = ResourceRepository(db, tenant_id)
    upserted = await repo.upsert_many(normalized)

    connection.last_resource_sync = datetime.now(UTC)
    connection.last_error = None
    await db.commit()

    by_service: dict[str, int] = {}
    for r in raws:
        by_service[r.service] = by_service.get(r.service, 0) + 1

    logger.info(
        "resource sync complete",
        extra={"tenant_id": tenant_id, "discovered": len(raws), "upserted": upserted},
    )

    return {
        "account_id": connection.account_id,
        "discovered": len(raws),
        "upserted": upserted,
        "by_service": by_service,
    }
