# Third-Party Credential Migration Plan

**Goal:** Migrate all third-party integrations from personal credentials to dedicated organization accounts before beta launch, with per-environment isolation and cost controls.

---

## Current State

All services are running on personal accounts with personal API keys. This is a risk for:
- **Security:** Personal keys have broader access than needed
- **Cost:** No spending limits, bills go to personal accounts
- **Continuity:** If personal account is locked/closed, app goes down
- **Compliance:** User data processed through personal accounts

---

## Service Inventory

| Service | Purpose in HomeScout | Current Account | Environments Needed |
|---------|---------------------|----------------|-------------------|
| **Supabase** | Auth (Google OAuth), user profiles, favorites, saved searches, tour pipeline, analytics | Personal project | 3 (dev/qa/prod) |
| **Google Cloud** | OAuth provider (Google Sign-In) | Personal GCP project | 1 project, 3 OAuth configs |
| **Anthropic (Claude)** | Search scoring, comparison analysis, inquiry emails, note enhancement, day plans, decision briefs | Personal API key | 3 keys (dev/qa/prod) |
| **OpenAI** | Whisper transcription for voice notes | Personal API key | 2 keys (dev+qa shared, prod) |
| **Apify** | Apartments.com scraping (19 markets) | Personal account | 1 account, separate tokens per env |
| **Stripe** | Pro subscription payments ($12/mo) | Personal test mode | 2 (test for dev/qa, live for prod) |
| **Resend** | Daily email alerts for Pro users with saved searches | Personal account | 2 (sandbox for dev/qa, prod) |
| **AWS** | ECS, RDS, Redis, ALB, ECR, Secrets Manager | Already org account | Already per-env |
| **ScrapingBee** | Craigslist scraping (backup) | Personal API key | 1 key (prod only) |

---

## Migration Steps (by service)

### 1. Anthropic (Claude) — CRITICAL

**Why first:** Highest usage, highest cost, core product feature.

- [ ] Create Anthropic organization account at console.anthropic.com
- [ ] Create workspace "HomeScout"
- [ ] Generate 3 API keys: `homescout-dev`, `homescout-qa`, `homescout-prod`
- [ ] Set monthly spend limit: $50 (dev), $50 (qa), $200 (prod)
- [ ] Enable email alerts at 80% of spend limit
- [ ] Store keys in AWS Secrets Manager per environment
- [ ] Update ECS task definitions to reference new key ARNs
- [ ] Verify scoring works in dev with new key
- [ ] Revoke personal API key from dev/qa/prod

### 2. Supabase — CRITICAL

**Why second:** Holds all user data, auth, profiles.

- [ ] Create Supabase organization "HomeScout"
- [ ] Create 3 projects: `homescout-dev`, `homescout-qa`, `homescout-prod`
- [ ] For each project:
  - [ ] Run all migrations (001 through latest) in SQL Editor
  - [ ] Enable Google OAuth provider
  - [ ] Configure redirect URLs for that environment
  - [ ] Enable RLS policies
  - [ ] Note: `service_role_key`, `anon_key`, `jwt_secret` per project
- [ ] Migrate existing prod user data (profiles, favorites, saved searches) from personal project
- [ ] Update backend env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
- [ ] Update frontend env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- [ ] Test auth flow in dev with new project
- [ ] Delete personal project only after prod is stable for 1 week

### 3. Google Cloud (OAuth) — CRITICAL

**Why third:** Required for Google Sign-In to work.

- [ ] Create GCP project "homescout-prod"
- [ ] Enable "Google Identity" / OAuth2 API
- [ ] Create OAuth consent screen:
  - App name: "HomeScout"
  - Support email: team email
  - Authorized domains: `homescout.app`, `snugd.ai`
  - Scopes: `email`, `profile`, `openid`
  - **Publishing status: "In production"** (requires verification for >100 users)
- [ ] Create OAuth 2.0 Client IDs:
  - Type: Web application
  - Authorized redirect URIs per environment:
    - Dev: `https://[homescout-dev-project].supabase.co/auth/v1/callback`
    - QA: `https://[homescout-qa-project].supabase.co/auth/v1/callback`
    - Prod: `https://[homescout-prod-project].supabase.co/auth/v1/callback`
- [ ] Enter Client ID + Secret in each Supabase project's Google provider config
- [ ] Submit OAuth consent screen for Google verification (can take 2-4 weeks)
- [ ] Test sign-in flow in each environment

### 4. Stripe — HIGH

