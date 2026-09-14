"""Bedrock intelligence schemas.

Cost and usage are kept as separate concerns. Any derived ratio (cost per
invocation, tokens per invocation) is flagged as OUR calculation, not an AWS
fact. Metrics AWS does not provide are represented as null (unavailable), never
zero.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class BedrockCostFacts(BaseModel):
    available: bool
    total_cost: Decimal
    currency: str
    source: str = "COST_EXPLORER"
    reason: str | None = None  # why unavailable, if applicable


class BedrockUsageFacts(BaseModel):
    available: bool
    source: str = "CLOUDWATCH"
    # None means AWS did not provide the metric (unavailable), not zero.
    invocations: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    metrics_present: list[str] = []
    reason: str | None = None


class ModelUsage(BaseModel):
    model_id: str
    invocations: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class EfficiencyFacts(BaseModel):
    """Ratios we compute from separate cost + usage facts. Always our calc."""

    is_calculated: bool = True
    cost_per_invocation: Decimal | None = None
    tokens_per_invocation: Decimal | None = None
    note: str


class BedrockSpike(BaseModel):
    detected: bool
    metric: str | None = None            # "invocations" | "cost"
    day: str | None = None
    baseline: Decimal | None = None
    observed: Decimal | None = None
    difference: Decimal | None = None
    # Cost change associated with the same window (measurement, not causation).
    associated_cost_change: Decimal | None = None
    message: str | None = None
    reason: str | None = None            # e.g. insufficient history


class BedrockIntelligence(BaseModel):
    period_start: str
    period_end: str
    cost: BedrockCostFacts
    usage: BedrockUsageFacts
    by_model: list[ModelUsage]
    efficiency: EfficiencyFacts
    spike: BedrockSpike
    # High-level state so the UI can render empty / partial / error cleanly.
    has_any_data: bool
    notes: list[str] = []


class BedrockExplanationRead(BaseModel):
    text: str
    generated_by: str  # "ai" | "template"
