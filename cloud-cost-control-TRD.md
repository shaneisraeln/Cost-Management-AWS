# Technical Requirements Document (TRD)
# Cloud Cost Control Platform

**Version:** 1.0  
**Status:** Build-ready MVP specification  
**Architecture:** AWS-first, read-only by default  
**Audience:** Coding agent + engineering team

---

# 1. Technical Objective

Build a secure multi-tenant web application that connects to an AWS account, ingests cost/usage and resource/activity data, normalizes it, attributes cost to resources/projects/users, detects anomalies and waste, exposes an investigation timeline, and provides a foundation for GitHub-based infrastructure cost estimation.

The system must be designed so that **read-only operation is the default** and all future write operations are isolated behind explicit permissions and approval.

---

# 2. Recommended Stack

## Frontend

- Next.js
- TypeScript
- Tailwind CSS
- Recharts or equivalent charting library
- TanStack Query

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## Database

- PostgreSQL

## AWS SDK

- boto3

## Authentication

Use a managed authentication provider or a well-supported application authentication library.

The authentication provider must not be confused with AWS identity. Application users and AWS principals are separate concepts.

## Background jobs

For MVP:

- Celery + Redis, OR
- a simple scheduled worker process

Keep the architecture replaceable.

## Deployment

Initial development can run locally.

Production can use:

- managed PostgreSQL
- containerized backend
- Next.js deployment
- scheduled worker

Avoid unnecessary AWS infrastructure in the product itself during MVP.

---

# 3. High-Level Architecture

```text
                         Browser
                            |
                            v
                     Next.js Frontend
                            |
                            v
                         FastAPI
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   PostgreSQL          Job Scheduler       GitHub API
        |
        |
        +-----------------------------+
        |                             |
        v                             v
 AWS Cost/Data APIs              AWS Resource APIs
        |                             |
        v                             v
 Cost Ingestion                  Resource Sync
        |
        v
 CloudTrail ingestion
        |
        v
 Event Normalization
        |
        v
 Attribution Engine
        |
        v
 Anomaly / Waste Engine
        |
        v
 Recommendation Engine
```

---

# 4. Core Data Flow

```text
AWS
 |
 +-- Cost data
 |
 +-- Resource metadata
 |
 +-- Tags
 |
 +-- CloudTrail activity
 |
 v
Ingestion
 |
 v
Raw normalized records
 |
 v
Canonical cost model
 |
 v
Attribution
 |
 v
Aggregations
 |
 v
API
 |
 v
Frontend
```

---

# 5. AWS Integration Strategy

## 5.1 Authentication

The product should use an AWS IAM role that the customer explicitly creates and allows the product to assume.

Preferred model:

```text
Customer AWS Account
        |
        | trusts product AWS role
        v
Product backend
        |
        | AssumeRole
        v
Temporary AWS credentials
```

Do not require customers to provide permanent IAM access keys.

If cross-account role assumption is not practical for the first local prototype, support a local development credential configuration, but never design the production architecture around storing customer secret keys.

---

# 6. AWS Permissions

## Read-only MVP

The final policy must be generated from actual API usage and minimized.

Expected capability categories:

### Billing/cost

- Cost Explorer
- AWS Data Exports / CUR-related access as required

### Resource discovery

Only services implemented by the MVP.

Initially prioritize:

- EC2
- EBS
- S3
- RDS

### Activity

- CloudTrail lookup/read access as required

### Metrics

- CloudWatch read access where required for waste detection

Do not request `AdministratorAccess`.

Do not request broad `*:*` permissions.

---

# 7. Billing Data Architecture

There are two cost-data paths.

## Path A — Cost Explorer

Use for:

- recent summaries
- interactive aggregates
- simple dashboards
- quick synchronization

## Path B — Detailed billing export

Use AWS's detailed cost/usage export mechanism for resource-level and historical analysis where available.

The ingestion layer must abstract the provider source.

```text
CostProvider
   |
   +-- CostExplorerProvider
   |
   +-- DetailedBillingProvider
```

This prevents the rest of the system from depending directly on one AWS API.

---

# 8. Canonical Cost Model

Create an internal normalized representation.

Suggested entity:

```text
CostRecord

id
account_id
period_start
period_end
service
region
resource_id
resource_arn
usage_type
operation
cost
currency
source
tags
metadata
created_at
```

Do not assume every AWS cost line has a resource ID.

Resource ID may be null.

---

# 9. Resource Model

