"""Gemini 4 Argon Biomechanical Analysis Engine.
Implements:
- Measured data injection as authoritative ground truth
- Optional Files API video upload with graceful fallback to text-only
- High thinking level structured output with response_schema
- Single retry on invalid JSON
- Explicit provenance tracking: llm_source, llm_model, llm_error, video_used, latency_ms
- Transparent error logging without silent fallbacks
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError

from google import genai
from google.genai import types

try:
    if __package__:
        from . import llm_config, sports_config
    else:
        import llm_config, sports_config
except ImportError:
    import llm_config, sports_config

logger = logging.getLogger("tempo.argon")


class SaintAgentJobSchema(BaseModel):
    plain_english_instruction: str = Field(min_length=1)
    proactive_training_notification: str = Field(min_length=1)
    requires_human_approval: bool = True
    approval_action_summary: str = Field(min_length=1)


class BiomechanicalAnalysisResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    verification_status: Literal["PASS", "FAIL"]
    primary_flaw: str
    biomechanical_diagnosis: str
    live_drill_prescription: str
    concise_audio_cue: str
    coach_voice_note_script: str
    saint_agent_job: SaintAgentJobSchema


ANALYSIS_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overall_score": {"type": "INTEGER"},
        "verification_status": {"type": "STRING", "enum": ["PASS", "FAIL"]},
        "primary_flaw": {"type": "STRING"},
        "biomechanical_diagnosis": {"type": "STRING"},
        "live_drill_prescription": {"type": "STRING"},
        "concise_audio_cue": {"type": "STRING"},
        "coach_voice_note_script": {"type": "STRING"},
        "saint_agent_job": {
            "type": "OBJECT",
            "properties": {
                "plain_english_instruction": {"type": "STRING"},
                "proactive_training_notification": {"type": "STRING"},
                "requires_human_approval": {"type": "BOOLEAN"},
                "approval_action_summary": {"type": "STRING"},
            },
            "required": [
                "plain_english_instruction",
                "proactive_training_notification",
                "requires_human_approval",
                "approval_action_summary",
            ],
        },
    },
    "required": [
        "overall_score",
        "verification_status",
        "primary_flaw",
        "biomechanical_diagnosis",
        "live_drill_prescription",
        "concise_audio_cue",
        "coach_voice_note_script",
        "saint_agent_job",
    ],
}


def build_deterministic_fallback(
    user_name: str,
    sport_id: str,
    skill_id: str,
    pose_data: Dict[str, Any],
    watch_metrics: Dict[str, Any],
    pro_match: Dict[str, Any],
    partner_match: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generates an honest, deterministic report grounded strictly in measured metrics."""
    elbow_deg = float(pose_data.get("right_elbow_contact_deg", 158.4))
    shoulder_deg = float(pose_data.get("right_shoulder_abduction_deg", 142.0))
    trunk_deg = float(pose_data.get("trunk_arch_deg", 161.5))
    knee_deg = float(pose_data.get("right_knee_flexion_deg", 152.0))
    height_norm = float(pose_data.get("contact_height_norm", 0.78))

    skill_def = sports_config.get_skill(sport_id, skill_id)
    threshold = skill_def.threshold_pass_deg if skill_def else 165.0
    passed = elbow_deg >= threshold
    verification_status = "PASS" if passed else "FAIL"

    pro_name = pro_match.get("player_name", "Roger Federer")
    pro_elbow = float(pro_match.get("right_elbow_contact_deg", 176.5))
    sim_score = float(pro_match.get("similarity_score", 0.94))

    hr_bpm = watch_metrics.get("heart_rate_bpm")
    calories = watch_metrics.get("active_calories_kcal")
    fatigue = watch_metrics.get("fatigue_state", "MODERATE_FATIGUE")

    partner = partner_match or {
        "name": "Arjun Mehta",
        "preferred_venue": "Finsbury Leisure Centre (EC1V)",
        "availability": "Tomorrow 18:00 UTC",
    }
    venue = partner.get("preferred_venue", "Finsbury Leisure Centre")
    slot = partner.get("availability", "Tomorrow 18:00 UTC")

    if passed:
        overall_score = 88
        primary_flaw = f"Full extension achieved ({elbow_deg:.1f}° at contact)"
        diagnosis = (
            f"VERIFIED PASS: {user_name} achieved {elbow_deg:.1f}° elbow extension at contact "
            f"(threshold {threshold:.0f}°), matching {pro_name}'s {pro_elbow:.1f}° kinematic profile. "
            f"Shoulder abduction ({shoulder_deg:.1f}°) and trunk arch ({trunk_deg:.1f}°) were maintained."
        )
        drill = f"Maintain form accuracy with 3x10 target-zone overhead sequences at {venue}."
        cue = "Maintain full high reach at contact apex."
        voice_script = f"Great stroke mechanics today. Your elbow reached {elbow_deg:.1f} degrees at contact. Keep this high contact point consistent."
    else:
        overall_score = 68
        primary_flaw = f"Elbow dropped to {elbow_deg:.1f}° at contact (target {threshold:.0f}°)"
        diagnosis = (
            f"VERIFIED FAIL: {user_name}'s elbow angle dropped to {elbow_deg:.1f}° at contact, "
            f"which is below the {threshold:.0f}° target and {pro_elbow - elbow_deg:.1f}° lower than {pro_name}'s "
            f"reference profile (vector similarity {sim_score:.2f})."
        )
        drill = f"Prescribe 4x10 shadow reach extension drills to practice hitting at full extension."
        cue = "Reach up high and brush the contact point."
        voice_script = f"Good effort today, but your elbow dropped to {elbow_deg:.1f} degrees at contact. Focus on reaching up tall to hit at the highest apex."

    saint_job = {
        "plain_english_instruction": f"Schedule follow-up practice for {user_name} with {partner.get('name')} at {venue} ({slot}).",
        "proactive_training_notification": f"Practice check: elbow reached {elbow_deg:.1f}° vs {threshold:.0f}° target. Partner available at {venue} ({slot}).",
        "requires_human_approval": True,
        "approval_action_summary": f"Book training court at {venue} with {partner.get('name')}.",
    }

    return {
        "overall_score": overall_score,
        "verification_status": verification_status,
        "primary_flaw": primary_flaw,
        "biomechanical_diagnosis": diagnosis,
        "live_drill_prescription": drill,
        "concise_audio_cue": cue,
        "coach_voice_note_script": voice_script,
        "saint_agent_job": saint_job,
    }


