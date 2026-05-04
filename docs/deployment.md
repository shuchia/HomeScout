# Deployment

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references

Backend runs on AWS (ECS Fargate behind ALB, RDS Postgres, ElastiCache Redis, S3 for tour media, ECR for images, CloudWatch monitoring). Frontend deploys to Vercel. Active hosted environment: **qa only**. **Dev runs locally on your laptop**. **Prod is dormant** — it was torn down on 2026-05-04 to save spend; a final RDS snapshot `snugd-prod-final` is retained, and re-provisioning is `terraform apply -var-file=environments/prod.tfvars`.

## Quick Commands

```bash
# Local Docker build/run
cd backend
docker build -t snugd-api .
docker run -p 8000:8000 --env-file .env snugd-api

# Deploy script (multi-mode)
./scripts/deploy.sh <env> build       # docker build + push to ECR
./scripts/deploy.sh <env> deploy      # update ECS service to new image
./scripts/deploy.sh <env> migrate     # run alembic upgrade head as one-off task
./scripts/deploy.sh <env> status      # ECS service summary
./scripts/deploy.sh <env> logs <svc>  # tail CloudWatch logs
./scripts/deploy.sh <env> scrape      # trigger on-demand scrape via admin API
./scripts/deploy.sh <env> tf-plan
./scripts/deploy.sh <env> tf-apply

# Promote a tested image up the pipeline (qa → prod via release branches)
./scripts/promote.sh qa prod

# Smoke test deployed env
./scripts/smoke-test.sh <env>
```

## Architecture

```
            ┌──────────────────────────┐
            │  Vercel (frontend)       │  ← branch push to main = prod
            │  https://snugd.ai         │     other branches = preview
            └─────────────┬────────────┘
                          │ fetch /api/*
                          ▼
             ┌────────────────────────┐
             │   ALB (HTTPS)          │
             └────────────┬───────────┘
                          │
       ┌──────────────────┼─────────────────┐
       ▼                  ▼                 ▼
  ECS:api task      ECS:worker task    ECS:beat task
  (Fargate)         (Celery worker)    (Celery beat — qa only)
       │                  │                 │
       └────────┬─────────┴────┬────────────┘
                ▼              ▼
            RDS Postgres   ElastiCache Redis
                                 │
                                 ▼
                            S3 bucket: snugd-tours-<env>
                            (voice notes, photos)
```

## Terraform Modules

`infra/main.tf` calls each module; `infra/variables.tf` defines inputs; `infra/outputs.tf` exposes ALB DNS, RDS endpoint, etc.

| Module | Provisions |
|--------|-----------|
| `networking` | VPC, public/private subnets across 2 AZs, NAT, route tables |
| `alb` | Application Load Balancer, listeners (80→443 redirect, 443 HTTPS), target groups, ACM cert binding |
| `ecr` | Docker image repository — **owned by qa state** (count = qa); prod reads via `data "aws_ecr_repository"` |
| `ecs` | Fargate cluster, services (`api`, `worker`, `beat`), task definitions, IAM (`infra/modules/ecs/iam.tf`) |
| `rds` | Postgres instance, parameter group, subnet group |
| `elasticache` | Redis (cluster mode disabled), subnet group |
| `monitoring` | CloudWatch log groups, alarms (CPU, memory, ALB 5xx) |

S3 bucket `aws_s3_bucket.tours` (`snugd-tours-<env>`) is declared **inline in `infra/main.tf`** (not a separate module). IAM permissions for ECS to read/write it live in `infra/modules/ecs/iam.tf` (recent commit `6110a11`).

`infra/bootstrap/` provisions the Terraform state backend (S3 + DynamoDB lock) — run once per AWS account before the main stack.

## Environments

| Env | tfvars | VPC CIDR | Status | Beat | RDS | Log level | Branch trigger |
|-----|--------|----------|--------|------|-----|-----------|----------------|
| dev | `infra/environments/dev.tfvars` | 10.0.0.0/16 | **decommissioned 2026-05-04** — runs locally now | n/a | n/a | n/a | none |
| qa | `infra/environments/qa.tfvars` | 10.1.0.0/16 | active | 1 (scheduled scrapes run here) | db.t4g.micro / 20 GB | INFO | `release/qa` |
| prod | `infra/environments/prod.tfvars` | 10.2.0.0/16 | **dormant** — torn down 2026-05-04, snapshot retained | 0 (until launch) | (re-provision; was db.t4g.micro / 50 GB) | INFO | `release/prod` |

The `dev.tfvars` and `prod.tfvars` files are preserved in repo for reproducibility — re-applying them would recreate the respective stacks. Day-to-day development uses the local backend (`uvicorn` + `brew services start postgresql@16 redis`).

