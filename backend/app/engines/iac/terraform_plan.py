"""Terraform plan JSON parser (`terraform show -json` output).

Reads the resolved ``resource_changes`` array — concrete before/after values
and actions — so we estimate from what Terraform actually intends to apply,
not from unresolved HCL. Only a narrow, well-understood set of AWS resource
types is mapped; everything else is reported as unsupported (not faked).
"""
from __future__ import annotations

from app.engines.iac.base import IaCParser, ParseResult, ResourceChange

# Terraform resource type -> our internal service code + attribute extractor.
SUPPORTED_TYPES = {
    "aws_instance": "EC2",
    "aws_ebs_volume": "EBS",
    "aws_db_instance": "RDS",
    "aws_s3_bucket": "S3",
}


def _extract_attributes(iac_type: str, values: dict | None) -> dict:
    """Pull the attributes the pricing layer needs from a resource's values."""
    values = values or {}
    if iac_type == "aws_instance":
        return {"instance_type": values.get("instance_type")}
    if iac_type == "aws_ebs_volume":
        return {"size_gb": values.get("size"), "volume_type": values.get("type")}
    if iac_type == "aws_db_instance":
        return {
            "instance_class": values.get("instance_class"),
            "engine": values.get("engine"),
        }
    if iac_type == "aws_s3_bucket":
        # S3 has no size in the plan; leave empty so the estimator marks it
        # not-estimated unless a size is supplied elsewhere.
        return {}
    return {}


def _normalize_action(actions: list[str]) -> str:
    """Terraform actions arrive as a list, e.g. ["create"] or ["delete","create"]."""
    if not actions:
        return "no-op"
    if actions == ["no-op"]:
        return "no-op"
    if "delete" in actions and "create" in actions:
        return "update"  # replacement
    if "create" in actions:
        return "create"
    if "delete" in actions:
        return "delete"
    if "update" in actions:
        return "update"
    return actions[0]


class TerraformPlanParser:
    iac_format = "terraform_plan"

    def parse(self, document: dict) -> ParseResult:
        changes: list[ResourceChange] = []
        unsupported: set[str] = set()

        for rc in document.get("resource_changes", []):
            iac_type = rc.get("type", "")
            change = rc.get("change", {}) or {}
            action = _normalize_action(change.get("actions", []))
            if action == "no-op":
                continue

            service = SUPPORTED_TYPES.get(iac_type)
            if service is None:
                unsupported.add(iac_type)
                continue

            changes.append(
                ResourceChange(
                    address=rc.get("address", iac_type),
                    iac_type=iac_type,
                    action=action,
                    service=service,
                    before=_extract_attributes(iac_type, change.get("before")),
                    after=_extract_attributes(iac_type, change.get("after")),
                )
            )

        return ParseResult(
            changes=changes,
            unsupported=sorted(unsupported),
            iac_format=self.iac_format,
        )


def get_parser(iac_format: str) -> IaCParser:
    if iac_format == "terraform_plan":
        return TerraformPlanParser()
    raise ValueError(f"Unsupported IaC format: {iac_format}")
