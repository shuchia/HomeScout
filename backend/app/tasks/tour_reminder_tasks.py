import logging
from datetime import datetime, timezone, timedelta, time as dt_time
from app.celery_app import celery_app
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)


@celery_app.task
def check_tour_reminders():
    """Create reminder notifications for tours that ended ~30 min ago."""
    if not supabase_admin:
        return

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    # Find scheduled tours for today that haven't been toured yet
    result = (
        supabase_admin.table("tour_pipeline")
        .select("id, user_id, apartment_id, scheduled_date, scheduled_time")
        .eq("scheduled_date", today)
        .eq("stage", "scheduled")
        .execute()
    )

    for tour in (result.data or []):
        scheduled_time_str = tour.get("scheduled_time")
        if not scheduled_time_str:
            continue

        try:
            # Parse time (HH:MM:SS or HH:MM format)
            parts = scheduled_time_str.split(":")
            tour_time = dt_time(int(parts[0]), int(parts[1]))
            tour_dt = datetime.combine(now.date(), tour_time, tzinfo=timezone.utc)

            # Check if tour was 25-35 minutes ago (reminder window)
            minutes_ago = (now - tour_dt).total_seconds() / 60
            if 25 <= minutes_ago <= 35:
                # Check if we already sent a reminder for this tour
                existing = (
                    supabase_admin.table("notifications")
                    .select("id")
                    .eq("type", "tour_reminder")
                    .eq("apartment_id", tour["apartment_id"])
                    .eq("user_id", tour["user_id"])
                    .execute()
                )
                if existing.data:
                    continue

                supabase_admin.table("notifications").insert({
                    "user_id": tour["user_id"],
                    "type": "tour_reminder",
                    "title": "How was your tour?",
                    "message": "Just toured? Tap to rate and capture your impressions.",
                    "apartment_id": tour["apartment_id"],
                }).execute()

                logger.info(f"Created tour reminder for user {tour['user_id']}, apt {tour['apartment_id']}")

        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid scheduled_time for tour {tour['id']}: {e}")
