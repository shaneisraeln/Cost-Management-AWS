"""Builds the customer-facing IAM setup material for the connection wizard.

- Read policy: the exact least-privilege read-only policy the application needs
  (loaded from docs/iam/read-policy.json so there is a single source of truth).
- Trust policy: allows ONLY the application's principal to assume the role,
  gated by the per-connection External ID (confused-deputy mitigation).

No secrets are included. If the deployment has no stable app principal yet, the
trust policy is omitted and a prerequisite note is returned instead.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

# backend/app/services/connection_setup.py -> repo root is 4 parents up.
_READ_POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "iam" / "read-policy.json"
)

# Fallback mirrors docs/iam/read-policy.json so the API still works if the docs
# file is not shipped alongside the backend. Kept in sync intentionally.
_READ_POLICY_FALLBACK = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CostExplorerRead",
            "Effect": "Allow",
            "Action": ["ce:GetCostAndUsage"],
            "Resource": "*",
        },
        {
            "Sid": "ResourceDiscoveryRead",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeVolumes",
                "ec2:DescribeRegions",
                "ec2:DescribeTags",
                "s3:ListAllMyBuckets",
                "s3:GetBucketLocation",
                "s3:GetBucketTagging",
                "rds:DescribeDBInstances",
                "rds:ListTagsForResource",
            ],
            "Resource": "*",
        },
        {
            "Sid": "ActivityRead",
            "Effect": "Allow",
            "Action": ["cloudtrail:LookupEvents", "sts:GetCallerIdentity"],
            "Resource": "*",
        },
        {
            "Sid": "BedrockUsageMetricsRead",
            "Effect": "Allow",
            "Action": ["cloudwatch:ListMetrics", "cloudwatch:GetMetricData"],
            "Resource": "*",
        },
    ],
}


@lru_cache
def read_policy() -> dict:
    try:
        return json.loads(_READ_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _READ_POLICY_FALLBACK


def trust_policy(app_principal_arn: str, external_id: str) -> dict:
    """Trust policy the customer attaches to their read-only role."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": app_principal_arn},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:ExternalId": external_id}},
            }
        ],
    }


def build_setup_info(external_id: str, region: str) -> dict:
    """Assemble the wizard payload. Trust policy omitted if no app principal."""
    settings = get_settings()
    principal = settings.app_aws_principal_arn or None
    info = {
        "assume_role_available": bool(principal),
        "app_principal_arn": principal,
        "external_id": external_id,
        "region": region,
        "read_policy": read_policy(),
        "trust_policy": trust_policy(principal, external_id) if principal else None,
        "prerequisite_note": None,
    }
    if not principal:
        info["prerequisite_note"] = (
            "This deployment does not yet have an application AWS principal "
            "configured (APP_AWS_PRINCIPAL_ARN). Cross-account AssumeRole "
            "connections cannot be created until the operator sets it. Local "
            "profile mode remains available for development."
        )
    return info
