import os
import logging
from io import BytesIO
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_openai_client = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# Whisper invents text for silence ("Enjoy!", "Thank you.") rather than
# returning nothing — a pocketed or accidental recording became a note nobody
# said. verbose_json gives each segment Whisper's own estimate that it held no
# speech. A segment counts as silent by Whisper's reference rule (no_speech_prob
# > 0.6 with avg_logprob < -1) or when it is very sure on its own (> 0.8).
NO_SPEECH_PROB = 0.6
NO_SPEECH_PROB_ALONE = 0.8
LOW_AVG_LOGPROB = -1.0


def _field(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _is_silent(segment) -> bool:
    no_speech = _field(segment, "no_speech_prob", 0.0) or 0.0
    logprob = _field(segment, "avg_logprob", 0.0) or 0.0
    return no_speech > NO_SPEECH_PROB_ALONE or (no_speech > NO_SPEECH_PROB and logprob < LOW_AVG_LOGPROB)


class WhisperService:
    @staticmethod
    def transcribe(audio_data: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio bytes using OpenAI Whisper API.

        Returns "" when the recording held no speech.
        """
        if not audio_data:
            raise ValueError("Empty audio data")
        client = _get_openai_client()
        audio_file = BytesIO(audio_data)
        audio_file.name = filename
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
        )
        if isinstance(response, str):
            return response.strip()
        text = (_field(response, "text", "") or "").strip()
        segments = _field(response, "segments", None) or []
        if segments and all(_is_silent(seg) for seg in segments):
            logger.info("Whisper heard no speech; discarding %r", text[:80])
            return ""
        return text

    @staticmethod
    def transcribe_from_s3(s3_key: str) -> str:
        """Download audio from S3 and transcribe."""
        from app.services.storage.photo_service import _get_s3_client, S3_BUCKET
        s3 = _get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        audio_data = response["Body"].read()
        filename = s3_key.split("/")[-1] if "/" in s3_key else s3_key
        return WhisperService.transcribe(audio_data, filename)
