"""Pure normalization of raw discovered resources into canonical values."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.providers.aws.resources import RawResource


@dataclass(frozen=True)
class NormalizedResource:
    account_id: str | None
    provider: str
    provider_resource_id: str
    arn: str | None
    service: str
    resource_type: str
    region: str | None
    state: str | None
    provider_created_at: datetime | None
    tags: dict
    resource_metadata: dict


def normalize_resource(
    raw: RawResource, *, account_id: str | None, provider: str = "AWS"
) -> NormalizedResource:
    return NormalizedResource(
        account_id=account_id,
        provider=provider,
        provider_resource_id=raw.provider_resource_id,
        arn=raw.arn,
        service=raw.service,
        resource_type=raw.resource_type,
        region=raw.region,
        state=raw.state,
        provider_created_at=raw.created_at,
        tags=dict(raw.tags),
        resource_metadata=dict(raw.metadata),
    )


def normalize_resources(
    raws: list[RawResource], *, account_id: str | None, provider: str = "AWS"
) -> list[NormalizedResource]:
    return [normalize_resource(r, account_id=account_id, provider=provider) for r in raws]
