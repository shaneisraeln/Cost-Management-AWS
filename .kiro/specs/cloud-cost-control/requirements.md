# Requirements Document

## Introduction

The Cloud Cost Control Platform is a developer-first, AWS-first system that connects AWS spending, resources, activity, ownership, and GitHub changes so small engineering teams (2–20 developers) can understand what caused cloud costs, predict cost impact, detect waste and anomalies, and safely act on them.

The product's value is a trustworthy chain: **cost → resource → ownership → evidence → explanation → action**. The system is **read-only by default**; any write action is isolated behind explicit permissions, policy checks, and user approval. Billing calculations are deterministic. AI is used only to convert deterministic facts into natural language, never as a source of financial truth.

This document defines the requirements for the full product across all phases (Phases 0–8 in the TRD). Requirements use the EARS (Easy Approach to Requirements Syntax) format.

### Product Principles (constraints applied across all requirements)

- **P1 — Read-only first:** The initial product must never modify customer infrastructure.
- **P2 — Explain before acting:** Every recommendation shows detection, evidence, estimated impact, confidence, and proposed action.
- **P3 — Never invent attribution:** If ownership cannot be established, cost is marked Unknown or Shared.
- **P4 — Separate facts from inference:** The UI distinguishes AWS facts, calculated values, inferred relationships, and AI-generated text.
- **P5 — Every dollar must reconcile:** Total = Attributed + Shared + Unknown for any time range.
- **P6 — Developer-first language:** Plain language over FinOps jargon.

---

## Requirements

### Requirement 1: AWS Account Connection

**User Story:** As a founder, I want to connect my AWS account securely, so that the application can read cost and resource information without storing long-lived secrets.

#### Acceptance Criteria

1. WHEN a user with OWNER or ADMIN role initiates an AWS connection THEN the system SHALL create a connection record scoped to the tenant.
2. WHERE local development is configured THE system SHALL authenticate to AWS using the local credential profile via the boto3 default credential chain.
3. THE system SHALL access AWS credentials only through an `AwsCredentialProvider` abstraction so that AssumeRole with temporary credentials can replace local credentials without changing business logic.
4. THE system SHALL NOT require or store long-lived customer AWS secret access keys by default.
5. WHEN a connection is created THEN the system SHALL validate the required read-only permissions and display the permission status.
6. THE system SHALL display the AWS account ID, connection status, last successful sync per data type, permission status, and data coverage.
7. WHERE a required permission is missing THE system SHALL report which capability is unavailable rather than failing silently.
8. THE system SHALL default every connection to read-only mode.

### Requirement 2: Cost Ingestion and Normalization

**User Story:** As a developer, I want AWS cost data ingested and normalized, so that I can see consistent spending information regardless of the underlying AWS source.

#### Acceptance Criteria

1. THE system SHALL retrieve cost data via a `CostProvider` abstraction with at least a `CostExplorerProvider` implementation.
2. THE system SHALL provide a `DetailedBillingProvider` implementation seam for CUR/Data Exports that can be enabled later without changing consumers.
3. WHEN cost data is ingested THEN the system SHALL normalize it into a canonical `CostRecord` model.
4. THE system SHALL allow `resource_id` to be null on a `CostRecord` because not every AWS cost line maps to a resource.
5. WHEN the same cost sync runs more than once for the same period THEN the system SHALL NOT create duplicate cost records (idempotency).
6. IF AWS cost data is unavailable THEN the system SHALL surface the failure state and SHALL NOT display a false zero cost.
7. THE system SHALL store the provider source and ingestion timestamp on normalized records.

### Requirement 3: Resource Discovery

**User Story:** As a developer, I want the system to discover my AWS resources, so that I can see an inventory of what exists and what it costs.

#### Acceptance Criteria