- [ ] Create Stripe account for business entity (or continue using same account)
- [ ] Create separate Product + Price for prod vs test mode
- [ ] Generate restricted API keys per environment:
  - Dev/QA: Test mode keys (prefix `sk_test_`)
  - Prod: Live mode keys (prefix `sk_live_`)
- [ ] Create webhook endpoints per environment:
  - `https://api-dev.snugd.ai/api/webhooks/stripe`
  - `https://api-qa.snugd.ai/api/webhooks/stripe`
  - `https://api.snugd.ai/api/webhooks/stripe`
- [ ] Store `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` in Secrets Manager
- [ ] Test checkout flow in dev with test card

### 5. OpenAI (Whisper) — MEDIUM

- [ ] Create OpenAI organization account or project
- [ ] Generate 2 API keys: `homescout-dev` (shared dev/qa), `homescout-prod`
- [ ] Set monthly spend limits: $20 (dev), $50 (prod)
- [ ] Store in Secrets Manager
- [ ] Test voice note transcription in dev

### 6. Apify — MEDIUM

- [ ] Create dedicated Apify account (or keep personal with separate tokens)
- [ ] Generate API tokens per environment
- [ ] Set monthly usage limits per token
- [ ] Store `APIFY_API_TOKEN` in Secrets Manager
- [ ] Verify scraping works in dev

### 7. Resend — LOW

- [ ] Create Resend account for HomeScout
- [ ] Verify sending domain: `homescout.app` (DNS records: SPF, DKIM, DMARC)
- [ ] Create API keys: sandbox (dev/qa), production (prod)
- [ ] Set `ALERT_FROM_EMAIL=alerts@homescout.app`
- [ ] Store `RESEND_API_KEY` in Secrets Manager
- [ ] Test email delivery in sandbox mode

### 8. ScrapingBee — LOW

- [ ] Create dedicated account (or keep personal)
- [ ] Generate prod API key
- [ ] Store in Secrets Manager

---

## Cost Budget (Monthly)

| Service | Dev | QA | Prod | Total |
|---------|-----|-----|------|-------|
| Supabase | Free | Free | Free (or Pro $25) | $0-25 |
| Anthropic | $10 limit | $10 limit | $200 limit | $220 |
| OpenAI | $5 | shared | $50 limit | $55 |
| Apify | $10 | shared | $49 (Starter) | $59 |
| Stripe | 0 (test) | 0 (test) | 2.9% + $0.30/txn | Variable |
| Resend | Free (100/day) | shared | Free (3k/mo) | $0 |
| ScrapingBee | 0 | 0 | $29 (Freelance) | $29 |
| **Subtotal (third-party)** | | | | **~$363-388/mo** |
| AWS (from deploy plan) | $50-70 | $50-70 | $150-250 | $250-390 |
| **Grand total** | | | | **~$613-778/mo** |

---

## Security Checklist

- [ ] All API keys stored in AWS Secrets Manager (never in code)
- [ ] Per-environment isolation (dev key can't access prod)
- [ ] Spending limits set on all services with alerts
- [ ] Restricted API keys where possible (Stripe restricted keys)
- [ ] API key rotation schedule: quarterly
- [ ] Document key names and which Secrets Manager path holds each
- [ ] Revoke all personal keys after migration verified (1 week soak period)
- [ ] Enable 2FA on all service accounts
- [ ] Add team email as recovery/billing contact (not personal email)

---

## Migration Order & Timeline

| Week | Services | Blocker? |
|------|----------|----------|
| 1 | Anthropic + OpenAI (API key swap, no data migration) | No |
| 1 | Resend + ScrapingBee (simple key swap) | No |
| 2 | Supabase (requires data migration + auth reconfiguration) | Yes — users re-auth |
| 2 | Google Cloud OAuth (must align with Supabase migration) | Yes — tied to Supabase |
| 2 | Stripe (webhook URL updates) | No |
| 3 | Apify (token swap, verify scraping) | No |
| 3 | Revoke personal keys, final verification | — |

**Critical dependency:** Supabase + Google OAuth must migrate together. Users will need to re-authenticate after the Supabase project changes (refresh tokens are project-scoped).

---

## Rollback Plan

Each service migration is independent (except Supabase + Google):
- Keep personal keys active for 1 week after each migration
- If production breaks, revert Secrets Manager to personal key ARN
- Supabase: keep personal project active for 2 weeks; can repoint `SUPABASE_URL` back
