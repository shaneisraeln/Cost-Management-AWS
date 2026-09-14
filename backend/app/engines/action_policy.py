"""Action policy engine (pure): all safety checks before any AWS write.

Every check must pass or the action is DENIED. Production is protected by
default: unless we can positively confirm a resource is non-production, it is
blocked. This engine performs no I/O; the caller supplies the resource facts
and re-runs it both at preview and immediately before execution
(Requirements 16.3, 16.4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models.action_request import ActionType
from app.db.models.user import UserRole

ALLOWED_ACTIONS = {ActionType.STOP_INSTANCE}
ALLOWED_ROLES = {UserRole.OWNER, UserRole.ADMIN}

# Tag keys/values that signal production or explicit protection.
PROTECTED_TAG_KEYS = {"protected", "do-not-stop", "do_not_stop", "donotstop"}
ENV_TAG_KEYS = {"environment", "env", "stage"}
PRODUCTION_VALUES = {"prod", "production", "prd", "live"}
NONPROD_VALUES = {"dev", "development", "test", "testing", "staging", "sandbox", "qa"}


@dataclass(frozen=True)
class PolicyInputs:
    action_type: ActionType
    role: UserRole
    resource_exists: bool
    resource_service: str | None       # must be "EC2"
    current_state: str | None          # must be "running"
    tags: dict[str, str] = field(default_factory=dict)
    approved: bool = False             # explicit confirmation present


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reasons: list[str]                 # why blocked (empty when allowed)
    checks: list[dict]                 # per-check result for transparency


def _is_protected(tags: dict[str, str]) -> tuple[bool, str]:
    lowered = {k.lower(): (v or "").lower() for k, v in tags.items()}

    # Explicit protection tag.
    for key in PROTECTED_TAG_KEYS:
        if key in lowered and lowered[key] not in ("false", "no", "0", ""):
            return True, f"explicit protection tag '{key}'"

    # Environment tag says production.
    env_value = None
    for key in ENV_TAG_KEYS:
        if key in lowered and lowered[key]:
            env_value = lowered[key]
            break

    if env_value is None:
        # Production-by-default: unknown environment is treated as protected.
        return True, "environment unknown (protected by default)"
    if env_value in PRODUCTION_VALUES:
        return True, f"environment '{env_value}' is production"
    if env_value in NONPROD_VALUES:
        return False, f"environment '{env_value}' is non-production"
    # Unrecognized environment value -> protected by default.
    return True, f"environment '{env_value}' not recognized as non-production"


def evaluate(inputs: PolicyInputs) -> PolicyDecision:
    checks: list[dict] = []
    reasons: list[str] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})
        if not ok:
            reasons.append(detail)

    # 1. Authorization.
    record(
        "authorization",
        inputs.role in ALLOWED_ROLES,
        "requires OWNER or ADMIN" if inputs.role not in ALLOWED_ROLES else "role permitted",
    )

    # 2. Action allowlist.
    record(
        "action_allowed",
        inputs.action_type in ALLOWED_ACTIONS,
        f"action {inputs.action_type} not permitted"
        if inputs.action_type not in ALLOWED_ACTIONS
        else "action permitted",
    )

    # 3. Resource exists and is an EC2 instance.
    record(
        "resource_exists",
        inputs.resource_exists,
        "resource not found" if not inputs.resource_exists else "resource found",
    )
    record(
        "is_ec2",
        inputs.resource_service == "EC2",
        f"only EC2 supported (got {inputs.resource_service})"
        if inputs.resource_service != "EC2"
        else "resource is EC2",
    )

    # 4. Production protection (default-deny).
    protected, prot_detail = _is_protected(inputs.tags)
    record("not_protected", not protected, prot_detail)

    # 5. Current-state precondition: must be running.
    record(
        "is_running",
        inputs.current_state == "running",
        f"instance state is '{inputs.current_state}', must be 'running'"
        if inputs.current_state != "running"
        else "instance is running",
    )

    # 6. Explicit approval.
    record(
        "approved",
        inputs.approved,
        "explicit confirmation required" if not inputs.approved else "confirmed",
    )

    allowed = all(c["passed"] for c in checks)
    return PolicyDecision(allowed=allowed, reasons=reasons if not allowed else [], checks=checks)
