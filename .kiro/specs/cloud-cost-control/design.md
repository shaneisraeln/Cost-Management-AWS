# Design Document

## Overview

The Cloud Cost Control Platform is a secure, multi-tenant web application that connects to AWS, ingests cost/usage/resource/activity data, normalizes it into a canonical model, attributes cost to resources/projects/users, detects anomalies and waste, exposes an investigation timeline, and provides a foundation for GitHub-based PR cost estimation and safe user-approved remediation.

The architecture is organized around one non-negotiable idea: a **trustworthy, deterministic chain** from AWS cost to resource to ownership to evidence to explanation to action. Everything that could compromise that trust — AI text generation, external pricing, provider-specific quirks — is isolated behind interfaces so the core stays deterministic and testable.

This document describes the system architecture, the technology choices and their rationale, the data model, the provider abstractions and engines, the API surface, the background job system, the security and multi-tenancy model, and the testing strategy.

### Design Goals

1. **Read-only by default.** No AWS write path exists in the core product until Phase 8, and even then it is gated behind policy + approval + audit.
2. **Deterministic financial truth.** All money math is pure, testable, and reproducible. AI never produces numbers.
3. **Provider isolation.** AWS APIs, pricing, credentials, and the LLM are all behind interfaces so implementations can be swapped (local creds → AssumeRole, Cost Explorer → CUR) without touching consumers.
4. **Reconciliation as a first-class invariant.** Total = Attributed + Shared + Unknown is enforced and tested, never silently violated.
5. **Multi-tenant from day one.** Every business record is tenant-scoped and every query is authorized server-side.
6. **Incremental delivery.** Each phase is independently shippable and demoable.

---

## Technology Stack and Rationale

### Backend: Python + FastAPI + Pydantic + SQLAlchemy + Alembic

- **Python** is the natural choice because boto3 is the most complete AWS SDK, the cost/attribution/anomaly math is expressed cleanly in Python, and Groq ships a first-class Python SDK.
- **FastAPI** gives async I/O (important for many concurrent AWS API calls), automatic OpenAPI docs, and native Pydantic validation.
- **Pydantic** enforces the boundary between untrusted external data (AWS/GitHub responses) and our canonical models.
- **SQLAlchemy 2.0** (typed, async) + **Alembic** for migrations gives us relational integrity and the DB constraints the TRD requires (unique keys, non-negative cost, confidence range).

### Frontend: Next.js (App Router) + TypeScript + Tailwind + TanStack Query + Recharts

- **Next.js App Router** for server components, routing, and a clean deployment story (Vercel).
- **TanStack Query** for server-state caching of costs/resources/anomalies/recommendations, matching the TRD's server-state requirement.
- **URL-driven filters** make investigations shareable/reproducible (e.g. `/costs?from=...&to=...&service=EC2`).
- **Recharts** is sufficient; the product is investigation-first, not a charting product.

### Database: PostgreSQL

Relational integrity, transactional reconciliation, JSONB for flexible `tags`/`metadata`/`evidence`, and strong constraint support.

### Background Jobs: Celery + Redis

Chosen over a bare scheduled worker because this is a real long-lived product needing retries, exponential backoff, idempotency, scheduling (Celery Beat), and observability. Redis also serves as the pricing/response cache. This is the one area where we invest setup cost up front to avoid a rewrite.

### Authentication: Clerk

Clerk **Organizations** map directly to our tenants, and Clerk organization roles map to OWNER/ADMIN/MEMBER/VIEWER. This gives hosted auth UI, team management, and JWT verification with minimal custom code. Application identity is kept strictly separate from AWS identity.

### AI: Groq

Groq provides fast LLM inference. The model name is configurable via env (`GROQ_MODEL`). The AI layer only converts deterministic facts to natural language and always has a deterministic templated fallback.

### Pricing: AWS Price List API + cache

The AWS Price List API is the legitimate source of truth. Because it is slow and rate-limited, results are cached in Postgres (durable) and Redis (hot), with source + timestamp recorded on every price used.

### Local Infrastructure: Docker Compose

Postgres + Redis run in Docker Compose so every environment is identical. The FastAPI app and Next.js app can run on the host or in containers.

---

## Architecture

### High-Level Component Diagram