```text
Resource

id
account_id
provider
provider_resource_id
arn
service
resource_type
region
state
created_at
tags
metadata
owner_id
project_id
environment
attribution_status
attribution_confidence
created_at
updated_at
```

---

# 10. User Model

```text
User

id
tenant_id
name
email
role
created_at
updated_at
```

Application users are NOT automatically equivalent to AWS IAM identities.

---

# 11. AWS Identity Model

```text
AwsIdentity

id
tenant_id
account_id
principal_type
principal_id
arn
display_name
metadata
created_at
```

Examples:

- IAM user
- assumed role
- Identity Center identity
- service principal

---

# 12. Project Model

```text
Project

id
tenant_id
name
description
budget
status
created_at
updated_at
```

---

# 13. Ownership Model

Do not place all attribution logic directly inside `Resource`.

Create an attribution record.

```text
Attribution

id
tenant_id
resource_id
owner_user_id
project_id
environment
status
confidence
source
evidence
valid_from
valid_to
created_at
```

Possible status:

```text
ATTRIBUTED
SHARED
UNKNOWN
DISPUTED
```

---

# 14. Attribution Engine

Create a dedicated service:

```text
AttributionEngine
```

Input:

```text
Resource
Tags
CloudTrail events
AWS identities
Project mappings
Manual rules
```

Output:

```text
AttributionResult
```

Example:

```json
{
  "status": "ATTRIBUTED",
  "owner_user_id": "usr_123",
  "project_id": "proj_backend",
  "confidence": 0.92,
  "evidence": [
    {
      "type": "OWNER_TAG",
      "weight": 0.60
    },
    {
      "type": "CLOUDTRAIL_CREATOR",
      "weight": 0.32
    }
  ]
}
```

Weights must be configurable.

---

# 15. Cost Allocation

After resource attribution:

```text
CostRecord
     |
     v
Resource
     |
     v
Attribution
     |
     +---- User
     |
     +---- Project
     |
     +---- Shared
     |
     +---- Unknown
```

For every selected period:

```text
Total
=
Attributed
+
Shared
+
Unknown
```

Build a reconciliation test.

The system must not silently drop unallocated cost.

---

# 16. Sync Architecture

Each AWS account gets a synchronization state.

```text
AwsConnection

id
tenant_id
account_id
role_arn
status
last_cost_sync
last_resource_sync
last_event_sync
last_error
created_at
updated_at
```

Jobs:

```text
CostSyncJob
ResourceSyncJob
CloudTrailSyncJob
MetricsSyncJob
AggregationJob
AnomalyDetectionJob
```

---

# 17. Idempotency

All ingestion jobs must be idempotent.

Running the same sync twice must not duplicate:

- costs
- resources
- events
- anomalies

Use provider IDs, timestamps, hashes, or deterministic keys as appropriate.

---

# 18. Event Model

```text
Event

id
tenant_id
account_id
event_type
timestamp
actor_identity_id
resource_id
source
raw_reference
normalized_data
created_at
```

Event types:

```text
RESOURCE_CREATED
RESOURCE_UPDATED
RESOURCE_DELETED
API_ACTION
GITHUB_PR_OPENED
GITHUB_PR_MERGED
DEPLOYMENT
COST_ANOMALY
BUDGET_THRESHOLD
RECOMMENDATION_CREATED
REMEDIATION_APPROVED
REMEDIATION_EXECUTED
```

---

# 19. CloudTrail Processing

The system should ingest relevant CloudTrail events.

Extract where available:

- actor
- timestamp
- service
- action
- resource
- region
- request parameters

Do not assume every API event maps cleanly to a billable resource.

Create a correlation layer rather than directly assigning cost from a single event.

---

# 20. Timeline Correlation

Correlation engine:

```text
CostChange
   |
   +-- time window
   +-- resource
   +-- service
   +-- actor
   +-- deployment
   +-- GitHub PR
```

Produce:

```text
Correlation

id
cost_change_id
event_id
correlation_type
score
evidence
created_at
```

Correlation types:

```text
TEMPORAL
RESOURCE_MATCH
ACTOR_MATCH
DEPLOYMENT_MATCH
USAGE_MATCH
```

The score represents evidence strength, not mathematical proof.

---

# 21. Cost Change Detection

Create a cost-change record:

```text
CostChange

id
tenant_id
period
resource_id
service
baseline_cost
observed_cost
absolute_change
percentage_change
classification
confidence
created_at
```

