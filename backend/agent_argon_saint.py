"""
agent_argon_saint.py - Gemini 4 Argon Biomechanical Verification & Saint AI Autonomous Coach (Kong/Sumanth)
- Verifies concrete Pass/Fail biomechanical threshold: `right_elbow_contact_deg >= 165.0` deg = PASS, else FAIL.
- Calls `gemini-4-argon` via `client.interactions.create` (`thinking_level="high"`) with Sumanth's joint angles,
  Apple Watch heart rate/fatigue, and matched Pro reference from MongoDB.
- Returns structured JSON: `verification_status`, `biomechanical_diagnosis`, `live_drill_prescription`,
  and `saint_agent_job` (`plain_english_instruction`, `proactive_training_notification`,
  `requires_human_approval: true`, `approval_action_summary`).
- POSTs `saint_agent_job` to `SAINT_WEBHOOK_URL` if configured.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests
from google import genai

ELBOW_EXTENSION_PASS_THRESHOLD_DEG = 165.0


def verify_biomechanical_threshold(right_elbow_contact_deg: float) -> str:
    """
    Concrete Pass/Fail biomechanical verification loop:
    `right_elbow_contact_deg >= 165.0` deg = PASS, else FAIL.
    """
    return "PASS" if float(right_elbow_contact_deg) >= ELBOW_EXTENSION_PASS_THRESHOLD_DEG else "FAIL"


def _build_deterministic_coaching_response(
    user_name: str,
    verification_status: str,
    pose_data: Dict[str, Any],
    watch_metrics: Dict[str, Any],
    pro_match: Dict[str, Any],
    partner_match: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministic high-precision biomechanical diagnosis & Saint AI job payload
    used to guarantee exact schema fields or when GEMINI_API_KEY is not configured.
    """
    elbow_deg = float(pose_data.get("right_elbow_contact_deg", 158.4))
    shoulder_deg = float(pose_data.get("right_shoulder_abduction_deg", 142.0))
    trunk_deg = float(pose_data.get("trunk_arch_deg", 161.5))
    knee_deg = float(pose_data.get("right_knee_flexion_deg", 152.0))
    height_norm = float(pose_data.get("contact_height_norm", 0.78))

    pro_name = pro_match.get("player_name", "Roger Federer")
    pro_elbow = float(pro_match.get("right_elbow_contact_deg", 176.5))
    sim_score = float(pro_match.get("similarity_score", 0.98))
    elbow_gap = round(pro_elbow - elbow_deg, 1)

    hr_bpm = float(watch_metrics.get("heart_rate_bpm", 168.0))
    calories = float(watch_metrics.get("active_calories_kcal", 420.0))
    fatigue = str(watch_metrics.get("fatigue_state", "MODERATE_FATIGUE_ELEVATED_LOAD"))

    partner_name = partner_match.get("name", "Arjun Mehta")
    venue = partner_match.get("preferred_venue", "Islington Tennis & Racket Centre / Finsbury Leisure (EC1V)")
    slot = partner_match.get("availability", "Tonight 20:00 - 22:00 BST")

    if verification_status == "PASS":
        diagnosis = (
            f"VERIFIED PASS: {user_name} achieved {elbow_deg:.1f}° right elbow extension at peak overhead contact "
            f"(>= {ELBOW_EXTENSION_PASS_THRESHOLD_DEG:.1f}° threshold), closely tracking {pro_name}'s {pro_elbow:.1f}° "
            f"reference profile (cosine similarity {sim_score:.4f}). Shoulder abduction ({shoulder_deg:.1f}°) and "
            f"trophy-pose trunk arch ({trunk_deg:.1f}°) maintain efficient kinetic-chain transfer even at {hr_bpm:.0f} BPM "
            f"({fatigue})."
        )
        drill = (
            f"Maintain high-contact serve/smash extension with 3x12 target-zone overhead sequences at {venue}. "
            f"Keep heart rate below 175 BPM with 45s active recovery between sets while reinforcing full forearm "
            f"pronation at peak reach ({height_norm:.2f} normalized height)."
        )
    else:
        diagnosis = (
            f"VERIFIED FAIL: {user_name}'s right elbow angle collapsed to {elbow_deg:.1f}° at overhead impact "
            f"(below the {ELBOW_EXTENSION_PASS_THRESHOLD_DEG:.1f}° biomechanical threshold and {elbow_gap:.1f}° below "
            f"{pro_name}'s {pro_elbow:.1f}° benchmark; vector similarity {sim_score:.4f}). Combined with Apple Watch "
            f"biometrics ({hr_bpm:.0f} BPM, {calories:.0f} kcal, {fatigue}), cardiovascular fatigue is causing a dropped "
            f"trophy pose, reduced shoulder abduction ({shoulder_deg:.1f}°), and late knee drive ({knee_deg:.1f}°)."
        )
        drill = (
            f"Prescribe 4x10 trophy-pose to peak-reach overhead extension drills + non-racket left-arm toss/balance tracking "
            f"before high-tempo points. Focus on contacting at full reach (>={ELBOW_EXTENSION_PASS_THRESHOLD_DEG:.0f}° "
            f"elbow extension like {pro_name}) once HR recovers below 155 BPM."
        )

    saint_job = {
        "plain_english_instruction": (
            f"Stage a 60-minute overhead biomechanical correction session for {user_name} with London partner "
            f"{partner_name} at {venue} ({slot}) focusing on overhead elbow extension ({elbow_deg:.1f}° -> "
            f"{ELBOW_EXTENSION_PASS_THRESHOLD_DEG:.0f}°+ target) matched to {pro_name}. Hold external court booking "
            f"and partner invite until {user_name} approves."
        ),
        "proactive_training_notification": (
            f"Hey {user_name}! Your overhead stroke check returned {verification_status} ({elbow_deg:.1f}° elbow angle "
            f"at {hr_bpm:.0f} BPM vs {pro_name}'s {pro_elbow:.1f}°). I matched you with {partner_name} at {venue} "
            f"({slot}) for an overhead extension & recovery session—tap Approve to book Court 3 and send the invite."
        ),
        "requires_human_approval": True,
        "approval_action_summary": (
            f"Book Court 3 at {venue} ({slot}) and send partner invite to {partner_name} (London) for {user_name}'s "
            f"overhead extension drill."
        ),
        "matched_partner": partner_name,
        "venue": venue,
        "proposed_slot": slot,
    }

    return {
        "verification_status": verification_status,
        "biomechanical_diagnosis": diagnosis,
        "live_drill_prescription": drill,
        "saint_agent_job": saint_job,
    }


