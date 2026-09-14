"""AWS resource discovery providers.

Each provider is a thin, read-only adapter over describe/list calls for one
service, returning AWS-shaped `RawResource` values. Normalization into the
canonical `Resource` model happens in a separate engine. New services are
added by adding a provider and registering it; consumers iterate the registry
(Requirements 3.1, 3.6, 25.2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

import boto3
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class RawResource:
    """An AWS-shaped resource record from a discovery call."""

    provider_resource_id: str
    service: str
    resource_type: str
    region: str | None
    arn: str | None = None
    state: str | None = None
    created_at: datetime | None = None
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class ResourceProvider(Protocol):
    """Discovers resources for one AWS service."""

    service: str

    def discover(self, session: boto3.Session, region: str) -> list[RawResource]: ...


def _tags_to_dict(tag_list: list[dict] | None) -> dict[str, str]:
    """Convert AWS [{Key, Value}] tag lists into a plain dict."""
    if not tag_list:
        return {}
    return {t.get("Key", ""): t.get("Value", "") for t in tag_list if t.get("Key")}


class Ec2ResourceProvider:
    """EC2 instances (regional)."""

    service = "EC2"

    def discover(self, session: boto3.Session, region: str) -> list[RawResource]:
        client = session.client("ec2", region_name=region)
        resources: list[RawResource] = []
        paginator = client.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    resources.append(
                        RawResource(
                            provider_resource_id=inst["InstanceId"],
                            service=self.service,
                            resource_type="instance",
                            region=region,
                            state=inst.get("State", {}).get("Name"),
                            created_at=inst.get("LaunchTime"),
                            tags=_tags_to_dict(inst.get("Tags")),
                            metadata={
                                "instance_type": inst.get("InstanceType"),
                                "availability_zone": inst.get("Placement", {}).get(
                                    "AvailabilityZone"
                                ),
                                "private_ip": inst.get("PrivateIpAddress"),
                                "image_id": inst.get("ImageId"),
                            },
                        )
                    )
        return resources


class EbsResourceProvider:
    """EBS volumes (regional)."""

    service = "EBS"

    def discover(self, session: boto3.Session, region: str) -> list[RawResource]:
        client = session.client("ec2", region_name=region)
        resources: list[RawResource] = []
        paginator = client.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page.get("Volumes", []):
                attachments = vol.get("Attachments", [])
                resources.append(
                    RawResource(
                        provider_resource_id=vol["VolumeId"],
                        service=self.service,
                        resource_type="volume",
                        region=region,
                        state=vol.get("State"),
                        created_at=vol.get("CreateTime"),
                        tags=_tags_to_dict(vol.get("Tags")),
                        metadata={
                            "size_gb": vol.get("Size"),
                            "volume_type": vol.get("VolumeType"),
                            "attached": bool(attachments),
                            "attached_instance": (
                                attachments[0].get("InstanceId") if attachments else None
                            ),
                        },
                    )
                )
        return resources


class S3ResourceProvider:
    """S3 buckets (global list; per-bucket region + tags).

    S3 is a global service, so discovery runs once (not per region). The
    provider resolves each bucket's region and tags, tolerating buckets with
    no tags (AWS returns an error rather than an empty set).
    """

    service = "S3"

    def discover(self, session: boto3.Session, region: str) -> list[RawResource]:
        client = session.client("s3")
        resources: list[RawResource] = []
        buckets = client.list_buckets().get("Buckets", [])
        for bucket in buckets:
            name = bucket["Name"]
            bucket_region = self._bucket_region(client, name)
            resources.append(
                RawResource(
                    provider_resource_id=name,
                    service=self.service,
                    resource_type="bucket",
                    region=bucket_region,
                    arn=f"arn:aws:s3:::{name}",
                    state=None,
                    created_at=bucket.get("CreationDate"),
                    tags=self._bucket_tags(client, name),
                    metadata={},
                )
            )
        return resources

    @staticmethod
    def _bucket_region(client, name: str) -> str | None:
        try:
            loc = client.get_bucket_location(Bucket=name).get("LocationConstraint")
            # us-east-1 is reported as None by AWS.
            return loc or "us-east-1"
        except (ClientError, BotoCoreError):
            return None

    @staticmethod
    def _bucket_tags(client, name: str) -> dict[str, str]:
        try:
            tagset = client.get_bucket_tagging(Bucket=name).get("TagSet", [])
            return _tags_to_dict(tagset)
        except ClientError as exc:
            # No tags on the bucket is a normal condition, not an error.
            if exc.response.get("Error", {}).get("Code") == "NoSuchTagSet":
                return {}
            return {}
        except BotoCoreError:
            return {}


class RdsResourceProvider:
    """RDS DB instances (regional). Tags require a separate call."""

    service = "RDS"

    def discover(self, session: boto3.Session, region: str) -> list[RawResource]:
        client = session.client("rds", region_name=region)
        resources: list[RawResource] = []
        paginator = client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                arn = db.get("DBInstanceArn")
                resources.append(
                    RawResource(
                        provider_resource_id=db["DBInstanceIdentifier"],
                        service=self.service,
                        resource_type="db_instance",
                        region=region,
                        arn=arn,
                        state=db.get("DBInstanceStatus"),
                        created_at=db.get("InstanceCreateTime"),
                        tags=self._db_tags(client, arn),
                        metadata={
                            "engine": db.get("Engine"),
                            "engine_version": db.get("EngineVersion"),
                            "instance_class": db.get("DBInstanceClass"),
                            "allocated_storage_gb": db.get("AllocatedStorage"),
                            "multi_az": db.get("MultiAZ"),
                        },
                    )
                )
        return resources

    @staticmethod
    def _db_tags(client, arn: str | None) -> dict[str, str]:
        if not arn:
            return {}
        try:
            tags = client.list_tags_for_resource(ResourceName=arn).get("TagList", [])
            return _tags_to_dict(tags)
        except (ClientError, BotoCoreError):
            return {}


# Providers that must run per-region vs once (global).
REGIONAL_PROVIDERS: list[ResourceProvider] = [
    Ec2ResourceProvider(),
    EbsResourceProvider(),
    RdsResourceProvider(),
]
GLOBAL_PROVIDERS: list[ResourceProvider] = [
    S3ResourceProvider(),
]


def list_regions(session: boto3.Session, default_region: str) -> list[str]:
    """Enumerate enabled EC2 regions; fall back to the connection's region."""
    try:
        client = session.client("ec2", region_name=default_region)
        resp = client.describe_regions(AllRegions=False)
        regions = [r["RegionName"] for r in resp.get("Regions", [])]
        return regions or [default_region]
    except (ClientError, BotoCoreError):
        return [default_region]
