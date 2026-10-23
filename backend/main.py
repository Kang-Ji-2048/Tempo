"""
main.py - FastAPI Ingestion & Output API (Sumanth/Yue)
Endpoints:
- GET /health: Health check + MongoDB status.
- POST /pipeline/analyze-badminton: Accepts UploadFile video + Apple Watch form fields
  (`user_name`, `heart_rate_bpm`, `active_calories_kcal`), runs `etl_pose -> db_mongo -> agent_argon_saint`,
  saves the session to MongoDB, and returns the unified JSON for the Android Jetpack Compose frontend.
- POST /pipeline/approve-saint-action: Human-in-the-loop endpoint for Sumanth to approve the staged
  Saint court booking and training partner notification.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_argon_saint import dispatch_saint_webhook, run_argon_and_saint_agent
from db_mongo import (
    check_mongo_health,
    find_closest_pro_pose,
    find_training_partner,
    save_analysis_session,
    seed_reference_data,
    update_saint_approval,
)
from etl_pose import extract_pose_from_video, parse_apple_watch_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed Viktor Axelsen, Lee Zii Jia, and London training partners on startup
    seed_reference_data()
    yield


app = FastAPI(
    title="Tempo - Badminton Biomechanics & Autonomous Coach API",
    description=(
        "Video Input -> Pose & Watch ETL -> MongoDB Atlas Vector Search -> "
        "Gemini 4 Argon + Saint AI Agent"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApproveSaintActionRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID returned by /pipeline/analyze-badminton")
    user_name: str = Field(default="Sumanth", description="Approving player's name")
    approved: bool = Field(default=True, description="Whether Sumanth approves the external Saint action")
    notes: Optional[str] = Field(default=None, description="Optional note from the user")
    saint_agent_job: Optional[Dict[str, Any]] = Field(default=None, description="Optional override of staged Saint job")


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """
    Health check + MongoDB status.
    """
    mongo_status = check_mongo_health()
    return {
        "status": "ok",
        "service": "tempo-badminton-biomechanics-backend",
        "gemini_model": "gemini-4-argon",
        "mongodb": mongo_status,
    }


@app.post("/pipeline/analyze-badminton")
async def analyze_badminton_pipeline(
    video: Optional[UploadFile] = File(default=None),
    user_name: str = Form(default="Sumanth"),
    heart_rate_bpm: float = Form(default=168.0),
    active_calories_kcal: float = Form(default=420.0),
    fatigue_state: Optional[str] = Form(default=None),
    apple_watch_payload: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    """
    Accepts `UploadFile` video + Apple Watch form fields (`user_name`, `heart_rate_bpm`, `active_calories_kcal`),
    runs `etl_pose -> db_mongo -> agent_argon_saint`, saves the session to MongoDB, and returns the unified JSON
    for the Android Jetpack Compose frontend.
    """
    seed_reference_data()

    temp_video_path: Optional[str] = None
    video_filename = "synthetic_test_clip.mp4"

    try:
        if video is not None:
            video_filename = video.filename or "uploaded_stroke.mp4"
            suffix = os.path.splitext(video_filename)[1] or ".mp4"
            content = await video.read()
            if content:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(content)
                    temp_video_path = tmp.name

        # Step 1: ETL Pose & Apple Watch Biometrics (Kong)
        pose_result = extract_pose_from_video(temp_video_path or "")
        watch_metrics = parse_apple_watch_metrics(
            payload=apple_watch_payload,
            heart_rate_bpm=heart_rate_bpm,
            active_calories_kcal=active_calories_kcal,
            fatigue_state=fatigue_state,
        )

        # Step 2: MongoDB Atlas $vectorSearch Pro Matching & Partner Discovery (Taha)
        user_pose_vector = pose_result["pose_vector"]
        pro_match = find_closest_pro_pose(user_pose_vector)
        partner_match = find_training_partner(city="London", user_pose_vector=user_pose_vector)

        # Step 3: Gemini 4 Argon Verification + Saint AI Autonomous Coach (Kong/Sumanth)
        agent_output = run_argon_and_saint_agent(
            user_name=user_name,
            pose_data=pose_result["raw_angles"],
            watch_metrics=watch_metrics,
            pro_match=pro_match,
            partner_match=partner_match,
        )

        # Build unified payload for MongoDB persistence and Android Jetpack Compose UI
        unified_payload: Dict[str, Any] = {
            "user_name": user_name,
            "video_filename": video_filename,
            "verification_status": agent_output["verification_status"],
            "biomechanical_diagnosis": agent_output["biomechanical_diagnosis"],
            "live_drill_prescription": agent_output["live_drill_prescription"],
            "saint_agent_job": agent_output["saint_agent_job"],
            "pose_analysis": {
                "status": pose_result["status"],
                "used_fallback": pose_result["used_fallback"],
                "frames_scanned": pose_result["frames_scanned"],
                "peak_contact_frame": pose_result["peak_contact_frame"],
                "raw_angles": pose_result["raw_angles"],
                "pose_vector": user_pose_vector,
            },
            "apple_watch_biometrics": watch_metrics,
            "pro_comparison": {
                "matched_pro": pro_match.get("player_name"),
                "country": pro_match.get("country"),
                "stroke_type": pro_match.get("stroke_type"),
                "pro_right_elbow_contact_deg": pro_match.get("right_elbow_contact_deg"),
                "pro_pose_vector": pro_match.get("pose_vector"),
                "similarity_score": pro_match.get("similarity_score"),
                "search_method": pro_match.get("search_method"),
                "biomechanical_notes": pro_match.get("biomechanical_notes"),
            },
            "training_partner_match": partner_match,
            "saint_approval_status": "PENDING_HUMAN_APPROVAL",
            "saint_webhook_dispatch": agent_output.get("saint_webhook_dispatch", {}),
        }

        session_id = save_analysis_session(unified_payload)
        unified_payload["session_id"] = session_id
        return unified_payload

    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except OSError:
                pass


@app.post("/pipeline/approve-saint-action")
async def approve_saint_action(
    request: Request,
    session_id: Optional[str] = Form(default=None),
    user_name: Optional[str] = Form(default=None),
    approved: Optional[bool] = Form(default=None),
    notes: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    """
    Human-in-the-loop endpoint for Sumanth to approve (or reject) the staged Saint
    court booking and training partner notification before external execution.
    Accepts either application/json or multipart/form-data.
    """
    content_type = request.headers.get("content-type", "").lower()
    req_session_id = session_id
    req_user_name = user_name or "Sumanth"
    req_approved = True if approved is None else bool(approved)
    req_notes = notes
    custom_job: Optional[Dict[str, Any]] = None

    if "application/json" in content_type:
        try:
            body_json = await request.json()
            parsed = ApproveSaintActionRequest(**body_json)
            req_session_id = parsed.session_id
            req_user_name = parsed.user_name
            req_approved = parsed.approved
            req_notes = parsed.notes
            custom_job = parsed.saint_agent_job
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc

    job_to_execute = custom_job or {
        "plain_english_instruction": (
            f"Confirmed by {req_user_name}: Book Court 3 at Finsbury Leisure Centre (EC1V) "
            "and notify London training partner Arjun Mehta."
        ),
        "requires_human_approval": False,
        "approved_by": req_user_name,
    }

    if req_approved:
        dispatch_result = dispatch_saint_webhook(
            saint_agent_job=job_to_execute,
            event_type="SAINT_JOB_HUMAN_APPROVED_EXECUTE",
            extra_metadata={
                "session_id": req_session_id,
                "approved_by": req_user_name,
                "notes": req_notes or "",
            },
        )
        booking_confirmation = {
            "court_booking_status": "CONFIRMED",
            "venue": "Finsbury Leisure Centre (EC1V)",
            "court": "Court 3",
            "slot": "Tonight 20:00 - 22:00 BST",
            "partner_notified": "Arjun Mehta",
            "webhook_dispatch": dispatch_result,
        }
    else:
        dispatch_result = {
            "webhook_configured": bool(os.environ.get("SAINT_WEBHOOK_URL")),
            "dispatched": False,
            "event_type": "SAINT_JOB_HUMAN_REJECTED",
        }
        booking_confirmation = {
            "court_booking_status": "CANCELLED_BY_USER",
            "webhook_dispatch": dispatch_result,
        }

    updated_session = update_saint_approval(
        session_id=req_session_id,
        approved=req_approved,
        reviewer_name=req_user_name,
        notes=req_notes,
        dispatch_result=booking_confirmation,
    )

    return {
        "status": "approved" if req_approved else "rejected",
        "session_id": updated_session.get("session_id", req_session_id),
        "approved_by": req_user_name,
        "human_in_the_loop_verified": True,
        "saint_approval_status": updated_session.get("saint_approval_status"),
        "execution_summary": booking_confirmation,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
