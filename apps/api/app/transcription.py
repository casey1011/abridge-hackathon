"""Speech-to-text via Groq's hosted Whisper.

Docs: https://console.groq.com/docs/speech-to-text
"""
from functools import lru_cache

from groq import Groq

from .config import settings


@lru_cache
def _client() -> Groq:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set (see apps/api/.env.example)")
    return Groq(api_key=settings.groq_api_key)


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe raw audio bytes to text.

    `filename`'s extension tells Groq the container format
    (wav, mp3, m4a, flac, ogg, webm, ...).
    """
    resp = _client().audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=settings.groq_transcribe_model,
        response_format="text",
    )
    # With response_format="text" the SDK returns the transcript string.
    return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
