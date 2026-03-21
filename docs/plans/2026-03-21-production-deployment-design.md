# Production Deployment & CI/CD Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the corresponding implementation plan task-by-task.

**Goal:** Deploy HomeScout to production with a CI/CD pipeline and three isolated environments (dev, qa, prod) on AWS + Vercel.

**Architecture:** Split-platform approach — Vercel for Next.js frontend, AWS ECS Fargate for backend services (API, Celery Worker, Celery Beat). Terraform for infrastructure as code, GitHub Actions for CI/CD. RDS PostgreSQL and ElastiCache Redis per environment.

**Tech Stack:** AWS (ECS Fargate, RDS, ElastiCache, ALB, ECR, CloudWatch, Secrets Manager, Route53), Terraform, GitHub Actions, Vercel, Docker.

---

## 1. Repository Structure & Dockerization

### New files

```
HomeScout/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Lint, test, build on every PR
│       ├── deploy-backend.yml      # Build + push Docker image + deploy ECS
│       └── deploy-frontend.yml     # Trigger Vercel deploy (if not auto)
├── backend/
│   ├── Dockerfile                  # Multi-stage build for FastAPI
│   └── .dockerignore
├── frontend/
│   └── .dockerignore               # For Vercel (exclude test files etc.)
├── infra/
│   ├── main.tf                     # Root module, provider config
│   ├── variables.tf                # Input variables (env, sizing)
│   ├── outputs.tf                  # ALB URL, RDS endpoint, etc.
│   ├── environments/
│   │   ├── dev.tfvars
│   │   ├── qa.tfvars
│   │   └── prod.tfvars
│   └── modules/
│       ├── networking/             # VPC, subnets, security groups
│       ├── ecs/                    # ECS cluster, services, task defs
│       ├── rds/                    # PostgreSQL instance
│       ├── elasticache/            # Redis cluster
│       ├── ecr/                    # Container registry
│       └── alb/                    # Application Load Balancer
└── scripts/
    └── deploy.sh                   # Helper for manual deploys
```

### Backend Dockerfile

Multi-stage build:
- Stage 1: Install Python dependencies into a virtual env
- Stage 2: Copy venv + app code into slim image
- Runs uvicorn (API), celery worker, or celery beat based on a `SERVICE_TYPE` env var
- One image, three ECS services (different CMD per task definition)
- Health check endpoint: `GET /health`

### Frontend

No Dockerfile. Vercel handles build and deploy natively. Connected to backend via `NEXT_PUBLIC_API_URL` env var per environment.

---

## 2. AWS Infrastructure (per environment)

### Networking (VPC)

- 1 VPC per environment: dev `10.0.0.0/16`, qa `10.1.0.0/16`, prod `10.2.0.0/16`
- 2 public subnets (ALB) + 2 private subnets (ECS, RDS, Redis) across 2 AZs
- NAT Gateway for outbound traffic from private subnets
- Dev/QA: single NAT Gateway. Prod: one per AZ for redundancy

### ECS Fargate Services

| Service | CPU | Memory | Count | Auto-scale |
|---------|-----|--------|-------|------------|
| `api` | 256 (dev/qa), 512 (prod) | 512MB (dev/qa), 1GB (prod) | 1 (dev/qa), 2 (prod) | Prod: 2-6 on CPU |
| `celery-worker` | 256 (dev/qa), 512 (prod) | 512MB (dev/qa), 1GB (prod) | 1 (all) | Prod: 1-3 on queue depth |
| `celery-beat` | 256 | 512MB | 1 (all) | Never (singleton) |

- All services in private subnets
- API registers with ALB target group
- Worker and Beat have no inbound traffic

### RDS PostgreSQL

| Setting | Dev | QA | Prod |
|---------|-----|-----|------|
| Instance | `db.t4g.micro` | `db.t4g.micro` | `db.t4g.small` |
| Storage | 20GB gp3 | 20GB gp3 | 50GB gp3 |
| Multi-AZ | No | No | Yes |
| Backups | 1 day | 1 day | 7 days |
| Deletion protection | No | No | Yes |

### ElastiCache Redis