```text
                          Browser (Next.js UI)
                                  |
                           HTTPS + Clerk JWT
                                  |
                                  v
                        FastAPI Application
        ┌─────────────────────────┼───────────────────────────┐
        | Auth Middleware (Clerk JWT verify + tenant resolve)   |
        | Tenant-scoping repository layer                       |
        └─────────────────────────┼───────────────────────────┘
                                  |
     ┌───────────────┬────────────┼───────────────┬─────────────────┐
     v               v            v                v                 v
 REST API       Engines      Providers        Celery enqueue     GitHub API
 (routers)   (Attribution,  (Cost, Pricing,   (sync/aggregate)   (App/OAuth)
             Anomaly, Waste, Credential,
             Forecast, Recc, AWS resource,
             Variance)      CloudWatch, LLM)
     |
     v
 PostgreSQL  <────────────────────────────────────────────┐
     ^                                                     |
     |                                                     |
 Celery Workers  ── Redis (broker + cache) ── Celery Beat  |
     |                                                     |
     v                                                     |
 AWS SDK (boto3): Cost Explorer, EC2/EBS/S3/RDS,           |
 CloudTrail, CloudWatch, Pricing  ────────────────────────┘
```

### Layered Structure (backend)

```text
app/
  api/            # FastAPI routers (thin; validation + auth + delegation)
  core/           # config, logging, security, dependencies
  db/             # SQLAlchemy models, session, base, migrations wiring
  schemas/        # Pydantic request/response + canonical models
  repositories/   # tenant-scoped data access (all queries filtered by tenant_id)
  services/        # orchestration between repositories, engines, providers
  engines/        # deterministic domain logic (attribution, anomaly, waste, forecast, recommendation, variance, correlation, allocation)
  providers/      # external-system adapters behind interfaces
    aws/          # credential, cost, resource, cloudtrail, cloudwatch, pricing
    llm/          # Groq client + templated fallback
    github/       # GitHub App/OAuth adapter
  jobs/           # Celery app, tasks, beat schedule
  tests/
```

The dependency rule: **api → services → (engines + repositories + providers)**. Engines are pure and depend on nothing external. Providers depend only on their SDKs. This keeps deterministic logic isolated and unit-testable with mock providers.

---

## Provider Abstractions (Interfaces)

All external systems sit behind Python `Protocol`/ABC interfaces so implementations are swappable and mockable.

### AwsCredentialProvider

```python
class AwsCredentialProvider(Protocol):
    def get_session(self, connection: AwsConnection) -> boto3.Session: ...
```

- `LocalProfileCredentialProvider` — uses the boto3 default chain / named profile (now).
- `AssumeRoleCredentialProvider` — assumes the customer role for temporary creds (later, production).

Consumers only ever receive a ready `boto3.Session`; they never know how credentials were obtained.

### CostProvider

```python
class CostProvider(Protocol):
    def get_cost_and_usage(self, session, start, end, granularity, group_by) -> list[RawCostLine]: ...
```

- `CostExplorerProvider` — Cost Explorer `GetCostAndUsage` (now).
- `DetailedBillingProvider` — CUR/Data Exports from S3 (later seam).

### ResourceProvider (per service)

```python
class ResourceProvider(Protocol):
    service: str
    def discover(self, session, region) -> list[RawResource]: ...
```

Implementations: `Ec2ResourceProvider`, `EbsResourceProvider`, `S3ResourceProvider`, `RdsResourceProvider`. New services are added by adding a provider; consumers iterate a registry.

### CloudTrailProvider / MetricsProvider (CloudWatch)

Read activity events and utilization metrics behind interfaces so waste/attribution logic never calls boto3 directly.

### PricingProvider

```python
class PricingProvider(Protocol):
    def get_price(self, service, region, resource_type, parameters) -> PriceResult: ...
```

`AwsPriceListProvider` backed by a `PriceCache` (Postgres + Redis). Every `PriceResult` carries `source` and `retrieved_at`.

### LlmProvider

```python
class LlmProvider(Protocol):
    def explain(self, facts: ExplanationFacts) -> str: ...
```

`GroqLlmProvider` (configurable model) with `TemplatedLlmProvider` fallback used when Groq is unavailable or facts are insufficient.

### GithubProvider

Wraps GitHub App/OAuth: list installations/repos, fetch PR changed files, post PR comments.

---

## Deterministic Engines

Engines are pure domain logic with no external I/O; they receive data and return results. This is where every unit test for cost/attribution rules lives (Requirement 25.4).

### AllocationEngine (Requirement 5)

