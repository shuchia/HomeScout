# Prod Stand-up Runbook

How to bring `api.snugd.ai` + `snugd.ai` up as the real app, with `qa.snugd.ai` reverting to internal staging. Written 2026-10-18 against a verified clean slate; decisions folded in 2026-10-25.

**Decided 2026-10-25:**
- Prod starts from a copy of QA — **both** the RDS corpus (step 3) and the Supabase project: users, profiles, saved listings, tours, notes, invite codes (step 7) — plus the tour-assets bucket (step 6), so testers keep their history when they move to snugd.ai.
- snugd.ai builds from `release/prod` (step 9).
- Prod Supabase is the existing project `arbfkxvrkdsaojyecjby`.
- Alarms go to `shuchi@snugd.ai` (`alert_email`, step 3).
- Still open: the mobile deep-link scheme (not needed until the mobile apps — step 7.5).

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
| Branches | `main` fast-forwarded to `release/qa` on 2026-10-25 (equal); `release/prod` is far behind, last touched 2026-04-10 |
| Vercel `snugd` project (snugd.ai) | Builds from **`main`**; switching to `release/prod` in step 9 |

## Terraform changes already made (branch `chore/prod-standup-prep`)

- `prod.tfvars`: `use_floorplan_search = "true"`, `beat_desired_count = 1`, `rds_snapshot_identifier = "snugd-qa-prod-bootstrap"`, `rds_engine_version = "16"`, storage 50 → 20 GB, `alert_email = "shuchi@snugd.ai"`.
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

Prod then starts with QA's corpus, floorplan buckets, `market_configs` and alembic head. It also carries QA's scrape-job history — harmless. Nothing user-owned lives in RDS — tester data is in Supabase and is copied separately in step 7. Saved listings and tours reference apartment IDs, which match because both copies come from QA.

Alternative: delete `rds_snapshot_identifier` from `prod.tfvars` for an empty DB; the CI migrate step builds the schema and the first scrape fills it (a few hours of empty search).

**`alert_email`** (`shuchi@snugd.ai` in `prod.tfvars`) subscribes that address to the prod SNS topic for the four CloudWatch alarms: API 5xx errors, API p95 latency, RDS CPU, and RDS low storage. AWS sends a "confirm subscription" email first; nothing arrives until it's clicked. Leaving it `""` creates the alarms with nowhere to send them. These cover infrastructure only — a stopped worker or a stale scrape shows up in `pipeline-health`, not here.

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

**Tour assets** **[Claude w/ approval]** — voice notes and photos live in `snugd-tours-${env}`, and the rows copied in step 7 point at keys that only exist in QA's bucket. Copy them once the prod bucket exists; re-run right before the step 7 copy to pick up anything new:

```bash
aws s3 sync s3://snugd-tours-qa s3://snugd-tours-prod
```

Prod has no expiry rule on this bucket (`infra/main.tf`, `count = environment != "prod"`), so copied recordings stop ageing out.

## 7. DNS and Supabase **[human]**

**DNS:** at the registrar, `api.snugd.ai` → CNAME to `alb_dns_name`. The `*.snugd.ai` ACM cert already covers it. Then `curl https://api.snugd.ai/health`.

**Supabase prod (`arbfkxvrkdsaojyecjby`)** — prod gets a copy of QA's project: schema, users and data. That replaces applying migrations by hand; whatever QA has applied (015 included, 016 if it has landed) comes across with the schema.

**When:** this is a snapshot. Anything testers do on qa.snugd.ai after it stays on QA. Run it last, just before snugd.ai switches to the app (step 9), and tell testers to stop using QA from that point.

**What carries over, and what doesn't:**
- Users keep their accounts and data. Google sign-in matches on the Google account ID, which is the same for both projects, so a tester who signs in on snugd.ai lands on their own profile, favourites and tours.
- Sessions don't carry over (the projects have different JWT secrets) — everyone signs in once more.
- The QA test users (`qa-test-bot@`, `qa-test-free@`) come too; delete them in prod afterwards or keep them for prod smoke tests.
- Prod's existing waitlist sign-ups are kept and merged with QA's.

### 7.1 Prerequisites **[human]**
- Both database connection strings: each project → Connect → **Session pooler** URI (port 5432), with the database password filled in. Put them in a temp file — never on the command line or in the repo:
  ```bash
  TMP=$(mktemp -d); chmod 700 "$TMP"
  printf 'QA_DB=%s\nPROD_DB=%s\n' '<qa uri>' '<prod uri>' > "$TMP/db.env"   # or paste with an editor
  set -a; . "$TMP/db.env"; set +a
  ```
