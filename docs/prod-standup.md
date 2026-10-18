# Prod Stand-up Runbook

How to bring `api.snugd.ai` + `snugd.ai` up as the real app, with `qa.snugd.ai` reverting to internal staging. Written 2026-10-18 against a verified clean slate.

**Owner key:** **[human]** = needs you (console, credentials, DNS, or a judgement call). **[Claude w/ approval]** = Claude can run it, but it changes something live, so it asks first.

## State on 2026-10-18 (verified, not assumed)

| Thing | State |
|---|---|
| `snugd/prod/secrets`, `snugd/prod/db-password` | **Do not exist** (only the two QA secrets are in Secrets Manager) |
| Prod VPC / ECS / ALB / Redis / log groups | None |
| Terraform state `infra/prod/terraform.tfstate` | Deleted in S3 (delete marker after the 2026-05-04 teardown), **but its MD5 digest is still in the DynamoDB lock table**, so `terraform init` for prod fails with "state data in S3 does not have the expected content" — fixed in step 1 |
| RDS snapshot `snugd-prod-final` | Exists, 2026-05-04, 50 GB. **Don't use it** — five months of schema and listings behind |
| QA RDS | Postgres 16.13 (auto-minor-upgraded from the 16.6 in Terraform), 20 GB, daily automated snapshots |
| Prod Supabase project `arbfkxvrkdsaojyecjby` | Exists; waitlist on snugd.ai writes to it. Which other migrations are applied is unknown — check in step 6 |
| GitHub `prod` environment | Exists with required reviewers. `PROD_PRIVATE_SUBNETS` / `PROD_ECS_SG` are from **2026-04-14** and point at the destroyed VPC — must be replaced in step 5 |
| Branches | `main` is 51 commits **behind** `release/qa` (0 ahead); `release/prod` is 221 behind `release/qa`, last touched 2026-04-10 |
| Vercel `snugd` project (snugd.ai) | Builds from **`main`**, not `release/prod` — see step 9 |

## Terraform changes already made (branch `chore/prod-standup-prep`)

- `prod.tfvars`: `use_floorplan_search = "true"`, `beat_desired_count = 1`, `rds_snapshot_identifier = "snugd-qa-prod-bootstrap"`, `rds_engine_version = "16"`, storage 50 → 20 GB, `alert_email = ""` placeholder.
- `modules/rds`: optional `snapshot_identifier` (null default; `ignore_changes` so clearing it later can't replace the DB) and `engine_version` variable (default `16.6` — QA's config is unchanged).
- `scripts/deploy.sh tf-plan|tf-apply`: `init` now passes `-reconfigure`.
- `terraform validate` and `fmt -check` pass. `plan` for prod has **not** been run — it is blocked by the stale digest (step 1).

---

## 1. Clear the stale Terraform digest **[Claude w/ approval]**

The 2026-05-04 teardown deleted the state object but left `…-md5` in DynamoDB. First confirm the last state version was the post-destroy one (zero resources) — **[human]**, since a non-empty state file contains the old DB password:

```bash
VER=$(aws s3api list-object-versions --bucket homescout-terraform-state \
  --prefix infra/prod/terraform.tfstate \
  --query 'Versions[?LastModified==`2026-05-04T22:19:08+00:00`].VersionId' --output text)
aws s3api get-object --bucket homescout-terraform-state --key infra/prod/terraform.tfstate \
  --version-id "$VER" /dev/stdout | jq '.resources | length'     # expect 0
```

Then remove the digest:

```bash
aws dynamodb delete-item --table-name homescout-terraform-locks --region us-east-1 \
  --key '{"LockID":{"S":"homescout-terraform-state/infra/prod/terraform.tfstate-md5"}}'
```

## 2. Give prod an image to pull **[Claude w/ approval]**

ECS services are created pointing at `:prod-latest`, which doesn't exist yet. Retag the current QA image (no rebuild; ECR is shared):

