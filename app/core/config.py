"""
app/core/config.py - Application Configuration using Pydantic Settings
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings and environment configurations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Tempo - Ingestion & Biomechanics Pipeline"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # MongoDB Atlas settings
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "courtvision_db"
    SESSIONS_COLLECTION: str = "sessions"
    TELEMETRY_COLLECTION: str = "telemetry_timeseries"

    # Storage settings
    UPLOAD_DIR: str = "/tmp/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 250 * 1024 * 1024  # 250 MB
    CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB chunked writes
    ALLOWED_VIDEO_MIME_TYPES: List[str] = [
        "video/mp4",
        "video/quicktime",
        "video/x-matroska",
        "video/webm",
    ]

    # Gemini 4 Argon settings
    GEMINI_MODEL: str = "gemini-4-argon"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MOCK_MODE: bool = False

    # Processing parameters
    ESTIMATED_ANALYSIS_TIME_SEC: int = 8


@lru_cache()
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()
