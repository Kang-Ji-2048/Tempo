"""
app/models/session.py - Pydantic v2 schemas for Session Ingestion and Data Pipeline
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(str, Enum):
    """Lifecycle status flags for a practice session."""

    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BiometricDataPoint(BaseModel):
    """
    Biometric time-series data point captured from wearable sensors (e.g., Android Health Connect).
    """

    model_config = ConfigDict(extra="ignore")

    timestamp_ms: int = Field(
        ...,
        description="Epoch timestamp in milliseconds",
        examples=[1729724400000],
    )
    heart_rate: int = Field(
        ...,
        gt=0,
        le=260,
        description="Instantaneous heart rate in beats per minute (BPM)",
        examples=[168],
    )
    cadence: Optional[int] = Field(
        default=None,
        ge=0,
        description="Cadence or stroke frequency (steps or swings per minute)",
        examples=[45],
    )
    active_energy_burned: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Active calories burned in kcal",
        examples=[12.5],
    )


class SessionIngestRequest(BaseModel):
    """
    Session metadata and raw telemetry payload submitted alongside practice video.
    """

    model_config = ConfigDict(extra="ignore")

    session_id: Optional[str] = Field(
        default=None,
        description="Optional client-generated UUID for the session",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="Unique user/player identifier",
        examples=["usr_sumanth_001"],
    )
    sport: str = Field(
        ...,
        min_length=1,
        description="Sport category (e.g., tennis, badminton)",
        examples=["badminton"],
    )
    stroke_type: str = Field(
        ...,
        min_length=1,
        description="Specific stroke technique (e.g., one_handed_backhand, overhead_clear, jump_smash)",
        examples=["overhead_clear"],
    )
    target_archetype: Optional[str] = Field(
        default=None,
        description="Target pro or textbook archetype for kinematic comparison (e.g., 'Axelsen', 'Federer', 'Fundamentals')",
        examples=["Axelsen"],
    )
    user_intent: Optional[str] = Field(
        default=None,
        description="Athlete's free-text focus or intent for the session",
        examples=["Working on steep angle and early high contact"],
    )
    telemetry: List[BiometricDataPoint] = Field(
        default_factory=list,
        description="Chronological time-series biometric readings from Health Connect",
    )


class SessionRecord(BaseModel):
    """
    MongoDB document representation persisted in `sports_coach_db.sessions`.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
    )

    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique UUID for this practice session",
    )
    user_id: str = Field(..., description="User ID of the player")
    sport: str = Field(..., description="Sport category")
    stroke_type: str = Field(..., description="Stroke type analyzed")
    target_archetype: Optional[str] = Field(default=None, description="Pro/baseline archetype")
    user_intent: Optional[str] = Field(default=None, description="Athlete's free-text intent or focus")
    status: SessionStatus = Field(default=SessionStatus.PENDING, description="Session ingestion/processing status")
    video_storage_path: Optional[str] = Field(default=None, description="Local or object storage pointer to stored video")
    video_url: Optional[str] = Field(default=None, description="Signed remote URL if video was ingested via URL")
    telemetry_count: int = Field(default=0, description="Total number of biometric points recorded")
    telemetry_summary: Optional[Dict[str, Any]] = Field(default=None, description="Summary statistics of biometrics")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of session ingestion",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last status update",
    )
    error_message: Optional[str] = Field(default=None, description="Error details if status is FAILED")

    # Future-proof multimodal & kinematic fields
    gemini_feedback: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Multimodal diagnostic output, voice coaching cues, and biomechanical breakdown from Gemini Argon",
    )
    kinematic_vector: Optional[List[float]] = Field(
        default=None,
        description="Normalized joint angle/pose vector extracted from the video for Atlas Vector Search",
    )
    active_widgets: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Server-Driven UI (SDUI) widget definitions emitted for Android Jetpack Compose",
    )

    def to_mongo(self) -> Dict[str, Any]:
        """Converts model to MongoDB-compatible dictionary."""
        data = self.model_dump(by_alias=True)
        data["_id"] = data["session_id"]
        return data


class SessionIngestResponse(BaseModel):
    """
    Response returned to client upon successful 202 Accepted session ingestion.
    """

    session_id: str = Field(..., description="Generated session identifier")
    status: SessionStatus = Field(default=SessionStatus.PENDING, description="Initial processing status")
    estimated_analysis_time_sec: int = Field(
        default=8,
        description="Estimated processing time before Gemini Argon analysis completes",
    )
    message: str = Field(
        default="Session ingestion accepted. Biomechanical analysis initiated.",
        description="Informational message",
    )