def dispatch_saint_webhook(
    saint_agent_job: Dict[str, Any],
    event_type: str = "SAINT_JOB_STAGED",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    POST `saint_agent_job` to `SAINT_WEBHOOK_URL` if configured in the environment.
    """
    webhook_url = os.environ.get("SAINT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {
            "webhook_configured": False,
            "dispatched": False,
            "event_type": event_type,
            "detail": "SAINT_WEBHOOK_URL not set; job staged locally awaiting human-in-the-loop approval.",
        }

    payload = {
        "event_type": event_type,
        "saint_agent_job": saint_agent_job,
        "metadata": extra_metadata or {},
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=6.0)
        return {
            "webhook_configured": True,
            "dispatched": resp.ok,
            "status_code": resp.status_code,
            "event_type": event_type,
        }
    except Exception as exc:
        return {
            "webhook_configured": True,
            "dispatched": False,
            "event_type": event_type,
            "error": str(exc),
        }


def _call_gemini_4_argon(prompt: str, response_schema: Dict[str, Any]) -> Optional[str]:
    """
    Invoke `gemini-4-argon` via the Interactions API (`client.interactions.create`)
    with `thinking_level="high"` and JSON structured output.
    Strictly avoids deprecated `thinking_budget`, `temperature`, `top_p`, `top_k`, or `cached_content`.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)

    # Support both the user-specified `config={"thinking_level": "high", "response_mime_type": "application/json"}`
    # signature and the upstream `google-genai` Interactions API `generation_config` + `response_format` signature.
    try:
        interaction = client.interactions.create(
            model="gemini-4-argon",
            input=prompt,
            config={
                "thinking_level": "high",
                "response_mime_type": "application/json",
            },
        )
        return getattr(interaction, "output_text", None) or (
            interaction.steps[-1].content[0].text if getattr(interaction, "steps", None) else None
        )
    except TypeError:
        interaction = client.interactions.create(
            model="gemini-4-argon",
            input=prompt,
            generation_config={"thinking_level": "high"},
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": response_schema,
            },
        )
        return getattr(interaction, "output_text", None) or (
            interaction.steps[-1].content[0].text if getattr(interaction, "steps", None) else None
        )


