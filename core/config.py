"""Desktop-compatible settings loader for service layer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings as django_settings


@dataclass(frozen=True)
class AppSettings:
    groq_api_key: str
    whisper_model: str
    chat_model: str
    chroma_host: str
    chroma_port: int
    chroma_collection: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    audio_prefix: str
    document_prefix: str
    temp_dir: Path


def load_settings() -> AppSettings:
    return AppSettings(
        groq_api_key=django_settings.GROQ_API_KEY,
        whisper_model=django_settings.GROQ_WHISPER_MODEL,
        chat_model=django_settings.GROQ_CHAT_MODEL,
        chroma_host=django_settings.CHROMA_HOST,
        chroma_port=django_settings.CHROMA_PORT,
        chroma_collection=django_settings.CHROMA_COLLECTION,
        minio_endpoint=django_settings.MINIO_ENDPOINT,
        minio_access_key=django_settings.MINIO_ACCESS_KEY,
        minio_secret_key=django_settings.MINIO_SECRET_KEY,
        minio_bucket=django_settings.MINIO_BUCKET,
        minio_secure=django_settings.MINIO_SECURE,
        audio_prefix=django_settings.MINIO_AUDIO_PREFIX,
        document_prefix=django_settings.MINIO_DOCUMENT_PREFIX,
        temp_dir=django_settings.OMNISCRIBE_TEMP_DIR,
    )
