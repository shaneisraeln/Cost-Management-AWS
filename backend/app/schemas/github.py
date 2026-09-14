"""GitHub + cost-estimate schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    full_name: str = Field(..., max_length=512)
    project_id: str | None = None
    environment: str | None = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    project_id: str | None
    environment: str | None
    created_at: datetime


class EstimateCreate(BaseModel):
    """Submit an IaC plan document for estimation."""

    iac_format: str = "terraform_plan"
    plan: dict
    repository_id: str | None = None
    pr_number: int | None = None
    base_commit: str | None = None
    head_commit: str | None = None


class CostEstimateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str | None
    pr_number: int | None
    base_commit: str | None
    head_commit: str | None
    account_id: str | None
    project_id: str | None
    environment: str | None
    deployed_at: datetime | None
    baseline_monthly: Decimal
    proposed_monthly: Decimal
    estimated_monthly_delta: Decimal
    currency: str
    line_items: list
    unsupported: list
    iac_format: str
    pricing_source: str | None
    status: str
    created_at: datetime
    # Persisted guardrail summary (full detail via the guardrail endpoint).
    guardrail_status: str | None = None
    guardrail_warning_threshold: Decimal | None = None
    guardrail_review_threshold: Decimal | None = None
    guardrail_evaluated_at: datetime | None = None


class CostDriverRead(BaseModel):
    address: str
    detail: str
    delta_monthly: Decimal


class GuardrailRead(BaseModel):
    estimate_id: str
    status: str  # PASS | WARNING | REVIEW_REQUIRED
    monthly_delta: Decimal
    currency: str
    baseline_monthly: Decimal
    proposed_monthly: Decimal
    warning_threshold: Decimal
    review_threshold: Decimal
    threshold: Decimal | None
    message: str
    is_savings: bool
    estimate_complete: bool
    incomplete_note: str | None
    unsupported: list
    pricing_source: str | None
    cost_drivers: list[CostDriverRead]
    evaluated_at: datetime
    # Always an estimate, never actual billing.
    is_estimate: bool = True


class ExplanationRead(BaseModel):
    text: str
    generated_by: str


class MarkDeployedRequest(BaseModel):
    account_id: str | None = None
    project_id: str | None = None
    environment: str | None = None


class ServiceObservation(BaseModel):
    service: str
    observed_window: str
    observed_monthly: str


class VarianceRead(BaseModel):
    estimate_id: str
    predicted_monthly: Decimal
    actual_monthly: Decimal
    absolute_variance: Decimal
    percentage_variance: float | None
    verdict: str  # HIGHER | LOWER | CLOSE | INSUFFICIENT_DATA
    actual_days_observed: int
    possible_reasons: list[str]
    is_causal_claim: bool
    window_start: str
    window_end: str
    account_scoped: bool
    service_breakdown: list[ServiceObservation]
    note: str
