"""AWS credential provider abstraction.

Consumers always receive a ready-to-use boto3 Session and never know how the
credentials were obtained. This lets us start with a local IAM profile and
later swap to cross-account AssumeRole without touching business logic
(Requirements 1.2, 1.3, 1.4, 22.2).
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings


class AuthMode(str, Enum):
    """How the platform obtains AWS credentials for a connection."""

    LOCAL_PROFILE = "LOCAL_PROFILE"
    ASSUME_ROLE = "ASSUME_ROLE"


@runtime_checkable
class AwsCredentialProvider(Protocol):
    """Returns a boto3 Session usable to call AWS APIs for a connection."""

    def get_session(self, region: str | None = None) -> boto3.Session: ...


class LocalProfileCredentialProvider:
    """Uses the local credential profile via the boto3 default chain.

    This is the development/prototype mode. It relies on credentials
    configured on the host (``aws configure`` / environment / SSO) and never
    stores long-lived customer secret keys in the product.
    """

    def __init__(self, profile_name: str | None = None, region: str | None = None) -> None:
        settings = get_settings()
        self._profile_name = profile_name or settings.aws_profile or None
        self._region = region or settings.aws_region

    def get_session(self, region: str | None = None) -> boto3.Session:
        return boto3.Session(
            profile_name=self._profile_name,
            region_name=region or self._region,
        )


class AssumeRoleError(Exception):
    """Raised when the application cannot assume the customer role.

    Carries the AWS error code so callers can produce a friendly message.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Small in-process cache of assumed-role sessions, keyed by (role_arn,
# external_id, region). Temporary credentials only; never persisted.
_assume_cache: dict[tuple[str, str | None, str], tuple[float, boto3.Session]] = {}
_ASSUME_TTL_SECONDS = 1800  # re-assume well within the 1h STS default


class AssumeRoleCredentialProvider:
    """Assumes a customer-provided IAM role for temporary credentials.

    This is the production model. The application's own principal (instance/
    task role in production, or a named app profile in local dev) calls STS
    ``AssumeRole`` on the customer's role, passing the per-connection External
    ID. Only temporary credentials are used; nothing is stored.
    """

    def __init__(
        self,
        role_arn: str,
        *,
        external_id: str | None = None,
        region: str | None = None,
    ) -> None:
        settings = get_settings()
        self._role_arn = role_arn
        self._external_id = external_id
        self._region = region or settings.aws_region

    def _base_session(self) -> boto3.Session:
        """Credentials the application itself runs as (never the customer's)."""
        settings = get_settings()
        # In local dev an app profile may be configured; in production the
        # default chain resolves the instance/task role.
        profile = settings.app_aws_profile or None
        return boto3.Session(profile_name=profile, region_name=self._region)

    def get_session(self, region: str | None = None) -> boto3.Session:
        import time

        region = region or self._region
        cache_key = (self._role_arn, self._external_id, region)
        cached = _assume_cache.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]

        sts = self._base_session().client("sts")
        kwargs: dict = {
            "RoleArn": self._role_arn,
            "RoleSessionName": "cloud-cost-control",
            "DurationSeconds": 3600,
        }
        if self._external_id:
            kwargs["ExternalId"] = self._external_id

        try:
            resp = sts.assume_role(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "AssumeRoleError")
            raise AssumeRoleError(code, str(exc)) from exc
        except BotoCoreError as exc:
            raise AssumeRoleError("BotoCoreError", str(exc)) from exc

        creds = resp["Credentials"]
        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=region,
        )
        _assume_cache[cache_key] = (time.time() + _ASSUME_TTL_SECONDS, session)
        return session


def get_credential_provider(
    auth_mode: AuthMode | str,
    *,
    profile_name: str | None = None,
    role_arn: str | None = None,
    external_id: str | None = None,
    region: str | None = None,
) -> AwsCredentialProvider:
    """Factory selecting a credential provider based on the connection mode."""
    mode = AuthMode(auth_mode)
    if mode is AuthMode.LOCAL_PROFILE:
        return LocalProfileCredentialProvider(profile_name=profile_name, region=region)
    if mode is AuthMode.ASSUME_ROLE:
        if not role_arn:
            raise ValueError("role_arn is required for ASSUME_ROLE mode")
        return AssumeRoleCredentialProvider(
            role_arn=role_arn, external_id=external_id, region=region
        )
    raise ValueError(f"Unsupported auth mode: {auth_mode}")
