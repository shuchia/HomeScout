"""Admin endpoints for beta usage reporting.

Read-only aggregations over the Supabase tables that track invite codes,
profiles, tours, saved searches, and beta feedback. Auth via X-Admin-Key —
same pattern as data_collection.py and invite.py.

The bulk of the heavy lifting is here so the CLI wrapper
(``scripts/beta-report.sh``) just curls a URL and pretty-prints. Keeps
the report data accessible to anything else that wants JSON — a Slack
bot, dashboard, weekly cron, etc.
"""
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "homescout-dev-admin-key")


async def verify_admin_key(x_admin_key: str = Header(...)):
    """Same X-Admin-Key gate used by /api/admin/invite-codes and
    /api/admin/data-collection/*. Pulled per-environment from
    AWS Secrets Manager (snugd/{env}/secrets).
    """
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return x_admin_key


router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Reports"],
    dependencies=[Depends(verify_admin_key)],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    """Parse a Supabase ISO timestamp string. Returns None on bad input
    so a single malformed row doesn't blow up the whole report.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        # Supabase returns ISO with 'Z' suffix; fromisoformat needs +00:00
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@router.get("/beta-report")
async def beta_report(
    days: int = Query(default=14, ge=1, le=180, description="Lookback window for engagement aggregates."),
    top_n: int = Query(default=10, ge=1, le=50, description="How many top-active users to include."),
    feedback_limit: int = Query(default=5, ge=0, le=50, description="How many recent feedback entries to include."),
) -> Dict[str, Any]:
    """Beta usage snapshot — read-only.

    Aggregates from: invite_codes, invite_redemptions, profiles,
    tour_pipeline, tour_notes, tour_photos, saved_searches, beta_feedback.

    Returns a structured JSON intended for the scripts/beta-report.sh
    wrapper to render as markdown, but useful directly for any other
    consumer (Slack bot, weekly cron, dashboard).
    """
    if not supabase_admin:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    now = _utcnow()
    cutoff = now - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    # ── Invite codes + redemptions ────────────────────────────────────
    codes_resp = (
        supabase_admin.table("invite_codes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    codes = codes_resp.data or []

    redemptions_resp = (
        supabase_admin.table("invite_redemptions")
        .select("code,user_id,redeemed_at")
        .order("redeemed_at", desc=True)
        .execute()
    )
    redemptions = redemptions_resp.data or []

    last_redeemed_by_code: Dict[str, str] = {}
    redemptions_by_code: Dict[str, int] = Counter()
    for r in redemptions:
        code = r.get("code")
        if not code:
            continue
        redemptions_by_code[code] += 1
        if code not in last_redeemed_by_code:  # iterating desc, so first hit is the latest
            last_redeemed_by_code[code] = r.get("redeemed_at")

    codes_summary: List[Dict[str, Any]] = []
    for c in codes:
        code_str = c.get("code")
        max_uses = c.get("max_uses") or 0
        times_used = c.get("times_used") or 0
        # Cross-check times_used against actual redemptions count — divergence
        # would signal an atomicity bug; surface both so the operator can see.
        actual_redemptions = redemptions_by_code.get(code_str, 0)
        codes_summary.append({
            "code": code_str,
            "max_uses": max_uses,
            "times_used": times_used,
            "actual_redemptions": actual_redemptions,
            "remaining": max(0, max_uses - times_used),
            "expires_at": c.get("expires_at"),
            "created_at": c.get("created_at"),
            "last_redeemed_at": last_redeemed_by_code.get(code_str),
        })

    # ── Cohort: which users redeemed any invite code ──────────────────
    redeemer_ids = sorted({r["user_id"] for r in redemptions if r.get("user_id")})

    profiles_by_id: Dict[str, Dict[str, Any]] = {}
    if redeemer_ids:
        # Supabase REST has no per-row limit issue at this scale; pull in one shot
        prof_resp = (
            supabase_admin.table("profiles")
            .select("id,email,name,user_tier,pro_expires_at,created_at")
            .in_("id", redeemer_ids)
            .execute()
        )
        for p in (prof_resp.data or []):
            profiles_by_id[p["id"]] = p

    cohort_counts = Counter({"pro_active": 0, "pro_expired": 0, "free": 0, "unknown": 0})
    for uid in redeemer_ids:
        p = profiles_by_id.get(uid)
        if not p:
            cohort_counts["unknown"] += 1
            continue
        tier = (p.get("user_tier") or "free").lower()
        if tier == "pro":
            expires = _parse_iso(p.get("pro_expires_at"))
            if expires and expires > now:
                cohort_counts["pro_active"] += 1
            else:
                cohort_counts["pro_expired"] += 1
        else:
            cohort_counts["free"] += 1

    # ── Engagement signals (tours, notes, photos, saved searches) ─────
    # Filter to beta cohort only — non-redeemer users (e.g., test bot signing
    # in directly) skew aggregates and aren't the audience for this report.
    user_filter = redeemer_ids or [""]  # avoid empty .in_() error

    tours_resp = (
        supabase_admin.table("tour_pipeline")
        .select("id,user_id,apartment_id,stage,created_at,updated_at,decision,scheduled_date")
        .in_("user_id", user_filter)
        .execute()
    )
    all_tours = tours_resp.data or []

    stage_counts = Counter()
    decision_counts = Counter()
    tours_in_window = 0
    tours_by_user: Dict[str, int] = Counter()
    most_recent_by_user: Dict[str, str] = {}

    for t in all_tours:
        stage_counts[t.get("stage") or "unknown"] += 1
        if t.get("decision"):
            decision_counts[t["decision"]] += 1
        uid = t.get("user_id")
        if uid:
            tours_by_user[uid] += 1
            updated = t.get("updated_at") or t.get("created_at")
            if updated and (uid not in most_recent_by_user or updated > most_recent_by_user[uid]):
                most_recent_by_user[uid] = updated
        created = _parse_iso(t.get("created_at"))
        if created and created >= cutoff:
            tours_in_window += 1

    # Notes + photos count, joined to tour → user via tour_pipeline_id
    tour_id_to_user: Dict[str, str] = {t["id"]: t.get("user_id") for t in all_tours if t.get("id")}
    notes_by_user: Dict[str, int] = Counter()
    photos_by_user: Dict[str, int] = Counter()

    if tour_id_to_user:
        notes_resp = (
            supabase_admin.table("tour_notes")
            .select("tour_pipeline_id")
            .in_("tour_pipeline_id", list(tour_id_to_user.keys()))
            .execute()
        )
        for n in (notes_resp.data or []):
            uid = tour_id_to_user.get(n.get("tour_pipeline_id"))
            if uid:
                notes_by_user[uid] += 1

        photos_resp = (
            supabase_admin.table("tour_photos")
            .select("tour_pipeline_id")
            .in_("tour_pipeline_id", list(tour_id_to_user.keys()))
            .execute()
        )
        for p in (photos_resp.data or []):
            uid = tour_id_to_user.get(p.get("tour_pipeline_id"))
            if uid:
                photos_by_user[uid] += 1

    saved_resp = (
        supabase_admin.table("saved_searches")
        .select("user_id,is_active")
        .in_("user_id", user_filter)
        .execute()
    )
    saved_by_user: Dict[str, int] = Counter()
    for s in (saved_resp.data or []):
        uid = s.get("user_id")
        if uid:
            saved_by_user[uid] += 1

    # ── Per-user event funnel (analytics_events split by user × type) ──
    # Lets the report answer "Bharath searched 12 times but never added a
    # tour" — the kind of post-redemption friction signal you can't see
    # from the tour_pipeline aggregates alone (which only show tours that
    # WERE created, not what happened before that).
    events_per_user: Dict[str, Counter] = defaultdict(Counter)
    try:
        per_user_events_resp = (
            supabase_admin.table("analytics_events")
            .select("event_type,user_id,created_at")
            .gte("created_at", cutoff_iso)
            .in_("user_id", user_filter)
            .execute()
        )
        for ev in (per_user_events_resp.data or []):
            uid = ev.get("user_id")
            etype = ev.get("event_type") or "unknown"
            if uid:
                events_per_user[uid][etype] += 1
    except Exception as e:
        logger.warning(f"per-user analytics_events aggregation skipped: {e}")

    # ── Top N most-active users (by tours + notes + photos + saved) ───
    activity_score: Dict[str, int] = {}
    for uid in redeemer_ids:
        activity_score[uid] = (
            tours_by_user.get(uid, 0) * 3
            + notes_by_user.get(uid, 0)
            + photos_by_user.get(uid, 0)
            + saved_by_user.get(uid, 0) * 2
        )
    ranked = sorted(activity_score.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    # Event types we surface in the per-user funnel — keeps the report
    # focused on the actual funnel steps (vs every analytics_events key).
    # Any other event type still shows in the cohort-wide
    # analytics_events.by_type_in_window aggregate below.
    FUNNEL_EVENT_TYPES = (
        "search",
        "compare",
        "favorite-add",
        "tour-add",
        "message-generated",
        "redeem",
    )

    top_users: List[Dict[str, Any]] = []
    for uid, score in ranked:
        p = profiles_by_id.get(uid, {})
        ev_counts = events_per_user.get(uid, Counter())
        funnel = {etype: ev_counts.get(etype, 0) for etype in FUNNEL_EVENT_TYPES}
        top_users.append({
            "user_id": uid,
            "email": p.get("email"),
            "name": p.get("name"),
            "tier": p.get("user_tier"),
            "tours": tours_by_user.get(uid, 0),
            "notes": notes_by_user.get(uid, 0),
            "photos": photos_by_user.get(uid, 0),
            "saved_searches": saved_by_user.get(uid, 0),
            "activity_score": score,
            "last_active": most_recent_by_user.get(uid),
            "funnel_events": funnel,
        })

    # ── Beta feedback (recent first) ──────────────────────────────────
    feedback_summary: Dict[str, Any] = {"total": 0, "by_type": {}, "recent": []}
    if feedback_limit > 0:
        fb_resp = (
            supabase_admin.table("beta_feedback")
            .select("user_id,type,message,page_url,created_at")
            .order("created_at", desc=True)
            .limit(feedback_limit)
            .execute()
        )
        recent = fb_resp.data or []

        # Counts across the full table for the type breakdown
        all_fb_resp = (
            supabase_admin.table("beta_feedback")
            .select("type", count="exact")
            .execute()
        )
        feedback_summary["total"] = all_fb_resp.count or 0

        type_resp = (
            supabase_admin.table("beta_feedback")
            .select("type")
            .execute()
        )
        feedback_summary["by_type"] = dict(Counter(
            (r.get("type") or "unknown") for r in (type_resp.data or [])
        ))
        feedback_summary["recent"] = [
            {
                "type": r.get("type"),
                "message": (r.get("message") or "")[:240],
                "page_url": r.get("page_url"),
                "created_at": r.get("created_at"),
                "user_id": r.get("user_id"),
            }
            for r in recent
        ]

    # ── Analytics events (currently only `compare` fires; included for
    #    forward-compat once more event types are instrumented) ───────
    events_summary: Dict[str, Any] = {"by_type_in_window": {}, "total_in_window": 0}
    try:
        ev_resp = (
            supabase_admin.table("analytics_events")
            .select("event_type,user_id,created_at")
            .gte("created_at", cutoff_iso)
            .execute()
        )
        events = ev_resp.data or []
        events_summary["total_in_window"] = len(events)
        events_summary["by_type_in_window"] = dict(Counter(
            (e.get("event_type") or "unknown") for e in events
        ))
    except Exception as e:
        logger.warning(f"analytics_events aggregation skipped: {e}")

    return {
        "generated_at": now.isoformat(),
        "lookback_days": days,
        "invite_codes": codes_summary,
        "cohort": {
            "total_redeemers": len(redeemer_ids),
            **cohort_counts,
        },
        "tours": {
            "total": len(all_tours),
            "in_lookback_window": tours_in_window,
            "by_stage": dict(stage_counts),
            "by_decision": dict(decision_counts),
        },
        "saved_searches_total": sum(saved_by_user.values()),
        "tour_notes_total": sum(notes_by_user.values()),
        "tour_photos_total": sum(photos_by_user.values()),
        "top_users": top_users,
        "feedback": feedback_summary,
        "analytics_events": events_summary,
    }