```bash
MANIFEST=$(aws ecr batch-get-image --repository-name snugd-backend --region us-east-1 \
  --image-ids imageTag=qa-latest --query 'images[0].imageManifest' --output text)
aws ecr put-image --repository-name snugd-backend --region us-east-1 \
  --image-tag prod-latest --image-manifest "$MANIFEST"
```

CI replaces it with a real `:prod-{sha}` in step 8.

## 3. Snapshot QA for the prod database **[Claude w/ approval]**

A manual snapshot, so it isn't aged out by QA's 1-day automated retention. Same account, region and KMS key — no copy or share needed.

```bash
aws rds create-db-snapshot --region us-east-1 \
  --db-instance-identifier snugd-qa --db-snapshot-identifier snugd-qa-prod-bootstrap
aws rds wait db-snapshot-available --region us-east-1 --db-snapshot-identifier snugd-qa-prod-bootstrap
```

Prod then starts with QA's corpus, floorplan buckets, `market_configs` and alembic head. It also carries QA's scrape-job history — harmless. Nothing user-owned lives in RDS (that's Supabase), so no tester data crosses over.

Alternative: delete `rds_snapshot_identifier` from `prod.tfvars` for an empty DB; the CI migrate step builds the schema and the first scrape fills it (a few hours of empty search).

## 4. Terraform, phase A: data stores + secret container **[Claude w/ approval]**

Terraform owns the `snugd/prod/secrets` *container* (`aws_secretsmanager_secret.app_secrets`), so don't `create-secret` by hand — the apply would then fail with "already exists". But the secret must hold `DATABASE_URL` and `REDIS_URL`, which only exist once RDS and Redis do, and ECS refuses to start a task whose secret is missing a key. Hence two phases.

Always pass `-reconfigure` (`scripts/deploy.sh tf-plan|tf-apply` now does): a bare `terraform init -backend-config=key=…` in a directory already initialised for QA prompts to **copy QA's state into the prod key**. The targeted phase below isn't covered by `deploy.sh`, so it's spelled out.

```bash
cd infra
terraform init -reconfigure -backend-config="key=infra/prod/terraform.tfstate"
terraform plan  -var-file=environments/prod.tfvars \
  -target=aws_secretsmanager_secret.app_secrets -target=module.rds -target=module.elasticache
terraform apply -var-file=environments/prod.tfvars \
  -target=aws_secretsmanager_secret.app_secrets -target=module.rds -target=module.elasticache
```

(`module.networking` comes along as a dependency. The restore takes ~15–20 min.)

## 5. Populate `snugd/prod/secrets` **[human]** (Claude can assemble the non-secret parts)

Build the JSON in a temp file outside the repo, `chmod 600`, **never commit it**, delete it after. ECS injects exactly the 15 keys in `infra/modules/ecs/main.tf` (`local.secret_keys`); every one must be present or no task starts.

| Key | Required at task start | Prod value |
|---|---|---|
| `DATABASE_URL` | yes | **prod-specific** — composed from `snugd/prod/db-password` (below) |
| `REDIS_URL` | yes | **prod-specific** — `redis://<terraform output redis_endpoint>:6379/0` (no TLS on this cluster) |
| `SUPABASE_URL` | yes | **prod-specific** — `https://arbfkxvrkdsaojyecjby.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | **prod-specific** — prod project → Settings → API |
| `SUPABASE_JWT_SECRET` | yes | **prod-specific** — prod project → Settings → API → JWT secret |
| `ANTHROPIC_API_KEY` | yes | **prod-specific** — new key, own spend limit (AI is becoming free for all signed-in users) |
| `OPENAI_API_KEY` | yes | **prod-specific** — new key with a budget cap (Whisper) |
| `ADMIN_API_KEY` | yes | **prod-specific** — fresh random, e.g. `openssl rand -hex 32` |
| `RESEND_API_KEY` | yes | can reuse QA's; a separate key makes prod mail traceable |
| `APIFY_API_TOKEN` | yes | can reuse QA's (same account, same billing) |
| `GOOGLE_MAPS_API_KEY` | yes | can reuse QA's; check its HTTP-referrer/IP restrictions allow prod |
| `SCRAPINGBEE_API_KEY` | yes | can reuse QA's (fallback scraper) |
| `STRIPE_SECRET_KEY` | yes | **placeholder** (e.g. `unused`) — billing is dormant |
| `STRIPE_WEBHOOK_SECRET` | yes | **placeholder** |
| `STRIPE_PRICE_ID` | yes | **placeholder** |

Not needed: `FRONTEND_URL` is in the QA secret but ECS never reads it from there — Terraform sets it as plain env from `frontend_url`. Optional backend vars that nothing injects (so they're unset in QA too): `SLACK_WEBHOOK_URL` (app Slack alerts), `SUPABASE_WEBHOOK_SECRET` (falls back to `"test-secret"`), `ALERT_EMAIL_*`, `APIFY_*_ACTOR_ID` (have defaults). Adding one means adding it to `local.secret_keys` too.

Compose `DATABASE_URL` without printing it:

```bash
TMP=$(mktemp -d); chmod 700 "$TMP"
aws secretsmanager get-secret-value --secret-id snugd/prod/db-password --region us-east-1 \
  --query SecretString --output text \
  | jq -r '"postgresql+asyncpg://\(.username):\(.password)@\(.host):\(.port)/\(.dbname)"' > "$TMP/db_url"
# …build $TMP/prod-secrets.json with all 15 keys (jq --rawfile for each value)…
aws secretsmanager put-secret-value --secret-id snugd/prod/secrets --region us-east-1 \
  --secret-string "file://$TMP/prod-secrets.json"
rm -rf "$TMP"
```

Verify by **key names only**: `… get-secret-value … | jq -r 'keys[]'` → expect exactly the 15 above.

## 6. Terraform, phase B: everything else **[Claude w/ approval]**

```bash
terraform plan  -var-file=environments/prod.tfvars    # review: all creates, no replaces
terraform apply -var-file=environments/prod.tfvars
terraform output alb_dns_name
terraform output private_subnet_ids
terraform output ecs_security_group_id
```

Then update the GitHub `prod` environment secrets — the April values point at the destroyed VPC and the CI migrate step will fail on them **[Claude w/ approval]**:

```bash
gh secret set PROD_PRIVATE_SUBNETS --env prod --body "subnet-aaa,subnet-bbb"   # comma-separated, from the output
gh secret set PROD_ECS_SG          --env prod --body "sg-…"
```

Check the services came up (a stopped worker is silent): `./scripts/deploy.sh status prod`.

## 7. DNS and Supabase **[human]**

**DNS:** at the registrar, `api.snugd.ai` → CNAME to `alb_dns_name`. The `*.snugd.ai` ACM cert already covers it. Then `curl https://api.snugd.ai/health`.

**Supabase prod (`arbfkxvrkdsaojyecjby`)** — there is no migration runner; migrations go through the SQL editor (`supabase/CLAUDE.md`).

1. See what's already there (the waitlist means at least 007 ran, possibly out of order):
   ```sql
   select table_name from information_schema.tables where table_schema = 'public' order by 1;
   ```
2. Apply `001` → `014` in order, skipping any whose objects already exist (`007_waitlist.sql` uses a bare `create table`, so re-running it errors). `012_saved_listings_cutover.sql` warns about ordering against a live deploy — on a fresh project with no app reading it, that doesn't apply.
3. **Auth → Providers:** enable Google and Apple with prod OAuth clients. Google console: authorised redirect URI `https://arbfkxvrkdsaojyecjby.supabase.co/auth/v1/callback`. Apple: Services ID + key, same callback.
4. **Auth → URL configuration:** Site URL `https://snugd.ai`; redirect URLs `https://snugd.ai/**`, `https://www.snugd.ai/**`, and the future mobile deep link — placeholder `ai.snugd.app://auth/callback` (final scheme is decided when the Capacitor shell is built).

## 8. Promote code to prod **[Claude w/ approval]**

`promote.sh` is `--ff-only` both hops. `main` is currently **behind** `release/qa` (51 commits, 0 ahead), so before anything else lands on `main`, fast-forward it — otherwise the next `promote.sh qa` fails as diverged:

```bash
git checkout main && git merge --ff-only origin/release/qa && git push origin main
```

Then, once step 1 of the plan (AI free for all) is on `release/qa` and verified on qa.snugd.ai:

```bash
./scripts/promote.sh prod     # release/qa → release/prod; CI build + migrate + deploy, needs approval in Actions
```

`deploy-backend.yml` only triggers on `backend/**` changes — the first prod push has plenty, but if a later run doesn't fire, use workflow_dispatch.

**Markets:** with the QA snapshot, `market_configs` arrive as QA has them. Confirm the 8 live cities (Boston, Bryn Mawr, Cambridge, New York, Philadelphia, Pittsburgh, San Francisco, State College) are enabled:

```bash
KEY=$(aws secretsmanager get-secret-value --secret-id snugd/prod/secrets --region us-east-1 \
  --query SecretString --output text | jq -r .ADMIN_API_KEY)
curl -s -H "X-Admin-Key: $KEY" https://api.snugd.ai/api/admin/data-collection/markets | jq '.markets[] | {id, display_name, is_enabled, last_scrape_at}'
curl -s -X PUT -H "X-Admin-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"is_enabled": true}' https://api.snugd.ai/api/admin/data-collection/markets/<market_id>
```

## 9. Frontend on snugd.ai **[human]** (Vercel dashboard)

`snugd` project → Settings → Environment Variables, **Production** scope:

| Var | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.snugd.ai` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://arbfkxvrkdsaojyecjby.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | prod anon key |
| `NEXT_PUBLIC_FLOORPLAN_SEARCH` | `true` |

All `NEXT_PUBLIC_*` are build-time — **redeploy with a fresh build**, not a promote of an old one.

**Decide the production branch.** Vercel builds snugd.ai from `main`, while the backend ships from `release/prod` behind an approval. Once snugd.ai is the app, every merge to `main` would ship frontend to real users ahead of the backend it expects. Recommended: set the `snugd` project's Production Branch to `release/prod`.

The landing/app switch (the `/` → `/landing` host rewrite in `next.config.ts`, removing the "go to qa.snugd.ai with this code" flow) is step 3 of the overall plan — a code change, not part of this runbook.

## 10. Verify **[Claude w/ approval]**

```bash
./scripts/smoke-test.sh prod
curl -s -H "X-Admin-Key: $KEY" https://api.snugd.ai/api/admin/data-collection/pipeline-health | jq
./scripts/beta-report.sh prod 30 20      # empty cohort, healthy infra
```

Then sign in on snugd.ai with Google **and** Apple, run a search, favourite a listing (queues a `check_saved_listing` on the worker — `pipeline-health` → `listing_checks.unchecked_backlog` should stay 0), add a tour, record a voice note (worker + Whisper + S3).

## Cost

Same sizing as QA, us-east-1 on-demand, approximate:

| Item | $/mo |
|---|---|
| NAT gateway (single) + its public IP | ~36 |
| ALB + public IPs | ~20–25 |
| Fargate: api + worker + beat, 0.25 vCPU / 0.5 GB each | ~27 |
| RDS db.t4g.micro + 20 GB gp3 | ~14 |
| ElastiCache cache.t4g.micro | ~12 |
| Secrets, CloudWatch logs/alarms, S3 | ~5 |
| **Infra total** | **~$115–120** |

On top: Apify for prod's own weekly sweeps (QA keeps sweeping too, so scraping roughly doubles — still single-digit dollars at ~$0.0005/listing), and Anthropic/OpenAI usage, which is now driven by every signed-in user.
