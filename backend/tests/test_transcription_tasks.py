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


_MISSING = object()


class TestEnhanceVoiceNote:
    """The auto-enhance path had no coverage at all, which is why it ran for
    months handing {"apartment_id": ...} to a function that reads address,
    rent, bedrooms and bathrooms — not one of them that key. The third test
    above mocks enhance_voice_note out entirely, so nothing exercised it."""

    LISTING = {
        "id": "apt-001",
        "address": "9 Hancock St, Boston, MA 02129",
        "rent": 2650,
        "bedrooms": 1,
        "bathrooms": 1,
        "amenities": ["Laundry"],
        "description": "Bright one-bed.",
    }

    @staticmethod
    def _fake_supabase(listing):
        """Fake supabase_admin.

        `listing` is _MISSING for "no such saved listing", otherwise it is the
        value of the row's `listing` column. Tables are cached per name so a
        write made during the call can be inspected afterwards.
        """
        mock_sb = MagicMock()
        tables = {}

        def table_router(name):
            if name not in tables:
                t = MagicMock()
                if name == "saved_listings":
                    rows = [] if listing is _MISSING else [{"listing": listing}]
                    t.select.return_value.eq.return_value.execute.return_value = (
                        MagicMock(data=rows)
                    )
                tables[name] = t
            return tables[name]

        mock_sb.table.side_effect = table_router
        mock_sb.tables = tables
        return mock_sb

    def _run(self, listing, claude_result=None):
        mock_sb = self._fake_supabase(listing)
        result = claude_result or {
            "enhanced_text": "Bright kitchen.",
            "suggested_tags": [],
        }
        with patch("app.tasks.transcription_tasks.supabase_admin", mock_sb), \
             patch("app.services.claude_service.ClaudeService.__init__", return_value=None), \
             patch(
                 "app.services.claude_service.ClaudeService.enhance_note",
                 return_value=result,
             ) as mock_enhance:
            from app.tasks.transcription_tasks import enhance_voice_note
            enhance_voice_note("note-1", "bright kitchen uh", "tour-1")
        return mock_sb, mock_enhance

    def test_passes_the_saved_listing_as_context(self):
        """The listing the user saved reaches enhance_note, not a bare id."""
        _, mock_enhance = self._run(self.LISTING)

        mock_enhance.assert_called_once()
        ctx = mock_enhance.call_args[0][1]
        assert ctx == self.LISTING
        # The four keys enhance_note narrows to must actually be present.
        assert ctx["address"] == "9 Hancock St, Boston, MA 02129"
        assert ctx["rent"] == 2650
        assert ctx["bedrooms"] == 1
        assert ctx["bathrooms"] == 1

    def test_url_added_listing_still_gets_context(self):
        """apartment_id is NULL for a listing added by URL; `listing` is not,
        so the old corpus join found nothing for exactly these rows."""
        _, mock_enhance = self._run({**self.LISTING, "id": None})

        assert mock_enhance.call_args[0][1]["address"].startswith("9 Hancock St")

    def test_price_on_request_passes_none_not_a_number(self):
        """A saved floorplan with no published price must stay unpriced.

        project_matched_floorplan sets rent=None for a price-on-request
        bucket. Reading the corpus row instead substitutes the building's
        collapsed rent — a figure the property never quoted for this unit.
        """
        _, mock_enhance = self._run(
            {**self.LISTING, "rent": None, "price_on_request": True}
        )

        assert mock_enhance.call_args[0][1]["rent"] is None

    def test_writes_the_cleanup_beside_the_transcript(self):
        mock_sb, _ = self._run(self.LISTING)

        notes = mock_sb.tables["tour_notes"]
        notes.update.assert_called_once_with({"enhanced_content": "Bright kitchen."})
        notes.update.return_value.eq.assert_called_once_with("id", "note-1")

    def test_never_overwrites_content(self):
        """`content` is what the user said. Enhancement used to write over it,
        destroying the only copy of their words — the audio outlives the text
        it produced (365-day expiry off-prod, no rule at all in prod). The
        decision brief reads `content`, so it was also reasoning over the
        paraphrase with no artifact left to check against."""
        mock_sb, _ = self._run(self.LISTING)

        payload = mock_sb.tables["tour_notes"].update.call_args[0][0]
        assert "content" not in payload
        assert payload == {"enhanced_content": "Bright kitchen."}

    def test_missing_saved_listing_is_a_no_op(self):
        """No such row — return without calling Claude."""
        _, mock_enhance = self._run(_MISSING)

        mock_enhance.assert_not_called()

    def test_null_listing_degrades_to_an_empty_dict(self):
        """`listing` is NOT NULL in the schema, but the read must not hand
        None to a function that calls .get() on it."""
        _, mock_enhance = self._run(None)

        assert mock_enhance.call_args[0][1] == {}

    def test_claude_failure_leaves_the_transcript_alone(self):
        """Enhancement is non-fatal: a raising Claude must not blank the note."""
        mock_sb = self._fake_supabase(self.LISTING)
        with patch("app.tasks.transcription_tasks.supabase_admin", mock_sb), \
             patch("app.services.claude_service.ClaudeService.__init__", return_value=None), \
             patch(
                 "app.services.claude_service.ClaudeService.enhance_note",
                 side_effect=Exception("Claude down"),
             ):
            from app.tasks.transcription_tasks import enhance_voice_note
            enhance_voice_note("note-1", "bright kitchen uh", "tour-1")

        assert "tour_notes" not in mock_sb.tables