Classification:

```text
GROWTH
ENGINEERING_CHANGE
WASTE
SUSPICIOUS
UNKNOWN
```

V1 should use deterministic/statistical rules.

---

# 22. Anomaly Detection

Start with simple methods.

## Baseline

Calculate:

- rolling 7-day average
- rolling 30-day average when enough data exists
- standard deviation where appropriate

Example:

```text
z-score > threshold
```

or:

```text
current > average × configured_multiplier
```

Do not require ML for MVP.

Store:

```text
Anomaly

id
tenant_id
resource_id
service
detected_at
severity
baseline
observed
difference
algorithm
confidence
status
evidence
```

---

# 23. Waste Detection Engine

Create:

```text
WasteRule
WasteFinding
```

Initial rules:

### Unattached EBS

Input:

- volume state
- age
- size
- price estimate

### Idle EC2

Input:

- CPU utilization
- network activity
- runtime
- environment

### Development runtime

Input:

- environment tag
- runtime schedule
- utilization

### Missing metadata

Input:

- required tags
- ownership mapping

Every finding must contain:

```text
estimated_monthly_savings
confidence
risk
evidence
```

---

# 24. Pricing Engine

Do not hard-code cost numbers in application logic.

Create an abstraction:

```text
PricingProvider
```

Example:

```text
get_price(
    service,
    region,
    resource_type,
    parameters
)
```

The provider may use AWS pricing data or a controlled internal price cache.

Store the pricing source and timestamp for every estimate.

---

# 25. Forecast Engine

Create:

```text
ForecastEngine
```

V1:

- current spend
- elapsed period
- average daily spend
- remaining days

Example:

```text
forecast =
current_spend
+
average_daily_spend × remaining_days
```

Later versions can incorporate seasonality and workload signals.

---

# 26. Recommendation Engine

Input:

```text
Anomaly
WasteFinding
Forecast
Budget
Resource
Attribution
```

Output:

```text
Recommendation

id
tenant_id
type
resource_id
title
description
estimated_savings
confidence
risk
action_type
status
created_at
```

Action types:

```text
NONE
STOP_RESOURCE
SCHEDULE_RESOURCE
DELETE_RESOURCE
CHANGE_CONFIGURATION
REVIEW
```

MVP should mostly produce `REVIEW`.

---

# 27. Remediation Architecture

Never let recommendation generation directly execute AWS actions.

Use:

```text
Recommendation
      |
      v
User approval
      |
      v
Action request
      |
      v
Policy validation
      |
      v
AWS Action Executor
      |
      v
Audit log
```

---

# 28. Action Policy

Before any write action:

```text
ActionPolicyEngine
```

checks:

- user authorization
- resource protection
- environment
- action type
- account
- explicit approval
- current resource state

Production resources should be protected by default.

---

# 29. Audit Log

Every sensitive action:

```text
AuditLog

id
tenant_id
actor_user_id
action
resource_id
aws_api
request_summary
approval_id
result
timestamp
```

Do not store sensitive secrets.

---

# 30. GitHub Architecture

Use GitHub OAuth/App integration.

Entities:

```text
GithubInstallation
GithubRepository
GithubPullRequest
GithubCommit
GithubDeployment
```

Relations:

```text
Repository
   ↓
Project
   ↓
Environment
```

---

# 31. PR Cost Estimation

Create:

```text
CostEstimate

id
tenant_id
repository_id
pr_number
base_commit
head_commit
estimated_monthly_delta
currency
line_items
source
status
created_at
```

The estimator should initially support a narrow set of infrastructure definitions.

Example:

```text
EC2 instance
RDS instance
EBS volume
S3 storage
```

Do not claim full Terraform support until it is implemented and tested.

---

# 32. Cost Estimate Pipeline

```text
GitHub PR
   |
   v
Retrieve changed files
   |
   v
Detect supported infrastructure
   |
   v
Parse configuration
   |
   v
Resolve pricing
   |
   v
Calculate base cost
   |
   v
Calculate changed cost
   |
   v
Generate CostEstimate
   |
   v
Post GitHub comment
```

---

# 33. Actual vs Predicted

After deployment:

```text
CostEstimate
     +
ActualCost
     |
     v
VarianceEngine
```

Output:

```text
predicted
actual
absolute_variance
percentage_variance
possible_reasons
confidence
```

Never claim that the PR caused all observed variance unless evidence supports it.

---

