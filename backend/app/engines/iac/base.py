"""IaC parser abstraction.

Turns an infrastructure-change document into a normalized list of
`ResourceChange` values the cost engine understands. Terraform plan JSON is
the first supported format; the interface lets other formats (HCL,
CloudFormation, CDK) be added later without changing the estimator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ResourceChange:
    """A normalized single-resource change extracted from an IaC document."""

    address: str                       # e.g. "aws_instance.web"
    iac_type: str                      # e.g. "aws_instance"
    action: str                        # "create" | "update" | "delete" | "no-op"
    # Our internal service code (EC2/EBS/RDS/S3) or None if unsupported.
    service: str | None
    before: dict = field(default_factory=dict)   # attributes before the change
    after: dict = field(default_factory=dict)     # attributes after the change


@dataclass(frozen=True)
class ParseResult:
    changes: list[ResourceChange]
    unsupported: list[str]             # iac_type values we don't estimate yet
    iac_format: str


@runtime_checkable
class IaCParser(Protocol):
    iac_format: str

    def parse(self, document: dict) -> ParseResult: ...
