# Product Requirements Document (PRD)
# Cloud Cost Control Platform

**Version:** 1.0  
**Status:** Build-ready MVP specification  
**Target:** Small AWS-first engineering teams (2–20 developers)

---

## 1. Product Definition

### 1.1 One-line product

A developer-first cloud cost control platform that connects **AWS spending, resources, activity, ownership, and GitHub changes** so engineering teams can understand what caused cloud costs, predict cost impact, detect waste/anomalies, and safely act on them.

### 1.2 Core product promise

The product must answer four questions:

1. **What are we spending?**
2. **What resource/workload caused it?**
3. **Who or what project is responsible?**
4. **Why did it change, and what should we do?**

The long-term loop is:

```text
Code / PR
   ↓
Infrastructure change
   ↓
Estimated cost
   ↓
Deploy
   ↓
Actual usage + cost
   ↓
Attribution
   ↓
Detect change/anomaly/waste
   ↓
Explain
   ↓
Recommend action
   ↓
User-approved remediation
```

The dashboard is an interface to this loop, not the product itself.

### 1.3 Target user

Primary user:

- Founder
- Lead developer
- Small engineering team member
- Developer responsible for an AWS account

Target environment:

- 2–20 engineers
- AWS-first
- No dedicated FinOps team
- Wants fast onboarding
- Wants actionable cost information rather than enterprise accounting complexity

### 1.4 Non-goals

V1 will NOT attempt to be:

- A replacement for AWS Billing/Cost Explorer
- A full enterprise FinOps suite
- A multi-cloud platform
- A Kubernetes cost platform
- An autonomous infrastructure administrator
- A complete Terraform cost estimator
- An accounting system
- A production incident-management platform

AWS is the only supported cloud provider in V1.

---

# 2. Product Principles

### P1 — Read-only first

The initial product must never modify customer infrastructure.

### P2 — Explain before acting

Every recommendation must show:

- what was detected
- evidence
- estimated impact
- confidence
- proposed action

### P3 — Never invent attribution

If ownership cannot be established, mark the cost as **Unknown** or **Shared**.

### P4 — Separate facts from inference

The UI must distinguish:

- AWS-provided facts
- calculated values
- inferred relationships
- AI-generated explanations

### P5 — Every dollar must reconcile

For a selected time range:

```text
Total AWS cost
=
Attributed
+ Shared
+ Unknown
```

Any discrepancy must be surfaced.

### P6 — Developer-first language

Avoid FinOps jargon where possible. Say:

> "This EC2 instance cost $18"

rather than:

> "This resource incurred an unallocated compute expenditure."

---

# 3. MVP Scope

The MVP consists of seven capabilities:

1. AWS account connection
2. Cost ingestion and normalization
3. Resource discovery
4. Ownership/attribution
5. Cost timeline and anomaly detection
6. Cost explanations and recommendations
7. GitHub PR cost estimation foundation

MVP automation remains **user-approved only**.

---

# 4. User Stories

## 4.1 Connect AWS

As a founder, I want to connect my AWS account securely so the application can read cost and resource information.

Acceptance:

- Connection can be created without storing long-lived AWS secret keys.
- IAM permissions are clearly displayed.
- Connection status is visible.
- Read-only mode is default.

## 4.2 View spending

As a developer, I want to see current and historical AWS spending.

Acceptance:

- Current month cost
- Previous-period comparison
- Daily trend
- Service breakdown
- Region breakdown where available
- Resource-level data where available

## 4.3 Find ownership

As a developer, I want to know who owns an expensive resource.

Acceptance:

- Resource owner
- Project
- Environment
- Attribution source
- Attribution confidence
- Unknown/Shared state

## 4.4 Investigate a spike

As a developer, I want to understand why spending changed.

Acceptance:

- Detect significant change
- Show affected services/resources
- Show relevant activity/events
- Correlate deployment/resource changes where possible
- Give a human-readable explanation
- Show confidence

## 4.5 Detect waste

As a developer, I want the system to identify obvious waste.

Initial examples:

- Idle EC2 instance
- Unattached EBS volume
- Development resource running continuously
- Resources missing ownership metadata

Recommendations must include estimated savings where calculable.

## 4.6 GitHub cost estimation

As a developer, I want a pull request to show the estimated cost impact of supported infrastructure changes.

V1 may initially support a narrow set of infrastructure inputs rather than all Terraform/AWS resources.

Acceptance:

- PR can be linked to an environment/project.
- Estimated monthly cost delta is calculated.
- Estimate is clearly labeled as an estimate.
- Cost calculation is deterministic and traceable.

## 4.7 Safe action

As a developer, I want to approve a remediation recommendation.

MVP:

- Show action
- Require explicit confirmation
- Log action
- Do not perform destructive actions automatically

Actual write actions may be enabled only after the read-only MVP is stable and tested.

