"""Lightweight event logging to Supabase."""
import logging
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)


class AnalyticsService:

    @staticmethod
    async def log_event(
        event_type: str,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Fire-and-forget event logging. Never raises."""
        try:
            if not supabase_admin:
                return
            supabase_admin.table("analytics_events").insert({
                "event_type": event_type,
                "user_id": user_id,
                "metadata": metadata or {},
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to log analytics event: {e}")