Partitions `CostRecord`s for a period into Attributed / Shared / Unknown and asserts the reconciliation invariant `Total == Attributed + Shared + Unknown`. Any residual is explicitly bucketed to Unknown, never dropped.

### AttributionEngine (Requirement 4)

Given a resource, its tags, CloudTrail events, AWS identities, project mappings, and manual rules, it evaluates evidence in configurable precedence with configurable weights and produces an `AttributionResult` (status, owner, project, environment, confidence 0–1, evidence list). Confidence is a bounded combination of matched evidence weights. If nothing matches → UNKNOWN. If conflicting strong evidence → DISPUTED. If shared across owners → SHARED.

### CorrelationEngine (Requirement 7)

Links a `CostChange` to `Event`s by TEMPORAL / RESOURCE_MATCH / ACTOR_MATCH / DEPLOYMENT_MATCH / USAGE_MATCH, producing `Correlation` records with an evidence score (not proof).

### AnomalyEngine + CostChangeClassifier (Requirement 8)

Computes rolling 7/30-day averages and standard deviation; flags anomalies via configurable multiplier or z-score. Classifies changes as GROWTH / ENGINEERING_CHANGE / WASTE / SUSPICIOUS / UNKNOWN using deterministic rules combined with correlation evidence.

### WasteEngine (Requirement 9)

Runs registered `WasteRule`s (unattached EBS, idle EC2, continuous dev runtime, missing metadata), each returning `WasteFinding`s with estimated monthly savings (via PricingProvider), confidence, risk, and evidence. Low utilization alone never yields a finding without supporting evidence.

### ForecastEngine (Requirement 10)

`forecast = current_spend + average_daily_spend × remaining_days`, returning methodology and a quality indicator. Never presented as exact.

### RecommendationEngine (Requirement 12)

Consumes anomalies, waste findings, forecast, budget, resource, and attribution to produce `Recommendation`s with problem/evidence/savings/confidence/risk/action_type/required_permission. MVP mostly emits REVIEW.

### VarianceEngine (Requirement 15)

Compares `CostEstimate` vs `ActualCost`, computing absolute/percentage variance and candidate reasons with confidence; never asserts full causality without evidence.

### PolicyEngine (Requirement 16)

Validates every proposed write action against user authorization, resource protection, environment, action type, account, explicit approval, and current resource state. Production resources are protected by default.

---

## Data Model

All tables include `tenant_id` (Requirement 18) and appropriate `created_at`/`updated_at`. Money stored as `NUMERIC(18,6)` with a non-negative check where applicable; confidence as `NUMERIC(4,3)` with a `0..1` check.

### Identity & Tenancy

- **Tenant** — `id`, `clerk_org_id` (unique), `name`, `created_at`, `updated_at`.
- **User** — `id`, `tenant_id`, `clerk_user_id`, `name`, `email`, `role` (OWNER/ADMIN/MEMBER/VIEWER), timestamps.
- **AwsIdentity** — `id`, `tenant_id`, `account_id`, `principal_type`, `principal_id`, `arn`, `display_name`, `metadata`, `created_at`. (Distinct from application User.)

### AWS Connection & Sync

- **AwsConnection** — `id`, `tenant_id`, `account_id`, `role_arn` (nullable in local mode), `auth_mode` (LOCAL_PROFILE/ASSUME_ROLE), `profile_name`, `status`, `permission_status` (JSONB), `last_cost_sync`, `last_resource_sync`, `last_event_sync`, `last_metrics_sync`, `last_error`, timestamps. Unique per (tenant, account) where appropriate.

### Cost

- **CostRecord** — `id`, `tenant_id`, `account_id`, `period_start`, `period_end`, `service`, `region`, `resource_id` (nullable), `resource_arn` (nullable), `usage_type`, `operation`, `cost` (NUMERIC ≥ 0), `currency`, `source`, `tags` (JSONB), `metadata` (JSONB), `created_at`. Idempotency via a deterministic natural key hash unique per (tenant, account, period, service, resource, usage_type, operation).
- **AggregatedCost** — precomputed daily/service/owner/project rollups for fast dashboards.

### Resources & Ownership

