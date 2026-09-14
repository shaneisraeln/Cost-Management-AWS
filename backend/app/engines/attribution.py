"""Evidence-based attribution engine (pure).

Evaluates ownership evidence in a configurable precedence with configurable
weights and produces an AttributionResult. Core rules:

- Never invent an owner. No evidence -> UNKNOWN.
- An explicit manual mapping always wins (highest trust).
- A single clear owner -> ATTRIBUTED, confidence from combined evidence weight.
- Multiple distinct owners with comparable support -> DISPUTED.
- An explicit "shared"/"team" signal, or several weak co-owners -> SHARED.

Confidence is a bounded combination of matched evidence weights, capped at 1.0.
Every result lists its evidence so we can later explain the decision.
(Requirements 4.1-4.5, 6.1 attribution hierarchy, P3 never invent attribution.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models.attribution import AttributionStatus

# Default evidence weights (configurable via AttributionConfig).
DEFAULT_WEIGHTS: dict[str, float] = {
    "manual_mapping": 1.0,
    "owner_tag": 0.6,
    "project_tag": 0.2,
    "environment_tag": 0.1,
    "cloudtrail_creator": 0.35,
}

# Tag keys we recognize (case-insensitive), in priority order.
OWNER_TAG_KEYS = ["owner", "owner_email", "created_by", "team_owner"]
PROJECT_TAG_KEYS = ["project", "app", "application", "service_name"]
ENVIRONMENT_TAG_KEYS = ["environment", "env", "stage"]
# Values that signal shared/team ownership rather than a single person.
SHARED_OWNER_VALUES = {"shared", "team", "platform", "shared-services"}


@dataclass(frozen=True)
class AttributionConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    # Below this combined confidence we do not claim a single owner.
    attributed_threshold: float = 0.5


@dataclass(frozen=True)
class Evidence:
    type: str
    weight: float
    detail: str


@dataclass(frozen=True)
class AttributionResult:
    status: AttributionStatus
    owner_label: str | None
    project: str | None
    environment: str | None
    confidence: float
    evidence: list[Evidence]
    source: str

    def evidence_as_dicts(self) -> list[dict]:
        return [{"type": e.type, "weight": e.weight, "detail": e.detail} for e in self.evidence]


@dataclass(frozen=True)
class AttributionInputs:
    """Everything the engine needs for one resource (no I/O in the engine)."""

    tags: dict[str, str]
    # principal id/arn of whoever created the resource, if known from CloudTrail
    creator_principal: str | None = None
    # An explicit manual mapping, if one exists.
    manual_owner: str | None = None
    manual_project: str | None = None
    manual_environment: str | None = None


def _find_tag(tags: dict[str, str], keys: list[str]) -> tuple[str, str] | None:
    lowered = {k.lower(): (k, v) for k, v in tags.items()}
    for key in keys:
        if key in lowered:
            k, v = lowered[key]
            if v:
                return k, v
    return None


def attribute(
    inputs: AttributionInputs, config: AttributionConfig | None = None
) -> AttributionResult:
    config = config or AttributionConfig()
    w = config.weights
    evidence: list[Evidence] = []

    # 1. Manual mapping always wins.
    if inputs.manual_owner or inputs.manual_project or inputs.manual_environment:
        ev = [Evidence("manual_mapping", w["manual_mapping"], "explicit manual mapping")]
        return AttributionResult(
            status=AttributionStatus.ATTRIBUTED,
            owner_label=inputs.manual_owner,
            project=inputs.manual_project,
            environment=inputs.manual_environment,
            confidence=1.0,
            evidence=ev,
            source="manual_mapping",
        )

    # Resolve project / environment from tags (independent of owner).
    project = None
    project_tag = _find_tag(inputs.tags, PROJECT_TAG_KEYS)
    if project_tag:
        project = project_tag[1]
        evidence.append(
            Evidence("project_tag", w["project_tag"], f"{project_tag[0]}={project_tag[1]}")
        )

    environment = None
    env_tag = _find_tag(inputs.tags, ENVIRONMENT_TAG_KEYS)
    if env_tag:
        environment = env_tag[1]
        evidence.append(
            Evidence("environment_tag", w["environment_tag"], f"{env_tag[0]}={env_tag[1]}")
        )

    # Owner candidates with their supporting evidence weight.
    owner_candidates: dict[str, float] = {}
    owner_tag = _find_tag(inputs.tags, OWNER_TAG_KEYS)
    if owner_tag:
        owner_val = owner_tag[1]
        evidence.append(Evidence("owner_tag", w["owner_tag"], f"{owner_tag[0]}={owner_val}"))
        if owner_val.lower() in SHARED_OWNER_VALUES:
            # Explicit shared signal.
            return AttributionResult(
                status=AttributionStatus.SHARED,
                owner_label=owner_val,
                project=project,
                environment=environment,
                confidence=min(1.0, w["owner_tag"]),
                evidence=evidence,
                source="owner_tag",
            )
        owner_candidates[owner_val] = owner_candidates.get(owner_val, 0.0) + w["owner_tag"]

    if inputs.creator_principal:
        evidence.append(
            Evidence(
                "cloudtrail_creator",
                w["cloudtrail_creator"],
                f"created by {inputs.creator_principal}",
            )
        )
        owner_candidates[inputs.creator_principal] = (
            owner_candidates.get(inputs.creator_principal, 0.0) + w["cloudtrail_creator"]
        )

    # No owner evidence at all.
    if not owner_candidates:
        # We may still know project/environment; that's contextual, not ownership.
        return AttributionResult(
            status=AttributionStatus.UNKNOWN,
            owner_label=None,
            project=project,
            environment=environment,
            confidence=0.0,
            evidence=evidence,
            source="none",
        )

    # Pick the strongest candidate.
    ranked = sorted(owner_candidates.items(), key=lambda kv: kv[1], reverse=True)
    top_owner, top_score = ranked[0]

    # Disputed: two distinct owners with comparable, meaningful support.
    if len(ranked) > 1:
        second_score = ranked[1][1]
        if second_score >= top_score * 0.8 and second_score >= 0.3:
            return AttributionResult(
                status=AttributionStatus.DISPUTED,
                owner_label=None,
                project=project,
                environment=environment,
                confidence=round(min(1.0, top_score), 3),
                evidence=evidence,
                source="conflicting_evidence",
            )

    confidence = round(min(1.0, top_score), 3)
    status = (
        AttributionStatus.ATTRIBUTED
        if confidence >= config.attributed_threshold
        else AttributionStatus.SHARED
    )
    return AttributionResult(
        status=status,
        owner_label=top_owner,
        project=project,
        environment=environment,
        confidence=confidence,
        evidence=evidence,
        source="tag_and_activity",
    )