1. THE system SHALL discover resources for at least EC2, EBS, S3, and RDS in V1.
2. WHEN a resource is discovered THEN the system SHALL persist a `Resource` record including provider resource ID, ARN, service, resource type, region, account, state, tags, creation time, and metadata when available.
3. THE system SHALL enforce uniqueness of a provider resource ID within an account.
4. WHEN resource sync runs more than once THEN the system SHALL update existing records rather than duplicating them (idempotency).
5. WHERE a field is not available from AWS THE system SHALL store it as null rather than fabricating a value.
6. THE system SHALL access resource discovery through provider interfaces so additional services can be added without changing consumers.

### Requirement 4: Ownership and Attribution

**User Story:** As a developer, I want to know who or what project owns an expensive resource, so that I can hold the right people or teams accountable.

#### Acceptance Criteria

1. THE system SHALL implement a dedicated `AttributionEngine` that produces an `AttributionResult` for each resource.
2. THE system SHALL evaluate attribution evidence using a configurable precedence: explicit product mapping, explicit owner tag, project/environment tags, IAM/Identity Center identity, CloudTrail creator/activity, resource metadata, manual mapping, then Unknown.
3. THE system SHALL support configurable evidence weights.
4. WHEN attribution completes THEN the system SHALL record status as one of ATTRIBUTED, SHARED, UNKNOWN, or DISPUTED, along with a confidence value in the range 0–1 and a list of evidence items.
5. IF ownership cannot be established THEN the system SHALL mark the resource as UNKNOWN or SHARED and SHALL NOT fabricate an owner.
6. THE system SHALL store attribution in a dedicated `Attribution` record separate from the `Resource` record.
7. THE system SHALL support manual ownership mapping that overrides or supplements inferred attribution.
8. THE system SHALL retain attribution validity windows (`valid_from`, `valid_to`) so historical attribution is preserved.

### Requirement 5: Cost Allocation and Reconciliation

**User Story:** As a developer, I want every dollar of spend to be accounted for, so that I can trust the numbers.

#### Acceptance Criteria

1. WHEN cost is allocated for a selected period THEN the system SHALL partition total cost into Attributed, Shared, and Unknown.
2. THE system SHALL guarantee that Total = Attributed + Shared + Unknown for any selected time range.
3. IF any discrepancy exists between total AWS cost and the sum of allocations THEN the system SHALL surface it rather than hiding it.
4. THE system SHALL NOT silently discard unallocated cost.
5. THE system SHALL provide a reconciliation test that validates the allocation invariant.

### Requirement 6: Cost Overview and Exploration

**User Story:** As a developer, I want to see current and historical spending with breakdowns, so that I can understand what is changing.

#### Acceptance Criteria

1. THE system SHALL display current-period spend, a previous comparable period, forecast, and budget on the overview.
2. THE system SHALL display a daily spend trend, top services, top resources, top owners, unknown/shared spend, and attribution coverage.
3. THE system SHALL provide a cost explorer with filters for date range, service, region, resource, owner, team, project, environment, tags, and attribution status.
4. THE system SHALL provide Total, Trend, Breakdown, and Table views, each allowing drill-down.
5. THE system SHALL represent investigation filters in URL query parameters so investigations are shareable and reproducible.

### Requirement 7: Event Timeline and Correlation

**User Story:** As a developer, I want a chronological view connecting cost changes with infrastructure activity, so that I can investigate why spending changed.

#### Acceptance Criteria

1. THE system SHALL ingest relevant CloudTrail events and normalize them into an `Event` model.
2. THE system SHALL support event types including resource created/updated/deleted, API action, GitHub PR opened/merged, deployment, cost anomaly, budget threshold, recommendation created, and remediation approved/executed.
3. THE system SHALL correlate cost changes with events through a `Correlation` record using types TEMPORAL, RESOURCE_MATCH, ACTOR_MATCH, DEPLOYMENT_MATCH, and USAGE_MATCH.
4. THE system SHALL express correlation strength as a score that represents evidence, not mathematical proof of causality.
5. THE system SHALL present the timeline as evidence and SHALL NOT claim causality without sufficient supporting evidence.
6. WHERE a CloudTrail event does not map cleanly to a billable resource THE system SHALL still record it without forcing an incorrect resource assignment.

