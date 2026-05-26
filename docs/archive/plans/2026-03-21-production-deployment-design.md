# Production Deployment & CI/CD Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the corresponding implementation plan task-by-task.

**Goal:** Deploy HomeScout to production with a CI/CD pipeline and three isolated environments (dev, qa, prod) on AWS + Vercel, with quality gates enforcing image promotion order.

**Architecture:** Split-platform approach — Vercel for Next.js frontend, AWS ECS Fargate for backend services (API, Celery Worker, Celery Beat). Terraform for infrastructure as code, GitHub Actions for CI/CD. RDS PostgreSQL and ElastiCache Redis per environment. Image promotion pipeline: dev → QA (E2E gate) → prod (manual approval gate).

**Tech Stack:** AWS (ECS Fargate, RDS, ElastiCache, ALB, ECR, CloudWatch, Secrets Manager, Route53), Terraform, GitHub Actions, Vercel, Docker, Playwright.

---

## Current State (as of 2026-04-06)

| Component | Dev | QA | Prod |
|-----------|-----|-----|------|
| AWS Infrastructure (Terraform) | ✅ Applied | ❌ Not applied | ❌ Not applied |
| Secrets Manager | ✅ Populated | ❌ Empty | ❌ Empty |
| DNS (Route53) | ✅ api-dev.snugd.ai | ❌ Not created | ❌ Not created |
| Supabase Project | ✅ homescout-dev | ❌ Not created | ❌ Not created |
| Stripe | ✅ Test mode | ❌ Not configured | ❌ Not configured |
| GitHub Environment | ✅ Exists | ❌ Not created | ❌ Not created |
| GitHub Actions Deploy | ✅ Working | ⚠️ Job exists, no infra | ⚠️ Job exists, no infra |
| Quality Gates | None | None | None |
| Vercel Frontend | ✅ main → dev | ❌ No branch mapping | ❌ No branch mapping |
| Monitoring/Alerting | None (not needed) | None (not needed) | ❌ Not configured |

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

---

## 7. Implementation Plan — Standing Up QA & Prod

### Phase 1: GitHub Environment Protection Rules (~15 min)

**Why first:** Free, immediate, and prevents accidental deploys to non-existent environments.

**Task 1: Configure GitHub Environments**

Create environments via GitHub UI (Settings → Environments):

| Environment | Protection Rules |
|-------------|-----------------|
| `dev` | None — auto-deploy on push to main |
| `qa` | None — manual trigger via `workflow_dispatch` |
| `prod` | ✅ Required reviewers (add yourself + any approvers), deployment branches: main only |

After Terraform provisions each environment (Phases 2-3), add environment-specific secrets:

```bash
# QA (after Task 3)
gh secret set QA_PRIVATE_SUBNETS --env qa --body "subnet-xxx,subnet-yyy"
gh secret set QA_ECS_SG --env qa --body "sg-xxx"

# Prod (after Task 6)
gh secret set PROD_PRIVATE_SUBNETS --env prod --body "subnet-xxx,subnet-yyy"
gh secret set PROD_ECS_SG --env prod --body "sg-xxx"
```

---

### Phase 2: Provision QA Infrastructure (~45 min)

**Task 2: Create Supabase QA Project**

1. Create `homescout-qa` in Supabase dashboard (same region as AWS: us-east-1)
2. Run all SQL migrations (profiles, favorites, saved_searches, notifications, tour_pipeline, tour_notes, analytics_events + RLS policies)
3. Save project URL, anon key, service role key, JWT secret

**Task 3: Terraform Apply QA**

```bash
cd infra
terraform init -backend-config="key=infra/qa/terraform.tfstate"
terraform plan -var-file=environments/qa.tfvars -out=qa.tfplan
terraform apply qa.tfplan
terraform output -json > qa-outputs.json
```

Expected: ~25 resources (VPC, subnets, NAT, ALB, ECS cluster + 3 services (beat at 0 desired), RDS, Redis, SGs, IAM, log groups, Secrets Manager). Takes ~10-15 min.

After apply, update GitHub environment secrets (Task 1) with real subnet/SG IDs from Terraform output.

**Task 4: Populate QA Secrets and DNS**

