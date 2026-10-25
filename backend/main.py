"""
main.py - FastAPI Ingestion, Real-Time Watch Companion & MongoDB Atlas Analytics API (Sumanth/Yue/Taha/Kong)
Endpoints:
- GET /health: Health check + MongoDB Atlas status & enabled features.
- POST /pipeline/analyze-badminton (and /pipeline/analyze-stroke): Accepts UploadFile video + Apple Watch form fields
  or live paired Apple Watch biometrics, runs `etl_pose -> db_mongo -> agent_argon_saint`, saves the session to MongoDB,
  and returns unified JSON for the Android Jetpack Compose frontend.
- POST /pipeline/approve-saint-action: Human-in-the-loop endpoint for Sumanth to approve staged Saint court booking.
- POST /pipeline/pair-watch: Generates a 6-character pairing code (`TMPO-88`) and Companion URL for the Android app.
- POST /pipeline/etl-apple-watch: Ingests Apple Watch biometrics into MongoDB Time-Series (`watch_telemetry_ts`)
  and broadcasts to connected Android SSE clients.
- GET /pipeline/watch-timeseries/{user_name}: MongoDB Time-Series `$setWindowFields` rolling HR & Fatigue window.
- GET /pipeline/analytics/{user_name}: MongoDB `$facet` + `$bucket` longitudinal Fatigue-vs-Elbow-Collapse analytics.
- GET /pipeline/live-stream: Server-Sent Events (SSE) stream backed by MongoDB Change Streams / live telemetry push
  for the Android Jetpack Compose app.
- GET /watch-companion: Mobile/Watch web bridge to push real Apple Watch biometrics into MongoDB & Android app.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import tempfile
from html import escape
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

try:
    # Verify HTTPS (ElevenLabs, Gemini) against the OS certificate store, so laptops whose antivirus
    # or proxy intercepts TLS still connect.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

if __package__:
    from .auth import install_auth, own, principal, event_visible, authenticate
    from .telemetry_time import require_recent
    from .agent_argon_saint import dispatch_saint_webhook, run_argon_and_saint_agent
    from . import saint_events
    from .argon_analysis import run_biomechanical_analysis
    from . import sports_config, llm_config, user_auth, coach_converse, voice_tts
    from .api.v1 import onboarding as onboarding_api
    from .api.v1 import omnichannel as omnichannel_api
    from .db_mongo import (
        check_mongo_health,
        create_watch_pairing_session,
        find_closest_pro_pose,
        find_training_partner,
        get_fatigue_biomechanics_analytics,
        get_latest_watch_telemetry,
        watch_pairing_owner,
        get_watch_timeseries_window,
        save_analysis_session,
        save_live_watch_telemetry,
        seed_reference_data,
        update_saint_approval,
        get_analysis_session,
        claim_saint_action,
        start_athlete_memory_watcher,
        stop_athlete_memory_watcher,
        get_athlete_memory,
    )
    from .etl_pose import extract_pose_from_video, get_pose_runtime_status, parse_apple_watch_metrics as _parse_watch_metrics
    from .android_api import create_android_router
    from . import kinematics_engine
else:
    from auth import install_auth, own, principal, event_visible, authenticate
    from telemetry_time import require_recent
    from agent_argon_saint import dispatch_saint_webhook, run_argon_and_saint_agent
    import saint_events
    from argon_analysis import run_biomechanical_analysis
    import sports_config, llm_config, user_auth, coach_converse, voice_tts
    from api.v1 import onboarding as onboarding_api
    from api.v1 import omnichannel as omnichannel_api
    from db_mongo import (
        check_mongo_health,
        create_watch_pairing_session,
        find_closest_pro_pose,
        find_training_partner,
        get_fatigue_biomechanics_analytics,
        get_latest_watch_telemetry,
        watch_pairing_owner,
        get_watch_timeseries_window,
        save_analysis_session,
        save_live_watch_telemetry,
        seed_reference_data,
        update_saint_approval,
        get_analysis_session,
        claim_saint_action,
        start_athlete_memory_watcher,
        stop_athlete_memory_watcher,
        get_athlete_memory,
    )
    from etl_pose import extract_pose_from_video, get_pose_runtime_status, parse_apple_watch_metrics as _parse_watch_metrics
    from android_api import create_android_router
    import kinematics_engine


def parse_apple_watch_metrics(*args, **kwargs):
    try:
        return _parse_watch_metrics(*args, **kwargs)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

# Connected Android SSE event queues for zero-latency push when Apple Watch or Saint approval updates
_SSE_SUBSCRIBERS: List[asyncio.Queue] = []


def _broadcast_sse_event(event_type: str, data: Dict[str, Any]) -> None:
    payload = {"event": event_type, "data": data}
    for q in list(_SSE_SUBSCRIBERS):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def analysis_skill(sport: str) -> tuple[str, str]:
    """Default skill for the uploaded sport; unknown sports keep the badminton overhead clear."""
    skill = sports_config.get_skill(sport, "")
    return (sports_config.get_sport(sport).id, skill.id) if skill else ("badminton", "overhead_clear")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    _log = logging.getLogger("tempo.main")
    if not llm_config.GEMINI_API_KEY:
        _log.error("GEMINI_API_KEY missing: AI features will report fallback")
    # Seed Roger Federer, Novak Djokovic, Carlos Alcaraz, Serena Williams, Sinner, Nadal,
    # London GeoJSON training partners, and MongoDB Time-Series collection on startup.
    seed_reference_data()
    if start_athlete_memory_watcher():
        _log.info("athlete_memory change stream watcher started")
    yield
    stop_athlete_memory_watcher()


app = FastAPI(
    title="Tempo - Racket Biomechanics, Apple Watch Time-Series & Autonomous Coach API",
    description=(
        "Video Input -> Pose & Watch ETL -> MongoDB Atlas ($vectorSearch + Time-Series + 2dsphere Geo + "
        "$facet Analytics) -> Gemini 4 Argon + Saint AI Agent"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

install_auth(app)
app.include_router(user_auth.router)


@app.get("/api/v1/sports")
def get_sports():
    return sports_config.get_all_sports()


@app.get("/api/v1/ai/status")
def get_ai_status(request: Request):
    principal(request)
    return llm_config.AI_STATUS


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApproveSaintActionRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID returned by /pipeline/analyze-badminton")
    user_name: str = Field(default="user_1", description="Approving player's name")
    approved: bool = Field(..., description="Whether user_1 approves the external Saint action")
    notes: Optional[str] = Field(default=None, description="Optional note from the user")
    saint_agent_job: Optional[Dict[str, Any]] = Field(default=None, description="Optional override of staged Saint job")


class PairWatchRequest(BaseModel):
    user_name: str = Field(default="user_1")
    android_device_id: str = Field(default="android_compose_app")


@app.get("/health")
def health_check(request: Request) -> Dict[str, Any]:
    """
    Health check + MongoDB Atlas status & enabled features.
    """
    if not getattr(request.state, 'identity', None) or request.state.identity['role'] != 'admin':
        return {'status': 'ready', 'service': 'tempo'}
    mongo_status = check_mongo_health()
    pose_runtime = get_pose_runtime_status()
    return {
        "status": "ok" if mongo_status.get("connected") and pose_runtime["configured"] else "degraded",
        "service": "tempo-biomechanics-backend",
        "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-4-argon"),
        "demo_mode": os.environ.get("TEMPO_DEMO_MODE", "false").lower() == "true",
        "realtime_transport": "process_local_sse",
        "healthkit_bridge": "manual_or_export_upload",
        "pose_runtime": pose_runtime,
        "mongodb": mongo_status,
    }


@app.post("/pipeline/pair-watch")
def pair_apple_watch_for_android(req: PairWatchRequest, request: Request) -> Dict[str, Any]:
    """
    Called by the Android Jetpack Compose app to initiate a zero-config Apple Watch link.
    Returns a 6-character pairing code (`TMPO-xx`) and a Companion URL (`http://<host>:8000/watch-companion?code=TMPO-xx`)
    that Sumanth can scan or tap on his iPhone/Watch to stream real biometrics through MongoDB to the Android app.
    """
    own(request, req.user_name)
    session = create_watch_pairing_session(
        user_name=req.user_name,
        android_device_id=req.android_device_id,
    )
    base_url = os.environ.get("TEMPO_PUBLIC_BASE_URL", str(request.base_url)).rstrip("/")
    companion_url = f"{base_url}/watch-companion?" + urlencode({"code": session["pairing_code"], "user": req.user_name})
    session["companion_url"] = companion_url
    session["shortcut_webhook_url"] = f"{base_url}/pipeline/etl-apple-watch"
    return session


@app.post("/pipeline/analyze-badminton")
@app.post("/pipeline/analyze-stroke")
async def analyze_badminton_pipeline(
    request: Request,
    video: Optional[UploadFile] = File(default=None),
    apple_watch_file: Optional[UploadFile] = File(default=None),
    user_name: str = Form(default="user_1"),
    heart_rate_bpm: Optional[float] = Form(default=None),
    sampled_at: Optional[str] = Form(default=None),
    active_calories_kcal: Optional[float] = Form(default=None),
    fatigue_state: Optional[str] = Form(default=None),
    apple_watch_payload: Optional[str] = Form(default=None),
    user_lon: float = Form(default=-0.1328),
    user_lat: float = Form(default=51.5248),
    sport: str = Form(default="badminton"),
) -> Dict[str, Any]:
    """
    Accepts `UploadFile` video + Apple Watch form fields (`user_name`, `heart_rate_bpm`, `active_calories_kcal`),
    an `apple_watch_file` (`.xml` / `.json` / `.zip` export), or automatically pulls the live synced Apple Watch
    biometrics from MongoDB `watch_telemetry_ts`.
    Runs `etl_pose -> db_mongo ($vectorSearch + 2dsphere $geoNear) -> agent_argon_saint`,
    saves the session to MongoDB, and returns the unified JSON for the Android Jetpack Compose frontend.
    """
    own(request, user_name)
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

        watch_raw_payload: Optional[Any] = apple_watch_payload
        if apple_watch_file is not None:
            watch_bytes = await apple_watch_file.read()
            if watch_bytes:
                watch_raw_payload = watch_bytes

        # Step 1: ETL Pose & Apple Watch Biometrics (Kong)
        # Segment reps against the athlete's own sport and skill focus (any stroke, either hand).
        athlete = await run_in_threadpool(get_athlete_memory, user_name)
        target_stroke = kinematics_engine.stroke_for_skill(athlete.get("skill_focus"))
        pose_result = await run_in_threadpool(extract_pose_from_video, temp_video_path or "",
                                              athlete.get("sport") or sport, target_stroke)
        demo_mode = os.environ.get("TEMPO_DEMO_MODE", "false").lower() == "true"
        if pose_result["status"] in {"fallback_no_video", "fallback_unreadable_video"} and not demo_mode:
            raise HTTPException(status_code=422, detail={
                "message": "Upload a readable MP4, MOV, MKV or WebM clip of your swing.",
                "pose_status": pose_result["status"],
            })
        engine_down = pose_result["status"] in {
            "pose_model_missing", "mediapipe_tasks_unavailable", "opencv_unavailable", "pose_inference_failed"}
        if pose_result["used_fallback"] and engine_down and not demo_mode:
            raise HTTPException(status_code=503, detail={
                "message": "Pose engine unavailable. Check /health and run setup_pose_model.py.",
                "pose_status": pose_result["status"],
            })
        # No reliable body in the clip (or another player dominated it): still coach, from the video alone,
        # but report no angles rather than the demo placeholders.
        pose_measured = not pose_result["used_fallback"] or demo_mode
        if not pose_measured:
            pose_result = {**pose_result, "raw_angles": {}, "pose_vector": None}
        live_cached = get_latest_watch_telemetry(user_name)
        if (
            watch_raw_payload is None
            and live_cached is not None
            and heart_rate_bpm is None
            and active_calories_kcal is None
            and fatigue_state is None
        ):
            try:
                require_recent(live_cached.get('sampled_at'))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            watch_metrics = parse_apple_watch_metrics(payload=live_cached)
            watch_metrics["source_format"] = "live_apple_watch_sync"
            watch_metrics["received_at"] = live_cached["updated_at"]
            watch_metrics["user_id"] = user_name
        else:
            now_iso = datetime.now(timezone.utc).isoformat()
            effective_hr = heart_rate_bpm if heart_rate_bpm is not None else (168.0 if demo_mode else 152.0)
            watch_metrics = parse_apple_watch_metrics(
                payload=watch_raw_payload,
                sampled_at=sampled_at or now_iso,
                heart_rate_bpm=effective_hr,
                active_calories_kcal=active_calories_kcal,
                fatigue_state=fatigue_state,
            )
            if not demo_mode and sampled_at:
                try:
                    require_recent(watch_metrics.get('sampled_at'))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            # With no watch file, payload or reading, the HR above is a placeholder: never store or coach on it.
            watch_metrics["measured"] = demo_mode or not (
                watch_raw_payload is None and heart_rate_bpm is None and active_calories_kcal is None)
            if watch_metrics["measured"]:
                save_live_watch_telemetry(user_name, watch_metrics)

        # Step 2: MongoDB Atlas $vectorSearch Pro Matching & 2dsphere Geospatial Partner Discovery (Taha)
        user_pose_vector = pose_result["pose_vector"]
        pro_match = (find_closest_pro_pose(user_pose_vector, sport=sport) if pose_measured else
                     {"player_name": None, "validation_status": "not_measured", "all_pro_matches": []})
        partner_match = find_training_partner(
            city="London",
            user_pose_vector=user_pose_vector,
            user_lon=user_lon,
            user_lat=user_lat,
        )

        # Step 3: Gemini 4 Argon Multimodal Verification & Provenance (argon_analysis.py)
        sport_id, skill_id = analysis_skill(athlete.get("sport") or sport)
        agent_output = await run_biomechanical_analysis(
            user_name=user_name,
            # The athlete's own sport and skill focus still win inside resolve_skill when set.
            sport_id=sport_id,
            skill_id=skill_id,
            pose_data=pose_result["raw_angles"],
            watch_metrics=watch_metrics,
            pro_match=pro_match,
            video_path=temp_video_path,
            partner_match=partner_match,
            pose_meta={k: pose_result.get(k) for k in (
                "status", "overhead_contact_detected", "contact_selection", "valid_pose_frames", "warnings",
                "handedness", "rep_analysis")},
        )

        # Dispatch Saint webhook if configured
        dispatch_saint_webhook(
            saint_agent_job=agent_output.get("saint_agent_job", {}),
            event_type="SAINT_AUTONOMOUS_PIPELINE_EXECUTION",
            extra_metadata={
                "user_name": user_name,
                "verification_status": agent_output.get("verification_status"),
                "overall_score": agent_output.get("overall_score"),
            },
        )

        # An Argon FAIL becomes a court proposal for Saint; a PASS after a FAIL tells Saint the fix is verified.
        try:
            verdict_event = saint_events.argon_verdict(user_name, {
                **agent_output, "right_elbow_contact_deg": pose_result["raw_angles"].get("right_elbow_contact_deg")})
            if verdict_event is not None:
                await run_in_threadpool(saint_events.push, verdict_event)
        except Exception:
            logging.getLogger("tempo.main").warning("Saint verdict event not pushed", exc_info=True)

        if os.environ.get('TEMPO_REQUIRE_LIVE_MODEL', 'false').lower() == 'true' and agent_output.get('llm_source') != 'gemini':
            raise HTTPException(503, 'Live coaching model unavailable; consult the runtime validation report')
        # Step 4: MongoDB Time-Series Window & Longitudinal Analytics Snapshot
        ts_window = get_watch_timeseries_window(user_name=user_name, limit=6)
        fatigue_analytics = get_fatigue_biomechanics_analytics(user_name=user_name)

        unified_payload: Dict[str, Any] = {
            "user_name": user_name,
            "demo_mode": demo_mode,
            "coaching_model": agent_output.get("llm_model", "gemini-4-argon"),
            "coaching_status": "live" if agent_output.get("llm_source") == "gemini" else "fallback",
            "coaching_error_type": agent_output.get("llm_error"),
            "llm_source": agent_output.get("llm_source", "gemini"),
            "llm_model": agent_output.get("llm_model", "gemini-4-argon"),
            "llm_error": agent_output.get("llm_error"),
            "video_used": agent_output.get("video_used", False),
            "video_error": agent_output.get("video_error"),
            "latency_ms": agent_output.get("latency_ms", 0),
            "overall_score": agent_output.get("overall_score", 88 if agent_output.get("verification_status") == "PASS" else 68),
            "primary_flaw": agent_output.get("primary_flaw", agent_output.get("biomechanical_diagnosis")),
            "concise_audio_cue": agent_output.get("concise_audio_cue", "Maintain comfortable overhead reach."),
            "coach_voice_note_script": agent_output.get("coach_voice_note_script", agent_output.get("biomechanical_diagnosis")),
            "analysis_limitations": ["Peak reach is a contact proxy, not detected impact", "165 degrees is a project heuristic, not a validated sports score", "Reference profiles are illustrative and unvalidated"],
            "video_filename": video_filename,
            "verification_status": agent_output["verification_status"],
            "biomechanical_diagnosis": agent_output["biomechanical_diagnosis"],
            "live_drill_prescription": agent_output["live_drill_prescription"],
            "saint_agent_job": agent_output["saint_agent_job"],
            "pose_analysis": {
                **pose_result,
                "status": pose_result["status"],
                "used_fallback": pose_result["used_fallback"],
                "frames_scanned": pose_result["frames_scanned"],
                "peak_contact_frame": pose_result["peak_contact_frame"],
                "raw_angles": pose_result["raw_angles"],
                "pose_vector": user_pose_vector,
            },
            "apple_watch_biometrics": watch_metrics,
            "watch_timeseries_window": ts_window,
            "pro_comparison": {
                "validation_status": pro_match.get("validation_status", "illustrative_unvalidated"),
                "matched_pro": pro_match.get("player_name"),
                "country": pro_match.get("country"),
                "sport": pro_match.get("sport", sport),
                "stroke_type": pro_match.get("stroke_type"),
                "pro_right_elbow_contact_deg": pro_match.get("right_elbow_contact_deg"),
                "pro_pose_vector": pro_match.get("pose_vector"),
                "similarity_score": pro_match.get("similarity_score"),
                "search_method": pro_match.get("search_method"),
                "biomechanical_notes": pro_match.get("biomechanical_notes"),
                "all_pro_matches": pro_match.get("all_pro_matches", []),
            },
            "training_partner_match": partner_match,
            "longitudinal_fatigue_analytics": fatigue_analytics,
            "saint_approval_status": "PENDING_HUMAN_APPROVAL",
            "saint_webhook_dispatch": agent_output.get("saint_webhook_dispatch", {}),
            "llm_source": agent_output.get("llm_source", "gemini" if agent_output.get("model_status") == "live" else "fallback"),
            "llm_model": agent_output.get("llm_model", agent_output.get("model", "gemini-4-argon")),
            "llm_error": agent_output.get("llm_error") or agent_output.get("model_error_type"),
            "video_used": agent_output.get("video_used", False),
            "latency_ms": agent_output.get("latency_ms", 0),
            "overall_score": agent_output.get("overall_score", 85 if agent_output.get("verification_status") == "PASS" else 65),
            "primary_flaw": agent_output.get("primary_flaw", agent_output.get("biomechanical_diagnosis")),
        }

        session_id = save_analysis_session(unified_payload)
        unified_payload["session_id"] = session_id

        _broadcast_sse_event("STROKE_ANALYSIS_COMPLETED", unified_payload)
        return unified_payload

    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except OSError:
                pass


@app.post("/pipeline/etl-apple-watch")
async def etl_apple_watch_endpoint(
    request: Request,
    apple_watch_file: Optional[UploadFile] = File(default=None),
    apple_watch_payload: Optional[str] = Form(default=None),
    user_name: Optional[str] = Form(default=None),
    pairing_code: Optional[str] = Form(default=None),
    heart_rate_bpm: Optional[float] = Form(default=None),
    sampled_at: Optional[str] = Form(default=None),
    active_calories_kcal: Optional[float] = Form(default=None),
    fatigue_state: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    """
    Dedicated Apple Watch Biometrics ETL endpoint:
    Accepts an Apple Health `export.xml`, `export.zip`, or JSON file upload (`apple_watch_file`),
    a raw JSON/XML string (`apple_watch_payload`), or direct JSON body from the iOS Shortcut /
    `/watch-companion` web bridge.
    Writes to the MongoDB Time-Series collection (`watch_telemetry_ts`) and broadcasts live to the Android app!
    """
    raw_payload: Optional[Any] = apple_watch_payload
    if apple_watch_file is not None:
        file_bytes = await apple_watch_file.read()
        if file_bytes:
            raw_payload = file_bytes
    elif "application/json" in request.headers.get("content-type", "").lower():
        try:
            raw_payload = await request.json()
        except Exception:
            pass

    metrics = parse_apple_watch_metrics(
        payload=raw_payload,
        heart_rate_bpm=heart_rate_bpm,
        active_calories_kcal=active_calories_kcal,
        fatigue_state=fatigue_state,
    )
    resolved_user = user_name or "user_1"
    resolved_code = pairing_code
    if isinstance(raw_payload, dict):
        if raw_payload.get("user_name"):
            resolved_user = str(raw_payload["user_name"])
        if raw_payload.get("pairing_code"):
            resolved_code = str(raw_payload["pairing_code"])

    try:
        resolved_user = watch_pairing_owner(resolved_code) if resolved_code else resolved_user
        own(request, resolved_user)
        if sampled_at and not metrics.get('sampled_at'):
            metrics = parse_apple_watch_metrics(payload=raw_payload, heart_rate_bpm=heart_rate_bpm,
                active_calories_kcal=active_calories_kcal, fatigue_state=fatigue_state, sampled_at=sampled_at)
        try:
            require_recent(metrics.get('sampled_at'))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        saved = save_live_watch_telemetry(resolved_user, metrics, pairing_code=resolved_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resolved_user = saved["user_name"]
    ts_window = get_watch_timeseries_window(user_name=resolved_user, limit=8)

    _broadcast_sse_event(
        "APPLE_WATCH_TELEMETRY_SYNC",
        {
            "apple_watch_biometrics": saved,
            "watch_timeseries_window": ts_window,
        },
    )

    return {
        "status": "ok",
        "synced_to_live_session": True,
        "apple_watch_biometrics": saved,
        "watch_timeseries_window": ts_window,
    }


@app.get("/pipeline/latest-apple-watch")
def get_latest_apple_watch_endpoint(request: Request, user_name: Optional[str] = None) -> Dict[str, Any]:
    """Return the most recently synced live Apple Watch biometrics + rolling Time-Series window."""
    target_user = user_name or principal(request)["user_id"]
    own(request, target_user)
    latest = get_latest_watch_telemetry(target_user)
    try:
        require_recent(latest.get('sampled_at') if latest else None)
        sample_is_fresh = True
    except ValueError:
        sample_is_fresh = False
    ts_window = get_watch_timeseries_window(user_name=target_user, limit=10)
    return {
        "status": "ok",
        "has_live_telemetry": latest is not None and sample_is_fresh,
        "sample_is_fresh": sample_is_fresh,
        "apple_watch_biometrics": latest,
        "watch_timeseries_window": ts_window,
    }


@app.get("/pipeline/watch-timeseries/{user_name}")
def watch_timeseries_endpoint(request: Request, user_name: str = "user_1", limit: int = Query(default=15, ge=1, le=1000)) -> Dict[str, Any]:
    """
    MongoDB Time-Series (`watch_telemetry_ts`) + `$setWindowFields` rolling moving-average endpoint
    for the Android Jetpack Compose real-time HR & Fatigue graph.
    """
    own(request, user_name)
    return get_watch_timeseries_window(user_name=user_name, limit=limit)


@app.get("/pipeline/analytics/{user_name}")
def player_fatigue_analytics_endpoint(request: Request, user_name: str = "user_1") -> Dict[str, Any]:
    """
    MongoDB `$facet` + `$bucket` longitudinal correlation endpoint showing how `user_1`'s
    overhead elbow extension (`right_elbow_contact_deg`) degrades across Apple Watch Heart-Rate Zones.
    """
    own(request, user_name)
    return get_fatigue_biomechanics_analytics(user_name=user_name)


@app.get("/pipeline/live-stream")
async def android_live_sse_stream(request: Request) -> StreamingResponse:
    """
    Server-Sent Events (SSE) stream for the Android Jetpack Compose app.
    Streams real-time `APPLE_WATCH_TELEMETRY_SYNC`, `STROKE_ANALYSIS_COMPLETED`,
    and `SAINT_ACTION_APPROVED` events the instant they hit MongoDB Atlas!
    """
    identity = principal(request)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _SSE_SUBSCRIBERS.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        identity = principal(request)
        try:
            latest = get_latest_watch_telemetry(identity["user_id"])
            yield f"data: {json.dumps({'event': 'CONNECTED', 'latest_watch': latest})}\n\n"
            while True:
                try:
                    identity = authenticate(request.headers, request.cookies)
                except HTTPException:
                    break
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if not event_visible(identity, msg):
                        continue
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if queue in _SSE_SUBSCRIBERS:
                _SSE_SUBSCRIBERS.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
    req_user_name = user_name or "user_1"
    req_approved = approved
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

    own(request, req_user_name)
    if not req_session_id or req_approved is None:
        raise HTTPException(status_code=422, detail="session_id and approved are required")
    if custom_job is not None:
        raise HTTPException(status_code=400, detail="Approve the saved proposal; job overrides are not supported")
    try:
        saved = get_analysis_session(req_session_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Unknown analysis session")
        if saved.get("user_name") != req_user_name:
            raise HTTPException(status_code=403, detail="Session belongs to another player")
        if not claim_saint_action(req_session_id, req_user_name):
            raise HTTPException(status_code=409, detail="Session already processed or being processed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Approval storage unavailable") from exc
    job_to_execute = dict(saved["saint_agent_job"])
    job_to_execute.update(requires_human_approval=False, approved_by=req_user_name)
    if req_approved:
        dispatch_result = await run_in_threadpool(dispatch_saint_webhook,
            saint_agent_job=job_to_execute,
            event_type="SAINT_JOB_HUMAN_APPROVED_EXECUTE",
            extra_metadata={"session_id": req_session_id, "approved_by": req_user_name,
                            "notes": req_notes or "", "idempotency_key": req_session_id},
        )
    else:
        dispatch_result = {"webhook_configured": bool(os.environ.get("SAINT_WEBHOOK_URL")),
                           "dispatched": False, "event_type": "SAINT_JOB_HUMAN_REJECTED"}
    booking_confirmation = {
        "court_booking_status": ("DISPATCHED_AWAITING_CONFIRMATION" if dispatch_result.get("dispatched")
                                 else "NOT_EXECUTED") if req_approved else "CANCELLED_BY_USER",
        "venue": job_to_execute.get("venue"), "slot": job_to_execute.get("proposed_slot"),
        "webhook_dispatch": dispatch_result,
    }

    updated_session = update_saint_approval(
        session_id=req_session_id,
        approved=req_approved,
        reviewer_name=req_user_name,
        notes=req_notes,
        dispatch_result=booking_confirmation,
    )

    response_payload = {
        "status": "approved" if req_approved else "rejected",
        "session_id": updated_session.get("session_id", req_session_id),
        "approved_by": req_user_name,
        "human_in_the_loop_verified": True,
        "saint_approval_status": updated_session.get("saint_approval_status"),
        "execution_summary": booking_confirmation,
    }
    _broadcast_sse_event("SAINT_ACTION_APPROVED" if req_approved else "SAINT_ACTION_REJECTED", response_payload)
    return response_payload


@app.get("/watch-companion", response_class=HTMLResponse)
def apple_watch_companion_web_bridge(request: Request, code: str = "TMPO-88", user: str = "user_1") -> str:
    """
    Zero-config Apple Watch / iPhone Web Companion page that links directly to the Android app
    via MongoDB Atlas Time-Series (`watch_telemetry_ts`).
    """
    own(request, user)
    try:
        own(request, watch_pairing_owner(code))
    except ValueError:
        raise HTTPException(404, 'Unknown pairing code')
    code = escape(code, quote=True)
    user = escape(user, quote=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tempo • Apple Watch -> Android Bridge</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --card: #151c28;
      --accent: #ccff00;
      --danger: #ff4d6d;
      --ok: #00f5d4;
      --text: #f8fafc;
      --muted: #94a3b8;
    }}
    * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); padding: 18px; }}
    .container {{ max-width: 460px; margin: 0 auto; }}
    .badge {{ display: inline-block; background: rgba(204,255,0,0.15); color: var(--accent); padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: 0.5px; }}
    h1 {{ font-size: 22px; margin: 10px 0 4px; }}
    p.sub {{ color: var(--muted); font-size: 13px; margin-top: 0; }}
    .card {{ background: var(--card); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 16px; margin-bottom: 14px; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
    .metric-big {{ font-size: 36px; font-weight: 800; color: var(--accent); }}
    .btn {{ width: 100%; padding: 14px; border-radius: 12px; border: none; font-weight: 700; font-size: 15px; cursor: pointer; margin-top: 8px; transition: 0.15s; }}
    .btn-primary {{ background: var(--accent); color: #0b0f17; }}
    .btn-danger {{ background: var(--danger); color: #fff; }}
    .btn-outline {{ background: transparent; color: var(--text); border: 1px solid rgba(255,255,255,0.2); }}
    input[type=range] {{ width: 100%; accent-color: var(--accent); }}
    .status {{ font-size: 12px; color: var(--ok); margin-top: 8px; min-height: 18px; }}
  </style>
</head>
<body>
  <div class="container">
    <span class="badge">PAIRED WITH ANDROID • {code}</span>
    <h1>Tempo Apple Watch Bridge</h1>
    <p class="sub">Manual telemetry simulator and Apple Health export uploader. Native HealthKit integration is required for live watch sensors. Sends data into MongoDB Time-Series (<code>watch_telemetry_ts</code>) &rarr; Android Jetpack Compose App.</p>

    <div class="card">
      <div class="row">
        <span>Player: <strong>{user}</strong></span>
        <span id="fatigueBadge" style="font-size:12px;color:#ff4d6d;font-weight:700;">HIGH FATIGUE</span>
      </div>
      <div class="row">
        <div>
          <div style="font-size:12px;color:var(--muted);">HEART RATE (BPM)</div>
          <div class="metric-big" id="hrVal">174</div>
        </div>
        <div>
          <div style="font-size:12px;color:var(--muted);">HRV SDNN (MS)</div>
          <div class="metric-big" id="hrvVal" style="color:#00f5d4;">22.5</div>
        </div>
        <div>
          <div style="font-size:12px;color:var(--muted);">ACTIVE KCAL</div>
          <div class="metric-big" id="calVal" style="color:#f8fafc;">510</div>
        </div>
      </div>

      <label style="font-size:12px;color:var(--muted);">Demo Heart Rate Input (BPM)</label>
      <input type="range" id="hrSlider" min="110" max="195" value="174" oninput="updateSliders()" />

      <label style="font-size:12px;color:var(--muted);">HRV SDNN Recovery (ms)</label>
      <input type="range" id="hrvSlider" min="15" max="75" value="22" oninput="updateSliders()" />

      <button class="btn btn-primary" onclick="pushTelemetry()">Sync Watch Beat to Android & MongoDB Now</button>
      <button class="btn btn-outline" id="streamBtn" onclick="toggleStream()">Start 2s Live Watch Stream</button>
      <div class="status" id="statusMsg">Ready to stream to MongoDB Time-Series.</div>
    </div>

    <div class="card">
      <div style="font-size:13px;font-weight:700;margin-bottom:6px;">Upload Apple Health Export (.xml / .zip / .json)</div>
      <input type="file" id="watchFile" accept=".xml,.zip,.json" style="font-size:12px;margin-bottom:8px;width:100%;" />
      <button class="btn btn-outline" onclick="uploadExportFile()">Upload HealthKit File</button>
    </div>
  </div>

  <script>
    let timer = null;
    function updateSliders() {{
      const hr = parseFloat(document.getElementById('hrSlider').value);
      const hrv = parseFloat(document.getElementById('hrvSlider').value);
      document.getElementById('hrVal').innerText = hr;
      document.getElementById('hrvVal').innerText = hrv;
      const badge = document.getElementById('fatigueBadge');
      if (hr >= 170 || hrv < 28) {{
        badge.innerText = 'HIGH FATIGUE OVERLOAD';
        badge.style.color = '#ff4d6d';
      }} else if (hr >= 150) {{
        badge.innerText = 'MODERATE LOAD';
        badge.style.color = '#fbbf24';
      }} else {{
        badge.innerText = 'OPTIMAL RECOVERY (FEDERER ZONE)';
        badge.style.color = '#00f5d4';
      }}
    }}

    async function pushTelemetry() {{
      const hr = parseFloat(document.getElementById('hrSlider').value);
      const hrv = parseFloat(document.getElementById('hrvSlider').value);
      const cal = parseFloat(document.getElementById('calVal').innerText);
      const res = await fetch('/pipeline/etl-apple-watch', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          user_name: '{user}',
          pairing_code: '{code}',
          heart_rate_bpm: hr,
          hrv_sdnn_ms: hrv,
          active_calories_kcal: cal
        }})
      }});
      const data = await res.json();
      document.getElementById('statusMsg').innerText =
        'Synced -> HR ' + data.apple_watch_biometrics.heart_rate_bpm + ' BPM | Fatigue Index ' +
        data.apple_watch_biometrics.fatigue_index + ' (' + new Date().toLocaleTimeString() + ')';
    }}

    function toggleStream() {{
      const btn = document.getElementById('streamBtn');
      if (timer) {{
        clearInterval(timer);
        timer = null;
        btn.innerText = 'Start 2s Live Watch Stream';
      }} else {{
        pushTelemetry();
        timer = setInterval(() => {{
          const slider = document.getElementById('hrSlider');
          const jitter = Math.floor(Math.random() * 5) - 2;
          slider.value = Math.min(195, Math.max(110, parseInt(slider.value) + jitter));
          updateSliders();
          pushTelemetry();
        }}, 2500);
        btn.innerText = 'Stop Live Watch Stream (Streaming...)';
      }}
    }}

    async function uploadExportFile() {{
      const fileInput = document.getElementById('watchFile');
      if (!fileInput.files.length) return;
      const fd = new FormData();
      fd.append('apple_watch_file', fileInput.files[0]);
      fd.append('user_name', '{user}');
      fd.append('pairing_code', '{code}');
      const res = await fetch('/pipeline/etl-apple-watch', {{ method: 'POST', body: fd }});
      const data = await res.json();
      document.getElementById('hrVal').innerText = data.apple_watch_biometrics.heart_rate_bpm;
      document.getElementById('hrvVal').innerText = data.apple_watch_biometrics.hrv_sdnn_ms;
      document.getElementById('calVal').innerText = data.apple_watch_biometrics.active_calories_kcal;
      document.getElementById('statusMsg').innerText = 'Uploaded HealthKit file & synced to Android!';
    }}
  </script>
</body>
</html>"""