| Setting | Dev | QA | Prod |
|---------|-----|-----|------|
| Node type | `cache.t4g.micro` | `cache.t4g.micro` | `cache.t4g.small` |
| Replicas | 0 | 0 | 1 |

### ALB (Application Load Balancer)

- HTTPS listener (port 443) with ACM certificate
- HTTP listener (port 80) redirects to HTTPS
- Health check: `GET /health`
- Target group routes to ECS API service on port 8000

### Shared Resources (not per-environment)

- 1 ECR repository for backend image (tagged `dev-<sha>`, `qa-<sha>`, `prod-<sha>`)
- 1 S3 bucket for Terraform state (with DynamoDB lock table)
- Route53 hosted zone: `api-dev.homescout.app`, `api-qa.homescout.app`, `api.homescout.app`

### Estimated Monthly Cost

- **Dev**: ~$50-70/mo (Fargate + RDS micro + Redis micro + NAT + ALB)
- **QA**: ~$50-70/mo (same)
- **Prod**: ~$150-250/mo (larger instances, Multi-AZ, auto-scaling, 2 NATs)

---

## 3. CI/CD Pipeline (GitHub Actions)

### Workflow 1: `ci.yml` — On every PR

Runs in parallel:
- **Backend**: lint (ruff/flake8), unit tests (pytest), Docker build (verify only, no push)
- **Frontend**: lint (eslint), type check (tsc --noEmit), build (next build)
- Vercel auto-creates a preview deploy per PR (built-in)

### Workflow 2: `deploy-backend.yml` — Backend deploy

```
Merge to main
    │
    ▼
Build Docker image + push to ECR (tagged dev-<sha>)
    │
    ▼
Run Alembic migration task (ECS run-task)
    │
    ▼
Deploy to DEV (auto) → Smoke tests (curl /health, /api/apartments/stats)
    │
    ▼ (manual trigger: workflow_dispatch)
Retag image as qa-<sha>
    │
    ▼
Deploy to QA → Run E2E tests (Playwright against QA)
    │
    ▼ (manual trigger + GitHub Environment protection rule requiring approval)
Retag image as prod-<sha>
    │
    ▼
Deploy to PROD → Smoke tests → Monitor 5 min → Done
```

**Key principles:**
- **Image promotion, not rebuild**: Same Docker image flows dev → qa → prod (retagged). What you test is what you ship.
- **ECS deploy**: `aws ecs update-service --force-new-deployment` after updating task definition with new image tag
- **Rollback**: ECS circuit breaker auto-rolls back if new tasks fail health checks. Manual rollback via redeploying previous task definition.

### Workflow 3: `deploy-frontend.yml` — Vercel handles automatically

Vercel GitHub integration:
- **PR** → Preview deployment (unique URL)
- **Merge to main** → Deploy to dev environment

