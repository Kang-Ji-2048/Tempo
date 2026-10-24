"""
app/models/schedule.py - Schemas for Athlete Cadence, Training Schedules & Saint (Thea) Dispatch
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CadenceEventType(str, Enum):
    """Lifecycle triggers for athlete check-ins and proactive cadence prompts."""

    PRE_SESSION_PRIMING = "PRE_SESSION_PRIMING"
    POST_SESSION_DEBRIEF = "POST_SESSION_DEBRIEF"
    MISSED_SESSION_CHECKIN = "MISSED_SESSION_CHECKIN"
    RECOVERY_ADVICE = "RECOVERY_ADVICE"


class UserSchedule(BaseModel):
    """
    Athlete's target practice schedule and reminder preferences.
    """

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., description="Unique athlete ID", examples=["usr_sumanth_001"])
    sport: str = Field(default="badminton", description="Target sport (badminton, tennis)")
    stroke_type: str = Field(default="overhead_clear", description="Primary technique focus")
    days_of_week: List[str] = Field(
        default_factory=lambda: ["Monday", "Wednesday", "Friday"],
        description="Active practice days of week",
        examples=[["Monday", "Wednesday", "Friday"]],
    )
    target_time_utc: str = Field(
        default="18:00",
        description="Target practice time in HH:MM (UTC)",
        examples=["18:00"],
    )
    priming_lead_minutes: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Minutes before scheduled practice to dispatch priming mental cue",
    )
    preferred_channel: str = Field(
        default="whatsapp",
        description="Delivery channel: whatsapp, push, sms",
    )
    is_active: bool = Field(default=True, description="Whether schedule monitoring is active")
    notes: Optional[str] = Field(default=None, description="Athlete personal goals or venue preferences")


class SaintNotificationPayload(BaseModel):
    """
    Structured notification payload dispatched to Saint (Thea) WhatsApp agent or push notification queue.
    """

    model_config = ConfigDict(extra="ignore")

    event_type: CadenceEventType = Field(..., description="Type of cadence notification trigger")
    user_id: str = Field(..., description="Athlete user ID")
    recipient_name: str = Field(..., description="Athlete's first name", examples=["Sumanth"])
    plain_text_message: str = Field(..., description="Humanized conversational debrief or cue")
    call_to_action: Optional[str] = Field(default=None, description="Suggested action (e.g., 'Reply YES to reschedule')")
    session_id: Optional[str] = Field(default=None, description="Related practice session ID if applicable")
    dispatched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of dispatch",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary context metadata (scores, venues, drills)",
    )