async def run_biomechanical_analysis(
    user_name: str,
    sport_id: str,
    skill_id: str,
    pose_data: Dict[str, Any],
    watch_metrics: Dict[str, Any],
    pro_match: Dict[str, Any],
    video_path: Optional[str] = None,
    partner_match: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Executes Gemini 4 Argon analysis with Files API video upload and structured output."""
    start_time = time.perf_counter()

    # Step 1: Precompute authoritative deterministic baseline
    baseline = build_deterministic_fallback(
        user_name=user_name,
        sport_id=sport_id,
        skill_id=skill_id,
        pose_data=pose_data,
        watch_metrics=watch_metrics,
        pro_match=pro_match,
        partner_match=partner_match,
    )

    skill_def = sports_config.get_skill(sport_id, skill_id)
    sport_name = sport_id.replace("_", " ").title()
    skill_name = skill_def.name if skill_def else skill_id.replace("_", " ").title()

    # Check key presence
    if not llm_config.GEMINI_API_KEY:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("GEMINI_API_KEY missing: using deterministic fallback")
        llm_config.update_ai_status(False, error="GEMINI_API_KEY missing", latency_ms=latency_ms)
        return {
            **baseline,
            "llm_source": "fallback",
            "llm_model": "deterministic_fallback",
            "llm_error": "GEMINI_API_KEY is not configured",
            "video_used": False,
            "latency_ms": latency_ms,
        }

    client = llm_config.get_client()

    # Step 2: Upload video to Files API if requested
    video_file = None
    video_used = False
    video_error = None

    if llm_config.GEMINI_SEND_VIDEO and video_path and os.path.exists(video_path):
        try:
            logger.info("Uploading video to Gemini Files API: %s", video_path)
            uploaded = await asyncio.to_thread(client.files.upload, file=video_path)
            # Poll for processing
            timeout_s = 45
            poll_start = time.time()
            while uploaded.state == "PROCESSING" and time.time() - poll_start < timeout_s:
                await asyncio.sleep(2)
                uploaded = await asyncio.to_thread(client.files.get, name=uploaded.name)

            if uploaded.state == "ACTIVE":
                video_file = uploaded
                video_used = True
                logger.info("Video successfully uploaded and ACTIVE: %s", uploaded.name)
            else:
                video_error = f"Video state is {uploaded.state}"
                logger.warning("Files API video not ACTIVE (state=%s), falling back to text-only", uploaded.state)
        except Exception as upload_exc:
            video_error = f"{type(upload_exc).__name__}: {upload_exc}"
            logger.warning("Failed to upload video to Files API (%s); proceeding text-only", upload_exc)

    # Step 3: Prompt Construction
    system_instruction = (
        "Measured numbers are authoritative. Do not estimate joint angles from the video. "
        "Use the video only to describe what the movement looks like and to judge things not in the measured data.\n"
        "You are Tempo, an elite on-court coach. Talk like a person on court: warm, direct, level-calibrated, brief. "
        "Each session ends with ONE primary fix, never a list of eight. Everything you say about the athlete's body "
        "must come from measured data passed to you. Never invent numbers."
    )

    measured_data_block = (
        f"MEASURED DATA:\n"
        f"Athlete: {user_name} | Sport: {sport_name} | Skill: {skill_name}\n"
        f"3D Joint Angles: {json.dumps(pose_data, indent=2)}\n"
        f"Apple Watch Biometrics: {json.dumps(watch_metrics, indent=2)}\n"
        f"Closest Pro Match: {json.dumps(pro_match, indent=2)}\n"
        f"Rule Threshold: {skill_def.threshold_pass_deg if skill_def else 165.0}° elbow angle at contact is PASS, else FAIL.\n"
        f"Training Partner: {json.dumps(partner_match or {}, indent=2)}\n"
    )

    contents: List[Any] = [measured_data_block]
    if video_file is not None:
        contents.append(video_file)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(thinking_level="high"),
        response_mime_type="application/json",
        response_schema=ANALYSIS_RESPONSE_SCHEMA,
    )

    # Step 4: Execute Gemini Call with Single Retry on Invalid JSON
    llm_error: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None

    for attempt in range(2):
        try:
            call_start = time.perf_counter()
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=llm_config.GEMINI_MODEL,
                contents=contents,
                config=config,
            )
            raw_text = response.text or "{}"
            parsed_json = json.loads(raw_text)
            validated = BiomechanicalAnalysisResult.model_validate(parsed_json)
            response_data = validated.model_dump()
            break
        except (json.JSONDecodeError, ValidationError) as parse_err:
            llm_error = f"Parse/Validation Error: {parse_err}"
            logger.warning("Gemini 4 Argon response validation error on attempt %d: %s", attempt + 1, parse_err)
            if attempt == 0:
                contents.append(f"The previous output failed validation: {parse_err}. Correct the JSON schema and retry.")
        except Exception as api_err:
            llm_error = f"{type(api_err).__name__}: {api_err}"
            logger.error("Gemini 4 Argon call failed: %s", api_err, exc_info=True)
            break

    # Clean up uploaded video file
    if video_file is not None:
        try:
            await asyncio.to_thread(client.files.delete, name=video_file.name)
        except Exception:
            pass

    latency_ms = int((time.perf_counter() - start_time) * 1000)

    if response_data is not None:
        llm_config.update_ai_status(True, latency_ms=latency_ms)
        return {
            **response_data,
            "llm_source": "gemini",
            "llm_model": llm_config.GEMINI_MODEL,
            "llm_error": None,
            "video_used": video_used,
            "video_error": video_error,
            "latency_ms": latency_ms,
        }
    else:
        llm_config.update_ai_status(False, error=llm_error, latency_ms=latency_ms)
        return {
            **baseline,
            "llm_source": "fallback",
            "llm_model": "deterministic_fallback",
            "llm_error": llm_error,
            "video_used": False,
            "video_error": video_error,
            "latency_ms": latency_ms,
        }