### Requirement 8: Cost Change Detection and Anomaly Detection

**User Story:** As a developer, I want the system to detect and classify significant cost changes, so that I am alerted to problems early.

#### Acceptance Criteria

1. THE system SHALL create a `CostChange` record with baseline cost, observed cost, absolute change, percentage change, classification, and confidence.
2. THE system SHALL classify changes as GROWTH, ENGINEERING_CHANGE, WASTE, SUSPICIOUS, or UNKNOWN using deterministic/statistical rules in V1.
3. THE system SHALL detect anomalies using deterministic methods including rolling 7-day and 30-day averages, standard deviation, and configurable multiplier or z-score thresholds.
4. THE system SHALL NOT require machine learning for anomaly detection in V1.
5. WHEN an anomaly is detected THEN the system SHALL store an `Anomaly` record including severity, baseline, observed, difference, algorithm, confidence, status, and evidence.
6. THE system SHALL make anomaly thresholds configurable.

### Requirement 9: Waste Detection

**User Story:** As a developer, I want the system to identify obvious waste, so that I can reduce unnecessary spending.

#### Acceptance Criteria

1. THE system SHALL implement `WasteRule` and `WasteFinding` abstractions.
2. THE system SHALL detect at least: unattached EBS volumes, idle EC2 instances, continuously running development resources, and resources missing required ownership/project/environment metadata.
3. WHEN a waste finding is produced THEN it SHALL include estimated monthly savings, confidence, risk, and evidence.
4. THE system SHALL NOT classify a resource as waste solely because utilization is low; it SHALL show evidence and confidence.
5. WHERE utilization metrics are required THE system SHALL read them from CloudWatch through a provider interface.

### Requirement 10: Forecasting

**User Story:** As a developer, I want a transparent forecast of current-period spend, so that I can anticipate the bill.

#### Acceptance Criteria

1. THE system SHALL implement a `ForecastEngine` that computes forecast as current spend plus average daily spend times remaining days.
2. THE system SHALL display period, current spend, forecast, a confidence/quality indicator, and the methodology.
3. THE system SHALL NOT present a forecast as an exact value.

### Requirement 11: Budgets and Alerts

**User Story:** As a developer, I want to configure budgets and receive alerts, so that I am warned before overspending.

#### Acceptance Criteria

1. THE system SHALL allow configuring monthly company, project, team, and optional service budgets.
2. THE system SHALL support configurable alert thresholds with defaults at 50%, 75%, 90%, and 100%.
3. WHEN spend crosses a configured threshold THEN the system SHALL record a budget threshold event.

### Requirement 12: Recommendations

**User Story:** As a developer, I want actionable recommendations, so that I know exactly what to do to reduce cost.

#### Acceptance Criteria

1. THE system SHALL implement a `RecommendationEngine` that consumes anomalies, waste findings, forecast, budget, resource, and attribution.
2. WHEN a recommendation is produced THEN it SHALL include problem, affected resource, evidence, estimated savings, confidence, action type, risk, and required permission.
3. THE system SHALL support action types NONE, STOP_RESOURCE, SCHEDULE_RESOURCE, DELETE_RESOURCE, CHANGE_CONFIGURATION, and REVIEW.
4. THE MVP recommendation engine SHALL mostly produce REVIEW actions.

### Requirement 13: Pricing

**User Story:** As a developer, I want cost estimates based on legitimate pricing data, so that estimates are accurate and traceable.

#### Acceptance Criteria

1. THE system SHALL access pricing only through a `PricingProvider` abstraction exposing a `get_price(service, region, resource_type, parameters)` method.
2. THE system SHALL source pricing from the AWS Price List API and cache results.
3. THE system SHALL NOT hard-code cost numbers in application logic.
4. WHEN a price is used in an estimate THEN the system SHALL store the pricing source and timestamp.

### Requirement 14: GitHub Integration and PR Cost Estimation

