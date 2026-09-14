# Implementation Plan

This plan implements the Cloud Cost Control Platform incrementally across phases matching the TRD. Each task is a discrete, testable coding step. Tasks reference the requirements they satisfy. Complete tasks in order; each phase is independently shippable.

---

## Phase 0 — Foundation

- [ ] 1. Initialize the monorepo structure
  - Create `/backend` and `/frontend` directories, root `README.md`, root `.gitignore`, and `.editorconfig`.
  - Add a root `docker-compose.yml` defining Postgres and Redis services with named volumes and health checks.
  - Create `.env.example` files at root, `/backend`, and `/frontend` documenting all required variables (DB URL, Redis URL, Clerk keys, Groq key/model, AWS profile/region).
  - _Requirements: 25.1_

- [ ] 2. Scaffold the FastAPI backend skeleton
  - Create the `app/` package layout: `api/`, `core/`, `db/`, `schemas/`, `repositories/`, `services/`, `engines/`, `providers/`, `jobs/`, `tests/`.
  - Add `pyproject.toml` (or `requirements.txt`) with FastAPI, uvicorn, SQLAlchemy 2.0, Alembic, psycopg, pydantic-settings, boto3, celery, redis, groq, httpx, pytest, moto.
  - Implement `core/config.py` (pydantic-settings loading env), `core/logging.py` (structured JSON logging), and `main.py` with an app factory.
  - Add a public `GET /healthz` endpoint returning service and DB/Redis connectivity status.
  - _Requirements: 19.1, 23.1_

- [ ] 3. Set up the database layer and migrations
  - Configure async SQLAlchemy engine/session in `db/session.py` and a declarative `Base` with common mixins (`id`, `tenant_id`, `created_at`, `updated_at`).
  - Initialize Alembic; wire it to the settings DB URL; create the initial empty migration.
  - Implement the `Tenant` and `User` models with the `clerk_org_id`/`clerk_user_id` fields and role enum; generate and apply the migration.
  - _Requirements: 18.1, 19.3, 24.2_

- [ ] 4. Implement Clerk authentication and tenant context
  - Add Clerk JWT verification middleware/dependency in `core/security.py` that extracts `org_id` and `user_id`.
  - Implement lazy provisioning: resolve or create the `Tenant` (from Clerk org) and `User` (from Clerk user) on first authenticated request.
  - Build a `TenantContext` dependency (tenant_id, user, role) injected into requests, and a `require_role(...)` guard.
  - Add a Clerk webhook endpoint to sync org/user/role changes.
  - _Requirements: 18.2, 18.3, 18.5, 19.2, 19.3, 19.4, 19.5_

- [ ] 5. Implement the tenant-scoped repository base
  - Create a generic repository base that always filters queries by the `tenant_id` from `TenantContext` and rejects tenant IDs from request bodies.
  - Write unit tests proving cross-tenant reads/writes are impossible through the repository.
  - _Requirements: 18.2, 18.3, 18.4_

- [ ] 6. Scaffold the Next.js frontend shell
  - Initialize Next.js (App Router) + TypeScript + Tailwind; configure TanStack Query provider and a typed API client.
  - Integrate Clerk (`@clerk/nextjs`) with sign-in, organization switching, and a protected app layout.
  - Build the primary navigation shell (Overview, Costs, Resources, People, Projects, Alerts, Timeline, Recommendations, GitHub, Settings) with placeholder pages.
  - _Requirements: 18.5, 19.2_

- [ ] 7. Set up Celery and CI
  - Create the Celery app in `jobs/celery_app.py` with Redis broker/backend and a Beat schedule placeholder; add a smoke task and verify a worker runs.
  - Add CI (GitHub Actions): backend lint + pytest against a Postgres/Redis service, frontend lint + typecheck + build.
  - _Requirements: 20.2_

## Phase 1 — AWS Connection

- [ ] 8. Implement the AwsCredentialProvider abstraction
  - Define the `AwsCredentialProvider` interface and `LocalProfileCredentialProvider` (boto3 default chain / named profile); stub `AssumeRoleCredentialProvider`.
  - Add a factory that selects the provider based on `AwsConnection.auth_mode`.
  - _Requirements: 1.2, 1.3, 1.4, 22.2_

- [ ] 9. Implement the AwsConnection model and onboarding API
  - Add the `AwsConnection` model and migration (auth_mode, profile_name, role_arn nullable, status, permission_status, sync timestamps, last_error).
  - Add `POST /api/v1/aws/connections` (OWNER/ADMIN only) and `GET /api/v1/aws/connections`.
  - _Requirements: 1.1, 1.6, 19.4, 20.1_

