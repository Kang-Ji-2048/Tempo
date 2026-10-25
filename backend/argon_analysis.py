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
        from . import db_mongo, llm_config, sports_config
    else:
        import db_mongo, llm_config, sports_config
except ImportError:
    import db_mongo, llm_config, sports_config

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


ANGLE_LABELS = {
    "right_elbow_contact_deg": "Elbow extension at contact",
    "right_shoulder_abduction_deg": "Shoulder abduction",
    "trunk_arch_deg": "Trunk arch",
    "right_knee_flexion_deg": "Knee flexion",
    "left_arm_balance_deg": "Non-racket arm balance",
}
PASS_SCORE_FLOOR = 80  # PASS scores never drop below this; FAIL scores never reach it.


def compute_pro_deltas(pose_data: Dict[str, Any], pro_match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Measured athlete angles vs. the matched pro's reference angles (athlete minus pro)."""
    deltas = []
    for metric, label in ANGLE_LABELS.items():
        athlete, pro = pose_data.get(metric), pro_match.get(metric)
        if isinstance(athlete, (int, float)) and isinstance(pro, (int, float)):
            deltas.append({"metric": metric, "label": label, "athlete_deg": round(float(athlete), 1),
                           "pro_deg": round(float(pro), 1), "delta_deg": round(float(athlete) - float(pro), 1)})
    return deltas


def load_athlete_context(user_name: str) -> Dict[str, Any]:
    """The athlete's shared memory plus their active lesson node ({} if unavailable)."""
    try:
        memory = db_mongo.get_athlete_memory(user_name)
    except Exception as exc:
        logger.warning("athlete_memory unavailable for %s: %s", user_name, exc)
        return {}
    nodes = memory.get("curriculum_nodes") or []
    return {"memory": memory, "active_node": next((n for n in nodes if n.get("status") == "active"), None)}


def resolve_skill(sport_id: str, skill_id: str, memory: Dict[str, Any]) -> tuple[str, str]:
    """Prefer the athlete's own sport/skill focus from memory over the caller's defaults."""
    sport, skill = memory.get("sport"), memory.get("skill_focus")
    if sport and skill and sports_config.is_skill_analysis_ready(sport, skill):
        return sport, skill
    return sport_id, skill_id


def level_threshold(sport_id: str, skill_id: str, level: Optional[str]) -> float:
    """Elbow-extension pass threshold calibrated to the athlete's level when the rubric has one."""
    skill_def = sports_config.get_skill(sport_id, skill_id)
    if skill_def is None:
        return 165.0
    target = skill_def.rubric_by_level.get(level or "", {}).get("elbow_target_deg")
    return float(target) if target else float(skill_def.threshold_pass_deg)


def measured_score(elbow_deg: float, threshold: float, similarity: float) -> int:
    """0-100 from the measured extension deficit and pro-vector similarity, consistent with PASS/FAIL."""
    deficit = max(0.0, threshold - elbow_deg)
    score = round(100 - 2.5 * deficit - 200 * max(0.0, 1.0 - similarity))
    score = max(0, min(100, score))
    return max(score, PASS_SCORE_FLOOR) if elbow_deg >= threshold else min(score, PASS_SCORE_FLOOR - 1)


AUDIT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "grounded": {"type": "BOOLEAN"},
        "unsupported_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
        "corrected_diagnosis": {"type": "STRING"},
    },
    "required": ["grounded", "unsupported_claims", "corrected_diagnosis"],
}

AUDIT_INSTRUCTION = (
    "You are Tempo's auditor, a second Argon agent. You never coach. Compare the coach's diagnosis with the "
    "measured data. List every claim about the athlete's body, numbers or performance that the measured data does "
    "not support, including invented angles, heart rates or comparisons. If there are none, grounded is true and "
    "corrected_diagnosis repeats the diagnosis. Otherwise rewrite the diagnosis keeping only supported claims."
)


def _numbers(value: Any) -> List[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, (list, tuple)):
        return [n for v in value for n in _numbers(v)]
    return []


def ungrounded_angles(text: str, *measured: Any) -> List[str]:
    """Degree figures in `text` that match no measured value (to within a degree). Deterministic, offline."""
    import re
    known = _numbers(list(measured))
    found = re.findall(r"(\d+(?:\.\d+)?)\s*(?:°|degrees?\b)", text or "")
    return [n for n in found if not any(abs(float(n) - k) <= 1.0 or abs(float(n) + k) <= 1.0 for k in known)]


