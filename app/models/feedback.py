"""
app/models/feedback.py - Pydantic v2 schemas for Gemini 4 Argon Biomechanical Feedback
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class KineticPhase(BaseModel):
    """
    Kinematic evaluation of a distinct phase within the athletic stroke
    (e.g., Preparation, Loading / Trophy Pose, Impact, Follow-Through).
    """

    model_config = ConfigDict(extra="ignore")

    phase_name: str = Field(
        ...,
        description="Phase name (Preparation, Loading, Impact, Follow-Through)",
        examples=["Impact"],
    )
    timestamp_ms: int = Field(
        ...,
        description="Video timestamp offset in milliseconds where this kinetic phase occurs",
        examples=[1850],
    )
    joint_angles: Dict[str, float] = Field(
        default_factory=dict,
        description="Key anatomical joint angles in degrees during this phase",
        examples=[{"right_elbow_deg": 172.5, "shoulder_abduction_deg": 165.0, "trunk_inclination_deg": 168.0}],
    )
    form_accuracy_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Form fidelity score (0-100) benchmarked against the target archetype",
        examples=[88],
    )
    observation: str = Field(
        ...,
        description="Granular biomechanical observation of kinetic chain transfer during this phase",
        examples=["Elbow reached 172.5° extension with stable shoulder abduction; forearm pronation was timed cleanly."],
    )


class BiomechanicalReport(BaseModel):
    """
    Comprehensive structured biomechanical evaluation produced by Gemini 4 Argon.
    """

    model_config = ConfigDict(extra="ignore")

    model_version: str = Field(
        default="gemini-4-argon",
        description="Gemini model version executing the evaluation",
    )
    overall_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Aggregated technical stroke score from 0 (poor) to 100 (mastery)",
        examples=[82],
    )
    matched_archetype: str = Field(
        ...,
        description="Pro or textbook archetype benchmarked against (e.g., 'Fundamentals Baseline', 'Viktor Axelsen', 'Roger Federer')",
        examples=["Viktor Axelsen"],
    )
    primary_flaw: str = Field(
        ...,
        description="Root-cause kinematic defect identified in the kinetic chain",
        examples=["Premature elbow flexion drop prior to shuttle contact resulting in loss of steepness."],
    )
    fatigue_correlation: Optional[str] = Field(
        default=None,
        description="Wearable correlation describing how mechanics degraded as heart rate elevated or cadence dropped",
        examples=["Contact point dropped 8cm during final 3 reps as heart rate spiked above 168 BPM."],
    )
    kinetic_phases: List[KineticPhase] = Field(
        default_factory=list,
        description="Sequential breakdown of stroke phases across the kinematic chain",
    )
    concise_audio_cue: str = Field(
        ...,
        description="Punchy, actionable audio cue (max 12 words) for real-time earbud feedback",
        examples=["Drive hips before elbow release on the forward swing."],
    )
    coach_voice_note_script: str = Field(
        ...,
        description="A natural 30-45 second spoken coaching debrief script for personalized voice playback",
        examples=[
            "Great session today! Your preparation and loading were solid, but as your heart rate hit 168 BPM, "
            "we saw your elbow drop slightly at contact. Focus on driving your hips earlier to create an explosive "
            "whip and maintain full reach. Let's hit the 30-second pronation drill next!"
        ],
    )