---

# 5. Core Product Modules

## 5.1 Account Connection

UI:

```text
Connect AWS
    ↓
Choose account
    ↓
Configure IAM role
    ↓
Validate permissions
    ↓
Connected
```

The connection page must show:

- AWS account ID
- connection status
- last successful sync
- permission status
- data coverage

---

## 5.2 Cost Overview

The overview should answer:

> "How much are we spending and what's changing?"

Required:

- Current period spend
- Previous comparable period
- Forecast
- Budget
- Daily spend chart
- Top services
- Top resources
- Top owners
- Unknown/shared spend
- Attribution coverage

Example:

```text
September

Spend          $184.21
Forecast       $241.70
Budget         $300.00

Attribution    93%

Top driver:
EC2 / production-worker
```

---

## 5.3 Cost Explorer

Filters:

- Date range
- Service
- Region
- Resource
- Owner
- Team
- Project
- Environment
- Tags
- Attribution status

Views:

- Total
- Trend
- Breakdown
- Table

Every visualization must allow drilling down.

---

## 5.4 Resource Inventory

Each resource record should contain, when available:

- AWS resource ID
- ARN
- resource type
- service
- region
- account
- tags
- creation time
- current state
- owner
- project
- environment
- estimated/current cost
- attribution source
- attribution confidence

---

# 6. Attribution Engine

This is a core differentiator and must be treated as a first-class subsystem.

## 6.1 Attribution hierarchy

Use strongest evidence first.

Suggested precedence:

1. Explicit product mapping
2. Explicit owner tag
3. Project/environment tags
4. IAM/Identity Center identity associated with activity
5. CloudTrail creator/activity
6. Resource metadata
7. Manual mapping
8. Unknown

The exact precedence must be configurable.

## 6.2 Attribution result

Each resource/cost allocation should produce:

```json
{
  "owner": "user_id",
  "project": "backend",
  "environment": "development",
  "status": "attributed",
  "confidence": 0.91,
  "evidence": [
    "owner_tag",
    "cloudtrail_creator"
  ]
}
```

Possible status:

- attributed
- shared
- unknown
- disputed

## 6.3 Never fake certainty

Example:

```text
EC2: $40

Owner: Shane
Confidence: 92%
Evidence:
✓ owner tag
✓ creator activity
```

For uncertain data:

```text
RDS: $120

Owner: Backend team
Confidence: 58%
Status: Shared
```

---

# 7. Event Timeline

The product must provide a chronological view connecting cost changes with infrastructure activity.

Example:

```text
10:32  PR #142 opened
11:04  PR #142 merged
11:06  deployment started
11:10  EC2 resource created
13:00  usage increased
13:20  cost anomaly detected
```

Event types:

- GitHub PR opened
- PR merged
- deployment
- resource created
- resource modified
- resource deleted
- cost spike
- budget threshold
- anomaly
- recommendation
- remediation action

The timeline is evidence, not proof of causality.

---

# 8. Cost Change Classification

When spending changes, classify it where evidence allows:

### Growth

Cost increased because usage/traffic increased.

### Engineering change

Cost changed after a deployment/infrastructure change.

### Waste

Cost is associated with underused/unneeded resources.

### Security/suspicious activity

Behavior is significantly outside normal patterns.

### Unknown

Insufficient evidence.

Classification must include confidence.

---

# 9. Anomaly Detection

V1 should use deterministic statistical rules before ML.

Examples:

### Daily spike

```text
today > rolling_average × threshold
```

### Resource spike

```text
resource_cost > historical_baseline × threshold
```

### New resource

Detect newly created costly resources.

### Unusual activity

Detect unusual:

- creation time
- region
- instance type
- quantity
- identity

An anomaly contains:

```text
severity
detected_at
resource
owner
baseline
actual
difference
evidence
confidence
status
```

---

# 10. Waste Detection

Initial rules:

## Idle EC2

Potentially idle based on available utilization metrics.

Do not call a resource waste solely because utilization is low; show the evidence and confidence.

## Unattached EBS

An unattached volume may be unnecessary.

## Development resources

Identify development resources that run continuously.

## Missing metadata

Resources without ownership/project/environment information.

Output:

```text
Potential waste

Resource: dev-server
Current cost: $41/month
Potential saving: $35/month

Why:
Low activity + development environment + continuous runtime

[Review]
```

---

# 11. Forecasting

V1 uses a transparent baseline forecast.

Example:

```text
Forecast =
current spend
+
expected remaining spend
```

Forecast must show:

- period
- current spend
- forecast
- confidence/quality indicator
- methodology

Do not present an estimate as exact.

---

# 12. Budgets

Users can configure:

- monthly company budget
- project budget
- team budget
- optional service budget

Alerts:

- 50%
- 75%
- 90%
- 100%

Thresholds should be configurable.

