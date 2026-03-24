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


class WhisperService:
    @staticmethod
    def transcribe(audio_data: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio bytes using OpenAI Whisper API."""
        if not audio_data:
            raise ValueError("Empty audio data")
        client = _get_openai_client()
        audio_file = BytesIO(audio_data)
        audio_file.name = filename
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )
        return response.strip()

    @staticmethod
    def transcribe_from_s3(s3_key: str) -> str:
        """Download audio from S3 and transcribe."""
        from app.services.storage.photo_service import _get_s3_client, S3_BUCKET
        s3 = _get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        audio_data = response["Body"].read()
        filename = s3_key.split("/")[-1] if "/" in s3_key else s3_key
        return WhisperService.transcribe(audio_data, filename)
