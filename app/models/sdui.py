"""
app/models/sdui.py - Server-Driven UI (SDUI) Widget Schemas for Android Jetpack Compose
"""

from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field


class PathNode(BaseModel):
    """A single skill progression node in the mastery tree."""

    model_config = ConfigDict(extra="ignore")

    node_id: str = Field(..., description="Unique node identifier", examples=["rear_court_smash_01"])
    title: str = Field(..., description="Skill node title", examples=["Full Elbow Extension"])
    status: str = Field(..., description="Status: LOCKED, ACTIVE, COMPLETED", examples=["ACTIVE"])
    xp_reward: int = Field(default=50, description="XP awarded on completion")


class PathProgressWidget(BaseModel):
    """
    Skill mastery progression tree widget for Android Jetpack Compose.
    """

    model_config = ConfigDict(extra="ignore")

    widget_type: str = Field(default="PathProgressWidget", description="SDUI widget discriminator")
    current_streak: int = Field(..., ge=0, description="Consecutive days streak", examples=[5])
    active_node_id: str = Field(..., description="Current in-progress node ID", examples=["rear_court_smash_01"])
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="Skill tree nodes")


class DrillCardWidget(BaseModel):
    """
    Actionable remedial drill card widget prescribed to correct biomechanical flaws.
    """

    model_config = ConfigDict(extra="ignore")

    widget_type: str = Field(default="DrillCardWidget", description="SDUI widget discriminator")
    id: str = Field(..., description="Unique drill ID", examples=["drill_pronation_wall_30s"])
    title: str = Field(..., description="Title of the drill", examples=["30s Rapid Pronation Drill"])
    instruction: str = Field(
        ...,
        description="Step-by-step biomechanical drill instructions",
        examples=["Stand 1 meter from wall. Rapidly pronate forearm against shuttlecock target maintaining elbow height."],
    )
    target_reps: int = Field(..., gt=0, description="Prescribed repetition or duration count", examples=[15])
    focus_cue: str = Field(
        ...,
        description="Key mental cue during drill execution",
        examples=["Snap wrist and pronate forearm at top of reach."],
    )


class ConceptQuizWidget(BaseModel):
    """
    Interactive micro-quiz widget reinforcing tactical & kinematic principles.
    """

    model_config = ConfigDict(extra="ignore")

    widget_type: str = Field(default="ConceptQuizWidget", description="SDUI widget discriminator")
    question: str = Field(
        ...,
        description="Kinematic conceptual question",
        examples=["Why is early hip rotation critical before racket acceleration in the overhead clear?"],
    )
    options: List[str] = Field(
        ...,
        min_length=2,
        description="Multiple-choice answer candidates",
        examples=[
            "It transfers ground force through the core into the shoulder.",
            "It lowers the shuttlecock trajectory.",
            "It reduces cardiovascular demand.",
            "It prevents knee flexion.",
        ],
    )
    correct_index: int = Field(
        ...,
        ge=0,
        description="0-indexed pointer to the correct answer",
        examples=[0],
    )
    explanation: str = Field(
        ...,
        description="Biomechanical explanation displayed after player selects an option",
        examples=["Hip rotation initiates the kinetic chain, allowing ground reaction force to multiply through the trunk into the arm."],
    )


class SDUIPayload(BaseModel):
    """
    Unified Server-Driven UI payload rendered dynamically by the Android client.
    """

    model_config = ConfigDict(extra="ignore")

    screen: str = Field(
        default="post_session_analysis",
        description="Target client screen identifier",
    )
    coach_summary: str = Field(
        ...,
        description="High-level debrief summary for top card banner",
    )
    widgets: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Polymorphic list of SDUI widgets rendered in order",
    )
