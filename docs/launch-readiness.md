# Beta Launch Readiness

> Last updated: **2026-06-22**.
> Status: **beta in production on `qa.snugd.ai`** with 5 active Pro testers, 17 invite codes minted, 7 tours created. Prod environment dormant; launch gated by human-side prerequisites (Stripe live keys, prod-tier API keys, DNS cutover) — no remaining engineering blockers.

## Status at a glance

**Functionally complete and validated on QA:**
- Scraper produces fresh data, 1,047 active listings across 6 markets (Pittsburgh, Philadelphia, Boston, Cambridge, San Francisco, New York, Baltimore, Washington, Bryn Mawr, Somerville), avg `data_quality_score` 98.73
- Search anonymous / free / Pro tiers with metering + 429 over-limit
- Search heuristic + Pro AI scoring (Claude Haiku) via `/api/search/score-batch` with Redis caching
- **Compare** with Claude head-to-head analysis — now Haiku 4.5 (18s fresh, 1s cached), Sonnet 4.5 still accessible via `?ai_model=sonnet` override (commit `2fc89e5`)
- Tour pipeline: schedule, rate (auto-advances stage), tag, typed/voice notes, photo upload, decision
- **Contact tab** (renamed from Email): phone-first UX with call / SMS / apartments.com deep-link buttons (`#sendMessageBtn`, `#checkAvailabilityTourBtn` verified IDs). AI inquiry message editable inline, persisted on blur. (`53450db`, `205efc9`, `9b3455f`, `a2c2a3d`)
- **Day Plan** optimizer with optional starting-address input, persisted in localStorage (`2d36bab`)
- Voice notes → S3 → Whisper → Claude enhance, ~10s round-trip
- Photo upload → S3 → grid display
- Admin auth on `/api/admin/data-collection/*`, `/api/admin/invite-codes`, `/api/admin/beta-report` via X-Admin-Key
- `snugd-tours-qa` S3 bucket + IAM + OPENAI_API_KEY + S3_BUCKET_NAME in ECS task def
- `beds_label` / `baths_label` API fields for multi-floor-plan listings
- Enrichment fields extracted from raw scrape data: `specials`, `walk_score`, `transit_score`, `apartments_com_rating`, `available_units`, `transit_options`, `virtual_tour_urls`, `nearby_schools`, `floor_plans` (Commits 1 + 27)
- Smarter utility detection in `cost_estimator.py` — negation guard + per-utility description regex + broader amenity matching (`e40d225`)
- PWA installable on phone home screens (`b642317`, `6d02f87`)
- Commute calculator for tour/compare/favorites (`ebc666e`)
- Production waitlist live on `snugd.ai` (Vercel + Supabase prod direct writes)
- E2E test suite green; CI workflow stops fighting Terraform for ECS image ownership (`a66cc2e`)
- Beta usage report endpoint + CLI (`scripts/beta-report.sh`) — covers redemption stats, cohort, tour pipeline, top users, feedback, analytics events (`03850f1`, `eba8198`)
- Analytics event instrumentation for `search`, `compare`, `redeem`, `tour-add`, `message-generated`, `favorite-add`, `favorite-remove` — funnel signal now readable from `beta-report` output

**17 invite codes minted, 5 redeemed (29%), all 5 active Pro:**
- `BETA-PITT` (50 uses, 0 redeemed) — Pittsburgh cohort
- `BETA-GIRLHACKS` (30 uses, 0 redeemed, expires 2026-09-15) — event-specific
- 5× legacy single-use codes redeemed: `BETA-AD7366`, `BETA-91E169`, `BETA-6F283D`, `BETA-399E27`, `BETA-012D87`
- 10× unredeemed single-use codes still circulating

## Open items (none P0)

Each item references the in-session task tracker.