To bring prod back: restore from the final snapshot via the RDS module (`snapshot_identifier = "snugd-prod-final"`) or apply fresh, then push to `release/prod`.

Wildcard ACM cert (`*.snugd.ai`) is shared across envs and bound on the ALB.

## Backend Deploy Flow

```
git push origin <branch>
   │
   ▼
GitHub Actions (.github/workflows/deploy-backend.yml)
   │
   ├─ docker build & push to ECR (tagged with commit SHA + env tag)
   ├─ register new ECS task definition (revision N+1)
   ├─ update ECS services (api, worker, [beat])
   ├─ wait for service-stable
   ├─ run alembic upgrade as one-off ECS task (3 retries on failure)
   ├─ run scripts/smoke-test.sh
   └─ qa-only: run frontend Playwright suite against the deployed API
```

The branch-based trigger map:

- `release/qa` → qa
- `release/prod` → prod
- `main` → no automatic deploy (CI runs only); push to a `release/*` branch to deploy

Per-PR CI gates run via `.github/workflows/ci.yml` (lint + tests, no deploy).

## Frontend Deploy Flow

Vercel auto-deploys from the GitHub repo:

- `main` → production (snugd.ai).
- Other branches → preview deploys with the PR.

`frontend/vercel.json` sets framework + security headers (CSP, HSTS, X-Frame-Options, etc.). Env vars (`NEXT_PUBLIC_API_URL`, Supabase keys) are configured per env in the Vercel dashboard.

## Backend Container

`backend/Dockerfile` — Python 3.11 slim, multi-stage:

1. Build stage: install build deps, `pip install -r requirements.txt` to a venv.
2. Runtime stage: copy venv, app source; `ENTRYPOINT ["./docker-entrypoint.sh"]`.

`backend/docker-entrypoint.sh` switches on `SERVICE_TYPE`:

| `SERVICE_TYPE` | Command |
|----------------|---------|
| `api` (default) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `worker` | `celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance` |
| `beat` | `celery -A app.celery_app beat --loglevel=info` |
| `migrate` | `alembic upgrade head` (one-off) |

## Smoke Test

`scripts/smoke-test.sh <env>` checks:

1. `GET /health` → 200
2. `GET /api/apartments/stats` → 200 with non-zero counts
3. `GET /api/apartments/list?limit=5` → 200 with 5 listings
4. First listing has a `true_cost_monthly` field (regression check for cost-breakdown wiring)

Single-quote escaping in apartment data was fixed in `2033579`.

## Promote Script

`scripts/promote.sh <from-env> <to-env>` — fast-forward merges the deploy branch up the pipeline (`main` → `release/qa` → `release/prod`), letting the deploy workflow handle the actual ECS update. Avoids re-building the same image; the ECR tag is reused.

## Secrets Management

ECS task definitions reference AWS Secrets Manager entries (`infra/modules/ecs/main.tf` lines 32–46). Required:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY` (added in `afad790`)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`
- `APIFY_API_TOKEN`, `SCRAPINGBEE_API_KEY`
- `RESEND_API_KEY`
- `DATABASE_URL`, `REDIS_URL` (constructed from Terraform outputs into Secrets Manager)

Non-secret env vars (`USE_DATABASE`, `FRONTEND_URL`, log level, beat-flag) live in the task definition `environment` block.

## CI/CD Workflows

`.github/workflows/`:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | PR + push | Backend pytest + frontend lint/build (no deploy) |
| `deploy-backend.yml` | Push to `main` / `release/qa` / `release/prod` | Full backend deploy with smoke test |
| `seed-data.yml` | Manual `workflow_dispatch` | On-demand scrape against an env (`bd2b330`) |

## SSL & DNS

ACM wildcard cert is bound on the ALB listener. The Snugd apex/wildcard DNS records point to the ALB DNS name; DNS itself is managed outside Terraform (record updates handled by hand or through whichever registrar). Frontend `snugd.ai` points at Vercel.

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| ECR access denied across envs | ECR repo is owned by qa state, read by prod via data source; ensure each env's task role has `ecr:GetDownloadUrlForLayer` on the shared repo ARN |
| RDS pool exhausted | Pool size capped (`d17fe8d`); avoid spawning extra async sessions per task |
| Smoke test fails on apostrophes | Single-quote escaping fix `2033579` — re-run latest |
| Beat not running in prod | Intentional — only qa runs scheduled scrapes (`6134bb4`); prod beat enabled only at launch |
| Migrations fail mid-deploy | Workflow retries 3× with backoff; on persistent failure, run `./scripts/deploy.sh <env> migrate` manually |
| OPENAI_API_KEY missing in ECS | Older deploys lacked it; current task definition includes it (`afad790`) |
| Image not updating after deploy | ECS service may be cached on a previous revision — `aws ecs update-service --force-new-deployment` |