Secrets Manager (`snugd/qa/secrets`):
```bash
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id snugd/qa/db-password --query SecretString --output text)

aws secretsmanager put-secret-value --secret-id snugd/qa/secrets --secret-string '{
  "ANTHROPIC_API_KEY": "<key>",
  "DATABASE_URL": "postgresql+asyncpg://snugd_qa:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/snugd_qa",
  "REDIS_URL": "redis://${REDIS_ENDPOINT}:6379/0",
  "SUPABASE_URL": "<qa-url>",
  "SUPABASE_SERVICE_ROLE_KEY": "<qa-key>",
  "SUPABASE_JWT_SECRET": "<qa-secret>",
  "STRIPE_SECRET_KEY": "<stripe-test-key>",
  "STRIPE_WEBHOOK_SECRET": "<stripe-qa-webhook>",
  "STRIPE_PRICE_ID": "<stripe-test-price>",
  "APIFY_API_TOKEN": "<token>",
  "RESEND_API_KEY": "<sandbox-key>",
  "SCRAPINGBEE_API_KEY": "<key>"
}'
```

DNS (Route53):
```bash
ALB_DNS=$(terraform output -raw alb_dns_name)
ALB_ZONE_ID=$(terraform output -raw alb_zone_id)
# Create A alias record: api-qa.snugd.ai → QA ALB
```

ACM: Use wildcard cert `*.snugd.ai` if available, otherwise request `api-qa.snugd.ai` cert.

First deploy + verify:
```bash
gh workflow run deploy-backend.yml -f environment=qa
curl -sf https://api-qa.snugd.ai/health
```

---

### Phase 3: Provision Prod Infrastructure (~45 min)

**Task 5: Create Supabase Prod Project**

Same as Task 2 but for `homescout-prod`.

**Task 6: Terraform Apply Prod**

```bash
cd infra
terraform init -backend-config="key=infra/prod/terraform.tfstate"
terraform plan -var-file=environments/prod.tfvars -out=prod.tfplan
# Review carefully: Multi-AZ RDS, redundant NATs, larger instances → ~$150-250/mo
terraform apply prod.tfplan
```

After apply, update GitHub environment secrets for `prod`.

**Task 7: Populate Prod Secrets, DNS, and Stripe Live Mode**

Secrets Manager (`snugd/prod/secrets`): Same structure as QA but with:
- `STRIPE_SECRET_KEY`: **Live mode** key
- `STRIPE_WEBHOOK_SECRET`: New endpoint at `https://api.snugd.ai/webhooks/stripe` (events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`)
- `RESEND_API_KEY`: Production key (not sandbox)

DNS: `api.snugd.ai` → Prod ALB

First deploy (requires GitHub approval):
```bash
gh workflow run deploy-backend.yml -f environment=prod
# Approve in GitHub Actions UI
curl -sf https://api.snugd.ai/health
```

---

### Phase 4: Quality Gates in CI/CD (~30 min)

**Task 8: Add Comprehensive Smoke Tests**

Create `scripts/smoke-test.sh`:

```bash
#!/bin/bash
set -euo pipefail

ENV=${1:?Usage: smoke-test.sh <env>}

case "$ENV" in
  dev)  BASE_URL="https://api-dev.snugd.ai" ;;
  qa)   BASE_URL="https://api-qa.snugd.ai" ;;
  prod) BASE_URL="https://api.snugd.ai" ;;
  *)    echo "Unknown env: $ENV"; exit 1 ;;
esac

echo "=== Smoke testing ${ENV} at ${BASE_URL} ==="

echo -n "Health check... "
curl -sf "${BASE_URL}/health" | python3 -c "
import sys,json; d=json.load(sys.stdin); assert d['status']=='healthy', f'unhealthy: {d}'"
echo "OK"

echo -n "Apartments stats... "
curl -sf "${BASE_URL}/api/apartments/stats" | python3 -c "
import sys,json; d=json.load(sys.stdin); assert d.get('total_apartments',0)>=0"
echo "OK"

echo -n "Apartments list... "
LIST=$(curl -sf "${BASE_URL}/api/apartments/list?limit=1")
echo "$LIST" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'apartments' in d"
echo "OK"

