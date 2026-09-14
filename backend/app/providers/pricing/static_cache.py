"""Internal static price cache provider (transparent, documented rates).

These are approximate on-demand us-east-1 monthly rates used as a controlled
internal cache for the MVP estimator. They are clearly labeled as estimates
and carry a source + timestamp. Rates not present return found=False so the
estimator marks the item "not estimated" rather than fabricating a number.

Assumes 730 hours/month for hourly resources. Not a substitute for the AWS
Price List API, which plugs in behind the same PricingProvider interface later.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.providers.pricing.base import PriceResult

HOURS_PER_MONTH = Decimal("730")
_RATES_ASOF = "2026-01-01"  # documented as-of date for these static rates

# EC2 on-demand hourly (USD, us-east-1, Linux) for a small supported subset.
EC2_HOURLY = {
    "t3.micro": Decimal("0.0104"),
    "t3.small": Decimal("0.0208"),
    "t3.medium": Decimal("0.0416"),
    "t3.large": Decimal("0.0832"),
    "m5.large": Decimal("0.096"),
    "m5.xlarge": Decimal("0.192"),
    "c5.large": Decimal("0.085"),
}

# RDS on-demand hourly (USD, us-east-1, single-AZ) subset.
RDS_HOURLY = {
    "db.t3.micro": Decimal("0.017"),
    "db.t3.small": Decimal("0.034"),
    "db.t3.medium": Decimal("0.068"),
    "db.m5.large": Decimal("0.171"),
}

# EBS $/GB-month (gp3) and S3 Standard $/GB-month.
EBS_GB_MONTH = Decimal("0.08")
S3_GB_MONTH = Decimal("0.023")


class StaticPriceCacheProvider:
    source = "internal_static_cache"

    def get_monthly_price(
        self, *, service: str, region: str, attributes: dict
    ) -> PriceResult:
        now = datetime.now(UTC).isoformat()

        def _result(price: Decimal, unit: str, note: str | None = None) -> PriceResult:
            return PriceResult(
                found=True,
                monthly_unit_price=price,
                unit=unit,
                currency="USD",
                source=f"{self.source}@{_RATES_ASOF}",
                retrieved_at=now,
                note=note,
            )

        def _missing(note: str) -> PriceResult:
            return PriceResult(
                found=False,
                monthly_unit_price=Decimal("0"),
                unit="",
                currency="USD",
                source=self.source,
                retrieved_at=now,
                note=note,
            )

        if service == "EC2":
            itype = attributes.get("instance_type")
            rate = EC2_HOURLY.get(itype)
            if rate is None:
                return _missing(f"no cached rate for EC2 instance_type={itype}")
            return _result(rate * HOURS_PER_MONTH, "instance-month",
                           note=f"{itype} @ ${rate}/hr x 730h")

        if service == "RDS":
            iclass = attributes.get("instance_class")
            rate = RDS_HOURLY.get(iclass)
            if rate is None:
                return _missing(f"no cached rate for RDS instance_class={iclass}")
            return _result(rate * HOURS_PER_MONTH, "instance-month",
                           note=f"{iclass} @ ${rate}/hr x 730h")

        if service == "EBS":
            size = attributes.get("size_gb")
            if not size:
                return _missing("EBS size unknown")
            return _result(EBS_GB_MONTH * Decimal(str(size)), "volume-month",
                           note=f"{size}GB gp3 @ ${EBS_GB_MONTH}/GB-mo")

        if service == "S3":
            # S3 cost is usage-driven; without an assumed data size we cannot
            # estimate honestly. Only estimate if an explicit size is provided.
            size = attributes.get("estimated_gb")
            if not size:
                return _missing("S3 cost depends on stored data; no size provided")
            return _result(S3_GB_MONTH * Decimal(str(size)), "bucket-month",
                           note=f"{size}GB Standard @ ${S3_GB_MONTH}/GB-mo")

        return _missing(f"unsupported service {service}")