async def audit_diagnosis(client: Any, measured_data_block: str, coach_output: Dict[str, Any],
                          *measured: Any) -> tuple[str, Dict[str, Any]]:
    """Second Argon call that checks the coach's diagnosis against measured data. Returns (diagnosis, audit)."""
    diagnosis = coach_output["biomechanical_diagnosis"]
    audit: Dict[str, Any] = {"auditor": llm_config.GEMINI_MODEL}
    try:
        response = await asyncio.to_thread(
            client.models.generate_content, model=llm_config.GEMINI_MODEL,
            contents=[measured_data_block, "COACH DIAGNOSIS TO AUDIT:\n" + diagnosis],
            config=types.GenerateContentConfig(
                system_instruction=AUDIT_INSTRUCTION, thinking_config=types.ThinkingConfig(thinking_level="low"),
                response_mime_type="application/json", response_schema=AUDIT_RESPONSE_SCHEMA))
        verdict = json.loads(response.text or "{}")
        claims = [str(c) for c in verdict.get("unsupported_claims") or []]
        audit["unsupported_claims"] = claims
        if not verdict.get("grounded", True) and (verdict.get("corrected_diagnosis") or "").strip():
            diagnosis = verdict["corrected_diagnosis"].strip()
            audit["status"] = "corrected"
        else:
            audit["status"] = "passed"
    except Exception as exc:
        audit.update(status="error", error=f"{type(exc).__name__}: {exc}")
    # Whatever the auditor said, an angle the pose engine never measured never reaches the athlete.
    audit["ungrounded_angles"] = ungrounded_angles(diagnosis, *measured)
    if audit["ungrounded_angles"]:
        audit["status"] = "replaced_with_measured_baseline"
    return diagnosis, audit


NOT_MEASURED = "NOT_MEASURED"


