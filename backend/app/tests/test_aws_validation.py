"""Unit tests for AWS connection permission validation.

boto3 is fully mocked so no real AWS calls occur. We verify account
discovery and the CONNECTED / DEGRADED / ERROR status logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.db.models.aws_connection import (
    AwsConnection,
    ConnectionAuthMode,
    ConnectionStatus,
)
from app.services import aws_connection as svc


def _connection() -> AwsConnection:
    return AwsConnection(
        auth_mode=ConnectionAuthMode.LOCAL_PROFILE,
        profile_name=None,
        role_arn=None,
        region="us-east-1",
    )


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "op")


def _session_factory(clients: dict[str, MagicMock]) -> MagicMock:
    session = MagicMock()

    def _client(name: str, **_kwargs):
        return clients[name]

    session.client.side_effect = _client
    return session


def _all_clients(sts, ce) -> dict[str, MagicMock]:
    # All capability clients default to MagicMock (succeed) unless overridden.
    return {
        "sts": sts,
        "ce": ce,
        "ec2": MagicMock(),
        "s3": MagicMock(),
        "rds": MagicMock(),
        "cloudtrail": MagicMock(),
        "cloudwatch": MagicMock(),
    }


@pytest.mark.asyncio
async def test_all_capabilities_available_is_connected(monkeypatch) -> None:
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "123456789012"}
    session = _session_factory(_all_clients(sts, MagicMock()))

    monkeypatch.setattr(
        svc, "get_credential_provider", lambda *a, **k: MagicMock(get_session=lambda **kw: session)
    )

    account_id, probes, status, err = await svc.validate_connection(_connection())

    assert account_id == "123456789012"
    assert status is ConnectionStatus.CONNECTED
    assert err is None
    assert all(p.available for p in probes)


@pytest.mark.asyncio
async def test_missing_cost_explorer_is_degraded(monkeypatch) -> None:
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "123456789012"}
    ce = MagicMock()
    ce.get_cost_and_usage.side_effect = _client_error("AccessDeniedException")
    session = _session_factory(_all_clients(sts, ce))

    monkeypatch.setattr(
        svc, "get_credential_provider", lambda *a, **k: MagicMock(get_session=lambda **kw: session)
    )

    account_id, probes, status, err = await svc.validate_connection(_connection())

    assert account_id == "123456789012"
    assert status is ConnectionStatus.DEGRADED
    ce_probe = next(p for p in probes if p.capability == "cost_explorer")
    assert ce_probe.available is False
    assert ce_probe.detail == "AccessDeniedException"


@pytest.mark.asyncio
async def test_bad_credentials_is_error_and_skips_other_probes(monkeypatch) -> None:
    sts = MagicMock()
    sts.get_caller_identity.side_effect = _client_error("InvalidClientTokenId")
    ce = MagicMock()
    session = _session_factory(_all_clients(sts, ce))

    monkeypatch.setattr(
        svc, "get_credential_provider", lambda *a, **k: MagicMock(get_session=lambda **kw: session)
    )

    account_id, probes, status, err = await svc.validate_connection(_connection())

    assert account_id is None
    assert status is ConnectionStatus.ERROR
    # Only the STS probe runs when credentials fail.
    assert [p.capability for p in probes] == ["sts"]
    ce.get_cost_and_usage.assert_not_called()
