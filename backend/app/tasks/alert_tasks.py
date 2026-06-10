"""Daily email alert task for Pro users with saved searches."""
import os
import logging
from datetime import datetime, timezone

import resend
from celery import shared_task

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL", "alerts@snugd.app")


@shared_task(name="app.tasks.alert_tasks.send_daily_alerts")
def send_daily_alerts():
    """Find Pro users with active saved searches, check for new listings, send emails."""
    from app.services.tier_service import supabase_admin
    if not supabase_admin:
        logger.error("Supabase admin client not configured")
        return {"sent": 0}

    # Fetch active saved searches without a Supabase relationship join —
    # saved_searches.user_id FKs to auth.users, not public.profiles, so
    # PostgREST cannot auto-discover the relationship for `!inner`. Doing
    # this in two steps avoids needing a schema migration on prod Supabase.
    result = (
        supabase_admin.table("saved_searches")
        .select("*")
        .eq("is_active", True)
        .eq("notify_new_matches", True)
        .execute()
    )

    if not result.data:
        logger.info("No active saved searches to process")
        return {"sent": 0}

    # Batch-fetch profile rows for the saved-search owners, filtered to Pro.
    user_ids = sorted({s["user_id"] for s in result.data if s.get("user_id")})
    if not user_ids:
        return {"sent": 0}

    profiles_resp = (
        supabase_admin.table("profiles")
        .select("id, user_tier, email, name")
        .in_("id", user_ids)
        .eq("user_tier", "pro")
        .execute()
    )
    profiles_by_id = {p["id"]: p for p in (profiles_resp.data or [])}

    # Keep only searches whose owner is a Pro user with an email.
    pro_searches = [
        {**s, "_profile": profiles_by_id[s["user_id"]]}
        for s in result.data
        if s.get("user_id") in profiles_by_id
    ]
    if not pro_searches:
        logger.info("No Pro users with active saved searches to alert")
        return {"sent": 0}

    from app.services.apartment_service import ApartmentService
    service = ApartmentService()
    sent_count = 0

    for search in pro_searches:
        profile = search.get("_profile", {})
        email = profile.get("email")
        if not email:
            continue

        last_alerted = search.get("last_alerted_at")

        # Find apartments matching this search
        apartments = service.search_apartments(
            city=search["city"],
            budget=search.get("budget"),
            bedrooms=search.get("bedrooms"),
            bathrooms=search.get("bathrooms"),
            property_type=search.get("property_type"),
        )

        # Filter to only new listings since last alert
        if last_alerted:
            apartments = [
                apt for apt in apartments
                if apt.get("first_seen_at") and apt["first_seen_at"] > last_alerted
            ]

        if not apartments:
            continue

        # Build and send email
        try:
            apartment_lines = []
            for apt in apartments[:10]:
                apartment_lines.append(
                    f"- {apt.get('address', 'Unknown')} - ${apt.get('rent', '?')}/mo, "
                    f"{apt.get('bedrooms', '?')}bd/{apt.get('bathrooms', '?')}ba"
                )

            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            body = (
                f"Hi {profile.get('name', 'there')},\n\n"
                f"We found {len(apartments)} new apartment(s) matching your "
                f"\"{search['name']}\" search in {search['city']}:\n\n"
                + "\n".join(apartment_lines)
                + f"\n\nView them on Snugd: {frontend_url}"
                + f"\n\nManage your alerts: {frontend_url}/settings"
            )

            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": f"{len(apartments)} new apartment(s) in {search['city']} match your search",
                "text": body,
            })
            sent_count += 1

            # Update last_alerted_at
            supabase_admin.table("saved_searches").update({
                "last_alerted_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", search["id"]).execute()

        except Exception as e:
            logger.error(f"Failed to send alert for search {search['id']}: {e}")

    logger.info(f"Sent {sent_count} alert emails")
    return {"sent": sent_count}