echo -n "True cost field... "
echo "$LIST" | python3 -c "
import sys, json
apts = json.load(sys.stdin).get('apartments', [])
if apts:
    assert 'true_cost_monthly' in apts[0], 'true_cost_monthly missing'
    print('OK')
else:
    print('SKIP (no apartments)')
"

echo "=== All smoke tests passed for ${ENV} ==="
```

Update `.github/workflows/deploy-backend.yml` — replace inline `curl` smoke tests in all 3 jobs with:

```yaml
      - name: Smoke tests
        run: |
          sleep 10
          chmod +x scripts/smoke-test.sh
          ./scripts/smoke-test.sh <env>
```

Add E2E test step to QA deploy job (after smoke tests):

```yaml
      - name: Run E2E tests against QA
        working-directory: frontend
        run: |
          npm ci
          npx playwright install --with-deps chromium
          npx playwright test --project=chromium
        env:
          NEXT_PUBLIC_API_URL: https://api-qa.snugd.ai
          NEXT_PUBLIC_SUPABASE_URL: ${{ secrets.QA_SUPABASE_URL }}
          NEXT_PUBLIC_SUPABASE_ANON_KEY: ${{ secrets.QA_SUPABASE_ANON_KEY }}
          BASE_URL: https://qa.snugd.ai
```

**Task 9: Enforce Image Promotion Order**

Add image validation steps to `.github/workflows/deploy-backend.yml`:

QA job — before "Retag image for QA":
```yaml
      - name: Verify dev image exists
        run: |
          SHA=$(echo ${{ github.sha }} | cut -c1-7)
          aws ecr describe-images --repository-name ${{ env.ECR_REPOSITORY }} \
            --image-ids imageTag=dev-${SHA} || {
            echo "::error::No dev image for SHA ${SHA}. Deploy to dev first."
            exit 1
          }
```

Prod job — before "Retag image for Prod":
```yaml
      - name: Verify QA image exists
        run: |
          SHA=$(echo ${{ github.sha }} | cut -c1-7)
          aws ecr describe-images --repository-name ${{ env.ECR_REPOSITORY }} \
            --image-ids imageTag=qa-${SHA} || {
            echo "::error::No QA image for SHA ${SHA}. Deploy to QA first."
            exit 1
          }
```

---

### Phase 5: Frontend Multi-Environment on Vercel (~15 min)

**Task 10: Configure Vercel Branch-Based Deployments**

Vercel Dashboard → Project Settings → Environment Variables:

| Variable | Production | Preview | Development |
|----------|-----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `https://api.snugd.ai` | `https://api-qa.snugd.ai` | `https://api-dev.snugd.ai` |
| `NEXT_PUBLIC_SUPABASE_URL` | prod URL | qa URL | dev URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | prod key | qa key | dev key |

Vercel Dashboard → Project Settings → Domains:
- `dev.snugd.ai` → dev deployment
- `qa.snugd.ai` → QA preview deployment
- `snugd.ai` → production deployment

Branch strategy: `main` → dev (auto). QA and Prod use Vercel's "Promote to Production" from preview deployments, or branch mapping (`release/qa`, `release/prod`).

---

### Phase 6: Monitoring & Operational Readiness (~20 min)

**Task 11: Wire Prod Monitoring**

Add monitoring module call to `infra/main.tf` (if not already wired):

```hcl
module "monitoring" {
  source                 = "./modules/monitoring"
  environment            = var.environment
  alert_email            = var.alert_email
  target_group_arn_suffix = module.alb.target_group_arn_suffix
  alb_arn_suffix          = module.alb.alb_arn_suffix
  rds_instance_id         = module.rds.instance_id
}
```

Add to `variables.tf`:
```hcl
variable "alert_email" {
  description = "Email for CloudWatch alarm notifications (prod only)"
  type        = string
  default     = ""
}
```

Add to `prod.tfvars`:
```hcl
alert_email = "alerts@snugd.ai"
```

Apply: `terraform apply -var-file=environments/prod.tfvars`, then confirm SNS email subscription.

**Task 12: Scraping & Data Strategy Per Environment**

Scraping is expensive (Apify API calls cost per run). Only prod runs scheduled scraping. Dev and QA get data on-demand.