**User Story:** As a developer, I want a pull request to show the estimated cost impact of supported infrastructure changes, so that I can catch expensive changes before merging.

#### Acceptance Criteria

1. THE system SHALL integrate with GitHub via an OAuth/App integration and persist `GithubInstallation`, `GithubRepository`, `GithubPullRequest`, `GithubCommit`, and `GithubDeployment` entities.
2. THE system SHALL allow linking a repository to a project and environment.
3. WHEN a PR changes supported infrastructure definitions THEN the system SHALL parse the changed files, resolve pricing, and produce a `CostEstimate` with an estimated monthly delta and line items.
4. THE system SHALL initially support a narrow, well-tested set of infrastructure definitions (EC2, RDS, EBS, S3) and SHALL NOT claim full Terraform support until implemented and tested.
5. THE system SHALL post a GitHub comment showing the estimated monthly change, category breakdown, and budget impact, clearly labeled as an estimate.
6. THE system SHALL keep PR cost calculation deterministic and traceable.

### Requirement 15: Actual vs Predicted Variance

**User Story:** As a developer, I want to compare predicted PR cost against actual cost, so that I can learn how accurate estimates are.

#### Acceptance Criteria

1. WHEN both a `CostEstimate` and subsequent `ActualCost` exist THEN the system SHALL compute absolute and percentage variance via a `VarianceEngine`.
2. THE system SHALL produce possible reasons for variance with confidence.
3. THE system SHALL NOT claim the PR caused all observed variance unless evidence supports it.

### Requirement 16: Safe Actions and Remediation

**User Story:** As a developer, I want to approve remediation recommendations, so that I can act on them safely without risk of automatic destructive changes.

#### Acceptance Criteria

1. THE system SHALL NOT let recommendation generation directly execute AWS actions.
2. WHEN a user approves a remediation THEN the system SHALL route it through user approval, an `ActionPolicyEngine`, an AWS action executor, and an audit log, in that order.
3. THE `ActionPolicyEngine` SHALL check user authorization, resource protection, environment, action type, account, explicit approval, and current resource state before any write action.
4. THE system SHALL protect production resources by default.
5. THE system SHALL NOT perform automatic destructive actions by default.
6. THE system SHALL NOT perform any AWS write action in the initial read-only MVP.
7. WHERE write roles are used THE system SHALL use a separate IAM write role distinct from the read role.

### Requirement 17: AI Explanations

**User Story:** As a developer, I want plain-language explanations of cost changes, so that I can understand them quickly.

#### Acceptance Criteria

1. THE system SHALL use Groq as the LLM provider with the model name configurable via environment configuration.
2. THE system SHALL pass only deterministic facts, numbers, events, and evidence to the AI layer.
3. THE AI layer SHALL NOT invent costs, resources, or causal claims.
4. IF the AI provider is unavailable OR facts are insufficient THEN the system SHALL fall back to a deterministic templated explanation.
5. THE UI SHALL visually distinguish AI-generated text from deterministic facts.

### Requirement 18: Multi-Tenancy and Data Isolation

**User Story:** As a platform operator, I want strict tenant isolation, so that no tenant can access another tenant's data.

#### Acceptance Criteria

1. THE system SHALL include a `tenant_id` on every persistent business record.
2. THE system SHALL scope every query to the authenticated tenant.
3. THE system SHALL NOT trust tenant IDs supplied by the browser without server-side authorization checks.
4. THE system SHALL enforce tenant ownership validation on data access.
5. THE system SHALL map Clerk Organizations to tenants.

### Requirement 19: Authentication and Authorization

**User Story:** As a team lead, I want role-based access control, so that only authorized people can perform sensitive operations.

#### Acceptance Criteria

