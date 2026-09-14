"""AWS write-action executor (Phase 8: stop EC2 instance only).

Uses the same `AwsCredentialProvider` abstraction as read paths, so switching
to a dedicated AssumeRole *write* role later requires no change here — only a
different credential provider/connection auth mode. No credentials are stored
in the app or database; they come from the provider at call time.

Success is reported ONLY when AWS confirms the state transition. Any exception
or a non-confirming response is a failure.

Required IAM (separate write policy, see docs/iam/write-policy.json):
    ec2:StopInstances
"""
from __future__ import annotations

from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError

from app.providers.aws.credentials import get_credential_provider


@dataclass(frozen=True)
class ActionOutcome:
    confirmed: bool
    aws_api: str
    detail: str
    raw: dict


class Ec2ActionExecutor:
    """Executes ec2:StopInstances. Injectable session factory for testing."""

    def __init__(self, session_factory=None) -> None:
        # session_factory(region) -> boto3.Session. Defaults to the credential
        # abstraction; tests inject a mock so no real AWS call is made.
        self._session_factory = session_factory

    def _session(self, connection, region: str):
        if self._session_factory is not None:
            return self._session_factory(region)
        provider = get_credential_provider(
            connection.auth_mode,
            profile_name=connection.profile_name,
            role_arn=connection.role_arn,
            region=region,
        )
        return provider.get_session(region=region)

    def stop_instance(self, connection, *, instance_id: str, region: str) -> ActionOutcome:
        session = self._session(connection, region)
        client = session.client("ec2", region_name=region)
        try:
            resp = client.stop_instances(InstanceIds=[instance_id])
        except (ClientError, BotoCoreError) as exc:
            return ActionOutcome(
                confirmed=False,
                aws_api="ec2:StopInstances",
                detail=f"AWS call failed: {exc.__class__.__name__}: {exc}",
                raw={},
            )

        # Confirm AWS actually transitioned the instance.
        stopping = resp.get("StoppingInstances", [])
        match = next(
            (s for s in stopping if s.get("InstanceId") == instance_id), None
        )
        current = (match or {}).get("CurrentState", {}).get("Name")
        if match and current in ("stopping", "stopped"):
            return ActionOutcome(
                confirmed=True,
                aws_api="ec2:StopInstances",
                detail=f"AWS confirmed transition to '{current}'",
                raw=resp if isinstance(resp, dict) else {},
            )

        return ActionOutcome(
            confirmed=False,
            aws_api="ec2:StopInstances",
            detail="AWS did not confirm the stop transition",
            raw=resp if isinstance(resp, dict) else {},
        )