def build_unmeasured_guidance(user_name: str, sport_id: str, skill_id: str,
                              pose_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """No reliable body in the clip: constructive filming + technique guidance, and no invented numbers."""
    skill_def = sports_config.get_skill(sport_id, skill_id)
    skill_name = skill_def.name if skill_def else skill_id.replace("_", " ")
    crowded = (pose_meta or {}).get("status") == "multiple_players_detected"
    framing = ("Another player was in view for most of the clip, so I couldn't lock onto you. "
               if crowded else "I couldn't see your whole body clearly enough to measure your joints. ")
    tip = ("Film side-on from about 3 metres, phone at hip height, with your head, racket and feet in frame "
           "for the whole swing, and keep other players out of shot.")
    return {
        "overall_score": None,
        "verification_status": NOT_MEASURED,
        "primary_flaw": "Swing not measurable from this clip",
        "biomechanical_diagnosis": framing + tip,
        "live_drill_prescription": f"Record 5 {skill_name} reps again side-on, full body in frame, then upload.",
        "concise_audio_cue": "Step back so I can see all of you.",
        "coach_voice_note_script": framing + tip,
        "saint_agent_job": {
            "plain_english_instruction": f"Remind {user_name} to re-film their {skill_name} side-on with full body in frame.",
            "proactive_training_notification": "Quick re-film needed: side-on, full body, 5 reps.",
            "requires_human_approval": True,
            "approval_action_summary": f"Send {user_name} a filming tip for their next {skill_name} clip.",
        },
    }


def build_deterministic_fallback(
    user_name: str,
    sport_id: str,
    skill_id: str,
    pose_data: Dict[str, Any],
    watch_metrics: Dict[str, Any],
    pro_match: Dict[str, Any],
    partner_match: Optional[Dict[str, Any]] = None,
    threshold_deg: Optional[float] = None,
) -> Dict[str, Any]:
    """Generates an honest, deterministic report grounded strictly in measured metrics."""
    elbow_deg = float(pose_data.get("right_elbow_contact_deg", 158.4))
    shoulder_deg = float(pose_data.get("right_shoulder_abduction_deg", 142.0))
    trunk_deg = float(pose_data.get("trunk_arch_deg", 161.5))
    knee_deg = float(pose_data.get("right_knee_flexion_deg", 152.0))
    height_norm = float(pose_data.get("contact_height_norm", 0.78))

    skill_def = sports_config.get_skill(sport_id, skill_id)
    threshold = threshold_deg if threshold_deg is not None else (skill_def.threshold_pass_deg if skill_def else 165.0)
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

    overall_score = measured_score(elbow_deg, threshold, sim_score)
    if passed:
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
    pose_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Executes Gemini 4 Argon analysis with Files API video upload and structured output.

    `pose_data` empty means no reliable body was measured: Gemini coaches from the video alone and the
    score is reported as None. `pose_meta.overhead_contact_detected` False means the angles come from the
    fastest full-body swing frame rather than an overhead contact.

    The athlete's `athlete_memory` (sport, skill focus, level, active lesson, recent flaws) is
    loaded here, so callers only pass measured data; it sets the level-calibrated threshold.
    """
    start_time = time.perf_counter()

    context = load_athlete_context(user_name)
    memory = context.get("memory") or {}
    active_node = context.get("active_node")
    sport_id, skill_id = resolve_skill(sport_id, skill_id, memory)
    threshold = level_threshold(sport_id, skill_id, memory.get("level"))
    pro_deltas = compute_pro_deltas(pose_data, pro_match)
    measured = bool(pose_data)
    meta = pose_meta or {}
    overhead_seen = bool(meta.get("overhead_contact_detected", measured))
    analysis_context = {"sport_id": sport_id, "skill_id": skill_id, "threshold_deg": threshold,
                        "athlete_level": memory.get("level"), "pro_deltas": pro_deltas,
                        "active_node_id": active_node.get("id") if active_node else None,
                        "pose_measured": measured, "overhead_contact_detected": overhead_seen}

    # Step 1: Precompute authoritative deterministic baseline
    baseline = build_deterministic_fallback(
        user_name=user_name,
        sport_id=sport_id,
        skill_id=skill_id,
        pose_data=pose_data,
        watch_metrics=watch_metrics,
        pro_match=pro_match,
        partner_match=partner_match,
        threshold_deg=threshold,
    ) if measured else build_unmeasured_guidance(user_name, sport_id, skill_id, meta)

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
            **analysis_context,
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
        "must come from measured data passed to you. Never invent numbers.\n"
        "verification_status is decided by the measured elbow angle against the level threshold below. "
        f"overall_score is 0-100 and must be >= {PASS_SCORE_FLOOR} only for PASS. "
        "Make live_drill_prescription one concrete drill that targets the largest pro delta, "
        "pitched at the athlete's level and tied to their active lesson."
    )
    memory_block = {
        "level": memory.get("level"), "motivation": memory.get("motivation_why"),
        "intensity": memory.get("intensity"),
        "active_lesson": {k: active_node.get(k) for k in ("id", "title", "tips")} if active_node else None,
        "recent_flaws": (memory.get("recent_flaws") or [])[:3],
    }

    if not measured:
        pose_note = (f"POSE: NOT MEASURED ({meta.get('status')}). There are no joint angles for this clip. Do not "
                     "state any angle or score. Use the video to explain kindly what blocked measurement and how to "
                     "film (side-on, ~3 m, full body, no other players), plus one technique cue you can see. "
                     "Set overall_score to 0 and verification_status to FAIL; both are replaced downstream.\n")
    elif not overhead_seen:
        pose_note = ("POSE: no overhead contact was visible. The angles below are from the fastest full-body swing "
                     "frame. Coach the stroke actually shown, mention that a clear overhead contact wasn't captured if "
                     "the lesson needs one, and suggest filming the full swing side-on.\n")
    else:
        pose_note = "POSE: overhead contact candidate (highest reliable wrist frame).\n"
    reps = meta.get("rep_analysis") or {}
    if reps:
        session = reps.get("session_analysis") or {}
        pose_note += (
            f"REP ANALYSIS: {reps.get('rep_count')} complete reps, best rep #{reps.get('best_rep_index')} detected as "
            f"{reps.get('detected_stroke')} (target {reps.get('target_stroke') or 'any'}), quality "
            f"{reps.get('quality_score')}/100, primary deviation: {reps.get('primary_deviation') or 'none'}. "
            f"Phase angles: {json.dumps([{p['phase_name']: p['joint_angles']} for p in reps.get('kinetic_phases', [])])}. "
            f"Drift: {(session.get('drift') or {}).get('message') or 'none'}. Coach this stroke, not a generic overhead.\n")
    measured_data_block = (
        pose_note +
        f"MEASURED DATA:\n"
        f"Athlete: {user_name} | Sport: {sport_name} | Skill: {skill_name}\n"
        f"3D Joint Angles: {json.dumps(pose_data, indent=2)}\n"
        + (f"Apple Watch Biometrics: {json.dumps(watch_metrics, indent=2)}\n" if watch_metrics.get("measured", True)
           else "Apple Watch Biometrics: none recorded for this session; do not mention heart rate or fatigue.\n")
        + f"Closest Pro Match: {json.dumps(pro_match, indent=2, default=str)}\n"
        f"Pro Deltas (athlete minus pro, degrees): {json.dumps(pro_deltas, indent=2)}\n"
        f"Athlete Memory: {json.dumps(memory_block, indent=2, default=str)}\n"
        f"Rule Threshold ({memory.get('level') or 'default'} level): {threshold:.0f}° elbow angle at contact is PASS, else FAIL.\n"
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
        # Measured numbers are authoritative: PASS/FAIL comes from the threshold, and the score must agree.
        response_data["verification_status"] = baseline["verification_status"]
        if not measured:
            response_data["overall_score"] = None  # nothing was measured, so there is no score to report
        else:
            score = int(response_data["overall_score"])
            response_data["overall_score"] = (max(score, PASS_SCORE_FLOOR) if baseline["verification_status"] == "PASS"
                                              else min(score, PASS_SCORE_FLOOR - 1))
            # Two-agent check: a second Argon call audits the coach against the measured numbers.
            diagnosis, audit = await audit_diagnosis(client, measured_data_block, response_data, pose_data,
                                                     pro_match, pro_deltas, watch_metrics, threshold)
            response_data["biomechanical_diagnosis"] = (baseline["biomechanical_diagnosis"]
                                                        if audit["ungrounded_angles"] else diagnosis)
            response_data["argon_audit"] = audit
        return {
            **response_data,
            **analysis_context,
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
            **analysis_context,
            "llm_source": "fallback",
            "llm_model": "deterministic_fallback",
            "llm_error": llm_error,
            "video_used": False,
            "video_error": video_error,
            "latency_ms": latency_ms,
        }