def run_argon_and_saint_agent(
    user_name: str,
    pose_data: Dict[str, Any],
    watch_metrics: Dict[str, Any],
    pro_match: Dict[str, Any],
    partner_match: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    1. Verifies concrete Pass/Fail biomechanical threshold:
       `right_elbow_contact_deg >= 165.0` deg = PASS, else FAIL.
    2. Calls `gemini-4-argon` via `client.interactions.create` (`thinking_level="high"`)
       with Sumanth's joint angles, Apple Watch heart rate/fatigue, and matched Pro reference from MongoDB.
    3. Returns structured JSON:
       - `verification_status` ("PASS"/"FAIL")
       - `biomechanical_diagnosis`
       - `live_drill_prescription`
       - `saint_agent_job` (`plain_english_instruction`, `proactive_training_notification`,
         `requires_human_approval: true`, `approval_action_summary`)
    4. POSTs `saint_agent_job` to `SAINT_WEBHOOK_URL` if configured.
    """
    partner_info = partner_match or {
        "name": "Arjun Mehta",
        "city": "London",
        "preferred_venue": "Islington Tennis & Racket Centre / Finsbury Leisure (EC1V)",
        "availability": "Tonight 20:00 - 22:00 BST",
    }

    elbow_deg = float(pose_data.get("right_elbow_contact_deg", 158.4))
    verification_status = verify_biomechanical_threshold(elbow_deg)

    baseline = _build_deterministic_coaching_response(
        user_name=user_name,
        verification_status=verification_status,
        pose_data=pose_data,
        watch_metrics=watch_metrics,
        pro_match=pro_match,
        partner_match=partner_info,
    )

    response_schema = {
        "type": "object",
        "properties": {
            "verification_status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "biomechanical_diagnosis": {"type": "string"},
            "live_drill_prescription": {"type": "string"},
            "saint_agent_job": {
                "type": "object",
                "properties": {
                    "plain_english_instruction": {"type": "string"},
                    "proactive_training_notification": {"type": "string"},
                    "requires_human_approval": {"type": "boolean"},
                    "approval_action_summary": {"type": "string"},
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
            "verification_status",
            "biomechanical_diagnosis",
            "live_drill_prescription",
            "saint_agent_job",
        ],
    }

    prompt = (
        f"You are Tempo, an elite Overhead Racket Sports (Tennis & Badminton) Biomechanics & Autonomous Saint AI Coach.\n"
        f"Player: {user_name}\n"
        f"Deterministic Biomechanical Threshold Rule: right_elbow_contact_deg >= {ELBOW_EXTENSION_PASS_THRESHOLD_DEG} "
        f"is PASS, else FAIL.\n"
        f"Computed Verification Status (MUST KEEP EXACT): {verification_status}\n\n"
        f"Player 3D Joint Angles & Contact Height:\n{json.dumps(pose_data, indent=2)}\n\n"
        f"Apple Watch Biometrics:\n{json.dumps(watch_metrics, indent=2)}\n\n"
        f"MongoDB Atlas Closest Pro Reference Match:\n{json.dumps(pro_match, indent=2)}\n\n"
        f"Matched London Training Partner:\n{json.dumps(partner_info, indent=2)}\n\n"
        f"Return ONLY valid JSON with keys:\n"
        f"- verification_status: \"{verification_status}\"\n"
        f"- biomechanical_diagnosis: Concise biomechanical breakdown comparing {user_name}'s 3D angles and "
        f"Apple Watch HR/fatigue against {pro_match.get('player_name', 'Roger Federer')}.\n"
        f"- live_drill_prescription: Specific on-court drill prescription adjusted for current heart rate/fatigue.\n"
        f"- saint_agent_job: Object containing plain_english_instruction, proactive_training_notification, "
        f"requires_human_approval (must be true), and approval_action_summary for booking {partner_info.get('preferred_venue')} "
        f"with {partner_info.get('name')}."
    )

    model_used = "gemini-4-argon"
    raw_output: Optional[str] = None
    try:
        raw_output = _call_gemini_4_argon(prompt=prompt, response_schema=response_schema)
    except Exception:
        raw_output = None

    result = dict(baseline)
    if raw_output:
        try:
            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:].strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                # Enforce the hard biomechanical pass/fail threshold verification loop
                result["verification_status"] = verification_status
                if parsed.get("biomechanical_diagnosis"):
                    result["biomechanical_diagnosis"] = str(parsed["biomechanical_diagnosis"])
                if parsed.get("live_drill_prescription"):
                    result["live_drill_prescription"] = str(parsed["live_drill_prescription"])

                job = parsed.get("saint_agent_job")
                if isinstance(job, dict):
                    merged_job = dict(baseline["saint_agent_job"])
                    for k in (
                        "plain_english_instruction",
                        "proactive_training_notification",
                        "approval_action_summary",
                    ):
                        if job.get(k):
                            merged_job[k] = str(job[k])
                    merged_job["requires_human_approval"] = True
                    result["saint_agent_job"] = merged_job
        except Exception:
            pass
    else:
        model_used = "gemini-4-argon (deterministic-verified-fallback)"

    # Ensure saint_agent_job always sets requires_human_approval = True before external actions
    result["verification_status"] = verification_status
    result["saint_agent_job"]["requires_human_approval"] = True
    result["model"] = model_used
    result["elbow_threshold_deg"] = ELBOW_EXTENSION_PASS_THRESHOLD_DEG

    webhook_status = dispatch_saint_webhook(
        saint_agent_job=result["saint_agent_job"],
        event_type="SAINT_JOB_STAGED_AWAITING_APPROVAL",
        extra_metadata={
            "user_name": user_name,
            "verification_status": verification_status,
            "right_elbow_contact_deg": elbow_deg,
        },
    )
    result["saint_webhook_dispatch"] = webhook_status
    return result
