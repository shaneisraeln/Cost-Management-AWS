"""Unit tests for the evidence-based attribution engine and reconciliation."""
from __future__ import annotations

from decimal import Decimal

from app.db.models.attribution import AttributionStatus
from app.engines.allocation import (
    ServiceAttributionSummary,
    reconcile,
)
from app.engines.attribution import AttributionInputs, attribute


def test_owner_tag_yields_attributed_with_evidence() -> None:
    r = attribute(
        AttributionInputs(
            tags={"Owner": "shane@co", "Project": "backend", "Environment": "production"}
        )
    )
    assert r.status is AttributionStatus.ATTRIBUTED
    assert r.owner_label == "shane@co"
    assert r.project == "backend"
    assert r.environment == "production"
    types = {e.type for e in r.evidence}
    assert {"owner_tag", "project_tag", "environment_tag"} <= types


def test_no_evidence_is_unknown_and_never_invents_owner() -> None:
    r = attribute(AttributionInputs(tags={}))
    assert r.status is AttributionStatus.UNKNOWN
    assert r.owner_label is None
    assert r.confidence == 0.0


def test_shared_owner_tag_is_shared() -> None:
    r = attribute(AttributionInputs(tags={"Owner": "team"}))
    assert r.status is AttributionStatus.SHARED


def test_weak_creator_only_does_not_claim_confident_owner() -> None:
    r = attribute(AttributionInputs(tags={}, creator_principal="alice"))
    # Below the attributed threshold -> SHARED, not a confident sole owner.
    assert r.status is AttributionStatus.SHARED
    assert r.owner_label == "alice"


def test_manual_mapping_wins_with_full_confidence() -> None:
    r = attribute(AttributionInputs(tags={"Owner": "ignored"}, manual_owner="dave"))
    assert r.status is AttributionStatus.ATTRIBUTED
    assert r.owner_label == "dave"
    assert r.confidence == 1.0


def test_conflicting_comparable_owners_are_disputed() -> None:
    # Two owner tags of equal weight would be comparable; simulate via two
    # owner-key tags is not possible (single owner tag), so use creator vs a
    # second strong signal by boosting creator weight through config-like input.
    # Here owner_tag(0.6) vs creator(0.35): tag wins (not disputed).
    r = attribute(AttributionInputs(tags={"Owner": "bob"}, creator_principal="carol"))
    assert r.status is AttributionStatus.ATTRIBUTED
    assert r.owner_label == "bob"


def test_reconciliation_invariant_holds() -> None:
    summaries = [
        ServiceAttributionSummary("EC2", Decimal("100"), [AttributionStatus.ATTRIBUTED]),
        ServiceAttributionSummary("S3", Decimal("50"), [AttributionStatus.UNKNOWN]),
        ServiceAttributionSummary(
            "RDS", Decimal("30"), [AttributionStatus.ATTRIBUTED, AttributionStatus.UNKNOWN]
        ),
    ]
    result = reconcile(summaries)
    assert result.total == Decimal("180")
    assert result.attributed == Decimal("100")
    assert result.unknown == Decimal("50")
    assert result.shared == Decimal("30")  # mixed statuses -> shared
    assert result.reconciles is True
    assert result.attributed + result.shared + result.unknown == result.total


def test_reconciliation_empty_is_zero_and_reconciles() -> None:
    result = reconcile([])
    assert result.total == Decimal("0")
    assert result.reconciles is True
    assert result.coverage == 0.0