- [ ] 10. Implement permission validation and account discovery
  - Add a service that performs minimal read calls (STS get-caller-identity, a Cost Explorer probe) to validate permissions and record `permission_status` per capability.
  - Surface missing-capability details rather than failing silently.
  - Display account ID, status, last sync, permission status, and coverage in the frontend `/settings/aws` page.
  - _Requirements: 1.5, 1.6, 1.7, 1.8_

## Phase 2 — Cost Ingestion

- [ ] 11. Implement the CostProvider abstraction and Cost Explorer adapter
  - Define `CostProvider` and implement `CostExplorerProvider` (`GetCostAndUsage` with granularity and group-by); add a `DetailedBillingProvider` stub seam.
  - Add recorded/mocked fixtures for automated tests; guard real calls behind an opt-in env flag.
  - _Requirements: 2.1, 2.2, 25.2_

- [ ] 12. Implement the CostRecord model and normalization
  - Add the `CostRecord` model and migration with nullable `resource_id`, non-negative cost check, source/timestamp, and a deterministic natural-key hash unique constraint for idempotency.
  - Implement normalization from raw Cost Explorer lines to `CostRecord`.
  - Write unit tests for normalization and idempotent upsert (running twice yields no duplicates).
  - _Requirements: 2.3, 2.4, 2.5, 2.7, 24.2, 25.4_

- [ ] 13. Implement CostSyncJob and failure handling
  - Add the Celery `CostSyncJob` with idempotent upsert, exponential-backoff retries, `last_error` recording, and resumability.
  - Ensure unavailable data surfaces a failure state and never shows a false zero.
  - _Requirements: 2.6, 20.3, 20.4, 20.5, 39_

- [ ] 14. Build the cost overview and explorer APIs and UI
  - Add `/api/v1/costs`, `/costs/summary`, `/costs/breakdown` with filters (date, service, region, resource, owner, team, project, environment, tags, attribution status).
  - Build the Overview page (current spend, previous period, forecast placeholder, budget placeholder, daily trend, top services/resources/owners, unknown/shared, attribution coverage) and the Cost Explorer with Total/Trend/Breakdown/Table views and URL-driven filters.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

## Phase 3 — Resource Discovery

- [ ] 15. Implement the ResourceProvider abstraction and per-service adapters
  - Define `ResourceProvider` and implement `Ec2ResourceProvider`, `EbsResourceProvider`, `S3ResourceProvider`, `RdsResourceProvider`; register them in a discovery registry.
  - _Requirements: 3.1, 3.6, 25.2_

- [ ] 16. Implement the Resource model, ResourceSyncJob, and inventory UI
  - Add the `Resource` model and migration with unique (account, provider_resource_id) and nullable optional fields.
  - Implement idempotent `ResourceSyncJob` (upsert, no duplicates).
  - Build the `/resources` inventory and `/resources/:id` detail page (identity, cost, tags, activity placeholders).
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 20.3_

## Phase 4 — Attribution & Reconciliation

- [ ] 17. Implement the Attribution and Project models and manual mapping
  - Add `Attribution`, `Project`, and `AwsIdentity` models and migrations with confidence 0..1 check and validity windows.
  - Add `POST /api/v1/attributions` for manual mapping and `/api/v1/projects` CRUD.
  - _Requirements: 4.6, 4.7, 4.8, 18.1, 24.2_

- [ ] 18. Implement CloudTrailProvider and CloudTrailSyncJob
  - Define `CloudTrailProvider`, implement CloudTrail lookup ingestion, normalize to `Event`, and store actor identities as `AwsIdentity`.
  - Make the job idempotent (unique provider event id).
  - _Requirements: 7.1, 7.6, 20.3, 24.3_

- [ ] 19. Implement the AttributionEngine
  - Implement configurable precedence and weights, producing `AttributionResult` (status, owner, project, environment, confidence, evidence).
  - Handle UNKNOWN/SHARED/DISPUTED correctly; never fabricate an owner.
  - Write thorough unit tests for each precedence rule and confidence combination.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 25.4_

- [ ] 20. Implement the AllocationEngine and reconciliation
  - Partition period costs into Attributed/Shared/Unknown and enforce Total = Attributed + Shared + Unknown.
  - Surface discrepancies; never drop unallocated cost.
  - Write a reconciliation test asserting the invariant across scenarios.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 25.4_

## Phase 5 — Investigation

- [ ] 21. Implement CostChange detection and classification
  - Add the `CostChange` model and a classifier (GROWTH/ENGINEERING_CHANGE/WASTE/SUSPICIOUS/UNKNOWN) using deterministic rules and correlation evidence.
  - _Requirements: 8.1, 8.2, 25.3_

