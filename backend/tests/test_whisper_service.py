"""Tests for Whisper transcription service."""
from unittest.mock import patch, MagicMock
import pytest


class TestWhisperTranscribe:
    @patch("app.services.transcription.whisper_service._get_openai_client")
    def test_transcribe_success(self, mock_get_client):
        """transcribe() calls Whisper API and returns text."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "This is the transcription."
        mock_get_client.return_value = mock_client

        from app.services.transcription.whisper_service import WhisperService

        result = WhisperService.transcribe(b"fake-audio-data", "test.webm")

        assert result == "This is the transcription."
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["response_format"] == "text"

    def test_transcribe_empty_audio_raises(self):
        """transcribe() raises ValueError for empty audio data."""
        from app.services.transcription.whisper_service import WhisperService

        with pytest.raises(ValueError, match="Empty audio data"):
            WhisperService.transcribe(b"")

    @patch("app.services.transcription.whisper_service._get_openai_client")
    @patch("app.services.storage.photo_service._get_s3_client")
    def test_transcribe_from_s3(self, mock_get_s3, mock_get_openai):
        """transcribe_from_s3() downloads from S3 then transcribes."""
        # Mock S3
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"audio-bytes-from-s3"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_get_s3.return_value = mock_s3

        # Mock OpenAI
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Transcribed from S3."
        mock_get_openai.return_value = mock_client

        from app.services.transcription.whisper_service import WhisperService

        result = WhisperService.transcribe_from_s3("tours/user-1/tour-1/voice/abc.webm")

        assert result == "Transcribed from S3."
        mock_s3.get_object.assert_called_once()

    @patch("app.services.transcription.whisper_service._get_openai_client")
    def test_transcribe_strips_whitespace(self, mock_get_client):
        """transcribe() strips leading/trailing whitespace from response."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "  Hello world  \n"
        mock_get_client.return_value = mock_client

        from app.services.transcription.whisper_service import WhisperService

        result = WhisperService.transcribe(b"audio-data")
        assert result == "Hello world"
