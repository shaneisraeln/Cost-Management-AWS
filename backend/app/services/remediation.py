"""Remediation service: preview and execute the single supported write action.

Flow (execute):
  create ActionRequest(PENDING)
    -> re-run ActionPolicyEngine (deny -> BLOCKED + audit)
    -> live DescribeInstances re-check (must still be running)
    -> Ec2ActionExecutor.stop_instance (the one write call)
    -> EXECUTED only on AWS confirmation, else FAILED
    -> AuditLog written on EVERY attempt

Nothing here runs automatically; it is only invoked by an explicit,
role-checked, confirmed user request.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext
from app.db.models.action_request import (
    ActionRequest,
    ActionStatus,
    ActionType,
)
from app.db.models.audit_log import AuditLog
from app.engines.action_policy import PolicyInputs, evaluate
from app.providers.aws.actions import Ec2ActionExecutor
from app.providers.aws.credentials import get_credential_provider
from app.repositories.aws_connection import AwsConnectionRepository
from app.repositories.resource import ResourceRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewResult:
    resource_id: str
    provider_resource_id: str | None
    service: str | None
    current_state: str | None
    proposed_action: str
    allowed: bool
    reasons: list[str]
    checks: list[dict]


async def _live_ec2_state(connection, provider_resource_id: str, region: str) -> str | None:
    """Read current EC2 state via DescribeInstances (read-only). Off the loop."""

    def _call():
        provider = get_credential_provider(
            connection.auth_mode,
            profile_name=connection.profile_name,
            role_arn=connection.role_arn,
            region=region,
        )
        session = provider.get_session(region=region)
        resp = session.client("ec2", region_name=region).describe_instances(
            InstanceIds=[provider_resource_id]
        )
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                if inst.get("InstanceId") == provider_resource_id:
                    return inst.get("State", {}).get("Name")
        return None

    try:
        return await asyncio.to_thread(_call)
    except Exception:  # noqa: BLE001 - treat as unknown; policy will refuse
        logger.exception("live ec2 state check failed")
        return None


async def preview_stop_instance(
    db: AsyncSession, ctx: TenantContext, resource_id: str
) -> PreviewResult | None:
    resource = await ResourceRepository(db, ctx.tenant_id).get(resource_id)
    if resource is None:
        return None

    decision = evaluate(
        PolicyInputs(
            action_type=ActionType.STOP_INSTANCE,
            role=ctx.role,
            resource_exists=True,
            resource_service=resource.service,
            current_state=resource.state,
            tags=resource.tags or {},
            approved=False,  # preview never counts as approval
        )
    )
    return PreviewResult(
        resource_id=resource.id,
        provider_resource_id=resource.provider_resource_id,
        service=resource.service,
        current_state=resource.state,
        proposed_action="STOP_INSTANCE",
        # Preview shows whether everything EXCEPT approval passes.
        allowed=all(c["passed"] for c in decision.checks if c["check"] != "approved"),
        reasons=[r for r in decision.reasons if "confirmation" not in r],
        checks=decision.checks,
    )


async def _audit(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    action: str,
    resource_id: str | None,
    aws_api: str | None,
    summary: str,
    result: str,
    detail: dict,
) -> None:
    db.add(
        AuditLog(
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action=action,
            resource_id=resource_id,
            aws_api=aws_api,
            request_summary=summary,
            result=result,
            detail=detail,
        )
    )


async def execute_stop_instance(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    resource_id: str,
    confirmed: bool,
    executor: Ec2ActionExecutor | None = None,
) -> ActionRequest:
    executor = executor or Ec2ActionExecutor()
    resource = await ResourceRepository(db, ctx.tenant_id).get(resource_id)

    action = ActionRequest(
        tenant_id=ctx.tenant_id,
        action_type=ActionType.STOP_INSTANCE,
        resource_id=resource_id,
        provider_resource_id=resource.provider_resource_id if resource else None,
        account_id=resource.account_id if resource else None,
        region=resource.region if resource else None,
        requested_by=ctx.user_id,
        status=ActionStatus.PENDING,
    )
    db.add(action)

    # Policy re-evaluation (defense in depth; also enforces confirmation).
    decision = evaluate(
        PolicyInputs(
            action_type=ActionType.STOP_INSTANCE,
            role=ctx.role,
            resource_exists=resource is not None,
            resource_service=resource.service if resource else None,
            current_state=resource.state if resource else None,
            tags=(resource.tags if resource else {}) or {},
            approved=confirmed,
        )
    )
    action.policy_result = {"allowed": decision.allowed, "checks": decision.checks}

    if not decision.allowed:
        action.status = ActionStatus.BLOCKED
        action.result = {"reasons": decision.reasons}
        await _audit(
            db, ctx, action="STOP_INSTANCE",
            resource_id=action.provider_resource_id, aws_api=None,
            summary=f"Blocked stop of {action.provider_resource_id}",
            result="BLOCKED", detail={"reasons": decision.reasons},
        )
        await db.commit()
        await db.refresh(action)
        return action

    # Live state re-check immediately before the write.
    connection = None
    if resource and resource.account_id:
        connection = await AwsConnectionRepository(db, ctx.tenant_id).get_by_account(
            resource.account_id
        )
    if connection is None:
        # Fall back to any connection for the tenant.
        conns = await AwsConnectionRepository(db, ctx.tenant_id).list()
        connection = conns[0] if conns else None

    if connection is None:
        action.status = ActionStatus.FAILED
        action.result = {"error": "no AWS connection available"}
        await _audit(
            db, ctx, action="STOP_INSTANCE",
            resource_id=action.provider_resource_id, aws_api=None,
            summary="No connection", result="FAILED",
            detail={"error": "no AWS connection"},
        )
        await db.commit()
        await db.refresh(action)
        return action

    region = resource.region or connection.region
    live_state = await _live_ec2_state(connection, resource.provider_resource_id, region)
    if live_state != "running":
        action.status = ActionStatus.BLOCKED
        action.result = {"error": f"instance not running (live state: {live_state})"}
        await _audit(
            db, ctx, action="STOP_INSTANCE",
            resource_id=action.provider_resource_id, aws_api="ec2:DescribeInstances",
            summary=f"Live state {live_state}", result="BLOCKED",
            detail={"live_state": live_state},
        )
        await db.commit()
        await db.refresh(action)
        return action

    # The single write call. Executed off the event loop.
    outcome = await asyncio.to_thread(
        executor.stop_instance,
        connection,
        instance_id=resource.provider_resource_id,
        region=region,
    )

    if outcome.confirmed:
        action.status = ActionStatus.EXECUTED
        action.result = {"detail": outcome.detail, "aws_api": outcome.aws_api}
        audit_result = "EXECUTED"
    else:
        action.status = ActionStatus.FAILED
        action.result = {"detail": outcome.detail, "aws_api": outcome.aws_api}
        audit_result = "FAILED"

    await _audit(
        db, ctx, action="STOP_INSTANCE",
        resource_id=action.provider_resource_id, aws_api=outcome.aws_api,
        summary=f"Stop {action.provider_resource_id} in {region}",
        result=audit_result, detail={"detail": outcome.detail},
    )
    await db.commit()
    await db.refresh(action)
    return action
