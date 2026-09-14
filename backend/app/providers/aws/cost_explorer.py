"""Cost data providers.

`CostProvider` is the abstraction the rest of the system depends on.
`CostExplorerProvider` implements it against AWS Cost Explorer. A
`DetailedBillingProvider` seam is declared for a future CUR/Data Exports
implementation so consumers never bind to one AWS API (TRD Path A/B).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

import boto3

from app.schemas.cost import RawCostLine


@runtime_checkable
class CostProvider(Protocol):
    """Returns AWS-shaped cost lines for a date range."""

    source: str

    def get_daily_cost_by_service(
        self, session: boto3.Session, start: date, end: date
    ) -> list[RawCostLine]: ...


class CostExplorerProvider:
    """Fetches daily cost grouped by service from AWS Cost Explorer.

    Cost Explorer's ``end`` date is exclusive. Grouping by SERVICE keeps the
    MVP focused; region/usage_type grouping can be layered later without
    changing the normalized model.
    """

    source = "COST_EXPLORER"

    def get_daily_cost_by_service(
        self, session: boto3.Session, start: date, end: date
    ) -> list[RawCostLine]:
        client = session.client("ce")
        lines: list[RawCostLine] = []
        next_token: str | None = None

        while True:
            kwargs = {
                "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
                "Granularity": "DAILY",
                "Metrics": ["UnblendedCost"],
                "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
            }
            if next_token:
                kwargs["NextPageToken"] = next_token

            response = client.get_cost_and_usage(**kwargs)

            for result in response.get("ResultsByTime", []):
                period = result["TimePeriod"]
                p_start = date.fromisoformat(period["Start"])
                p_end = date.fromisoformat(period["End"])
                for group in result.get("Groups", []):
                    service = group["Keys"][0] if group.get("Keys") else None
                    metric = group["Metrics"]["UnblendedCost"]
                    lines.append(
                        RawCostLine(
                            period_start=p_start,
                            period_end=p_end,
                            service=service,
                            region=None,
                            usage_type=None,
                            operation=None,
                            amount=Decimal(str(metric["Amount"])),
                            currency=metric.get("Unit", "USD"),
                            source_ref={
                                "provider": self.source,
                                "granularity": "DAILY",
                                "group_by": "SERVICE",
                                "metric": "UnblendedCost",
                                "query_start": start.isoformat(),
                                "query_end": end.isoformat(),
                            },
                        )
                    )
                # Some periods report only an aggregate Total with no groups.
                if not result.get("Groups") and result.get("Total"):
                    total = result["Total"].get("UnblendedCost")
                    if total:
                        lines.append(
                            RawCostLine(
                                period_start=p_start,
                                period_end=p_end,
                                service=None,
                                region=None,
                                usage_type=None,
                                operation=None,
                                amount=Decimal(str(total["Amount"])),
                                currency=total.get("Unit", "USD"),
                                source_ref={
                                    "provider": self.source,
                                    "granularity": "DAILY",
                                    "group_by": "NONE",
                                    "metric": "UnblendedCost",
                                    "query_start": start.isoformat(),
                                    "query_end": end.isoformat(),
                                },
                            )
                        )

            next_token = response.get("NextPageToken")
            if not next_token:
                break

        return lines


class DetailedBillingProvider:
    """Seam for CUR / AWS Data Exports resource-level ingestion (later phase)."""

    source = "DETAILED_BILLING"

    def get_daily_cost_by_service(
        self, session: boto3.Session, start: date, end: date
    ) -> list[RawCostLine]:
        raise NotImplementedError(
            "Detailed billing (CUR/Data Exports) ingestion is a later phase."
        )