| # | Status | Type | Description |
|---|---|---|---|
| 24 | open | product | Swap Commute-address autocomplete from Nominatim/OSM to **Google Places Autocomplete** (Maps key already provisioned). Nominatim whiffs on building names ("The Tower at PNC Plaza" → 0 results) and picks the wrong city for bare street addresses. Contained change: `frontend/components/CommuteAddresses.tsx` + `frontend/lib/geocode.ts`. |
| 29 | open | feature | **Per-tour pro100chok detail enrichment** (FAQ-based utility detection). Full implementation plan saved at `docs/pro100chok-enrichment-plan.md`. Hybrid plan: keep epctex for bulk scrape; fire pro100chok detail call on favorite/compare/tour-add via BackgroundTasks. Unlocks authoritative utility-inclusion answers (vs current regex), office hours, structured per-pet-type fees, bike/sound scores. Effort: 1.5 days. Cost: ~$2-3/mo at beta scale. |
| 32 | open | product | **Surface `floor_plans` on apartment/tour detail** — already scraped → stored (`ApartmentModel.floor_plans` JSONB) → already returned by `/api/apartments/{id}` + `/batch` via `to_dict()`, but **no frontend consumes it** (absent from `frontend/types/apartment.ts`, no component). Frontend-only: add the field to the type + render a unit-models table (price / sqft / availability) in the tour-detail InfoTab. Complements per-person/occupancy pricing. **`nearby_schools` parked** (same extracted-but-unused state): deliberately not surfaced — low fit for the student/young-pro audience, and HUD fair-housing guidance bundles school-quality with crime data (disparate-impact risk); see roadmap "Dropped / Done Differently". |

