# Cloud Cost Control Platform

A developer-first, AWS-first cost control platform that connects AWS spending, resources, activity, ownership, and GitHub changes so small engineering teams can understand what caused cloud costs, predict cost impact, detect waste/anomalies, and safely act on them.

The product is built around a trustworthy, deterministic chain:

**cost → resource → ownership → evidence → explanation → action**

It is **read-only by default**. Any write action is isolated behind explicit permissions, policy checks, and user approval. Billing math is deterministic; AI only turns facts into natural language.

## Documentation

- Product Requirements: [`cloud-cost-control-PRD.md`](./cloud-cost-control-PRD.md)
- Technical Requirements: [`cloud-cost-control-TRD.md`](./cloud-cost-control-TRD.md)
- Spec (requirements/design/tasks): [`.kiro/specs/cloud-cost-control/`](./.kiro/specs/cloud-cost-control/)

## Monorepo Layout

```text
backend/    FastAPI + SQLAlchemy + Alembic + Celery (Python 3.11)
frontend/   Next.js (App Router) + TypeScript + Tailwind + TanStack Query
docker-compose.yml   Postgres + Redis for local development
```

## Tech Stack

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic, boto3, Celery
- **Frontend:** Next.js, TypeScript, Tailwind CSS, TanStack Query, Recharts
- **Database:** PostgreSQL
- **Cache / Broker:** Redis
- **Auth:** Clerk (Organizations map to tenants)
- **AI:** Groq (configurable model, deterministic templated fallback)
- **Pricing:** AWS Price List API cached behind a `PricingProvider` interface

## Prerequisites

- Python 3.11+
- Node.js 20+ (tested on 22)
- Docker + Docker Compose

## Quick Start (local development)

1. Copy env templates and fill in secrets:

   ```powershell
   Copy-Item .env.example .env
   Copy-Item backend/.env.example backend/.env
   Copy-Item frontend/.env.example frontend/.env.local
   ```

2. Start infrastructure (Postgres + Redis):

   ```powershell
   docker compose up -d
   ```

3. Backend:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

4. Frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Backend runs at http://localhost:8000 (docs at `/docs`), frontend at http://localhost:3000.

## Principles (enforced across the codebase)

- Read-only first — no AWS write path until Phase 8, gated by policy + approval + audit.
- Deterministic financial truth — AI never produces numbers.
- Provider isolation — AWS, pricing, credentials, and LLM sit behind interfaces.
- Every dollar reconciles — Total = Attributed + Shared + Unknown.
- Multi-tenant from day one — every record is tenant-scoped.

## Connecting an AWS account (cross-account, read-only)

Users connect their own AWS account without ever sharing AWS access keys,
secret keys, or root credentials. The application assumes a read-only IAM role
in the customer's account using AWS STS and temporary credentials.

### How it works

```text
Application IAM principal (our account)
        ↓  sts:AssumeRole (+ External ID)
Customer read-only IAM role (their account)
        ↓
Temporary credentials → read cost / resources / usage / activity
```

- We store only the **Role ARN** and a per-connection **External ID**
  (connection metadata). We never store AWS credentials.
- The role is **read-only**; it cannot create, modify, stop, or delete
  anything. The single remediation write action (Phase 8) uses a completely
  separate policy/role and is out of scope for onboarding.

### Steps for a new user

1. Sign in to the application and select/create your workspace (organization).
2. Open **Settings → Connect AWS**.
3. **Step 1 — Account ID:** copy your 12-digit AWS account ID from the console.
4. **Step 2 — Create the IAM role:** in AWS, go to *IAM → Roles → Create role →
   Custom trust policy*, and name it e.g. `CloudCostControlReadOnly`.
5. **Step 3 — Permissions & trust:** the wizard shows exact JSON with copy
   buttons:
   - **Trust policy** — allows only our application's principal to assume the
     role, gated by your unique External ID.
   - **Read-only permissions policy** — attach it to the role.
6. **Step 4 — Role ARN:** copy the role's ARN and paste it into the wizard.
7. Click **Connect & Validate**. The app assumes the role and runs read-only
   probes, then shows per-capability results.

### Permissions requested (read-only)

Source of truth: [`docs/iam/read-policy.json`](./docs/iam/read-policy.json).

| Capability | Actions |
| --- | --- |
| Cost | `ce:GetCostAndUsage` |
| Identity | `sts:GetCallerIdentity` |
| EC2 / EBS | `ec2:DescribeInstances`, `ec2:DescribeVolumes`, `ec2:DescribeRegions`, `ec2:DescribeTags` |
| S3 | `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetBucketTagging` |
| RDS | `rds:DescribeDBInstances`, `rds:ListTagsForResource` |
| CloudTrail | `cloudtrail:LookupEvents` |
| CloudWatch (Bedrock usage) | `cloudwatch:ListMetrics`, `cloudwatch:GetMetricData` |

No write permissions are requested. See [`docs/iam/README.md`](./docs/iam/README.md).

### Revoking access

Delete the IAM role in your AWS account, or remove our application's principal
from the role's trust relationship. Access stops immediately.

### Multiple AWS accounts

A workspace can connect more than one AWS account (e.g. dev / staging / prod).
The account selector in the app header chooses which connected account's data
is shown. All data is tenant-isolated server-side.

### Deployment prerequisite (production)

Cross-account AssumeRole requires the deployment to have a **stable application
AWS principal** that customer roles will trust. Set these environment variables
on the backend:

```text
APP_AWS_PRINCIPAL_ARN=arn:aws:iam::<your-app-account>:role/<ApplicationRole>
EXTERNAL_ID_SECRET=<a strong random secret>   # derives per-connection External IDs
```

Until `APP_AWS_PRINCIPAL_ARN` is set, the connection wizard reports that
cross-account connections are unavailable and shows this as a prerequisite (the
trust policy references the actual principal — never a placeholder). Local
development continues to work using a host AWS profile (advanced option in the
wizard) without any of the above.
