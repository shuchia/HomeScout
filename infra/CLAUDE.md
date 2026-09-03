# Infra CLAUDE.md

Claude Code guidance for Snugd infrastructure — Terraform on AWS (us-east-1, account `453636587892`) plus the GitHub Actions deploy pipeline.

> Frontend hosting is **Vercel**, not Terraform. Only the backend (API, worker, beat) and its data stores live here.

## Current State — read this first

| Env | API | Terraform applied? | Notes |
|-----|-----|--------------------|-------|
| dev | `api-dev.snugd.ai` | **No** | tfvars exist only |
| qa | `api-qa.snugd.ai` | **Yes — the only live env** | ECS cluster `snugd-qa` |
| prod | `api.snugd.ai` | **No** | `prod.tfvars` written but never applied |

Prod has no `snugd/prod/secrets` in Secrets Manager, no ECS cluster, and no DNS record for `api.snugd.ai`. Anything targeting prod (`./scripts/smoke-test.sh prod`, `./scripts/beta-report.sh prod`) fails until it's stood up.

## Layout

```
infra/
├── main.tf                  # Root module — wires all modules together
├── variables.tf
├── outputs.tf
├── bootstrap/               # One-time: TF state bucket + lock table
└── modules/
    ├── networking/          # VPC, subnets, NAT
    ├── ecr/                 # snugd-backend image repo
    ├── rds/                 # Postgres + snugd/{env}/db-password secret
    ├── elasticache/         # Redis (Celery broker + rate limiting)
    ├── alb/                 # Load balancer + ACM wildcard cert
    ├── ecs/                 # Fargate: api / worker / beat + IAM
    └── monitoring/          # SNS topic + CloudWatch alarms
```

Environment configs: `environments/{dev,qa,prod}.tfvars`.

## ECS Services

The `ecs` module defines **three** task definitions off one image, differentiated by `SERVICE_TYPE`:

| Service | `SERVICE_TYPE` | Purpose | QA count |
|---------|----------------|---------|----------|
| api | `api` | FastAPI behind the ALB | 1 |
| worker | `worker` | Celery worker (`celery,scraping,maintenance`) | 1 |
| beat | `beat` | Celery beat scheduler | 1 |

Shared container env set in Terraform: `USE_DATABASE=true`, `USE_FLOORPLAN_SEARCH` (from `var.use_floorplan_search`), `FRONTEND_URL`, `LOG_LEVEL`, `PYTHONUNBUFFERED=1`, `S3_BUCKET_NAME`. Everything secret comes from `snugd/{env}/secrets` in Secrets Manager, injected by task-role policy in `modules/ecs/iam.tf`.

**Only one beat instance may ever run** — `beat_desired_count` is 1 in QA. Two beats double every scheduled scrape.

## Terraform ↔ CI split (important)

The ECS module uses `lifecycle.ignore_changes` on `container_definitions` and the service's `task_definition` pointer, so **Terraform does not fight the deploy pipeline**. Consequences:

- `image_tag` in tfvars is only the *initial* image (`qa-latest`). CI owns every subsequent revision.
- CI pushes `:qa-{sha}` **and** `:qa-latest` so the tfvars value stays pullable.
- Running `terraform apply` will **not** roll the running image back — but it *will* restart beat if the beat task definition changes.
- After a Terraform apply that touches ECS, verify the worker actually came back up; a stopped worker is silent.

## Secrets

```bash
# Fetch the admin API key for an environment
aws secretsmanager get-secret-value --secret-id snugd/qa/secrets \
  --region us-east-1 --query SecretString --output text | jq -r .ADMIN_API_KEY
```

| Secret | Contents |
|--------|----------|
| `snugd/{env}/secrets` | App secrets — `ADMIN_API_KEY`, Anthropic, Supabase, Stripe, Apify, Resend, Google Maps, OpenAI |
| `snugd/{env}/db-password` | RDS password (created by the `rds` module) |

A missing key in `snugd/{env}/secrets` makes the ECS task fail to start with an opaque error — see the note in `modules/ecs/main.tf` about `GOOGLE_MAPS_API_KEY`.

## CI/CD

| Workflow | Trigger | Does |
|----------|---------|------|
| `ci.yml` | PR → `main` | Backend lint+test, backend Docker build, frontend lint+build |
| `deploy-backend.yml` | Push to `release/qa` or `release/prod` (paths: `backend/**`), or manual dispatch | Resolve env from branch → build & push to ECR → deploy ECS |
| `seed-data.yml` | Manual dispatch only | On-demand scrape to seed listings |

Prod deploys require **approval in GitHub Actions**.

### Branch flow

```
main  ──promote──▶  release/qa  ──promote──▶  release/prod
                    (auto-deploy QA)          (approval-gated)
```

```bash
./scripts/promote.sh qa      # fast-forward merge main → release/qa, push
./scripts/promote.sh prod    # fast-forward merge release/qa → release/prod, push
```

Both are **`--ff-only`**. If the merge is rejected, the branches have diverged — reconcile rather than forcing.

## Scripts

```bash
./scripts/deploy.sh <command> [env]
#   build | push | deploy | migrate | status | logs | scrape | tf-plan | tf-apply

./scripts/smoke-test.sh qa      # post-deploy endpoint checks
./scripts/beta-report.sh qa 30 20   # beta usage report (see root CLAUDE.md)
```

## Monitoring

`modules/monitoring` creates an SNS topic with email subscription plus CloudWatch alarms:

| Alarm | Watches |
|-------|---------|
| `snugd-{env}-api-5xx` | ALB 5xx rate |
| `snugd-{env}-api-latency-p95` | p95 target response time |
| `snugd-{env}-rds-cpu` | RDS CPU |
| `snugd-{env}-rds-low-storage` | RDS free storage |

The app also emits its own Slack alerts via `SLACK_WEBHOOK_URL` (`backend/app/services/monitoring/alerts.py`) and exposes `/metrics`.

## QA Sizing (`environments/qa.tfvars`)

- RDS `db.t4g.micro`, 20 GB, single-AZ, 1-day backups, deletion protection off
- Redis `cache.t4g.micro`, 1 node
- ECS 256 CPU / 512 MB per service, 1 task each
- `enable_redundant_nat = false`
- ACM wildcard `*.snugd.ai` shared across dev/qa/prod

## Gotchas

| Issue | Cause / fix |
|-------|-------------|
| `terraform apply` seems to revert the deployed image | It doesn't — `ignore_changes` covers container definitions. Check ECR tags instead |
| Beat restarts unexpectedly | A Terraform apply touching the beat task definition |
| Worker silently stopped after a deploy | Always verify worker health after ECS changes; failures aren't loud |
| ECS task won't start, unclear error | Usually a missing key in `snugd/{env}/secrets` |
| `promote.sh` fails | `--ff-only` — branches diverged, reconcile first |
| Anything prod | Not provisioned; see the state table above |
