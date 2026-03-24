import logging
from app.celery_app import celery_app
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def transcribe_voice_note(self, note_id: str, s3_key: str, user_id: str, tour_id: str):
    """Transcribe voice note, then auto-enhance for Pro users."""
    from app.services.transcription.whisper_service import WhisperService
    from app.services.tier_service import TierService
    import asyncio

    if not supabase_admin:
        logger.error("Supabase not configured, cannot update note")
        return

    try:
        text = WhisperService.transcribe_from_s3(s3_key)

        supabase_admin.table("tour_notes").update({
            "content": text,
            "transcription_status": "complete",
        }).eq("id", note_id).execute()

        logger.info(f"Transcribed voice note {note_id}: {len(text)} chars")

        # Check tier and chain enhancement for Pro users
        try:
            loop = asyncio.new_event_loop()
            tier = loop.run_until_complete(TierService.get_user_tier(user_id))
            loop.close()
        except Exception:
            tier = "free"

        if tier == "pro":
            enhance_voice_note.delay(note_id, text, tour_id)

    except Exception as exc:
        logger.error(f"Transcription failed for note {note_id}: {exc}")
        supabase_admin.table("tour_notes").update({
            "transcription_status": "failed",
        }).eq("id", note_id).execute()
        raise self.retry(exc=exc)


@celery_app.task(max_retries=1, default_retry_delay=10)
def enhance_voice_note(note_id: str, raw_text: str, tour_id: str):
    """Auto-enhance a transcribed voice note using Claude (Pro only)."""
    from app.services.claude_service import ClaudeService

    if not supabase_admin:
        return

    try:
        # Fetch apartment context
        tour_result = supabase_admin.table("tour_pipeline").select("apartment_id").eq("id", tour_id).execute()
        if not tour_result.data:
            return

        apartment_id = tour_result.data[0]["apartment_id"]
        apartment_context = {"apartment_id": apartment_id}

        claude = ClaudeService()
        result = claude.enhance_note(raw_text, apartment_context)

        enhanced_text = result.get("enhanced_text", raw_text)
        supabase_admin.table("tour_notes").update({
            "content": enhanced_text,
        }).eq("id", note_id).execute()

        logger.info(f"Enhanced voice note {note_id}")

    except Exception as e:
        logger.warning(f"Note enhancement failed (non-fatal): {e}")
