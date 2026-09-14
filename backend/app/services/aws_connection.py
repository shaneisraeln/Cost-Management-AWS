"""AWS connection onboarding and permission validation.

Validation obtains credentials via the credential abstraction (local profile
in dev, cross-account AssumeRole in production), discovers the account id, and
probes each capability the application uses so missing permissions are
surfaced per-capability rather than failing silently.

AssumeRole failures are distinguished from permission gaps and mapped to
friendly, actionable messages (Requirements 1.5-1.8; multi-account onboarding).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from botocore.exceptions import BotoCoreError, ClientError

from app.db.models.aws_connection import AwsConnection, ConnectionStatus
from app.providers.aws.credentials import AssumeRoleError, get_credential_provider


@dataclass
class CapabilityProbe:
    capability: str
    available: bool
    detail: str | None = None


# Human-friendly labels for the capabilities we probe.
CAPABILITY_LABELS = {
    "sts": "Identity",
    "cost_explorer": "Cost data",
    "ec2": "EC2 resources",
    "s3": "S3 resources",
    "rds": "RDS resources",
    "cloudtrail": "CloudTrail activity",
    "cloudwatch": "Bedrock usage",
}


def _reason(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", "ClientError")
    return exc.__class__.__name__


def _probe_sts(session) -> tuple[str | None, CapabilityProbe]:
    try:
        identity = session.client("sts").get_caller_identity()
        return identity["Account"], CapabilityProbe("sts", True)
    except (ClientError, BotoCoreError) as exc:
        return None, CapabilityProbe("sts", False, _reason(exc))


def _probe_cost_explorer(session) -> CapabilityProbe:
    try:
        client = session.client("ce")
        today = date.today()
        client.get_cost_and_usage(
            TimePeriod={
                "Start": (today - timedelta(days=1)).isoformat(),
                "End": today.isoformat(),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
        return CapabilityProbe("cost_explorer", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("cost_explorer", False, _reason(exc))


def _probe_ec2(session, region: str) -> CapabilityProbe:
    try:
        session.client("ec2", region_name=region).describe_instances(MaxResults=5)
        return CapabilityProbe("ec2", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("ec2", False, _reason(exc))


def _probe_s3(session) -> CapabilityProbe:
    try:
        session.client("s3").list_buckets()
        return CapabilityProbe("s3", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("s3", False, _reason(exc))


def _probe_rds(session, region: str) -> CapabilityProbe:
    try:
        session.client("rds", region_name=region).describe_db_instances(MaxRecords=20)
        return CapabilityProbe("rds", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("rds", False, _reason(exc))


def _probe_cloudtrail(session, region: str) -> CapabilityProbe:
    try:
        session.client("cloudtrail", region_name=region).lookup_events(MaxResults=1)
        return CapabilityProbe("cloudtrail", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("cloudtrail", False, _reason(exc))


def _probe_cloudwatch(session, region: str) -> CapabilityProbe:
    try:
        session.client("cloudwatch", region_name=region).list_metrics(
            Namespace="AWS/Bedrock"
        )
        return CapabilityProbe("cloudwatch", True)
    except (ClientError, BotoCoreError) as exc:
        return CapabilityProbe("cloudwatch", False, _reason(exc))


def _run_probes(
    connection: AwsConnection,
) -> tuple[str | None, list[CapabilityProbe], str | None]:
    """Synchronous boto3 work; executed off the event loop by the caller.

    Returns (account_id, probes, assume_error_code). If AssumeRole itself
    fails, probes will be empty and assume_error_code is set.
    """
    provider = get_credential_provider(
        connection.auth_mode,
        profile_name=connection.profile_name,
        role_arn=connection.role_arn,
        external_id=connection.external_id,
        region=connection.region,
    )
    try:
        session = provider.get_session(region=connection.region)
    except AssumeRoleError as exc:
        return None, [], exc.code

    region = connection.region
    account_id, sts_probe = _probe_sts(session)
    probes = [sts_probe]
    if sts_probe.available:
        probes.append(_probe_cost_explorer(session))
        probes.append(_probe_ec2(session, region))
        probes.append(_probe_s3(session))
        probes.append(_probe_rds(session, region))
        probes.append(_probe_cloudtrail(session, region))
        probes.append(_probe_cloudwatch(session, region))
    return account_id, probes, None


async def validate_connection(
    connection: AwsConnection,
) -> tuple[str | None, list[CapabilityProbe], ConnectionStatus, str | None]:
    """Validate a connection's read-only permissions.

    Returns (account_id, probes, status, assume_error_code).
    """
    account_id, probes, assume_error = await asyncio.to_thread(_run_probes, connection)

    if assume_error is not None:
        return None, probes, ConnectionStatus.ERROR, assume_error

    sts_ok = any(p.capability == "sts" and p.available for p in probes)
    if not sts_ok:
        status = ConnectionStatus.ERROR
    elif all(p.available for p in probes):
        status = ConnectionStatus.CONNECTED
    else:
        status = ConnectionStatus.DEGRADED

    return account_id, probes, status, None


def friendly_error(assume_error_code: str | None, probes: list[CapabilityProbe]) -> str | None:
    """Map AWS/AssumeRole failure codes to actionable guidance."""
    if assume_error_code:
        mapping = {
            "AccessDenied": (
                "The role exists, but AWS did not allow our application to "
                "assume it. Check the role's trust relationship."
            ),
            "NoSuchEntity": (
                "The role could not be found. Make sure the role name and "
                "account ID are correct."
            ),
            "ValidationError": (
                "Check that you entered the Role ARN from the correct AWS "
                "account."
            ),
        }
        # External ID mismatch surfaces as AccessDenied with a specific message;
        # we hint at it explicitly since it is a common setup mistake.
        base = mapping.get(assume_error_code)
        if base:
            if assume_error_code == "AccessDenied":
                return (
                    base
                    + " If you set an External ID, make sure it exactly matches "
                    "the value shown in this setup page."
                )
            return base
        return (
            "Our application could not assume the role. Verify the Role ARN, "
            "trust relationship, and External ID."
        )

    # No AssumeRole error: report the first missing capability, if any.
    missing = [p for p in probes if not p.available]
    if not missing:
        return None
    if any(p.capability == "cost_explorer" for p in missing):
        return "The role does not currently have permission to read AWS cost data."
    caps = ", ".join(CAPABILITY_LABELS.get(p.capability, p.capability) for p in missing)
    return f"The account connected, but these capabilities are unavailable: {caps}."
