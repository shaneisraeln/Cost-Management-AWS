"""CloudTrail provider focused on resource-creation identity events.

Rather than ingesting everything, this initially looks up the create-style
events that establish who created a resource. Each returned record carries the
actor identity, the created resource id (when extractable), and the timestamp
so the attribution engine can use "creator" as evidence (Requirement 7.1, 7.6,
19 focus on useful identity events; read-only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Creation events that establish ownership, per service.
CREATION_EVENT_NAMES = [
    "RunInstances",       # EC2 instance
    "CreateVolume",       # EBS volume
    "CreateBucket",       # S3 bucket
    "CreateDBInstance",   # RDS instance
]


@dataclass(frozen=True)
class RawEvent:
    provider_event_id: str
    event_name: str
    event_type: str
    timestamp: datetime | None
    actor_principal_id: str | None
    actor_arn: str | None
    actor_type: str | None
    resource_provider_id: str | None
    region: str | None
    raw: dict = field(default_factory=dict)


def _extract_resource_id(event_name: str, detail: dict) -> str | None:
    """Best-effort extraction of the created resource id from CloudTrail detail.

    Returns None rather than guessing when the shape is unfamiliar.
    """
    try:
        resp = detail.get("responseElements") or {}
        if event_name == "RunInstances":
            items = resp.get("instancesSet", {}).get("items", [])
            return items[0]["instanceId"] if items else None
        if event_name == "CreateVolume":
            return resp.get("volumeId")
        if event_name == "CreateBucket":
            req = detail.get("requestParameters") or {}
            return req.get("bucketName")
        if event_name == "CreateDBInstance":
            db = resp.get("dBInstance") or {}
            return db.get("dBInstanceIdentifier")
    except (KeyError, IndexError, TypeError):
        return None
    return None


class CloudTrailProvider:
    source = "CLOUDTRAIL"

    def lookup_creation_events(
        self, session: boto3.Session, region: str, start: date, end: date
    ) -> list[RawEvent]:
        client = session.client("cloudtrail", region_name=region)
        events: list[RawEvent] = []

        for event_name in CREATION_EVENT_NAMES:
            try:
                paginator = client.get_paginator("lookup_events")
                pages = paginator.paginate(
                    LookupAttributes=[
                        {"AttributeKey": "EventName", "AttributeValue": event_name}
                    ],
                    StartTime=datetime(start.year, start.month, start.day),
                    EndTime=datetime(end.year, end.month, end.day),
                )
                for page in pages:
                    for ev in page.get("Events", []):
                        events.append(self._to_raw(ev, region))
            except (ClientError, BotoCoreError):
                # A single event-name lookup failing must not abort the others.
                continue

        return events

    @staticmethod
    def _to_raw(ev: dict, region: str) -> RawEvent:
        detail = {}
        try:
            detail = json.loads(ev.get("CloudTrailEvent", "{}"))
        except (json.JSONDecodeError, TypeError):
            detail = {}

        user_identity = detail.get("userIdentity", {}) if detail else {}
        actor_arn = user_identity.get("arn")
        actor_principal = (
            user_identity.get("userName")
            or user_identity.get("principalId")
            or actor_arn
        )
        event_name = ev.get("EventName", "")

        return RawEvent(
            provider_event_id=ev.get("EventId", ""),
            event_name=event_name,
            event_type="RESOURCE_CREATED",
            timestamp=ev.get("EventTime"),
            actor_principal_id=actor_principal,
            actor_arn=actor_arn,
            actor_type=user_identity.get("type"),
            resource_provider_id=_extract_resource_id(event_name, detail),
            region=region,
            raw={
                "event_source": ev.get("EventSource"),
                "username": ev.get("Username"),
            },
        )
