"""Investigation schemas: anomalies, cost changes, timeline, explanation."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.db.models.anomaly import AnomalySeverity, AnomalyStatus
from app.db.models.cost_change import ChangeClassification


class AnomalyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service: str | None
    detected_for: date
    severity: AnomalySeverity
    baseline: Decimal
    observed: Decimal
    difference: Decimal
    algorithm: str
    confidence: float
    status: AnomalyStatus
    evidence: list
    created_at: datetime


class CostChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    period_date: date
    service: str | None
    baseline_cost: Decimal
    observed_cost: Decimal
    absolute_change: Decimal
    percentage_change: float | None
    classification: ChangeClassification
    confidence: float
    evidence: list
    created_at: datetime


class DetectionResult(BaseModel):
    anomalies_created: int
    cost_changes_created: int
    services_analyzed: int


class TimelineItem(BaseModel):
    kind: str
    timestamp: str | None
    title: str
    detail: dict


class ExplanationRead(BaseModel):
    text: str
    generated_by: str  # "ai" | "template"