- `pg_dump`/`psql` at least as new as the Supabase server (they're not installed on this machine): `brew install libpq && export PATH="$(brew --prefix libpq)/bin:$PATH"`.

### 7.2 Look before overwriting **[Claude w/ approval]**
```bash
psql "$PROD_DB" -c "select table_name from information_schema.tables where table_schema='public' order by 1"
psql "$PROD_DB" -c "select count(*) as auth_users from auth.users"
psql "$PROD_DB" -c "select count(*) as waitlist from public.waitlist"
```
Expect only `waitlist` and zero auth users. **If prod has auth users or other tables with data, stop** — the steps below assume nothing there needs keeping except the waitlist.

### 7.3 Copy **[Claude w/ approval]**
```bash
cd "$TMP"
# Prod's waitlist, as inserts that skip duplicates
pg_dump "$PROD_DB" --data-only --table=public.waitlist --inserts --on-conflict-do-nothing > prod_waitlist.sql
# QA: public schema (tables, RLS policies, grants, functions), then data
pg_dump "$QA_DB" --schema-only --schema=public --no-owner > schema.sql
pg_dump "$QA_DB" --data-only --schema=public > public_data.sql
pg_dump "$QA_DB" --data-only --table=auth.users --table=auth.identities > auth_data.sql

psql "$PROD_DB" --single-transaction -v ON_ERROR_STOP=1 <<'SQL'
-- Clear prod's public tables (only the waitlist, per 7.2; saved above)
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('drop table public.%I cascade', t);
  end loop;
end $$;
drop function if exists public.handle_new_user() cascade;
\i schema.sql
-- The signup trigger lives on auth.users, so a public-schema dump misses it
create trigger on_auth_user_created after insert on auth.users
  for each row execute procedure public.handle_new_user();
-- replica: skip triggers and FK order checks while loading, so copied users
-- don't get a second profile from handle_new_user
set session_replication_role = replica;
\i auth_data.sql
\i public_data.sql
set session_replication_role = origin;
\i prod_waitlist.sql
SQL
```
`--single-transaction` + `ON_ERROR_STOP`: any error rolls the whole thing back and prod is left as it was. If `schema.sql` fails on `CREATE SCHEMA public` (it already exists), delete that line and re-run.

### 7.4 Verify, then clean up **[Claude w/ approval]**
```bash
for t in auth.users profiles saved_listings tour_notes invite_codes invite_redemptions saved_searches waitlist; do
  echo "$t  qa=$(psql "$QA_DB" -Atc "select count(*) from $t")  prod=$(psql "$PROD_DB" -Atc "select count(*) from $t")"
done
rm -rf "$TMP"     # the dumps hold user emails
```
Counts should match, except `waitlist` (prod ≥ QA). Then re-check the 015 permission fix on prod: a signed-in user's `update profiles set user_tier='pro'` must return 403.

### 7.5 Auth settings **[human]** (dashboard — not copied by the dump)
1. **Auth → Providers:** enable Google and Apple with prod OAuth clients. Google console: authorised redirect URI `https://arbfkxvrkdsaojyecjby.supabase.co/auth/v1/callback`. Apple: Services ID + key, same callback.
2. **Auth → URL configuration:** Site URL `https://snugd.ai`; redirect URLs `https://snugd.ai/**`, `https://www.snugd.ai/**`.
3. **Mobile deep link — later.** When the iOS/Android apps exist, Google sign-in has to return to the *app*, not a browser tab. That's a URL the app claims — either a custom scheme (`snugd://auth/callback`) or a universal/app link (`https://snugd.ai/auth/callback` opened by the app). It gets added to the redirect URLs above when the app is built; nothing for prod web needs it.

## 8. Promote code to prod **[Claude w/ approval]**

`promote.sh` is `--ff-only` both hops. `main` was fast-forwarded to `release/qa` on 2026-10-25, after AI-free-for-all was verified on qa.snugd.ai. Keep the two from diverging — work lands on `main` and is promoted, not merged straight into `release/qa` — or the next `promote.sh qa` fails. Then:

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

**Production branch → `release/prod`** (decided 2026-10-25): `snugd` project → Settings → Git → Production Branch. Otherwise every merge to `main` ships frontend to real users ahead of the backend it expects, which ships from `release/prod` behind an approval. Changing the setting doesn't redeploy — snugd.ai keeps serving its current build until the next push to `release/prod`, which is the step 8 promote. Set the env vars above **before** that push, since it is the build that bakes them in.

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
