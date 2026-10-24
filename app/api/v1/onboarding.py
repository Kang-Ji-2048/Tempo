"""
app/api/v1/onboarding.py - Backend-Driven Onboarding Endpoint for Tempo
Emits Server-Driven UI (SDUI) widgets across the onboarding progression.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("tempo.onboarding")

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStepRequest(BaseModel):
    step_id: str = Field(default="", description="ID of the completed step")
    answer: str = Field(default="", description="User selected answer for step_id")
    answers: Dict[str, str] = Field(default_factory=dict, description="Accumulated answers map")


class UserProfileResponse(BaseModel):
    user_id: str = "usr_athlete_001"
    sport: str = "badminton"
    level: str = "intermediate"
    goal: str = "overhead_power"
    playstyle: str = "aggressive"
    injuries: str = "none"
    target_archetype: str = "Viktor Axelsen"
    calibration_completed: bool = True


class OnboardingStepResponse(BaseModel):
    step_id: str
    progress: float
    coach_message: str
    widget: Optional[Dict[str, Any]] = None
    is_completed: bool = False
    user_profile: Optional[UserProfileResponse] = None


@router.post(
    "/next",
    response_model=OnboardingStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Get next SDUI onboarding step",
)
async def next_onboarding_step(req: OnboardingStepRequest) -> OnboardingStepResponse:
    """
    Evaluates previous answer, updates user onboarding state, and emits the next SDUI widget.
    Scripted flow: sport -> level -> goal -> playstyle -> injuries -> archetype -> capture_prompt -> summary/permissions.
    """
    answers = dict(req.answers)
    if req.step_id and req.answer:
        answers[req.step_id] = req.answer

    current_step = req.step_id or "init"

    # Step 0: Initial request -> Sport ChoiceWidget
    if current_step in ("init", ""):
        return OnboardingStepResponse(
            step_id="sport",
            progress=0.125,
            coach_message="Hey! I'm your Tempo AI coach. Let's calibrate your biomechanics and dial in your movement baseline. What's your primary sport?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "sport",
                "title": "Select Your Sport",
                "subtitle": "Your kinematic models and Olympic benchmarks adapt to this sport.",
                "multi_select": False,
                "options": [
                    {
                        "id": "badminton",
                        "label": "Badminton",
                        "description": "High-velocity overhead clears, jump smashes, and lateral split-steps",
                        "emoji": "🏸",
                    },
                    {
                        "id": "tennis",
                        "label": "Tennis",
                        "description": "Heavy topspin groundstrokes, kinetic serve chain, and court transitions",
                        "emoji": "🎾",
                    },
                    {
                        "id": "pickleball",
                        "label": "Pickleball",
                        "description": "Kitchen dinks, rapid hand speed, reset mechanics, and rotational drives",
                        "emoji": "🏓",
                    },
                    {
                        "id": "squash",
                        "label": "Squash",
                        "description": "High cardiovascular tempo, low lunges, and tight wall angles",
                        "emoji": "💥",
                    },
                ],
            },
        )

    # Step 1 -> Level
    if current_step == "sport":
        sport_name = answers.get("sport", "badminton").title()
        return OnboardingStepResponse(
            step_id="level",
            progress=0.25,
            coach_message=f"{sport_name}! Fantastic sport for kinetic chain mastery. What level are you currently competing at?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "level",
                "title": "Current Skill Tier",
                "subtitle": "Determines pose analysis tolerance and real-time audio cue frequency.",
                "multi_select": False,
                "options": [
                    {
                        "id": "beginner",
                        "label": "Beginner / Recreational",
                        "description": "Building fundamental stroke paths, balance, and basic timing",
                        "emoji": "🌱",
                    },
                    {
                        "id": "intermediate",
                        "label": "Club / Intermediate",
                        "description": "Consistent rally player tuning power, depth, and technique",
                        "emoji": "⚡",
                    },
                    {
                        "id": "advanced",
                        "label": "Advanced / Competitive",
                        "description": "Tournament athlete optimizing milliseconds of kinetic lag",
                        "emoji": "🏆",
                    },
                ],
            },
        )

    # Step 2 -> Goal
    if current_step == "level":
        return OnboardingStepResponse(
            step_id="goal",
            progress=0.375,
            coach_message="Got it. Every athlete has a primary lever. What is the single biggest breakthrough you want from our sessions?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "goal",
                "title": "Primary Focus Area",
                "subtitle": "Our Gemini Argon pipeline prioritizes drills targeting this flaw.",
                "multi_select": False,
                "options": [
                    {
                        "id": "overhead_power",
                        "label": "Overhead Power & Steepness",
                        "description": "Maximize forearm pronation and steep downward attack trajectory",
                        "emoji": "⚡",
                    },
                    {
                        "id": "footwork_speed",
                        "label": "Footwork Speed & Recovery",
                        "description": "Quicker recovery to center court and explosive change of direction",
                        "emoji": "👟",
                    },
                    {
                        "id": "consistency_depth",
                        "label": "Stroke Consistency & Length",
                        "description": "Eliminate unforced frame errors and hit back line consistently",
                        "emoji": "🎯",
                    },
                ],
            },
        )

    # Step 3 -> Playstyle
    if current_step == "goal":
        return OnboardingStepResponse(
            step_id="playstyle",
            progress=0.50,
            coach_message="Love that focus. Now, how do you express yourself on court? What's your natural playstyle?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "playstyle",
                "title": "Court Playstyle",
                "subtitle": "Aligns tactical SDUI recommendations with your personality.",
                "multi_select": False,
                "options": [
                    {
                        "id": "defensive",
                        "label": "Defensive Retriever",
                        "description": "Patient, high clears, tireless court coverage, waiting for opponent errors",
                        "emoji": "🛡️",
                    },
                    {
                        "id": "aggressive",
                        "label": "Aggressive Attacker",
                        "description": "Heavy pace, steep jump smashes, intercepts early at the net",
                        "emoji": "🔥",
                    },
                    {
                        "id": "all_court",
                        "label": "All-Court Tactician",
                        "description": "Deceptive drops, shifts tempo unpredictably, controls geometry",
                        "emoji": "🧠",
                    },
                ],
            },
        )

    # Step 4 -> Injuries
    if current_step == "playstyle":
        return OnboardingStepResponse(
            step_id="injuries",
            progress=0.625,
            coach_message="Crucial biomechanical check: protect the kinetic chain. Any past or recurring limitations I should guard against?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "injuries",
                "title": "Injury Prevention Guardrails",
                "subtitle": "Tempo flags excessive joint stress during high-strain phases.",
                "multi_select": False,
                "options": [
                    {
                        "id": "none",
                        "label": "100% Healthy / No Issues",
                        "description": "Ready for maximum range of motion and load",
                        "emoji": "✨",
                    },
                    {
                        "id": "shoulder",
                        "label": "Rotator Cuff / Shoulder",
                        "description": "Guard against hyperextension during high loading phase",
                        "emoji": "⚠️",
                    },
                    {
                        "id": "elbow",
                        "label": "Forearm Tendon / Tennis Elbow",
                        "description": "Monitor impact shock and grip deceleration",
                        "emoji": "🩹",
                    },
                    {
                        "id": "knee",
                        "label": "Knee / Patellar Tendon",
                        "description": "Monitor jump landing angles and deep lunge shock",
                        "emoji": "🦵",
                    },
                ],
            },
        )

    # Step 5 -> "Who do you want to move like?" (Archetype)
    if current_step == "injuries":
        sport = answers.get("sport", "badminton").lower()
        if sport == "tennis":
            archetypes = [
                {
                    "id": "Roger Federer",
                    "label": "Roger Federer",
                    "description": "Effortless kinetic fluidity, precision balance, and early ball-strike",
                    "emoji": "🇨🇭",
                },
                {
                    "id": "Rafael Nadal",
                    "label": "Rafael Nadal",
                    "description": "Heavy topspin torque, explosive open stance, and maximum angular momentum",
                    "emoji": "🇪🇸",
                },
                {
                    "id": "Carlos Alcaraz",
                    "label": "Carlos Alcaraz",
                    "description": "Dynamic front-foot acceleration, steep drop deception, and lightning recovery",
                    "emoji": "⚡",
                },
            ]
        else:
            archetypes = [
                {
                    "id": "Viktor Axelsen",
                    "label": "Viktor Axelsen",
                    "description": "Full 175° reach, steep downward angles, suffocating court length",
                    "emoji": "🇩🇰",
                },
                {
                    "id": "Kento Momota",
                    "label": "Kento Momota",
                    "description": "Flawless footwork economy, surgical precision, deceptive defensive turns",
                    "emoji": "🇯🇵",
                },
                {
                    "id": "Lee Chong Wei",
                    "label": "Lee Chong Wei",
                    "description": "Lightning racket acceleration, explosive jump smashes, feline agility",
                    "emoji": "🇲🇾",
                },
            ]

        return OnboardingStepResponse(
            step_id="archetype",
            progress=0.75,
            coach_message="This is my favorite part. Biomechanics work best with a mental model. Who do you want to move like?",
            widget={
                "widget_type": "ChoiceWidget",
                "id": "archetype",
                "title": "Kinematic Benchmark Archetype",
                "subtitle": "Your 33-landmark skeleton will be compared directly against their gold standard.",
                "multi_select": False,
                "options": archetypes,
            },
        )

    # Step 6 -> 5-second capture prompt
    if current_step == "archetype":
        archetype = answers.get("archetype", "Viktor Axelsen")
        return OnboardingStepResponse(
            step_id="capture_prompt",
            progress=0.875,
            coach_message=f"Calibrating your baseline against {archetype}! Let's record a 5-second calibration swing so the AI maps your initial posture.",
            widget={
                "widget_type": "CapturePromptWidget",
                "id": "baseline_calibration",
                "title": "Baseline Stroke Calibration",
                "instruction": "Record 1 full-effort practice swing. Stand 3-4 meters away so your entire body and racket are visible in frame.",
                "camera_hint": "Film from behind-left • Full body in frame • 60fps",
                "duration_s": 5,
            },
        )

    # Step 7 -> Summary & Permissions
    selected_sport = answers.get("sport", "badminton")
    selected_level = answers.get("level", "intermediate")
    selected_goal = answers.get("goal", "overhead_power")
    selected_playstyle = answers.get("playstyle", "aggressive")
    selected_injuries = answers.get("injuries", "none")
    selected_archetype = answers.get("archetype", "Viktor Axelsen")

    user_profile = UserProfileResponse(
        user_id="usr_athlete_001",
        sport=selected_sport,
        level=selected_level,
        goal=selected_goal,
        playstyle=selected_playstyle,
        injuries=selected_injuries,
        target_archetype=selected_archetype,
        calibration_completed=True,
    )

    return OnboardingStepResponse(
        step_id="summary_permissions",
        progress=1.0,
        coach_message=f"You're all set! We've configured your profile benchmarked to {selected_archetype}. Grant the permissions below so Tempo can deliver live kinematic coaching.",
        widget=None,
        is_completed=True,
        user_profile=user_profile,
    )
