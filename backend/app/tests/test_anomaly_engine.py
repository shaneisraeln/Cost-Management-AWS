"""Unit tests for deterministic anomaly detection and templated explanation."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.db.models.cost_change import ChangeClassification
from app.engines.anomaly import (
    DailyPoint,
    DetectionConfig,
    classify_change,
    detect_service_anomalies,
)
from app.providers.llm.base import ExplanationFacts
from app.providers.llm.templated import TemplatedLlmProvider


def _series(values: list[str]) -> list[DailyPoint]:
    start = date(2026, 9, 1)
    return [
        DailyPoint(day=start + timedelta(days=i), amount=Decimal(v))
        for i, v in enumerate(values)
    ]


def test_flat_series_has_no_anomaly() -> None:
    series = _series(["10", "10", "10", "10", "10", "10", "10"])
    assert detect_service_anomalies("EC2", series) == []


def test_clear_spike_is_detected() -> None:
    # Steady ~10/day, then a jump to 100.
    series = _series(["10", "10", "10", "10", "10", "10", "100"])
    anomalies = detect_service_anomalies("EC2", series)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.observed == Decimal("100")
    assert a.baseline < Decimal("20")
    assert a.confidence >= 0.5
    assert a.algorithm in ("zscore", "multiplier")


def test_small_jump_below_min_absolute_is_ignored() -> None:
    # Below the default min_absolute of 1.0 currency unit.
    series = _series(["0.10", "0.10", "0.10", "0.10", "0.10", "0.10", "0.50"])
    assert detect_service_anomalies("EC2", series) == []


def test_insufficient_history_is_skipped() -> None:
    series = _series(["10", "100"])  # not enough baseline
    assert detect_service_anomalies("EC2", series) == []


def test_multiplier_threshold_configurable() -> None:
    series = _series(["10", "10", "10", "10", "25"])
    strict = detect_service_anomalies(
        "EC2", series, DetectionConfig(multiplier_threshold=3.0, z_threshold=99)
    )
    loose = detect_service_anomalies(
        "EC2", series, DetectionConfig(multiplier_threshold=2.0, z_threshold=99)
    )
    assert strict == []          # 2.5x < 3.0x
    assert len(loose) == 1       # 2.5x > 2.0x


def test_classify_change_uses_evidence_not_causality() -> None:
    eng, conf_eng = classify_change(
        difference=Decimal("50"), has_recent_creation_event=True, unusual_identity=False
    )
    assert eng is ChangeClassification.ENGINEERING_CHANGE and conf_eng > 0

    grow, _ = classify_change(
        difference=Decimal("50"), has_recent_creation_event=False, unusual_identity=False
    )
    assert grow is ChangeClassification.GROWTH

    sus, _ = classify_change(
        difference=Decimal("50"), has_recent_creation_event=False, unusual_identity=True
    )
    assert sus is ChangeClassification.SUSPICIOUS


def test_templated_explanation_is_deterministic_and_labeled() -> None:
    facts = ExplanationFacts(
        subject="EC2 cost change on 2026-09-10",
        baseline="10.00",
        observed="100.00",
        difference="90.00",
        classification="GROWTH",
        confidence=0.4,
        evidence=[],
    )
    out = TemplatedLlmProvider().explain(facts)
    assert out.generated_by == "template"
    assert "100.00" in out.text
    assert "GROWTH" in out.text
    assert "No correlated activity" in out.text