@app.get("/dashboard", response_class=HTMLResponse)
def live_laptop_dashboard() -> str:
    """
    Live Command Center on the laptop (`http://localhost:8000/dashboard`) that listens to
    `/pipeline/live-stream` (SSE) and displays incoming Apple Watch telemetry, MongoDB Time-Series
    rolling windows, Pro Vector Search comparisons, and Saint AI approvals in real time.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tempo • Live Watch & MongoDB Atlas Command Center</title>
  <style>
    :root {
      --bg: #080c14;
      --card: #111827;
      --border: rgba(255,255,255,0.09);
      --accent: #ccff00;
      --cyan: #00f5d4;
      --danger: #ff4d6d;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { margin: 0; background: var(--bg); color: var(--text); padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .live-pill { background: rgba(0,245,212,0.12); color: var(--cyan); border: 1px solid var(--cyan); padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 20px; }
    .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.7px; }
    .big { font-size: 46px; font-weight: 800; color: var(--accent); margin: 6px 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 600; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="margin:0;font-size:26px;">Tempo • Live Apple Watch &rarr; MongoDB Atlas Monitor</h1>
      <div style="color:var(--muted);font-size:13px;margin-top:4px;">Real-time SSE + MongoDB Time-Series (<code>watch_telemetry_ts</code>) + <code>$setWindowFields</code></div>
    </div>
    <div class="live-pill" id="connStatus">● LIVE STREAM CONNECTED</div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">Latest Synced Heart Rate (BPM)</div>
      <div class="big" id="hrBpm">--</div>
      <div id="syncTime" style="font-size:12px;color:var(--muted);">Waiting for phone/watch sync...</div>
    </div>
    <div class="card">
      <div class="label">HRV SDNN (ms) &amp; Active Calories</div>
      <div class="big" style="color:var(--cyan);" id="hrvCalories">--</div>
      <div id="sourceFormat" style="font-size:12px;color:var(--muted);">Source: --</div>
    </div>
    <div class="card">
      <div class="label">Biomechanical Fatigue State</div>
      <div class="big" style="font-size:24px;color:var(--danger);margin-top:16px;" id="fatigueState">--</div>
      <div id="fatigueIdx" style="font-size:13px;color:var(--muted);margin-top:8px;">Fatigue Index: -- / 100</div>
    </div>
  </div>

  <div class="card" style="margin-top:18px;">
    <div class="label">MongoDB Time-Series (<code>watch_telemetry_ts</code>) Rolling Window (<code>$setWindowFields</code>)</div>
    <table>
      <thead>
        <tr>
          <th>Timestamp (UTC)</th>
          <th>Player</th>
          <th>Heart Rate (BPM)</th>
          <th>Rolling Avg HR (3-Sample)</th>
          <th>HRV SDNN (ms)</th>
          <th>Active kcal</th>
          <th>Fatigue Index</th>
        </tr>
      </thead>
      <tbody id="tsTable"></tbody>
    </table>
  </div>

  <script>
    function renderData(biometrics, windowData) {
      if (biometrics) {
        document.getElementById('hrBpm').innerText = biometrics.heart_rate_bpm + ' BPM';
        document.getElementById('hrvCalories').innerText =
          (biometrics.hrv_sdnn_ms || '--') + ' ms  |  ' + (biometrics.active_calories_kcal || '--') + ' kcal';
        document.getElementById('fatigueState').innerText = biometrics.fatigue_state || '--';
        document.getElementById('fatigueIdx').innerText = 'Fatigue Index: ' + (biometrics.fatigue_index || '--') + ' / 100';
        document.getElementById('sourceFormat').innerText = 'Source: ' + (biometrics.source_format || 'apple_watch');
        document.getElementById('syncTime').innerText = 'Sample taken: ' + (biometrics.sampled_at || 'unknown') + ' | Received: ' + (biometrics.updated_at || 'unknown');
      }
      if (windowData && windowData.samples) {
        const tbody = document.getElementById('tsTable');
        tbody.replaceChildren();
        windowData.samples.forEach(s => {
          const row = document.createElement('tr');
          const values = [s.timestamp, (s.metadata && s.metadata.user_name) || '',
            s.heart_rate_bpm, Number(s.rolling_avg_hr_bpm || s.heart_rate_bpm).toFixed(1),
            s.hrv_sdnn_ms, s.active_calories_kcal, s.fatigue_index];
          values.forEach(value => { const cell = document.createElement('td'); cell.textContent = String(value ?? ''); row.appendChild(cell); });
          tbody.appendChild(row);
        });
      }
    }

    async function loadInitial() {
      const r = await fetch('/pipeline/latest-apple-watch');
      const d = await r.json();
      renderData(d.apple_watch_biometrics, d.watch_timeseries_window);
    }
    loadInitial();

    const evtSource = new EventSource('/pipeline/live-stream');
    evtSource.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.event === 'APPLE_WATCH_TELEMETRY_SYNC' && msg.data) {
          renderData(msg.data.apple_watch_biometrics, msg.data.watch_timeseries_window);
        } else {
          loadInitial();
        }
      } catch (_) {}
    };
  </script>
</body>
</html>"""


