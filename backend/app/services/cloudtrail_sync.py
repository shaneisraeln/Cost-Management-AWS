"""CloudTrail sync: ingest resource-creation identity events (read-only)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.aws_connection import AwsConnection
from app.db.models.event import Event
from app.providers.aws.cloudtrail import CloudTrailProvider, RawEvent
from app.providers.aws.credentials import get_credential_provider
from app.providers.aws.resources import list_regions
from app.repositories.attribution import AwsIdentityRepository, EventRepository

logger = logging.getLogger(__name__)


def _fetch_events(connection: AwsConnection, start: date, end: date) -> list[RawEvent]:
    cred = get_credential_provider(
        connection.auth_mode,
        profile_name=connection.profile_name,
        role_arn=connection.role_arn,
        region=connection.region,
    )
    session = cred.get_session(region=connection.region)
    provider = CloudTrailProvider()

    raws: list[RawEvent] = []
    # CloudTrail lookup is regional; scan enabled regions.
    for region in list_regions(session, connection.region):
        try:
            raws.extend(provider.lookup_creation_events(session, region, start, end))
        except Exception:  # noqa: BLE001
            logger.exception("cloudtrail lookup failed", extra={"region": region})
    return raws


async def sync_cloudtrail(
    db: AsyncSession, tenant_id: str, connection: AwsConnection, days: int = 90
) -> dict:
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days)

    try:
        raws = await asyncio.to_thread(_fetch_events, connection, start, end)
    except Exception as exc:  # noqa: BLE001
        connection.last_error = f"cloudtrail_sync: {exc.__class__.__name__}: {exc}"
        await db.commit()
        raise

    event_repo = EventRepository(db, tenant_id)
    identity_repo = AwsIdentityRepository(db, tenant_id)

    events = [
        Event(
            tenant_id=tenant_id,
            account_id=connection.account_id,
            provider_event_id=r.provider_event_id,
            event_type=r.event_type,
            event_name=r.event_name,
            timestamp=r.timestamp,
            source="CLOUDTRAIL",
            actor_principal_id=r.actor_principal_id,
            actor_arn=r.actor_arn,
            resource_provider_id=r.resource_provider_id,
            region=r.region,
            normalized_data=r.raw,
        )
        for r in raws
        if r.provider_event_id
    ]
    added = await event_repo.upsert_many(events)

    # Record distinct actor identities seen.
    seen: set[str] = set()
    for r in raws:
        if r.actor_principal_id and r.actor_principal_id not in seen:
            seen.add(r.actor_principal_id)
            await identity_repo.upsert(
                connection.account_id,
                r.actor_principal_id,
                principal_type=r.actor_type,
                arn=r.actor_arn,
                display_name=r.actor_principal_id,
            )

    connection.last_event_sync = datetime.now(UTC)
    connection.last_error = None
    await db.commit()

    return {
        "account_id": connection.account_id,
        "events_fetched": len(raws),
        "events_added": added,
        "identities_seen": len(seen),
    }
