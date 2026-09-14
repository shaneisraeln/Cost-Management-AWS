"""GitHub repository + PR cost-estimate endpoints.

Estimates are explicitly predictions (not actual billing). Groq is used only
to explain an already-computed estimate; it never computes cost.
Read-only with respect to AWS.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TenantContext, get_tenant_context, require_role
from app.db.models.cost_estimate import CostEstimate
from app.db.models.github import GithubRepository
from app.db.models.user import UserRole
from app.db.session import get_db
from app.providers.llm.base import ExplanationFacts
from app.providers.llm.groq import GroqLlmProvider
from app.repositories.github import CostEstimateRepository, GithubRepositoryRepo
from app.schemas.github import (
    CostDriverRead,
    CostEstimateRead,
    EstimateCreate,
    ExplanationRead,
    GuardrailRead,
    MarkDeployedRequest,
    RepositoryCreate,
    RepositoryRead,
    ServiceObservation,
    VarianceRead,
)
from app.services.estimation import (
    _summarize_for_explanation,
    estimate_from_plan,
)
from app.services.github import register_repository
from app.services.guardrail import evaluate_and_store
from app.services.variance import compute_estimate_variance, mark_deployed_now

router = APIRouter(tags=["github"])


@router.get("/github/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[GithubRepository]:
    return await GithubRepositoryRepo(db, ctx.tenant_id).list()


@router.post("/github/repositories", response_model=RepositoryRead)
async def create_repository(
    payload: RepositoryCreate,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> GithubRepository:
    return await register_repository(
        db,
        ctx.tenant_id,
        full_name=payload.full_name,
        project_id=payload.project_id,
        environment=payload.environment,
    )


@router.get("/estimates", response_model=list[CostEstimateRead])
async def list_estimates(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> list[CostEstimate]:
    return await CostEstimateRepository(db, ctx.tenant_id).list_recent()


@router.get("/estimates/{estimate_id}", response_model=CostEstimateRead)
async def get_estimate(
    estimate_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> CostEstimate:
    record = await CostEstimateRepository(db, ctx.tenant_id).get(estimate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")
    return record


@router.post("/estimates", response_model=CostEstimateRead, status_code=status.HTTP_201_CREATED)
async def create_estimate(
    payload: EstimateCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> CostEstimate:
    try:
        return await estimate_from_plan(
            db,
            ctx.tenant_id,
            plan_document=payload.plan,
            iac_format=payload.iac_format,
            repository_id=payload.repository_id,
            pr_number=payload.pr_number,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/estimates/{estimate_id}/guardrail", response_model=GuardrailRead)
async def estimate_guardrail(
    estimate_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> GuardrailRead:
    """Evaluate the Cost Guardrail for an estimate from its deterministic delta.

    Advisory only: no AWS action, no PR merge, no enforcement.
    """
    repo = CostEstimateRepository(db, ctx.tenant_id)
    record = await repo.get(estimate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")

    result = await evaluate_and_store(db, ctx.tenant_id, record)
    await db.commit()

    return GuardrailRead(
        estimate_id=record.id,
        status=result.status.value,
        monthly_delta=result.monthly_delta,
        currency=result.currency,
        baseline_monthly=record.baseline_monthly,
        proposed_monthly=record.proposed_monthly,
        warning_threshold=result.warning_threshold,
        review_threshold=result.review_threshold,
        threshold=result.threshold,
        message=result.message,
        is_savings=result.is_savings,
        estimate_complete=result.estimate_complete,
        incomplete_note=result.incomplete_note,
        unsupported=record.unsupported,
        pricing_source=record.pricing_source,
        cost_drivers=[
            CostDriverRead(
                address=d.address, detail=d.detail, delta_monthly=d.delta_monthly
            )
            for d in result.cost_drivers
        ],
        evaluated_at=result.evaluated_at,
    )


@router.post("/estimates/{estimate_id}/explain", response_model=ExplanationRead)
async def explain_estimate(
    estimate_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> ExplanationRead:
    record = await CostEstimateRepository(db, ctx.tenant_id).get(estimate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")

    summary = _summarize_for_explanation(record)
    guardrail_evidence = []
    if record.guardrail_status:
        guardrail_evidence.append(
            {
                "type": "guardrail",
                "detail": {
                    "status": record.guardrail_status,
                    "warning_threshold": str(record.guardrail_warning_threshold),
                    "review_threshold": str(record.guardrail_review_threshold),
                },
            }
        )
    facts = ExplanationFacts(
        subject=f"Estimated monthly cost impact of PR #{record.pr_number or '(unlinked)'}",
        baseline=summary["baseline_monthly"],
        observed=summary["proposed_monthly"],
        difference=summary["delta_monthly"],
        classification="ESTIMATE (not actual billing)",
        confidence=None,
        evidence=[
            {"type": "changed_resources", "detail": summary["changed_resources"]},
            {"type": "not_estimated", "detail": summary["not_estimated"]},
            {"type": "unsupported_types", "detail": summary["unsupported_types"]},
            *guardrail_evidence,
        ],
    )
    explanation = GroqLlmProvider().explain(facts)
    return ExplanationRead(text=explanation.text, generated_by=explanation.generated_by)


@router.post("/estimates/{estimate_id}/mark-deployed", response_model=CostEstimateRead)
async def mark_deployed(
    estimate_id: str,
    payload: MarkDeployedRequest,
    ctx: TenantContext = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> CostEstimate:
    repo = CostEstimateRepository(db, ctx.tenant_id)
    record = await repo.get(estimate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")
    record.account_id = payload.account_id
    record.project_id = payload.project_id
    record.environment = payload.environment
    mark_deployed_now(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/estimates/{estimate_id}/variance", response_model=VarianceRead)
async def estimate_variance(
    estimate_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> VarianceRead:
    repo = CostEstimateRepository(db, ctx.tenant_id)
    record = await repo.get(estimate_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")

    report = await compute_estimate_variance(db, ctx.tenant_id, record)
    r = report.result
    return VarianceRead(
        estimate_id=report.estimate_id,
        predicted_monthly=r.predicted_monthly,
        actual_monthly=r.actual_monthly,
        absolute_variance=r.absolute_variance,
        percentage_variance=r.percentage_variance,
        verdict=r.verdict.value,
        actual_days_observed=r.actual_days_observed,
        possible_reasons=r.possible_reasons,
        is_causal_claim=r.is_causal_claim,
        window_start=report.window_start.isoformat(),
        window_end=report.window_end.isoformat(),
        account_scoped=report.account_scoped,
        service_breakdown=[ServiceObservation(**s) for s in report.service_breakdown],
        note=report.note,
    )