# 34. API Structure

Suggested routes:

```text
/api/v1/auth/*
/api/v1/aws/connections
/api/v1/aws/connections/{id}/sync
/api/v1/costs
/api/v1/costs/summary
/api/v1/costs/breakdown
/api/v1/resources
/api/v1/resources/{id}
/api/v1/attributions
/api/v1/projects
/api/v1/users
/api/v1/events
/api/v1/timeline
/api/v1/anomalies
/api/v1/waste
/api/v1/recommendations
/api/v1/budgets
/api/v1/github/installations
/api/v1/github/repositories
/api/v1/github/pull-requests
/api/v1/estimates
/api/v1/audit-logs
```

---

# 35. Multi-Tenancy

Every persistent business record must contain:

```text
tenant_id
```

Every query must be tenant-scoped.

Never trust tenant IDs supplied by the browser without authorization checks.

Recommended structure:

```text
Tenant
 ├── Users
 ├── AWS Connections
 ├── Resources
 ├── Costs
 ├── Projects
 ├── Events
 ├── Recommendations
 └── GitHub installations
```

---

# 36. Database Constraints

Important constraints:

- unique AWS account connection per tenant where appropriate
- unique provider resource ID within account
- unique event/provider IDs where possible
- foreign-key integrity
- non-negative cost validation where applicable
- valid confidence range 0–1
- valid tenant ownership

---

# 37. Data Retention

MVP default:

- detailed cost records: configurable, initially 12 months
- normalized events: 90–180 days
- aggregated cost data: longer retention
- audit logs: longer retention

Do not retain raw CloudTrail data unnecessarily if only normalized fields are required.

---

# 38. Observability

Backend must log:

- request ID
- tenant ID
- job ID
- AWS account ID
- sync duration
- records processed
- records failed
- API latency
- error category

Metrics:

```text
aws_sync_success
aws_sync_failure
cost_records_ingested
resources_synced
events_processed
attribution_coverage
anomalies_detected
recommendations_created
github_estimates_created
```

---

# 39. Error Handling

AWS/API failures must not corrupt existing data.

Jobs should:

- retry transient failures
- use exponential backoff
- record last error
- remain resumable
- avoid duplicate ingestion

UI should show:

```text
Last successful sync:
2 hours ago

Current status:
Sync delayed

Reason:
AWS API unavailable
```

Do not show a false zero cost when data is unavailable.

---

# 40. Security Architecture

### Authentication

All application endpoints except public health checks require authenticated users.

### Authorization

Roles:

```text
OWNER
ADMIN
MEMBER
VIEWER
```

Only OWNER/ADMIN can:

- connect AWS
- change policies
- approve remediation
- manage team members

### AWS

- AssumeRole
- temporary credentials
- least privilege
- separate read/write roles later

### Secrets

- never log secrets
- encrypt at rest
- rotate where applicable

---

# 41. AI Architecture

AI is NOT a source of financial truth.

The deterministic backend produces:

```text
facts
numbers
events
evidence
recommendations
```

AI may convert these into natural language.

Example input:

```json
{
  "cost_change": 28.4,
  "resource": "ml-worker",
  "baseline": 2.1,
  "observed": 30.5,
  "events": [
    "EC2 created",
    "deployment occurred"
  ]
}
```

AI output:

> "Spending increased mainly because ml-worker was created and ran continuously."

The AI must not invent costs or resources.

---

# 42. Frontend State

Use server-state management for:

- costs
- resources
- anomalies
- recommendations
- AWS connection state

URL query parameters should represent investigation filters where practical.

Example:

```text
/costs?from=2026-09-01&to=2026-09-07&service=EC2
```

This makes investigations shareable and reproducible.

---

# 43. Frontend Pages

```text
/
  Overview

/costs
  Cost explorer

/resources
  Resource inventory

/resources/:id
  Resource detail

/people
  People spending

/projects
  Project spending

/alerts
  Anomalies

/timeline
  Event timeline

/recommendations
  Waste and actions

/github
  GitHub integration

/settings/aws
  AWS connection

/settings/team
  Team management

/settings/policies
  Budgets and automation policies
```

---

# 44. Resource Detail Page

Must answer:

```text
What is this?
How much does it cost?
Who owns it?
Why is it expensive?
What happened recently?
What can I do?
```

Sections:

- identity
- cost
- utilization
- ownership
- tags
- activity
- timeline
- recommendations
- audit history

---

# 45. Testing Strategy

