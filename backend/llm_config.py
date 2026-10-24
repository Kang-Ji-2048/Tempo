"""Single source of truth for Gemini 4 Argon LLM configuration and diagnostics."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import dotenv
from google import genai

logger = logging.getLogger("tempo.llm")

# Load backend/.env explicitly
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    dotenv.load_dotenv(dotenv_path=_env_file, override=False)
else:
    dotenv.load_dotenv(override=False)

GEMINI_API_KEY: str = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-4-argon").strip()
GEMINI_THINKING_LEVEL: str = os.environ.get("GEMINI_THINKING_LEVEL", "medium").strip()
GEMINI_FALLBACK_MODEL: str = os.environ.get("GEMINI_FALLBACK_MODEL", "").strip()
GEMINI_SEND_VIDEO: bool = os.environ.get("GEMINI_SEND_VIDEO", "1").strip().lower() in {"1", "true", "yes"}

def mask_key(key: str) -> str:
    if not key:
        return "None"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"

if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY missing: AI features will report fallback")
else:
    logger.info("Gemini configured with model=%s, key=%s", GEMINI_MODEL, mask_key(GEMINI_API_KEY))

# Global AI status tracking
AI_STATUS: Dict[str, Any] = {
    "configured": bool(GEMINI_API_KEY),
    "model": GEMINI_MODEL,
    "key_masked": mask_key(GEMINI_API_KEY),
    "last_call_ok": None,
    "last_error": None,
    "last_latency_ms": None,
    "last_checked_at": None,
}

def update_ai_status(success: bool, error: Optional[str] = None, latency_ms: Optional[int] = None) -> None:
    AI_STATUS["configured"] = bool(GEMINI_API_KEY)
    AI_STATUS["model"] = GEMINI_MODEL
    AI_STATUS["key_masked"] = mask_key(GEMINI_API_KEY)
    AI_STATUS["last_call_ok"] = success
    AI_STATUS["last_error"] = error
    AI_STATUS["last_latency_ms"] = latency_ms
    AI_STATUS["last_checked_at"] = datetime.now(timezone.utc).isoformat()

def get_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=GEMINI_API_KEY)