- [ ] 22. Implement the AnomalyEngine and AnomalyDetectionJob
  - Compute rolling 7/30-day averages and standard deviation; flag anomalies via configurable multiplier/z-score; store `Anomaly` records.
  - Write unit tests for the statistical rules; make thresholds configurable.
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 25.4_

- [ ] 23. Implement the CorrelationEngine, timeline, and alerts UI
  - Add `Event`, `Correlation` models; correlate cost changes to events (TEMPORAL/RESOURCE_MATCH/ACTOR_MATCH/DEPLOYMENT_MATCH/USAGE_MATCH) with evidence scores.
  - Build `/timeline` and `/alerts` pages; present correlations as evidence, not proof.
  - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [ ] 24. Implement the Groq AI explanation layer
  - Define `LlmProvider`, implement `GroqLlmProvider` (configurable model) and `TemplatedLlmProvider` fallback; assemble `ExplanationFacts` from deterministic data only.
  - Tag output as ai/template; render facts vs AI text distinctly in the UI.
  - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_

## Phase 6 — Optimization

- [ ] 25. Implement the PricingProvider and price cache
  - Define `PricingProvider`, implement `AwsPriceListProvider` with a Postgres + Redis `PriceCache`; store source and timestamp on every price.
  - Add the `PriceCacheEntry` model and migration.
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [ ] 26. Implement MetricsProvider and the WasteEngine
  - Define `MetricsProvider` (CloudWatch) and `MetricsSyncJob`.
  - Implement `WasteRule`/`WasteFinding` with rules: unattached EBS, idle EC2, continuous dev runtime, missing metadata; require evidence beyond low utilization.
  - Write unit tests for each rule and savings calculation.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 25.4_

- [ ] 27. Implement the ForecastEngine, Budgets, and RecommendationEngine
  - Implement the forecast formula with methodology/quality indicator; add `Budget` model, thresholds, and budget-threshold events.
  - Implement `RecommendationEngine` producing recommendations (mostly REVIEW) with full fields; build the `/recommendations` page.
  - Write unit tests for forecasting and recommendation generation.
  - _Requirements: 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 25.4_

## Phase 7 — GitHub

- [ ] 28. Implement the GitHub App/OAuth integration and models
  - Define `GithubProvider`; add `GithubInstallation`, `GithubRepository`, `GithubPullRequest`, `GithubCommit`, `GithubDeployment` models.
  - Add `/api/v1/github/*` routes and repo↔project/environment linking; build the `/github` page.
  - _Requirements: 14.1, 14.2_

- [ ] 29. Implement the PR cost estimation pipeline
  - Detect and parse a narrow set of supported infra definitions (EC2/RDS/EBS/S3) from PR changed files; resolve pricing; produce `CostEstimate` with line items; post a labeled PR comment.
  - Keep calculation deterministic and traceable; write unit tests for the parser and estimator.
  - _Requirements: 14.3, 14.4, 14.5, 14.6, 25.3, 25.4_

- [ ] 30. Implement the VarianceEngine (actual vs predicted)
  - Add `ActualCost`; implement `VarianceEngine` computing absolute/percentage variance and candidate reasons with confidence; avoid unfounded causality claims.
  - _Requirements: 15.1, 15.2, 15.3_

## Phase 8 — Safe Actions

- [ ] 31. Implement the remediation pipeline and PolicyEngine
  - Add `ActionRequest`; implement `PolicyEngine` checks (authorization, resource protection, environment, action type, account, explicit approval, resource state); protect production by default.
  - Ensure recommendation generation never executes AWS actions directly.
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [ ] 32. Implement the write role, action executor, and audit log
  - Introduce a separate IAM write role and `AssumeRoleCredentialProvider`; implement a guarded AWS action executor (e.g., EC2 stop) invoked only after policy + explicit approval.
  - Add the `AuditLog` model and write an entry for every sensitive action (no secrets); build audit views.
  - _Requirements: 16.6, 16.7, 21.1, 21.2, 21.3, 22.6_

## Cross-Cutting (apply throughout)

- [ ] 33. Enforce observability, retention, and security hardening
  - Add structured logging fields and metrics counters across jobs and requests.
  - Implement retention policies (cost 12mo configurable, events 90–180d, aggregates/audit longer) and a cleanup job.
  - Verify least-privilege IAM, secret handling, TLS, and separated read/write roles.
  - _Requirements: 22.1, 22.3, 22.4, 22.5, 23.1, 23.2, 24.1, 24.3_