## Unit tests

- cost normalization
- allocation
- attribution scoring
- forecasting
- anomaly detection
- waste rules
- pricing calculations
- authorization

## Integration tests

- AWS API adapters
- PostgreSQL
- CloudTrail parsing
- GitHub API

## End-to-end

Canonical scenario:

```text
Connect AWS
→ sync
→ resource discovered
→ cost ingested
→ attribution generated
→ anomaly detected
→ recommendation created
→ UI displays evidence
```

---

# 46. AWS Test Environment

Do not test destructive actions against production.

Create a dedicated test environment/account if possible.

Use:

- tagged test resources
- low-cost resources
- mock AWS responses for most automated tests

For action tests, use explicit disposable resources.

---

# 47. Development Phases

## Phase 0 — Foundation

- monorepo
- authentication
- PostgreSQL
- migrations
- tenant model
- API skeleton
- frontend shell
- CI

## Phase 1 — AWS Connection

- IAM role onboarding
- permission validation
- account discovery
- connection persistence

## Phase 2 — Cost

- Cost Explorer adapter
- detailed billing adapter
- normalization
- cost database
- overview UI

## Phase 3 — Resources

- EC2
- EBS
- S3
- RDS
- tags
- inventory

## Phase 4 — Attribution

- user mapping
- project mapping
- CloudTrail ingestion
- confidence
- unknown/shared
- reconciliation

## Phase 5 — Investigation

- timeline
- cost change detection
- anomaly detection
- explanations

## Phase 6 — Optimization

- idle/unused rules
- savings estimation
- recommendations

## Phase 7 — GitHub

- GitHub App
- PR detection
- basic cost estimator
- PR comments

## Phase 8 — Safe actions

Only after read-only system is reliable:

- action approval
- IAM write role
- protected resources
- EC2 stop action
- audit logging

---

# 48. Definition of Done for MVP

The MVP is complete when a real AWS account can be connected and the application can perform the following end-to-end:

```text
AWS Account
    ↓
Secure connection
    ↓
Cost ingestion
    ↓
Resource discovery
    ↓
Ownership attribution
    ↓
Cost reconciliation
    ↓
Anomaly detection
    ↓
Event timeline
    ↓
Actionable recommendation
```

and the user can understand:

> **What we spent → what caused it → who owns it → why it changed → what we can do.**

GitHub integration should be considered an MVP-extension milestone, not a blocker for the first working product.

---

# 49. Engineering Guardrails

The coding agent MUST:

1. Not introduce microservices without a concrete requirement.
2. Not introduce Kubernetes.
3. Not use AWS root credentials.
4. Not store long-lived customer AWS secrets by default.
5. Not request AdministratorAccess.
6. Not perform AWS write actions in the initial MVP.
7. Not fabricate missing cost/resource data.
8. Not silently discard unknown/unallocated costs.
9. Not claim causal relationships without evidence.
10. Keep provider-specific code behind interfaces.
11. Keep billing calculations deterministic.
12. Keep AI outside the financial source-of-truth path.
13. Write tests for every attribution and cost calculation rule.
14. Make sync jobs idempotent.
15. Keep all tenant data isolated.

---

# 50. Architecture North Star

The architecture must preserve this future flow:

```text
                         ENGINEERING
                              |
                         GitHub / CI
                              |
                              v
                       COST PREDICTION
                              |
                              v
                         DEPLOYMENT
                              |
                              v
 AWS ------------------> ACTUAL USAGE
  |                           |
  |                           v
  +--------------------> ACTUAL COST
                              |
                              v
                         ATTRIBUTION
                              |
                              v
                       EVENT TIMELINE
                              |
                 +------------+------------+
                 |            |            |
                 v            v            v
              GROWTH        WASTE       SUSPICIOUS
                 |            |            |
                 +------------+------------+
                              |
                              v
                          EXPLANATION
                              |
                              v
                       RECOMMENDATION
                              |
                              v
                       USER APPROVAL
                              |
                              v
                       SAFE AWS ACTION
                              |
                              v
                           AUDIT
```

The MVP may implement only the left and middle portions, but its interfaces and data model must not prevent the complete loop.

---

# 51. Final Technical Principle

**Build the smallest working system that creates a trustworthy chain from AWS cost to AWS resource to ownership to evidence.**

Everything else—AI, GitHub cost prediction, automation, multi-cloud, advanced optimization—should be layered on top of that trustworthy foundation.
