"""Unit tests for the AWS credential provider abstraction."""
from __future__ import annotations

import pytest

from app.providers.aws.credentials import (
    AssumeRoleCredentialProvider,
    AuthMode,
    AwsCredentialProvider,
    LocalProfileCredentialProvider,
    get_credential_provider,
)


def test_factory_returns_local_profile_provider() -> None:
    provider = get_credential_provider(AuthMode.LOCAL_PROFILE, profile_name="dev")
    assert isinstance(provider, LocalProfileCredentialProvider)
    assert isinstance(provider, AwsCredentialProvider)


def test_factory_returns_assume_role_provider() -> None:
    provider = get_credential_provider(
        AuthMode.ASSUME_ROLE, role_arn="arn:aws:iam::123456789012:role/Reader"
    )
    assert isinstance(provider, AssumeRoleCredentialProvider)


def test_factory_assume_role_requires_arn() -> None:
    with pytest.raises(ValueError):
        get_credential_provider(AuthMode.ASSUME_ROLE)


def test_factory_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        get_credential_provider("SOMETHING_ELSE")


def test_local_profile_builds_session_with_region() -> None:
    provider = LocalProfileCredentialProvider(profile_name=None, region="eu-west-1")
    session = provider.get_session()
    assert session.region_name == "eu-west-1"


def test_assume_role_calls_sts_with_external_id() -> None:
    from unittest.mock import MagicMock, patch

    sts = MagicMock()
    sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIA",
            "SecretAccessKey": "s",
            "SessionToken": "t",
        }
    }
    base = MagicMock()
    base.client.return_value = sts

    provider = AssumeRoleCredentialProvider(
        role_arn="arn:aws:iam::123:role/x", external_id="ccc-1", region="us-east-1"
    )
    with patch.object(provider, "_base_session", return_value=base):
        session = provider.get_session()
    assert session is not None
    _, kwargs = sts.assume_role.call_args
    assert kwargs["ExternalId"] == "ccc-1"
