"""Deterministic cost-change and anomaly detection (pure, no ML).

Given a per-service daily cost series, detect days whose spend is far above a
rolling baseline using two transparent rules:

- z-score:   (observed - mean) / stddev  >  z_threshold
- multiplier: observed > mean * multiplier_threshold

Both are computed over a trailing window (default 7 days). We deliberately
avoid ML: the rules are explainable and reproducible (Requirements 8.3, 8.4).

Classification of a detected change is deterministic and evidence-aware but
never asserts causality on its own — it only labels based on available signals
(Requirement 8.2, 8.7 timeline-is-evidence).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.db.models.anomaly import AnomalySeverity
from app.db.models.cost_change import ChangeClassification


@dataclass(frozen=True)
class DetectionConfig:
    window_days: int = 7
    z_threshold: float = 3.0
    multiplier_threshold: float = 2.0
    # Ignore noise: require an absolute jump of at least this many currency units.
    min_absolute: Decimal = Decimal("1.0")
    # Minimum baseline days needed before we trust the statistics.
    min_history: int = 3


@dataclass(frozen=True)
class DailyPoint:
    day: date
    amount: Decimal


@dataclass(frozen=True)
class DetectedAnomaly:
    service: str | None
    day: date
    baseline: Decimal
    observed: Decimal
    difference: Decimal
    algorithm: str
    severity: AnomalySeverity
    confidence: float
    evidence: list[dict] = field(default_factory=list)


def _severity(ratio: float) -> AnomalySeverity:
    if ratio >= 5:
        return AnomalySeverity.HIGH
    if ratio >= 3:
        return AnomalySeverity.MEDIUM
    return AnomalySeverity.LOW


def detect_service_anomalies(
    service: str | None,
    series: list[DailyPoint],
    config: DetectionConfig | None = None,
) -> list[DetectedAnomaly]:
    """Detect anomalous days in a single service's daily series."""
    config = config or DetectionConfig()
    series = sorted(series, key=lambda p: p.day)
    anomalies: list[DetectedAnomaly] = []

    for i, point in enumerate(series):
        window = series[max(0, i - config.window_days) : i]
        if len(window) < config.min_history:
            continue

        amounts = [float(p.amount) for p in window]
        mean = statistics.fmean(amounts)
        observed = float(point.amount)
        difference = observed - mean

        if Decimal(str(difference)) < config.min_absolute:
            continue

        stdev = statistics.pstdev(amounts) if len(amounts) > 1 else 0.0
        z = (observed - mean) / stdev if stdev > 0 else 0.0
        multiplier = observed / mean if mean > 0 else 0.0

        triggered_by = None
        if stdev > 0 and z > config.z_threshold:
            triggered_by = "zscore"
            ratio = z / config.z_threshold
        elif mean > 0 and multiplier > config.multiplier_threshold:
            triggered_by = "multiplier"
            ratio = multiplier / config.multiplier_threshold
        if triggered_by is None:
            continue

        # Confidence scales with how far past the threshold we are (capped).
        confidence = round(min(1.0, 0.5 + 0.15 * (ratio - 1) + 0.1), 3)
        confidence = max(0.5, min(1.0, confidence))

        anomalies.append(
            DetectedAnomaly(
                service=service,
                day=point.day,
                baseline=Decimal(str(round(mean, 6))),
                observed=Decimal(str(observed)),
                difference=Decimal(str(round(difference, 6))),
                algorithm=triggered_by,
                severity=_severity(ratio + 1),
                confidence=confidence,
                evidence=[
                    {"type": "baseline_window_days", "detail": str(len(window))},
                    {"type": "mean", "detail": f"{mean:.6f}"},
                    {"type": "stddev", "detail": f"{stdev:.6f}"},
                    {
                        "type": triggered_by,
                        "detail": (
                            f"{z:.2f}" if triggered_by == "zscore" else f"{multiplier:.2f}x"
                        ),
                    },
                ],
            )
        )

    return anomalies


def classify_change(
    *,
    difference: Decimal,
    has_recent_creation_event: bool,
    unusual_identity: bool,
) -> tuple[ChangeClassification, float]:
    """Deterministically classify a cost increase using available signals.

    - A resource-creation event around the change -> ENGINEERING_CHANGE.
    - An unusual identity/activity signal -> SUSPICIOUS.
    - Otherwise -> GROWTH (usage rose) with low confidence, or UNKNOWN if we
      genuinely have nothing.
    Confidence reflects supporting evidence, not proven causality.
    """
    if unusual_identity:
        return ChangeClassification.SUSPICIOUS, 0.55
    if has_recent_creation_event:
        return ChangeClassification.ENGINEERING_CHANGE, 0.7
    if difference > 0:
        return ChangeClassification.GROWTH, 0.4
    return ChangeClassification.UNKNOWN, 0.2