- **Resource** — `id`, `tenant_id`, `account_id`, `provider`, `provider_resource_id`, `arn`, `service`, `resource_type`, `region`, `state`, `created_at` (AWS), `tags` (JSONB), `metadata` (JSONB), `owner_id`, `project_id`, `environment`, `attribution_status`, `attribution_confidence`, timestamps. Unique (account, provider_resource_id).
- **Attribution** — `id`, `tenant_id`, `resource_id`, `owner_user_id`, `project_id`, `environment`, `status`, `confidence` (0..1), `source`, `evidence` (JSONB), `valid_from`, `valid_to`, `created_at`.
- **Project** — `id`, `tenant_id`, `name`, `description`, `budget`, `status`, timestamps.

### Events, Changes, Correlation

- **Event** — `id`, `tenant_id`, `account_id`, `event_type`, `timestamp`, `actor_identity_id`, `resource_id`, `source`, `raw_reference`, `normalized_data` (JSONB), `created_at`. Unique provider event id where possible.
- **CostChange** — `id`, `tenant_id`, `period`, `resource_id`, `service`, `baseline_cost`, `observed_cost`, `absolute_change`, `percentage_change`, `classification`, `confidence`, `created_at`.
- **Correlation** — `id`, `tenant_id`, `cost_change_id`, `event_id`, `correlation_type`, `score`, `evidence` (JSONB), `created_at`.
- **Anomaly** — `id`, `tenant_id`, `resource_id`, `service`, `detected_at`, `severity`, `baseline`, `observed`, `difference`, `algorithm`, `confidence`, `status`, `evidence` (JSONB).

### Optimization

- **WasteFinding** — `id`, `tenant_id`, `resource_id`, `rule`, `estimated_monthly_savings`, `confidence`, `risk`, `evidence` (JSONB), `status`, `created_at`.
- **Recommendation** — `id`, `tenant_id`, `type`, `resource_id`, `title`, `description`, `estimated_savings`, `confidence`, `risk`, `action_type`, `required_permission`, `status`, `created_at`.

### Budgets & Pricing

- **Budget** — `id`, `tenant_id`, `scope` (COMPANY/PROJECT/TEAM/SERVICE), `scope_ref`, `amount`, `thresholds` (JSONB, default [50,75,90,100]), `period`, timestamps.
- **PriceCacheEntry** — `id`, `service`, `region`, `resource_type`, `parameters_hash`, `unit_price`, `unit`, `currency`, `source`, `retrieved_at`. (Global, not tenant-scoped.)

### GitHub & Estimation

- **GithubInstallation**, **GithubRepository** (linked to `project_id`, `environment`), **GithubPullRequest**, **GithubCommit**, **GithubDeployment**.
- **CostEstimate** — `id`, `tenant_id`, `repository_id`, `pr_number`, `base_commit`, `head_commit`, `estimated_monthly_delta`, `currency`, `line_items` (JSONB), `source`, `status`, `created_at`.
- **ActualCost** — links deployed estimate to observed cost for variance.

### Actions & Audit

- **ActionRequest** — `id`, `tenant_id`, `recommendation_id`, `action_type`, `resource_id`, `approval_id`, `status`, `policy_result` (JSONB), timestamps.
- **AuditLog** — `id`, `tenant_id`, `actor_user_id`, `action`, `resource_id`, `aws_api`, `request_summary`, `approval_id`, `result`, `timestamp`. No secrets stored.

---

## API Structure (Requirement — TRD §34)

All routes are under `/api/v1`, require a valid Clerk JWT (except health), and are tenant-scoped server-side.

```text
/api/v1/auth/*
/api/v1/aws/connections            GET, POST
/api/v1/aws/connections/{id}/sync  POST
/api/v1/costs                      GET (filters via query params)
/api/v1/costs/summary              GET
/api/v1/costs/breakdown            GET
/api/v1/resources                  GET
/api/v1/resources/{id}             GET
/api/v1/attributions               GET, POST (manual mapping)
/api/v1/projects                   GET, POST
/api/v1/users                      GET
/api/v1/events                     GET
/api/v1/timeline                   GET
/api/v1/anomalies                  GET
/api/v1/waste                      GET
/api/v1/recommendations            GET
/api/v1/budgets                    GET, POST
/api/v1/github/installations       GET
/api/v1/github/repositories        GET, POST (link project/env)
/api/v1/github/pull-requests       GET
/api/v1/estimates                  GET
/api/v1/audit-logs                 GET
/healthz                           GET (public)
```

---

## Multi-Tenancy & Authorization (Requirements 18, 19)