@app.get("/architecture", response_class=HTMLResponse)
def pitch_deck_architecture_diagram() -> str:
    """
    Minimalist engineering architecture diagram at `http://localhost:8000/architecture`
    using solid, flat base colors (slate blue, warm amber, sage green, soft indigo, dusty coral)
    and varied geometric shapes (skewed I/O parallelograms, sharp rectangles, database cylinders,
    chamfered verification octagon, and double-bordered HITL gate).
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tempo — System Architecture</title>
  <style>
    :root {
      --canvas: #e9edf2;
      --ink: #1e293b;
      --muted: #475569;

      /* Plain / Flat Base Palette */
      --blue-zone: #dce6f7;
      --blue-fill: #eff4ff;
      --blue-cap: #bdd0f2;
      --blue-border: #2b4c7e;

      --amber-zone: #f9ebd2;
      --amber-fill: #fff8eb;
      --amber-gate: #f6d592;
      --amber-border: #8c5319;

      --green-zone: #d7ede1;
      --green-fill: #eef8f2;
      --green-cap: #addbc2;
      --green-border: #1b5e3c;

      --indigo-zone: #e3dff5;
      --indigo-fill: #f3f1fc;
      --indigo-border: #3f3478;

      --coral-fill: #faddd9;
      --coral-border: #8f2d22;
    }
    * {
      box-sizing: border-box;
      font-family: "Inter", "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body {
      margin: 0;
      background-color: var(--canvas);
      background-image:
        linear-gradient(to right, rgba(30, 41, 59, 0.05) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(30, 41, 59, 0.05) 1px, transparent 1px);
      background-size: 24px 24px;
      color: var(--ink);
      padding: 24px 32px;
      min-height: 100vh;
    }

    /* Top Title Bar */
    .header {
      background: #ffffff;
      border: 2px solid var(--ink);
      box-shadow: 4px 4px 0 var(--ink);
      padding: 14px 20px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .header h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.3px;
      color: var(--ink);
    }
    .header p {
      margin: 3px 0 0;
      font-size: 12.5px;
      color: var(--muted);
    }
    .legend {
      display: flex;
      gap: 10px;
      font-size: 11px;
      font-weight: 600;
    }
    .legend-chip {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border: 1.5px solid var(--ink);
      background: #f8fafc;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border: 1.5px solid var(--ink);
      display: inline-block;
    }

    /* 4-Stage Pipeline Grid */
    .arch-grid {
      display: grid;
      grid-template-columns: 1fr 54px 1.12fr 54px 1.32fr 54px 1.15fr;
      align-items: stretch;
    }

    .zone {
      border: 2px solid var(--ink);
      box-shadow: 4px 4px 0 var(--ink);
      display: flex;
      flex-direction: column;
    }
    .zone-blue { background: var(--blue-zone); border-color: var(--blue-border); box-shadow: 4px 4px 0 var(--blue-border); }
    .zone-amber { background: var(--amber-zone); border-color: var(--amber-border); box-shadow: 4px 4px 0 var(--amber-border); }
    .zone-green { background: var(--green-zone); border-color: var(--green-border); box-shadow: 4px 4px 0 var(--green-border); }
    .zone-indigo { background: var(--indigo-zone); border-color: var(--indigo-border); box-shadow: 4px 4px 0 var(--indigo-border); }

    .zone-banner {
      padding: 10px 14px;
      color: #ffffff;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid var(--ink);
    }
    .zone-blue .zone-banner { background: var(--blue-border); border-color: var(--blue-border); }
    .zone-amber .zone-banner { background: var(--amber-border); border-color: var(--amber-border); }
    .zone-green .zone-banner { background: var(--green-border); border-color: var(--green-border); }
    .zone-indigo .zone-banner { background: var(--indigo-border); border-color: var(--indigo-border); }

    .zone-title {
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .zone-file {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      background: rgba(255, 255, 255, 0.2);
      padding: 2px 7px;
      font-weight: 600;
    }

    .zone-body {
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 13px;
      flex: 1;
    }

    /* SHAPE 1: Skewed I/O Parallelogram (Edge Inputs) */
    .shape-io {
      background: var(--blue-fill);
      border: 2px solid var(--blue-border);
      padding: 11px 14px;
      transform: skewX(-5deg);
      box-shadow: 3px 3px 0 rgba(43, 76, 126, 0.25);
    }
    .shape-io-inner {
      transform: skewX(5deg);
    }

    /* SHAPE 2: Sharp Architectural Rectangle */
    .shape-rect {
      background: #ffffff;
      border: 2px solid var(--ink);
      padding: 11px 13px;
      box-shadow: 3px 3px 0 rgba(30, 41, 59, 0.2);
    }
    .zone-blue .shape-rect { background: var(--blue-fill); border-color: var(--blue-border); }
    .zone-amber .shape-rect { background: var(--amber-fill); border-color: var(--amber-border); }
    .zone-green .shape-rect { background: var(--green-fill); border-color: var(--green-border); }
    .zone-indigo .shape-rect { background: var(--indigo-fill); border-color: var(--indigo-border); }

    /* SHAPE 3: Database Cylinder (MongoDB Collections) */
    .shape-cylinder {
      background: var(--green-fill);
      border: 2px solid var(--green-border);
      border-radius: 50% / 13px;
      padding: 18px 13px 11px;
      position: relative;
      box-shadow: 0 3px 0 var(--green-border);
    }
    .shape-cylinder::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 16px;
      background: var(--green-cap);
      border-bottom: 2px solid var(--green-border);
      border-radius: 50% / 10px;
    }
    .shape-cylinder .node-head {
      margin-top: 4px;
    }

    /* SHAPE 4: Chamfered Octagon (Hard Verification Gate) */
    .shape-octagon {
      background: var(--amber-gate);
      border: 2px solid var(--amber-border);
      padding: 12px 14px;
      clip-path: polygon(
        11px 0, calc(100% - 11px) 0,
        100% 11px, 100% calc(100% - 11px),
        calc(100% - 11px) 100%, 11px 100%,
        0 calc(100% - 11px), 0 11px
      );
    }

    /* SHAPE 5: Hexagonal / Double-Framed Stamped Gate (Human-in-the-Loop) */
    .shape-hitl {
      background: var(--coral-fill);
      border: 3px double var(--coral-border);
      padding: 11px 13px;
      box-shadow: 3px 3px 0 rgba(143, 45, 34, 0.22);
    }

    .node-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .node-title {
      margin: 0;
      font-size: 13px;
      font-weight: 800;
      color: var(--ink);
    }
    .node-kind {
      font-size: 9.5px;
      font-weight: 700;
      text-transform: uppercase;
      padding: 1px 5px;
      background: rgba(30, 41, 59, 0.1);
      color: var(--ink);
      letter-spacing: 0.4px;
    }
    .node-desc {
      margin: 0;
      font-size: 11.5px;
      color: var(--muted);
      line-height: 1.42;
    }
    .meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-top: 7px;
    }
    .mono-pill {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 10px;
      font-weight: 600;
      padding: 2px 6px;
      background: #ffffff;
      color: var(--ink);
      border: 1px solid rgba(30, 41, 59, 0.35);
    }

    /* Connectors between columns */
    .connector {
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 8px;
    }
    .conn-pill {
      writing-mode: vertical-rl;
      text-orientation: mixed;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 10px;
      font-weight: 700;
      background: #ffffff;
      border: 1.5px solid var(--ink);
      padding: 7px 4px;
      color: var(--ink);
      letter-spacing: 0.5px;
    }

    /* Bottom Closed-Loop Swimlane */
    .swimlane {
      margin-top: 18px;
      background: #ffffff;
      border: 2px solid var(--ink);
      box-shadow: 4px 4px 0 var(--ink);
      padding: 12px 18px;
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: 18px;
    }
    .swim-title {
      font-size: 11.5px;
      font-weight: 800;
      text-transform: uppercase;
      background: var(--ink);
      color: #ffffff;
      padding: 5px 10px;
      letter-spacing: 0.5px;
    }
    .swim-steps {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 11.5px;
      font-weight: 600;
    }
    .swim-step {
      padding: 4px 10px;
      border: 1.5px solid var(--ink);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>TEMPO — MULTIMODAL RACKET BIOMECHANICS &amp; AUTONOMOUS COACH</h1>
      <p>System Blueprint: Edge Video &amp; Apple Watch HealthKit &rarr; FastAPI Pose/Biometric ETL &rarr; MongoDB Atlas (5 Engines) &rarr; Gemini 4 Argon &amp; Saint AI</p>
    </div>
    <div class="legend">
      <div class="legend-chip"><span class="swatch" style="background:var(--blue-fill);border-color:var(--blue-border);transform:skewX(-12deg);"></span>I/O Stream</div>
      <div class="legend-chip"><span class="swatch" style="background:var(--amber-gate);border-color:var(--amber-border);"></span>Rule Gate</div>
      <div class="legend-chip"><span class="swatch" style="background:var(--green-cap);border-color:var(--green-border);border-radius:50%;"></span>MongoDB Store</div>
      <div class="legend-chip"><span class="swatch" style="background:var(--indigo-fill);border-color:var(--indigo-border);"></span>AI / Compute</div>
      <div class="legend-chip"><span class="swatch" style="background:var(--coral-fill);border-color:var(--coral-border);"></span>HITL Approval</div>
    </div>
  </div>

  <div class="arch-grid">
    <!-- STAGE 1: EDGE CAPTURE & ANDROID CLIENT -->
    <div class="zone zone-blue">
      <div class="zone-banner">
        <span class="zone-title">01. Edge &amp; Wearable Capture</span>
        <span class="zone-file">user_1</span>
      </div>
      <div class="zone-body">
        <div class="shape-io">
          <div class="shape-io-inner">
            <div class="node-head">
              <h3 class="node-title">Apple Watch HealthKit</h3>
              <span class="node-kind">Sensor Input</span>
            </div>
            <p class="node-desc">Streams live Heart Rate (BPM), HRV SDNN (ms), and Active Energy (kcal) via iOS Shortcut or Health <code>export.zip</code>.</p>
            <div class="meta-row">
              <span class="mono-pill">POST /pipeline/etl-apple-watch</span>
              <span class="mono-pill">1Hz Biometrics</span>
            </div>
          </div>
        </div>

        <div class="shape-io">
          <div class="shape-io-inner">
            <div class="node-head">
              <h3 class="node-title">Stroke Video + London GPS</h3>
              <span class="node-kind">Camera Input</span>
            </div>
            <p class="node-desc">Smartphone <code>.mp4</code> overhead serve/smash clip paired with court GPS coordinates (<code>user_lon, user_lat</code>).</p>
            <div class="meta-row">
              <span class="mono-pill">POST /pipeline/analyze-stroke</span>
              <span class="mono-pill">Multipart .mp4</span>
            </div>
          </div>
        </div>

        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">Android Jetpack Compose App</h3>
            <span class="node-kind">Mobile UI</span>
          </div>
          <p class="node-desc">Kotlin Retrofit client + OkHttp Server-Sent Events (SSE) listener rendering live watch fatigue rings &amp; approval cards.</p>
          <div class="meta-row">
            <span class="mono-pill">TempoApiClient.kt</span>
            <span class="mono-pill">GET /pipeline/live-stream</span>
          </div>
        </div>
      </div>
    </div>

    <div class="connector">
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
      <span class="conn-pill">MULTIPART + JSON</span>
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
    </div>

    <!-- STAGE 2: FASTAPI + MULTIMODAL ETL -->
    <div class="zone zone-amber">
      <div class="zone-banner">
        <span class="zone-title">02. FastAPI &amp; Multimodal ETL</span>
        <span class="zone-file">etl_pose.py</span>
      </div>
      <div class="zone-body">
        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">OpenCV + MediaPipe 3D Pose</h3>
            <span class="node-kind">Vision ETL</span>
          </div>
          <p class="node-desc">Scans frames to isolate peak overhead contact (<code>min RIGHT_WRIST.y</code>) and computes 5 3D joint angles + normalized reach height.</p>
          <div class="meta-row">
            <span class="mono-pill">[elbow, shoulder, trunk, knee, l_arm, height]</span>
          </div>
        </div>

        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">Biometric Load Normalizer</h3>
            <span class="node-kind">Watch ETL</span>
          </div>
          <p class="node-desc">Parses HealthKit XML/ZIP/JSON into a <code>[0–100]</code> Fatigue Index and classifies cardiovascular load state.</p>
          <div class="meta-row">
            <span class="mono-pill">HIGH_FATIGUE_AEROBIC_OVERLOAD</span>
          </div>
        </div>

        <div class="shape-octagon">
          <div class="node-head">
            <h3 class="node-title">Biomechanical Verification Gate</h3>
            <span class="node-kind" style="background:#8c5319;color:#fff;">Pass / Fail Loop</span>
          </div>
          <p class="node-desc" style="color:#3b2106;font-weight:500;">Deterministic threshold check executed prior to Gemini 4 Argon reasoning:</p>
          <div class="meta-row">
            <span class="mono-pill" style="border-color:#8c5319;font-weight:800;">right_elbow_contact_deg &gt;= 165.0° &rarr; PASS | FAIL</span>
          </div>
        </div>
      </div>
    </div>

    <div class="connector">
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
      <span class="conn-pill">6D VECTOR + 1HZ TS</span>
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
    </div>

    <!-- STAGE 3: MONGODB ATLAS -->
    <div class="zone zone-green">
      <div class="zone-banner">
        <span class="zone-title">03. MongoDB Atlas Data Layer</span>
        <span class="zone-file">db_mongo.py</span>
      </div>
      <div class="zone-body">
        <div class="shape-cylinder">
          <div class="node-head">
            <h3 class="node-title">strokes • Atlas $vectorSearch</h3>
            <span class="node-kind">6D Cosine Index</span>
          </div>
          <p class="node-desc">Matches <code>user_1</code> against Tennis GOAT benchmarks: <strong>Roger Federer (176.5°)</strong>, <strong>Serena (175.5°)</strong>, <strong>Djokovic (174.0°)</strong>, <strong>Alcaraz</strong>, <strong>Sinner</strong>, <strong>Nadal</strong>.</p>
          <div class="meta-row">
            <span class="mono-pill">index: pose_vector_index</span>
            <span class="mono-pill">numDimensions: 6</span>
          </div>
        </div>

        <div class="shape-cylinder">
          <div class="node-head">
            <h3 class="node-title">watch_telemetry_ts • Time-Series</h3>
            <span class="node-kind">Time-Series DB</span>
          </div>
          <p class="node-desc">Stores 1Hz Apple Watch samples and runs <code>$setWindowFields</code> for 3-sample moving-average Heart Rate &amp; Fatigue.</p>
          <div class="meta-row">
            <span class="mono-pill">timeField: "timestamp"</span>
            <span class="mono-pill">$setWindowFields</span>
          </div>
        </div>

        <div class="shape-cylinder">
          <div class="node-head">
            <h3 class="node-title">players • 2dsphere $geoNear</h3>
            <span class="node-kind">Geospatial + Vector</span>
          </div>
          <p class="node-desc">Ranks London partners (UCL, Finsbury, Regent's Park, Roehampton) by 75% vector compatibility + 25% proximity (km).</p>
          <div class="meta-row">
            <span class="mono-pill">location_2dsphere_idx</span>
            <span class="mono-pill">GeoJSON Point</span>
          </div>
        </div>

        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">Longitudinal $facet + $bucket</h3>
            <span class="node-kind">Aggregation</span>
          </div>
          <p class="node-desc">Correlates HR Zones (&lt;145, 145–165, &gt;165 BPM) against <strong>-18.4° fatigue-induced elbow angle collapse</strong>.</p>
          <div class="meta-row">
            <span class="mono-pill">GET /pipeline/analytics/user_1</span>
          </div>
        </div>
      </div>
    </div>

    <div class="connector">
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
      <span class="conn-pill">PRO + GEO CONTEXT</span>
      <svg width="36" height="24" viewBox="0 0 36 24"><path d="M2 12h28M24 5l8 7-8 7" stroke="#1e293b" stroke-width="2.5" fill="none"/></svg>
    </div>

    <!-- STAGE 4: GEMINI 4 ARGON + SAINT AI -->
    <div class="zone zone-indigo">
      <div class="zone-banner">
        <span class="zone-title">04. Reasoning &amp; Saint AI Agent</span>
        <span class="zone-file">agent_argon_saint.py</span>
      </div>
      <div class="zone-body">
        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">Google Gemini 4 Argon</h3>
            <span class="node-kind">Interactions API</span>
          </div>
          <p class="node-desc">Synthesizes 3D joint angles, Apple Watch HRV/HR fatigue, and Federer/Djokovic benchmark into a diagnosis &amp; live drill prescription.</p>
          <div class="meta-row">
            <span class="mono-pill">model: "gemini-4-argon"</span>
            <span class="mono-pill">thinking_level: "high"</span>
          </div>
        </div>

        <div class="shape-rect">
          <div class="node-head">
            <h3 class="node-title">Saint AI Autonomous Coach</h3>
            <span class="node-kind">Agent Job</span>
          </div>
          <p class="node-desc">Builds proactive training notification, stages Court 3 booking (Finsbury / UCL), and prepares London partner invite for <code>user_1</code>.</p>
          <div class="meta-row">
            <span class="mono-pill">saint_agent_job</span>
            <span class="mono-pill">requires_human_approval: true</span>
          </div>
        </div>

        <div class="shape-hitl">
          <div class="node-head">
            <h3 class="node-title" style="color:var(--coral-border);">Human-in-the-Loop Approval Gate</h3>
            <span class="node-kind" style="background:var(--coral-border);color:#fff;">Safety Gate</span>
          </div>
          <p class="node-desc" style="color:#4a1610;">Blocks external court booking &amp; webhook dispatch until <code>user_1</code> explicitly approves on the Android app.</p>
          <div class="meta-row">
            <span class="mono-pill" style="border-color:var(--coral-border);color:var(--coral-border);font-weight:700;">POST /pipeline/approve-saint-action</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="swimlane">
    <span class="swim-title">Real-Time Closed Loop</span>
    <div class="swim-steps">
      <span class="swim-step" style="background:var(--blue-fill);">1. Watch / Video Ingest</span>
      <span>&rarr;</span>
      <span class="swim-step" style="background:var(--amber-fill);">2. 165.0° Elbow Gate</span>
      <span>&rarr;</span>
      <span class="swim-step" style="background:var(--green-fill);">3. Atlas $vectorSearch + $geoNear</span>
      <span>&rarr;</span>
      <span class="swim-step" style="background:var(--indigo-fill);">4. Gemini 4 Argon JSON</span>
      <span>&rarr;</span>
      <span class="swim-step" style="background:var(--coral-fill);">5. SSE Push &amp; HITL Court Booking</span>
    </div>
    <span style="font-family:ui-monospace,monospace;font-size:11px;color:var(--muted);font-weight:700;">tempo.ecp5gee.mongodb.net</span>
  </div>
</body>
</html>"""


app.include_router(create_android_router(analyze_badminton_pipeline, _broadcast_sse_event))
if __package__:
    from .saint_commands import router as saint_command_router
else:
    from saint_commands import router as saint_command_router
app.include_router(saint_command_router)
app.include_router(saint_events.router)

# Shared-memory onboarding assessment + home feed (replaces app.api.v1.onboarding on the same path).
app.include_router(onboarding_api.router)
# WhatsApp (Saint/Twilio/Meta) + Gemini adapters and Saint proactive cadence.
app.include_router(omnichannel_api.router)

# Unified omnichannel Coach Thea.
app.include_router(coach_converse.router)
# Coach Thea's ElevenLabs voice (falls back to on-device TTS in the app without a key).
app.include_router(voice_tts.router)

try:
    from app.api.v1.sdui import router as sdui_router
    app.include_router(sdui_router, prefix="/api/v1")
except Exception as _e:
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
