"""Unit tests for the action policy engine and EC2 stop executor (mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.db.models.action_request import ActionType
from app.db.models.user import UserRole
from app.engines.action_policy import PolicyInputs, evaluate
from app.providers.aws.actions import Ec2ActionExecutor


def _base(**overrides) -> PolicyInputs:
    defaults = dict(
        action_type=ActionType.STOP_INSTANCE,
        role=UserRole.ADMIN,
        resource_exists=True,
        resource_service="EC2",
        current_state="running",
        tags={"environment": "dev"},
        approved=True,
    )
    defaults.update(overrides)
    return PolicyInputs(**defaults)


def test_allows_when_all_checks_pass() -> None:
    assert evaluate(_base()).allowed is True


def test_blocks_non_admin() -> None:
    d = evaluate(_base(role=UserRole.MEMBER))
    assert d.allowed is False
    assert any("OWNER or ADMIN" in r for r in d.reasons)


def test_blocks_production_environment() -> None:
    d = evaluate(_base(tags={"environment": "production"}))
    assert d.allowed is False
    assert any("production" in r for r in d.reasons)


def test_blocks_unknown_environment_by_default() -> None:
    # No environment tag -> protected by default.
    d = evaluate(_base(tags={"Name": "web"}))
    assert d.allowed is False
    assert any("protected by default" in r for r in d.reasons)


def test_blocks_explicit_protection_tag() -> None:
    d = evaluate(_base(tags={"environment": "dev", "do-not-stop": "true"}))
    assert d.allowed is False


def test_blocks_when_not_running() -> None:
    d = evaluate(_base(current_state="stopped"))
    assert d.allowed is False
    assert any("running" in r for r in d.reasons)


def test_blocks_without_approval() -> None:
    d = evaluate(_base(approved=False))
    assert d.allowed is False
    assert any("confirmation" in r for r in d.reasons)


def test_blocks_non_ec2() -> None:
    d = evaluate(_base(resource_service="RDS"))
    assert d.allowed is False


# --- Executor with mocked boto3 (no real AWS call) ---


def _executor_with_response(response) -> tuple[Ec2ActionExecutor, MagicMock]:
    client = MagicMock()
    if isinstance(response, Exception):
        client.stop_instances.side_effect = response
    else:
        client.stop_instances.return_value = response
    session = MagicMock()
    session.client.return_value = client
    return Ec2ActionExecutor(session_factory=lambda region: session), client


def test_executor_confirms_on_stopping_response() -> None:
    resp = {
        "StoppingInstances": [
            {"InstanceId": "i-123", "CurrentState": {"Name": "stopping"}}
        ]
    }
    executor, client = _executor_with_response(resp)
    outcome = executor.stop_instance(MagicMock(), instance_id="i-123", region="us-east-1")
    assert outcome.confirmed is True
    assert outcome.aws_api == "ec2:StopInstances"
    client.stop_instances.assert_called_once_with(InstanceIds=["i-123"])


def test_executor_fails_when_not_confirmed() -> None:
    resp = {"StoppingInstances": []}
    executor, _ = _executor_with_response(resp)
    outcome = executor.stop_instance(MagicMock(), instance_id="i-123", region="us-east-1")
    assert outcome.confirmed is False


def test_executor_fails_on_aws_error() -> None:
    from botocore.exceptions import ClientError

    err = ClientError({"Error": {"Code": "UnauthorizedOperation"}}, "StopInstances")
    executor, _ = _executor_with_response(err)
    outcome = executor.stop_instance(MagicMock(), instance_id="i-123", region="us-east-1")
    assert outcome.confirmed is False
    assert "failed" in outcome.detail.lower()