| Environment | Beat Service | Scheduled Scraping | On-Demand Scraping |
|-------------|-------------|-------------------|-------------------|
| **Prod** | Running (`beat_desired_count = 1`) | ✅ Full schedule via dispatcher | ✅ Via admin API or CLI |
| **QA** | Stopped (`beat_desired_count = 0`) | ❌ No scheduled scrapes | ✅ Via admin API, CLI, or GHA workflow |
| **Dev** | Stopped (`beat_desired_count = 0`) | ❌ No scheduled scrapes | ✅ Via admin API, CLI, or GHA workflow |

**Terraform change:** Add `beat_desired_count` variable to `infra/modules/ecs/variables.tf` and use it in the beat service resource:

```hcl
# variables.tf
variable "beat_desired_count" {
  description = "Desired count for beat service (0 to disable scheduled tasks)"
  type        = number
  default     = 1
}
```

```hcl
# ecs service
resource "aws_ecs_service" "beat" {
  ...
  desired_count = var.beat_desired_count
}
```

Set in tfvars:
```hcl
# dev.tfvars
beat_desired_count = 0

# qa.tfvars
beat_desired_count = 0

# prod.tfvars
beat_desired_count = 1
```

**On-demand scraping — 3 triggers available in all environments:**

**1. Admin API (already exists)**

`POST /api/admin/data-collection/trigger-job` at `backend/app/routers/data_collection.py`:

```bash
# Scrape a specific city
curl -X POST https://api-qa.snugd.ai/api/admin/data-collection/trigger-job \
  -H "Content-Type: application/json" \
  -d '{"city": "Philadelphia", "max_listings": 100}'

# Full scrape (all enabled markets)
curl -X POST https://api-qa.snugd.ai/api/admin/data-collection/trigger-job \
  -H "Content-Type: application/json" \
  -d '{"max_listings": 100}'
```

**2. CLI script**

Add `scrape` command to `scripts/deploy.sh`:

```bash
  scrape)
    echo "Triggering on-demand scrape on ${ENV}..."
    CITY=${3:-}
    if [ -n "$CITY" ]; then
      OVERRIDE_CMD="from app.tasks.scrape_tasks import scrape_city_task; scrape_city_task.delay('$CITY')"
    else
      OVERRIDE_CMD="from app.tasks.dispatcher import dispatch_scrapes; dispatch_scrapes()"
    fi
    aws ecs run-task \
      --cluster snugd-${ENV} \
      --task-definition snugd-${ENV}-worker \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=$(aws ec2 describe-subnets \
        --filters "Name=tag:Name,Values=snugd-${ENV}-private-*" \
        --query 'Subnets[*].SubnetId' --output text | tr '\t' ','),assignPublicIp=DISABLED}" \
      --overrides "{\"containerOverrides\":[{\"name\":\"worker\",\"command\":[\"python\",\"-c\",\"${OVERRIDE_CMD}\"]}]}"
    echo "Scrape dispatched. Check: ./scripts/deploy.sh logs ${ENV}"
    ;;
```

Usage:
```bash
./scripts/deploy.sh scrape qa                    # all enabled markets
./scripts/deploy.sh scrape qa Philadelphia       # single city
./scripts/deploy.sh scrape dev "New York"        # works in dev too
```

**3. GitHub Actions workflow dispatch**

Create `.github/workflows/seed-data.yml`:

```yaml
name: Seed Data (On-Demand Scrape)

on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to seed"
        required: true
        type: choice
        options: [dev, qa]
      city:
        description: "City to scrape (blank = all enabled markets)"
        required: false
        type: string
      max_listings:
        description: "Max listings per market"
        required: false
        default: "100"
        type: string

jobs:
  seed:
    name: Seed ${{ inputs.environment }}
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Trigger scrape
        run: |
          ENV=${{ inputs.environment }}
          CITY="${{ inputs.city }}"

          if [ -n "$CITY" ]; then
            CMD="from app.tasks.scrape_tasks import scrape_city_task; scrape_city_task.delay('${CITY}', max_listings=${{ inputs.max_listings }})"
          else
            CMD="from app.tasks.dispatcher import dispatch_scrapes; dispatch_scrapes()"
          fi

          SUBNETS='${{ secrets[format('{0}_PRIVATE_SUBNETS', inputs.environment)] }}'
          SUBNET_JSON=$(echo "$SUBNETS" | tr ',' '\n' | sed 's/.*/"&"/' | paste -sd, -)

          TASK_ARN=$(aws ecs run-task \
            --cluster snugd-${ENV} \
            --task-definition snugd-${ENV}-worker \
            --launch-type FARGATE \
            --network-configuration "{\"awsvpcConfiguration\":{\"subnets\":[${SUBNET_JSON}],\"securityGroups\":[\"${{ secrets[format('{0}_ECS_SG', inputs.environment)] }}\"],\"assignPublicIp\":\"DISABLED\"}}" \
            --overrides "{\"containerOverrides\":[{\"name\":\"worker\",\"command\":[\"python\",\"-c\",\"${CMD}\"]}]}" \
            --query 'tasks[0].taskArn' --output text)
          echo "Task ARN: $TASK_ARN"
          echo "Monitor logs: aws logs tail /ecs/snugd-${ENV}/worker --follow --since 1m"

      - name: Wait for completion
        run: |
          echo "Scrape dispatched to Celery. Data will appear in ~5-10 minutes."
          echo "Check: https://api-${{ inputs.environment == 'dev' && 'dev.' || inputs.environment == 'qa' && 'qa.' || '' }}snugd.ai/api/apartments/stats"
```

**Note:** Prod is intentionally excluded from the workflow dispatch options — prod gets data only through its scheduled Beat pipeline. If you ever need a manual prod scrape, use the admin API or CLI directly.

**Task 13: ACM Certificate ARN in tfvars**

Ensure `certificate_arn` variable exists in `variables.tf` and is set in `qa.tfvars` and `prod.tfvars`. Use wildcard `*.snugd.ai` if available.

---

## 8. Execution Order Summary

```
Phase 1: GitHub Environments          [Task 1]         ~15 min
    │
    ▼
Phase 2: QA Infrastructure            [Tasks 2-4]      ~45 min
    │  ├─ Supabase QA project
    │  ├─ Terraform apply QA
    │  └─ Secrets + DNS + first deploy
    │
    ▼
Phase 3: Prod Infrastructure           [Tasks 5-7]      ~45 min
    │  ├─ Supabase Prod project
    │  ├─ Terraform apply Prod
    │  └─ Secrets + DNS + Stripe live + first deploy
    │
    ▼
Phase 4: Quality Gates                 [Tasks 8-9]      ~30 min
    │  ├─ Smoke test script
    │  ├─ E2E tests on QA
    │  └─ Image promotion enforcement
    │
    ▼
Phase 5: Frontend Multi-Environment    [Task 10]        ~15 min
    │  └─ Vercel config + domains
    │
    ▼
Phase 6: Monitoring & Data Seeding      [Tasks 11-13]    ~20 min
    │  ├─ CloudWatch alarms for Prod
    │  ├─ Scraping strategy (beat=0 for dev/qa, on-demand via 3 triggers)
    │  └─ ACM cert ARNs
```

---

## 9. Rollback Plan

| Scenario | Action |
|----------|--------|
| QA Terraform fails | `terraform destroy -var-file=environments/qa.tfvars` — safe, no user data |
| Prod deploy breaks | ECS circuit breaker auto-rolls back. Manual: redeploy previous task definition |
| Bad migration on Prod | `alembic downgrade -1` via ECS run-task. All migrations must be backwards-compatible |
| DNS not resolving | Check Route53 records, ACM certificate validation status |
| Secrets misconfigured | ECS tasks won't start — check CloudWatch logs, update Secrets Manager |

---

## 10. Post-Implementation Checklist

- [ ] `https://api-dev.snugd.ai/health` returns healthy
- [ ] `https://api-qa.snugd.ai/health` returns healthy
- [ ] `https://api.snugd.ai/health` returns healthy
- [ ] QA deploy runs E2E tests before marking success
- [ ] Prod deploy requires GitHub approval
- [ ] Prod deploy fails if no QA image exists for that SHA
- [ ] CloudWatch alarms fire on Prod 5xx spike
- [ ] Vercel frontend resolves correctly for all 3 domains
- [ ] Stripe webhook works in Prod live mode
- [ ] QA has seeded apartment data