1. THE system SHALL require authenticated users on all endpoints except public health checks.
2. THE system SHALL authenticate application users through Clerk, keeping application identity separate from AWS identity.
3. THE system SHALL support roles OWNER, ADMIN, MEMBER, and VIEWER derived from Clerk Organization roles.
4. THE system SHALL restrict connecting AWS, changing policies, approving remediation, and managing team members to OWNER and ADMIN roles.
5. THE system SHALL perform server-side authorization on every sensitive endpoint.

### Requirement 20: Synchronization and Idempotency

**User Story:** As a developer, I want reliable background synchronization, so that data stays current without duplication or corruption.

#### Acceptance Criteria

1. THE system SHALL maintain an `AwsConnection` sync state with last cost/resource/event sync timestamps and last error.
2. THE system SHALL implement CostSyncJob, ResourceSyncJob, CloudTrailSyncJob, MetricsSyncJob, AggregationJob, and AnomalyDetectionJob as background jobs using Celery with Redis.
3. THE system SHALL make all ingestion jobs idempotent so re-running does not duplicate costs, resources, events, or anomalies.
4. WHEN a transient AWS/API failure occurs THEN the job SHALL retry with exponential backoff, record the last error, and remain resumable.
5. IF a sync fails THEN the system SHALL NOT corrupt existing data.

### Requirement 21: Audit Logging

**User Story:** As a compliance-conscious operator, I want every sensitive action logged, so that there is an accountable record.

#### Acceptance Criteria

1. WHEN a sensitive action occurs THEN the system SHALL write an `AuditLog` entry with actor, action, resource, AWS API, request summary, approval ID, result, and timestamp.
2. THE system SHALL NOT store sensitive secrets in the audit log.
3. THE system SHALL retain audit logs longer than detailed cost records.

### Requirement 22: Security

**User Story:** As a security-conscious user, I want the platform to follow least-privilege and encryption practices, so that my AWS account and data are safe.

#### Acceptance Criteria

1. THE system SHALL use a read-only AWS IAM role by default and SHALL NOT request AdministratorAccess or broad `*:*` permissions.
2. THE system SHALL NOT use AWS root credentials.
3. THE system SHALL derive the final IAM policy from actual API usage and minimize it.
4. THE system SHALL encrypt stored secrets/configuration and encrypt data in transit.
5. THE system SHALL NOT log secrets.
6. THE system SHALL separate read and write AWS permissions.

### Requirement 23: Observability

**User Story:** As an operator, I want structured logs and metrics, so that I can monitor system health and sync performance.

#### Acceptance Criteria

1. THE system SHALL log request ID, tenant ID, job ID, AWS account ID, sync duration, records processed, records failed, API latency, and error category.
2. THE system SHALL emit metrics including aws_sync_success, aws_sync_failure, cost_records_ingested, resources_synced, events_processed, attribution_coverage, anomalies_detected, recommendations_created, and github_estimates_created.

### Requirement 24: Data Retention and Constraints

**User Story:** As an operator, I want sensible retention and database integrity, so that storage stays bounded and data stays consistent.

#### Acceptance Criteria

1. THE system SHALL retain detailed cost records for a configurable window defaulting to 12 months, normalized events for 90–180 days, and aggregated cost and audit data longer.
2. THE system SHALL enforce database constraints including unique provider resource IDs within an account, unique provider event IDs where possible, foreign-key integrity, non-negative cost validation, and confidence values within 0–1.
3. THE system SHALL NOT retain raw CloudTrail data unnecessarily when only normalized fields are required.

### Requirement 25: Engineering Guardrails

**User Story:** As the engineering owner, I want architectural guardrails enforced, so that the system stays maintainable and trustworthy.

#### Acceptance Criteria

1. THE system SHALL NOT introduce microservices or Kubernetes without a concrete requirement.
2. THE system SHALL keep all provider-specific code behind interfaces.
3. THE system SHALL keep billing calculations deterministic and outside the AI path.
4. THE system SHALL include tests for every attribution rule and cost calculation rule.
5. THE system SHALL keep interfaces and the data model capable of supporting the full future loop (Predict → Deploy → Measure → Attribute → Explain → Act) even where a phase is not yet implemented.
