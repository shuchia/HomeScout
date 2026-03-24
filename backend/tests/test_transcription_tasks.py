"""Tests for transcription Celery tasks."""
from unittest.mock import patch, MagicMock, AsyncMock


class TestTranscribeVoiceNote:
    @patch("app.tasks.transcription_tasks.supabase_admin")
    @patch("app.services.transcription.whisper_service._get_openai_client")
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_transcribe_task_success(self, mock_get_s3, mock_get_openai, mock_sb):
        """Task transcribes audio and saves content + status=complete."""
        # Mock S3
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"audio-bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_get_s3.return_value = mock_s3

        # Mock OpenAI
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Great kitchen layout."
        mock_get_openai.return_value = mock_client

        # Mock Supabase update chain
        mock_update = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        # Mock tier check to return "free" (no enhancement)
        with patch("app.services.tier_service.TierService.get_user_tier", new_callable=AsyncMock, return_value="free"):
            from app.tasks.transcription_tasks import transcribe_voice_note
            transcribe_voice_note(
                "note-1", "tours/u/t/voice/abc.webm", "user-1", "tour-1"
            )

        # Verify update was called with transcribed text
        mock_sb.table.assert_any_call("tour_notes")
        update_calls = mock_sb.table.return_value.update.call_args_list
        # Should have been called with content + complete status
        assert any(
            call[0][0].get("transcription_status") == "complete"
            for call in update_calls
        )

    @patch("app.tasks.transcription_tasks.supabase_admin")
    @patch("app.services.transcription.whisper_service._get_openai_client")
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_transcribe_task_failure(self, mock_get_s3, mock_get_openai, mock_sb):
        """Task sets status=failed when transcription raises."""
        # Mock S3 to raise
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = Exception("S3 error")
        mock_get_s3.return_value = mock_s3

        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        from app.tasks.transcription_tasks import transcribe_voice_note

        # Call directly (not via Celery) — the retry will re-raise
        try:
            transcribe_voice_note(
                "note-1", "tours/u/t/voice/abc.webm", "user-1", "tour-1"
            )
        except Exception:
            pass

        # Verify status was set to "failed"
        update_calls = mock_sb.table.return_value.update.call_args_list
        assert any(
            call[0][0].get("transcription_status") == "failed"
            for call in update_calls
        )

    @patch("app.tasks.transcription_tasks.enhance_voice_note")
    @patch("app.tasks.transcription_tasks.supabase_admin")
    @patch("app.services.transcription.whisper_service._get_openai_client")
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_pro_user_chains_enhancement(
        self, mock_get_s3, mock_get_openai, mock_sb, mock_enhance
    ):
        """Pro user triggers enhance_voice_note.delay after transcription."""
        # Mock S3
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"audio-bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_get_s3.return_value = mock_s3

        # Mock OpenAI
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Nice place."
        mock_get_openai.return_value = mock_client

        # Mock Supabase
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        # Mock tier check to return "pro"
        with patch("app.services.tier_service.TierService.get_user_tier", new_callable=AsyncMock, return_value="pro"):
            from app.tasks.transcription_tasks import transcribe_voice_note
            transcribe_voice_note(
                "note-1", "tours/u/t/voice/abc.webm", "user-1", "tour-1"
            )

        # Verify enhance was called
        mock_enhance.delay.assert_called_once_with("note-1", "Nice place.", "tour-1")