---

# 13. GitHub Integration

## V1 goal

Connect GitHub repositories to projects/environments.

The system should be able to associate:

```text
GitHub PR
→ repository
→ project
→ infrastructure change
→ estimated cost
```

The first implementation should support a narrow, well-tested infrastructure format rather than pretending to support every infrastructure-as-code system.

## PR comment

Example:

```text
Cloud Cost Impact

Estimated monthly change: +$42

Compute       +$31
Storage        +$4
Database       +$7

Budget impact:
Current       $180
After PR      $222

Status: PASS
```

---

# 14. Actual vs Predicted

When both values exist:

```text
Predicted: $42/month
Actual:    $57/month
Variance:  +$15/month
```

The system should investigate likely reasons:

- usage higher than assumed
- resource sizing difference
- additional resources
- longer runtime
- pricing/data mismatch

Never claim causality without sufficient evidence.

---

# 15. Recommendations

Recommendations must be actionable.

Bad:

> "EC2 is expensive."

Good:

> "This development EC2 instance has low observed utilization and has been running continuously. Stopping it outside working hours could save approximately $28/month."

Each recommendation contains:

- problem
- affected resource
- evidence
- estimated savings
- confidence
- action
- risk
- required permission

---

# 16. Automation Roadmap

### Phase A

Read-only.

### Phase B

User-approved action.

### Phase C

Scheduled safe actions.

Examples:

- stop development EC2 at night
- start it in the morning
- clean explicitly approved unused resources

### Phase D

Policy-based automation.

Never enable automatic destructive actions by default.

Production resources must be protected through explicit policies/allowlists.

---

# 17. Security Requirements

- Read-only AWS IAM role by default
- Least privilege
- No AWS root credentials
- No long-lived AWS access keys where avoidable
- Encrypt stored secrets/configuration
- Encrypt data in transit
- Audit all actions
- Separate read and write permissions
- Explicit confirmation for write actions
- Protected-resource mechanism
- No automatic production modification in MVP
- Tenant isolation
- Server-side authorization on every sensitive endpoint

---

# 18. Dashboard Requirements

The UI should prioritize investigation rather than charts.

Primary navigation:

```text
Overview
Costs
Resources
People
Projects
Alerts
Timeline
GitHub
Recommendations
Settings
```

The most important interaction is:

```text
Cost spike
   ↓
Why?
   ↓
Affected resource
   ↓
Owner
   ↓
Evidence
   ↓
Recommendation
```

---

# 19. MVP Success Criteria

A successful MVP can:

1. Connect one AWS account securely.
2. Retrieve real cost data.
3. Discover resources.
4. Show service/resource costs.
5. Attribute a meaningful subset of resources.
6. Explicitly represent unknown/shared spend.
7. Show attribution confidence.
8. Detect a simple cost anomaly.
9. Show an event timeline.
10. Produce an understandable explanation.
11. Detect at least two useful waste patterns.
12. Forecast current-period spend.
13. Connect a GitHub repository.
14. Calculate a basic supported PR cost estimate.
15. Never modify infrastructure without explicit user approval.

---

# 20. Demo Scenario

The canonical demo should be reproducible.

### Setup

Two users:

```text
Founder
Co-founder
```

Resources:

```text
production
development
experiment
```

### Demo

1. Connect AWS.
2. Show current spending.
3. Show resource ownership.
4. Start a development resource.
5. Observe increased cost/usage.
6. Generate an anomaly.
7. Show timeline.
8. Explain the cause.
9. Show estimated savings.
10. User approves a safe action.
11. Show audit log.
12. Open a GitHub PR with an infrastructure change.
13. Show predicted cost impact.
14. Compare predicted vs actual after deployment.

---

# 21. Product Roadmap

## Milestone 1 — AWS Cost Reader

AWS connection + cost ingestion + database + basic UI.

## Milestone 2 — Resource Intelligence

Resource inventory + tags + ownership + attribution.

## Milestone 3 — Investigation

Timeline + anomaly detection + explanations.

## Milestone 4 — Optimization

Waste detection + recommendations + savings.

## Milestone 5 — GitHub

Repository integration + PR cost estimation.

## Milestone 6 — Safe Actions

User-approved remediation.

## Milestone 7 — Closed Loop

Predicted → deployed → actual → variance → explanation.

## Future

- Terraform deeper integration
- CI/CD policies
- Kubernetes
- Azure/GCP
- AI spend
- SaaS spend
- automatic safe remediation
- cost-aware engineering metrics

---

# 22. Final Product Definition

The product is not:

> "A dashboard for AWS bills."

It is:

> **A control and intelligence layer that connects engineering activity to cloud cost, helping developers predict, understand, and safely control infrastructure spending.**

The core product loop must remain:

**Predict → Deploy → Measure → Attribute → Explain → Act.**
