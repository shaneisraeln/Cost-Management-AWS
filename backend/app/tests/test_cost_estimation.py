"""Unit tests for Terraform plan parsing and deterministic cost estimation."""
from __future__ import annotations

from decimal import Decimal

from app.engines.cost_estimation import estimate
from app.engines.iac.terraform_plan import TerraformPlanParser
from app.providers.pricing.static_cache import StaticPriceCacheProvider


def _plan(resource_changes: list[dict]) -> dict:
    return {"resource_changes": resource_changes}


def _rc(address, rtype, actions, before=None, after=None):
    return {
        "address": address,
        "type": rtype,
        "change": {"actions": actions, "before": before, "after": after},
    }


def test_parser_maps_supported_and_flags_unsupported() -> None:
    doc = _plan(
        [
            _rc(
                "aws_instance.web",
                "aws_instance",
                ["create"],
                after={"instance_type": "t3.micro"},
            ),
            _rc("aws_lambda_function.fn", "aws_lambda_function", ["create"], after={}),
        ]
    )
    result = TerraformPlanParser().parse(doc)
    assert len(result.changes) == 1
    assert result.changes[0].service == "EC2"
    assert result.unsupported == ["aws_lambda_function"]


def test_no_op_changes_are_ignored() -> None:
    doc = _plan([_rc("aws_instance.web", "aws_instance", ["no-op"])])
    assert TerraformPlanParser().parse(doc).changes == []


def test_create_ec2_produces_positive_delta() -> None:
    doc = _plan(
        [_rc("aws_instance.web", "aws_instance", ["create"], after={"instance_type": "t3.micro"})]
    )
    parsed = TerraformPlanParser().parse(doc)
    result = estimate(parsed, StaticPriceCacheProvider())
    # t3.micro: 0.0104 * 730 = 7.592/month
    assert result.baseline_monthly == Decimal("0")
    assert result.proposed_monthly == Decimal("7.592")
    assert result.delta_monthly == Decimal("7.592")
    assert result.line_items[0].estimated is True


def test_update_instance_type_computes_delta() -> None:
    doc = _plan(
        [
            _rc(
                "aws_instance.web",
                "aws_instance",
                ["delete", "create"],  # replacement -> update
                before={"instance_type": "t3.micro"},
                after={"instance_type": "t3.small"},
            )
        ]
    )
    parsed = TerraformPlanParser().parse(doc)
    result = estimate(parsed, StaticPriceCacheProvider())
    # small(0.0208) - micro(0.0104) = 0.0104/hr * 730 = 7.592/month
    assert result.delta_monthly == Decimal("7.592")


def test_unknown_instance_type_is_not_estimated_not_guessed() -> None:
    doc = _plan(
        [_rc("aws_instance.x", "aws_instance", ["create"], after={"instance_type": "z9.mega"})]
    )
    parsed = TerraformPlanParser().parse(doc)
    result = estimate(parsed, StaticPriceCacheProvider())
    assert result.delta_monthly == Decimal("0")  # not guessed
    assert result.line_items[0].estimated is False
    assert "not priceable" in result.line_items[0].detail


def test_s3_without_size_is_not_estimated() -> None:
    doc = _plan([_rc("aws_s3_bucket.b", "aws_s3_bucket", ["create"], after={})])
    parsed = TerraformPlanParser().parse(doc)
    result = estimate(parsed, StaticPriceCacheProvider())
    assert result.line_items[0].estimated is False


def test_ebs_volume_priced_by_size() -> None:
    doc = _plan(
        [_rc("aws_ebs_volume.d", "aws_ebs_volume", ["create"], after={"size": 100, "type": "gp3"})]
    )
    parsed = TerraformPlanParser().parse(doc)
    result = estimate(parsed, StaticPriceCacheProvider())
    # 100GB * 0.08 = 8.00/month
    assert result.proposed_monthly == Decimal("8.00")
