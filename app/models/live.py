"""
app/models/live.py - Schemas for Real-Time Edge WebSocket Video Ingestion & Instant Audio Cues
"""

from __future__ import annotations

import time
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LiveFramePacket(BaseModel):
    """
    Lightweight streaming frame packet ingested via WebSocket at 2-3 fps.
    """

    model_config = ConfigDict(extra="ignore")

    frame_b64: Optional[str] = Field(
        default=None,
        description="Base64-encoded JPEG/WebP video frame captured at edge",
    )
    heart_rate: int = Field(
        ...,
        gt=0,
        le=260,
        description="Live heart rate in BPM streamed from wearable (Health Connect)",
        examples=[164],
    )
    sport: str = Field(default="badminton", description="Sport category")
    stroke_type: str = Field(default="overhead_clear", description="Current stroke tracking mode")
    timestamp_ms: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="Client epoch timestamp in milliseconds",
    )


class LiveAudioCueResponse(BaseModel):
    """
    Immediate micro-audio coaching cue (<= 10 words) streamed back to client earbuds.
    """

    model_config = ConfigDict(extra="ignore")

    cue: str = Field(
        ...,
        description="Punchy, actionable audio cue (max 10 words) for real-time earbud playback",
        examples=["Keep elbow high before shuttle contact."],
    )
    timestamp_ms: int = Field(..., description="Timestamp of cue generation")
    audio_tts_url: Optional[str] = Field(
        default=None,
        description="Optional pre-rendered TTS audio stream pointer",
    )
    confidence_score: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description="Confidence score of the real-time kinematic detection",
    )