**Two data-quality notes** (acceptable for beta, naturally resolved by #29):
- Pet one-time fees ($240-$300) intentionally skipped by current normalizer; Pro renter-with-pet sees an under-counted `true_cost_move_in`. pro100chok itemizes per-pet-type fees → resolves automatically when #29 ships.
- Insurance zero-out edge case: when "Renters Insurance Required" amenity fires without a corresponding `amenity_fee`, `est_renters_insurance` zeroes without compensating charge.

## Production launch prerequisites

These need human-side action before `terraform apply -var-file=environments/prod.tfvars` is safe:

1. **Cost approval.** Prod is dormant per `docs/deployment.md`; re-provisioning RDS + ALB + ECS + Redis = ~$50–100/mo. Snapshot `snugd-prod-final` exists for RDS restore.
2. **Supabase prod project.** ✅ Already configured (`arbfkxvrkdsaojyecjby`). Site URL set to `https://snugd.ai`, redirect URLs to `https://snugd.ai/**`. Anon + service-role + JWT secret in AWS Secrets Manager at `snugd/prod/secrets`. Prod waitlist already live on snugd.ai writing directly to this project.
3. **Stripe live mode.** Real `STRIPE_SECRET_KEY`, real `STRIPE_PRICE_ID` for the $12/mo Pro plan, webhook endpoint configured to `https://api.snugd.ai/api/webhooks/stripe` with its own `STRIPE_WEBHOOK_SECRET`.
4. **OpenAI prod key.** Separate from QA so spend is segregated. Set a budget alert in the OpenAI dashboard.
5. **Anthropic key.** Same — separate key for prod budget tracking. Worth noting: compare endpoint now defaults to Haiku, which is ~10× cheaper than the prior Sonnet default.
6. **DNS update.** After `terraform apply prod` outputs the new ALB DNS, update the registrar (managed outside Terraform) to point `api.snugd.ai` at the prod ALB. Vercel-managed domains (`snugd.ai`, `qa.snugd.ai`) are unaffected.
7. **Launch city set.** Pick 2–4 cities to enable in `market_configs` (currently all disabled in prod by design). Beat will re-scrape those daily so `freshness_confidence ≥ 40` keeps them in search results.
8. **Smoke + invite.** Run `scripts/smoke-test.sh prod`, mint BETA codes against `snugd/prod/secrets`'s ADMIN_API_KEY, hand them out.

## Production deploy sequence (when ready)

```
1. terraform apply -var-file=environments/prod.tfvars
   - creates: VPC, RDS (from snugd-prod-final snapshot), Redis, ECS cluster + services, ALB
   - tfvars currently has beat_desired_count = 0 (intentional — see deployment.md)
   - image_tag = "prod-latest" (set in tfvars), CI publishes both :prod-{SHA} and :prod-latest
   - lifecycle.ignore_changes on container_definitions / task_definition means TF
     no longer fights CI for image ownership (a66cc2e)
2. Push to release/prod branch
   - CI builds image, pushes to ECR as prod-${SHA} AND prod-latest
   - registers new TD revision, updates ECS service
   - runs alembic migrations, smoke test
3. Update DNS: api.snugd.ai → new ALB DNS name
4. Vercel: confirm production env vars (NEXT_PUBLIC_API_URL=https://api.snugd.ai, prod Supabase URL + anon key)
5. Run scripts/smoke-test.sh prod
6. Enable selected market_configs for launch cities, scale beat to 1
7. Mint BETA codes against prod admin endpoint, hand out
8. scripts/beta-report.sh prod  (sanity-check empty cohort + healthy infra)
```

## Git state

`release/qa` and `main` synchronized as of the most recent merge. Most recent meaningful commits (newest first):
- `eba8198` — fix(scripts): beta-report.sh — pass JSON via env var, not stdin
- `03850f1` — feat(admin): beta usage report endpoint + CLI wrapper
- `664d6c7` — fix(ci): make CI green
- `ebc666e` — feat(commute): commute calculator for tour/compare/favorites
- `2fc89e5` — perf(compare): Redis cache + Haiku default + ?ai_model override
- `a2c2a3d` — feat(tours): apartments.com deep-link CTAs
- `e40d225` — fix(true-cost): smarter utility-inclusion detection
- `9b3455f` — feat(tours): editable inquiry draft + concise pre-action hint
- `205efc9` — feat(tours): Contact this property + Schedule a tour buttons
- `dec4e2b` — feat(extraction): pull nearby_schools + floor_plans out of raw_data
- `26a1626` — fix(tasks): persistent per-process event loop + direct-await /metrics
- `5a31f7b` — feat(enrichment): extract specials, walk/transit score, units from raw_data

`release/prod` last touched 2026-04-10 — needs fast-forward from `main` when ready to deploy.

## What changed since the 2026-05-29 snapshot

This section preserves the diff in case you want to scan-read what shipped:

- **All blockers from the prior list are closed.** #8/#9/#11/#16/#17/#19/#21/#22/#24 (the email→contact UX rework that closed the email-tab limitations) all resolved. None remain.
- **Compare endpoint is now fast.** 36s → 18s fresh, ~1s cached, ~$0.014/call (was $0.05).
- **scripts/beta-report.sh** exists for one-command usage reports across invite codes, cohort, tours, top users, feedback, and event funnel. Run as `./scripts/beta-report.sh qa 14 10` (env, days, top_n).
- **Compare AI gets smarter for free** once #29 ships — the FAQ data goes directly into Claude's compare prompt.
- **Vercel projects:** prod deploys from `main` (snugd.ai); QA deploys from `release/qa` (qa.snugd.ai).
- **17 invite codes** vs the original 5; cohort grew to 5 active Pro users.

## How to monitor beta health

```bash
# One-shot usage report (markdown to stdout)
./scripts/beta-report.sh qa

# Archive a daily snapshot
./scripts/beta-report.sh qa 14 10 > reports/beta-$(date +%Y%m%d).md

# Funnel queries via the JSON API directly
ADMIN=$(aws secretsmanager get-secret-value --secret-id snugd/qa/secrets --region us-east-1 \
  --query SecretString --output text | jq -r .ADMIN_API_KEY)
curl -sS -H "X-Admin-Key: $ADMIN" https://api-qa.snugd.ai/api/admin/beta-report | jq

# Smoke test (quick health check)
./scripts/smoke-test.sh qa
```

The event funnel currently logs: `search`, `compare`, `redeem`, `tour-add`, `message-generated`, `favorite-add`, `favorite-remove`. Conversion analysis is now possible — e.g., "of users who redeemed, how many added at least one tour."
