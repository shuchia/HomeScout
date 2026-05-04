# Roadmap

> Last updated: 2026-05-04 | Living document — keep it lean

## Next Up

**Email response tracking and auto-stage-advancement (touring pipeline).**

- Detect inbound landlord replies (Resend webhook for Pro alerts users, or per-user IMAP for users who reply from their own inbox).
- Use Claude Haiku to extract proposed tour times from email body.
- Show a one-click confirmation in the tour detail; on accept, advance `outreach_sent` → `scheduled` and set `scheduled_at`.
- Send reminder nudges if no response after N days.
- Reuses existing Resend infra and the tours router. Pro-tier only.

## Planned

- **Neighborhood insights** — walkability, transit, safety scores via a third-party API on apartment detail pages.
- **Commute calculator** — Google Distance Matrix or Mapbox; user adds work/school addresses, listings show transit/drive time.
- **Tour pipeline polish from beta feedback** — `FeedbackWidget` is collecting beta signal; triage and ship the high-value fixes once volume warrants.
- **Weekly + price-drop email digests** — extend the existing daily Pro alert task to add weekly summaries and price-drop notifications on saved searches.

## Recently Shipped (last 60 days)

- Multi-environment deploy pipeline (dev/qa/prod) with branch-based triggers, smoke tests, and on-demand scraping.
- True cost calculator with per-region utility/fees estimates and per-listing breakdowns.
- Per-person pricing detection and occupancy calculator for shared/per-bed listings.
- Touring pipeline phases 1–3 (CRUD, voice capture + Whisper, Decision Brief).
- AI performance work (lazy AI scoring with `score-batch`, prompt caching, semaphore concurrency control).
- Search/scoring improvements (proximity radius, removal of misleading "listed recently" badge, AI re-sort after async backfill, removed property-type filter).
- Tour-related infra: S3 bucket + IAM for voice notes and photos.

## Dropped / Done Differently

- **Milestone 3 polish** (image carousel refinement, transitions, cross-browser) — folded into ongoing UI work; embla carousel is stable.
- **Notes per apartment** — shipped as part of the touring pipeline (`tour_notes`).
- **Viewing appointment scheduler** — shipped as `TourScheduler` + `tour_pipeline.scheduled_at`.
- **Photo upload for visited apartments** — shipped as `tour_photos`, S3-backed.
- **Email notifications for new matches** — shipped as Pro daily Resend alerts (`send_daily_alerts` Celery task).
- **Deploy to Vercel + Railway/Fly** — done differently as Vercel (frontend) + AWS ECS Fargate / RDS / Terraform (backend) with a dev/qa/prod pipeline.
- **Real apartment API integration (Zillow, Apartments.com)** — done via Apify; apartments.com is the only currently-scheduled source. Native Zillow integration deprioritized.