Multi-environment on Vercel:
- `main` branch → dev
- `release/qa` branch → qa
- `release/prod` branch → prod (or use Vercel's "Promote to Production")
- Each environment gets its own `NEXT_PUBLIC_API_URL` pointing to the correct backend ALB

---

## 4. Environment Configuration & Secrets Management

### Secrets (AWS Secrets Manager)

Stored as JSON per environment (`homescout/dev/secrets`, `homescout/qa/secrets`, `homescout/prod/secrets`):

```json
{
  "ANTHROPIC_API_KEY": "sk-ant-...",
  "DATABASE_URL": "postgresql+asyncpg://...",
  "REDIS_URL": "redis://...",
  "SUPABASE_SERVICE_ROLE_KEY": "eyJ...",
  "SUPABASE_JWT_SECRET": "...",
  "STRIPE_SECRET_KEY": "sk_test_...",
  "STRIPE_WEBHOOK_SECRET": "whsec_...",
  "APIFY_API_TOKEN": "...",
  "SCRAPINGBEE_API_KEY": "...",
  "RESEND_API_KEY": "re_..."
}
```

- ECS task definitions reference secrets via `secrets` block (injected as env vars at container start)
- Never stored in code, `.env` files, or GitHub Actions secrets
- GitHub Actions only holds AWS credentials for deployment (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID`)

### Non-secret config (ECS task definition env vars)

```
USE_DATABASE=true
FRONTEND_URL=https://dev.homescout.app
SQL_ECHO=true                              # dev only
LOG_LEVEL=DEBUG                            # dev: DEBUG, qa: INFO, prod: WARNING
```

### External services per environment

| Service | Dev | QA | Prod |
|---------|-----|-----|------|
| Supabase | Separate project (`homescout-dev`) | Separate project (`homescout-qa`) | Production project (`homescout-prod`) |
| Stripe | Test mode (same account) | Test mode (same account) | Live mode (separate keys) |
| Resend | Sandbox (no real emails) | Sandbox | Production |
| Apify | Same account, lower limits | Same account | Same account, full limits |

### Vercel environment variables

| Variable | Dev | QA | Prod |
|----------|-----|-----|------|
| `NEXT_PUBLIC_API_URL` | `https://api-dev.homescout.app` | `https://api-qa.homescout.app` | `https://api.homescout.app` |
| `NEXT_PUBLIC_SUPABASE_URL` | dev project URL | qa project URL | prod project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | dev anon key | qa anon key | prod anon key |

---

## 5. Database Migrations Strategy

### Alembic (RDS — apartment data)

Alembic manages `apartments`, `scrape_jobs`, `data_sources`, `market_configs` tables.

**Execution:** A short-lived ECS migration task runs before each deployment:
1. GitHub Actions runs `aws ecs run-task` with command override `alembic upgrade head`
2. Same Docker image, different entrypoint
3. Task runs in same private subnet with RDS access
4. Workflow polls task status — if migration fails, deployment aborts

**Safety rules:**
- Migrations must be backwards-compatible (old code works with new schema during rolling deploy)
- Destructive migrations split into two deploys: (1) stop using column, (2) next release drops it

### Supabase Migrations (auth, profiles, favorites, tour pipeline)

Supabase manages `profiles`, `favorites`, `saved_searches`, `notifications`, `tour_pipeline`, `tour_notes`, `analytics_events`.

**Execution:** Manual — run in Supabase SQL Editor per environment before deploying dependent code.

**Promotion flow:**
1. Run migration in Supabase DEV → test with dev backend
2. Run migration in Supabase QA → E2E tests confirm
3. Run migration in Supabase PROD → then deploy backend code

Future option: adopt Supabase CLI (`supabase db push`) in CI/CD.

---

## 6. Monitoring & Observability

### Health Checks

| Component | Check | On Failure |
|-----------|-------|------------|
| ECS API | ALB → `GET /health` every 30s | ECS replaces unhealthy task |
| ECS Worker | Container health check (celery inspect ping) | ECS replaces task |
| ECS Beat | Container health check (process alive) | ECS replaces task |
| RDS | AWS auto-monitors | Failover (prod Multi-AZ) |
| ElastiCache | AWS auto-monitors | Alert |
| Frontend | Vercel built-in | Vercel handles |

### Logging (CloudWatch)

- All ECS containers log to CloudWatch Logs (built into Fargate)
- Log groups per service: `/ecs/homescout-{env}/api`, `/ecs/homescout-{env}/worker`, etc.
- Structured JSON logging via `python-json-logger`
- Retention: dev 7 days, qa 14 days, prod 30 days

### Alerting (Prod only — CloudWatch Alarms → SNS)

| Alarm | Condition |
|-------|-----------|
| API error rate | 5xx > 5% over 5 min |
| API latency | p95 > 3s over 5 min |
| ECS task failures | Task stopped unexpectedly |
| RDS CPU | > 80% for 10 min |
| RDS storage | < 5GB free |
| Redis memory | > 80% utilization |
| Celery queue depth | > 100 pending tasks |

Notifications via SNS → email/Slack. No alarms for dev/qa (save cost).

### Explicitly excluded (YAGNI)

- No APM tool (Datadog, New Relic) — CloudWatch sufficient to start
- No distributed tracing — single backend service
- No custom dashboards — CloudWatch auto-dashboards for ECS/RDS
- No PagerDuty / on-call rotation — email/Slack alerts for now
