"""Coach Thea's voice: `GET /api/v1/tts?text=...` streams ElevenLabs MP3 to the app.

The ElevenLabs key stays server-side (ELEVENLABS_API_KEY in backend/.env, loaded by
llm_config). Without a key the endpoint answers 503 and the app falls back to on-device
TextToSpeech. Finished clips are kept in a small in-memory LRU so repeated live cues
cost no credits and play instantly.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Iterator

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

if __package__:
    from .auth import principal
else:
    from auth import principal

logger = logging.getLogger("tempo.voice_tts")

router = APIRouter(prefix="/api/v1", tags=["coach-thea-voice"])

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs premade "Rachel"; override with ELEVENLABS_VOICE_ID
DEFAULT_MODEL_ID = "eleven_flash_v2_5"  # lowest-latency model
OUTPUT_FORMAT = "mp3_44100_128"
MAX_TEXT_CHARS = 1200  # a 45s debrief script is ~700 characters
CACHE_MAX_CLIPS = 200
CHUNK_BYTES = 4096

_cache: "OrderedDict[str, bytes]" = OrderedDict()
_cache_lock = threading.Lock()


def _settings() -> Dict[str, str]:
    return {
        "api_key": os.environ.get("ELEVENLABS_API_KEY", "").strip(),
        "voice_id": os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or DEFAULT_VOICE_ID,
        "model_id": os.environ.get("ELEVENLABS_MODEL_ID", "").strip() or DEFAULT_MODEL_ID,
    }


def _cache_key(voice_id: str, model_id: str, text: str) -> str:
    return hashlib.sha256(f"{voice_id}|{model_id}|{text}".encode()).hexdigest()


def _cache_get(key: str) -> bytes | None:
    with _cache_lock:
        clip = _cache.get(key)
        if clip is not None:
            _cache.move_to_end(key)
        return clip


def _cache_put(key: str, clip: bytes) -> None:
    with _cache_lock:
        _cache[key] = clip
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_CLIPS:
            _cache.popitem(last=False)


def _identity(request: Request) -> Dict[str, Any]:
    return principal(request)


@router.get("/tts")
def speak(text: str = Query(min_length=1, max_length=MAX_TEXT_CHARS),
          _: Dict[str, Any] = Depends(_identity)) -> Response:
    text = " ".join(text.split())
    if not text:
        raise HTTPException(422, "text is empty")
    cfg = _settings()
    if not cfg["api_key"]:
        raise HTTPException(503, "ElevenLabs is not configured; use on-device speech")

    key = _cache_key(cfg["voice_id"], cfg["model_id"], text)
    clip = _cache_get(key)
    if clip is not None:
        return Response(clip, media_type="audio/mpeg", headers={"X-Tempo-TTS-Cache": "hit"})

    try:
        upstream = requests.post(
            ELEVENLABS_URL.format(voice_id=cfg["voice_id"]),
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": cfg["api_key"], "accept": "audio/mpeg"},
            json={"text": text, "model_id": cfg["model_id"]},
            stream=True,
            timeout=(3, 15),
        )
    except requests.RequestException as e:
        logger.warning("ElevenLabs request failed: %s", e)
        raise HTTPException(502, "Voice service unreachable")
    if upstream.status_code != 200:
        logger.warning("ElevenLabs returned %s: %s", upstream.status_code, upstream.text[:300])
        upstream.close()
        raise HTTPException(502, "Voice service error")

    def relay() -> Iterator[bytes]:
        parts = []
        try:
            for chunk in upstream.iter_content(CHUNK_BYTES):
                if chunk:
                    parts.append(chunk)
                    yield chunk
        except requests.RequestException as e:
            logger.warning("ElevenLabs stream broke: %s", e)
            return
        finally:
            upstream.close()
        _cache_put(key, b"".join(parts))  # only complete clips are cached

    return StreamingResponse(relay(), media_type="audio/mpeg", headers={"X-Tempo-TTS-Cache": "miss"})
