"""Tests for cross-account AssumeRole: provider, External ID, validation errors.

All AWS calls are mocked. No real STS/AssumeRole is performed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.external_id import derive_external_id
from app.db.models.aws_connection import AwsConnection, ConnectionAuthMode
from app.providers.aws.credentials import (
    AssumeRoleCredentialProvider,
    AssumeRoleError,
    get_credential_provider,
)
from app.services import aws_connection as svc

# --- External ID derivation ---


def test_external_id_is_stable_and_scoped() -> None:
    a = derive_external_id("tenant-1", "conn-1")
    b = derive_external_id("tenant-1", "conn-1")
    assert a == b and a.startswith("ccc-")
    # Different tenant or connection -> different id.
    assert derive_external_id("tenant-2", "conn-1") != a
    assert derive_external_id("tenant-1", "conn-2") != a


# --- Factory wiring ---


def test_factory_builds_assume_role_provider_with_external_id() -> None:
    provider = get_credential_provider(
        ConnectionAuthMode.ASSUME_ROLE,
        role_arn="arn:aws:iam::123456789012:role/CloudCostControlReadOnly",
        external_id="ccc-abc",
        region="us-east-1",
    )
    assert isinstance(provider, AssumeRoleCredentialProvider)


def test_factory_requires_role_arn_for_assume_role() -> None:
    with pytest.raises(ValueError):
        get_credential_provider(ConnectionAuthMode.ASSUME_ROLE)


# --- AssumeRole provider (mocked STS) ---


def _provider() -> AssumeRoleCredentialProvider:
    return AssumeRoleCredentialProvider(
        role_arn="arn:aws:iam::123456789012:role/CloudCostControlReadOnly",
        external_id="ccc-abc",
        region="us-east-1",
    )


def test_assume_role_success_returns_temp_session() -> None:
    sts = MagicMock()
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIA...",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
        }
    }
    base = MagicMock()
    base.client.return_value = sts

    p = _provider()
    with patch.object(p, "_base_session", return_value=base):
        session = p.get_session()
    # A session was produced from the temporary credentials.
    assert session is not None
    # ExternalId was passed through.
    _, kwargs = sts.assume_role.call_args
    assert kwargs["ExternalId"] == "ccc-abc"
    assert kwargs["RoleArn"].endswith("CloudCostControlReadOnly")


def test_assume_role_access_denied_raises_typed_error() -> None:
    sts = MagicMock()
    sts.assume_role.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "AssumeRole"
    )
    base = MagicMock()
    base.client.return_value = sts

    # Unique role arn avoids the module-level session cache from other tests.
    p = AssumeRoleCredentialProvider(
        role_arn="arn:aws:iam::999:role/Denied", external_id="x", region="us-east-1"
    )
    with patch.object(p, "_base_session", return_value=base):
        with pytest.raises(AssumeRoleError) as exc:
            p.get_session()
    assert exc.value.code == "AccessDenied"


# --- Friendly error mapping ---


def test_friendly_error_access_denied_mentions_trust_and_external_id() -> None:
    msg = svc.friendly_error("AccessDenied", [])
    assert "trust relationship" in msg.lower()
    assert "external id" in msg.lower()


def test_friendly_error_role_not_found() -> None:
    msg = svc.friendly_error("NoSuchEntity", [])
    assert "could not be found" in msg.lower()


def test_friendly_error_missing_cost_explorer() -> None:
    probes = [
        svc.CapabilityProbe("sts", True),
        svc.CapabilityProbe("cost_explorer", False, "AccessDenied"),
    ]
    msg = svc.friendly_error(None, probes)
    assert "cost data" in msg.lower()


def test_friendly_error_none_when_all_ok() -> None:
    probes = [svc.CapabilityProbe("sts", True), svc.CapabilityProbe("cost_explorer", True)]
    assert svc.friendly_error(None, probes) is None


# --- Validation flow with mocked probes ---


@pytest.mark.asyncio
async def test_validate_assume_role_failure_is_error_status(monkeypatch) -> None:
    conn = AwsConnection(
        tenant_id="t", auth_mode=ConnectionAuthMode.ASSUME_ROLE,
        role_arn="arn:aws:iam::123:role/X", external_id="ccc-x", region="us-east-1",
    )
    monkeypatch.setattr(
        svc, "_run_probes", lambda c: (None, [], "AccessDenied")
    )
    account_id, probes, status, err = await svc.validate_connection(conn)
    assert account_id is None
    assert err == "AccessDenied"
    assert status.value == "ERROR"


@pytest.mark.asyncio
async def test_validate_degraded_when_some_capabilities_missing(monkeypatch) -> None:
    conn = AwsConnection(
        tenant_id="t", auth_mode=ConnectionAuthMode.ASSUME_ROLE,
        role_arn="arn:aws:iam::123:role/X", external_id="ccc-x", region="us-east-1",
    )
    probes = [
        svc.CapabilityProbe("sts", True),
        svc.CapabilityProbe("cost_explorer", True),
        svc.CapabilityProbe("ec2", False, "AccessDenied"),
    ]
    monkeypatch.setattr(svc, "_run_probes", lambda c: ("123456789012", probes, None))
    account_id, _probes, status, err = await svc.validate_connection(conn)
    assert account_id == "123456789012"
    assert status.value == "DEGRADED"
    assert err is None