- A FastAPI dependency verifies the Clerk JWT, extracts the Clerk `org_id` and `user_id`, and resolves the internal `Tenant` and `User` (creating on first login via Clerk webhook or lazy provisioning).
- A `TenantContext` (tenant_id, user, role) is injected into every request. The **repository layer** always filters by `tenant_id` from the context — never from request bodies (Requirement 18.3).
- Role checks are enforced by dependencies: `require_role(OWNER, ADMIN)` guards AWS connection, policy changes, remediation approval, and team management.
- Clerk org roles map to internal roles; a webhook keeps `User.role` in sync.

---

## Background Jobs (Requirement 20)

Celery app with Redis broker/result backend. Celery Beat schedules periodic syncs.

- **CostSyncJob** — Cost Explorer ingestion → normalize → upsert `CostRecord` (idempotent by natural key hash).
- **ResourceSyncJob** — per-service discovery → upsert `Resource`.
- **CloudTrailSyncJob** — event ingestion → normalize → `Event`.
- **MetricsSyncJob** — CloudWatch utilization for waste rules.
- **AggregationJob** — recompute `AggregatedCost` rollups.
- **AnomalyDetectionJob** — run AnomalyEngine over recent windows.

All jobs: idempotent, retry transient failures with exponential backoff, record `last_error` on the connection, remain resumable, and never corrupt data on partial failure (transactional upserts).

---

## AI Explanation Layer (Requirement 17)

The deterministic backend assembles an `ExplanationFacts` object (numbers, events, evidence). `GroqLlmProvider.explain(facts)` returns prose. On any failure or insufficient facts, `TemplatedLlmProvider` produces a deterministic sentence from the same facts. Responses are tagged `generated_by: "ai" | "template"` so the UI can visually distinguish AI text from facts (Requirement 17.5). The AI never receives free rein to produce numbers — it only rephrases provided facts.

---

## Security (Requirement 22)

- Read-only IAM permissions only; policy minimized from actual API calls; no AdministratorAccess, no `*:*`, no root, no long-lived keys stored by default.
- Secrets (Clerk keys, Groq key, DB URL) via environment/secret manager, never logged, encrypted at rest.
- TLS in transit. Read and write AWS roles separated (write role only introduced in Phase 8).
- Server-side authorization on every sensitive endpoint.

---

## Error Handling & Observability (Requirements 23, 39)

- Structured JSON logs with request ID, tenant ID, job ID, AWS account ID, durations, counts, latency, error category.
- Metrics counters: `aws_sync_success/failure`, `cost_records_ingested`, `resources_synced`, `events_processed`, `attribution_coverage`, `anomalies_detected`, `recommendations_created`, `github_estimates_created`.
- The UI surfaces sync status and reasons; it never renders a false zero when data is unavailable (shows "unavailable" state instead).

---

## Testing Strategy (Requirement 25.4, TRD §45)

- **Unit tests (pure engines):** cost normalization, allocation + reconciliation invariant, attribution scoring/precedence, forecasting, anomaly detection, waste rules, pricing calculations, authorization.
- **Integration tests:** AWS adapters (against recorded/mocked boto3 responses via `moto`/VCR-style fixtures), PostgreSQL repositories, CloudTrail parsing, GitHub API.
- **End-to-end:** the canonical scenario — connect AWS → sync → resource discovered → cost ingested → attribution generated → anomaly detected → recommendation created → UI shows evidence.
- Automated tests default to mock AWS responses; real-account calls are opt-in via env for manual verification.

---

## Frontend Design (TRD §42–§44)

Pages: `/` overview, `/costs`, `/resources`, `/resources/:id`, `/people`, `/projects`, `/alerts`, `/timeline`, `/recommendations`, `/github`, `/settings/aws`, `/settings/team`, `/settings/policies`.

- Server state via TanStack Query; filters in URL query params.
- The resource detail page answers: what is this, how much does it cost, who owns it, why is it expensive, what happened recently, what can I do — with sections for identity, cost, utilization, ownership, tags, activity, timeline, recommendations, audit history.
- Facts vs inference vs AI text are visually differentiated (badges/typography).

---

## Phasing Alignment

The design supports incremental delivery matching the TRD phases (0–8). Interfaces and the data model are complete enough to support the full future loop (Predict → Deploy → Measure → Attribute → Explain → Act) even where a phase is not yet implemented (Requirement 25.5). Detailed tasks are in `tasks.md`.
