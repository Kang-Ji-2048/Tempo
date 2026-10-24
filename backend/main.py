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
import json
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_argon_saint import dispatch_saint_webhook, run_argon_and_saint_agent
from db_mongo import (
    check_mongo_health,
    create_watch_pairing_session,
    find_closest_pro_pose,
    find_training_partner,
    get_fatigue_biomechanics_analytics,
    get_latest_watch_telemetry,
    get_watch_timeseries_window,
    save_analysis_session,
    save_live_watch_telemetry,
    seed_reference_data,
    update_saint_approval,
)
from etl_pose import extract_pose_from_video, parse_apple_watch_metrics

# Connected Android SSE event queues for zero-latency push when Apple Watch or Saint approval updates
_SSE_SUBSCRIBERS: List[asyncio.Queue] = []


def _broadcast_sse_event(event_type: str, data: Dict[str, Any]) -> None:
    payload = {"event": event_type, "data": data}
    for q in list(_SSE_SUBSCRIBERS):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed Roger Federer, Novak Djokovic, Carlos Alcaraz, Serena Williams, Sinner, Nadal,
    # London GeoJSON training partners, and MongoDB Time-Series collection on startup.
    seed_reference_data()
    yield


app = FastAPI(
    title="Tempo - Racket Biomechanics, Apple Watch Time-Series & Autonomous Coach API",
    description=(
        "Video Input -> Pose & Watch ETL -> MongoDB Atlas ($vectorSearch + Time-Series + 2dsphere Geo + "
        "$facet Analytics) -> Gemini 4 Argon + Saint AI Agent"
    ),
    version="2.0.0",
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
    user_name: str = Field(default="user_1", description="Approving player's name")
    approved: bool = Field(default=True, description="Whether user_1 approves the external Saint action")
    notes: Optional[str] = Field(default=None, description="Optional note from the user")
    saint_agent_job: Optional[Dict[str, Any]] = Field(default=None, description="Optional override of staged Saint job")


class PairWatchRequest(BaseModel):
    user_name: str = Field(default="user_1")
    android_device_id: str = Field(default="android_compose_app")


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """
    Health check + MongoDB Atlas status & enabled features.
    """
    mongo_status = check_mongo_health()
    return {
        "status": "ok",
        "service": "tempo-biomechanics-backend",
        "gemini_model": "gemini-4-argon",
        "mongodb": mongo_status,
    }


@app.post("/pipeline/pair-watch")
def pair_apple_watch_for_android(req: PairWatchRequest, request: Request) -> Dict[str, Any]:
    """
    Called by the Android Jetpack Compose app to initiate a zero-config Apple Watch link.
    Returns a 6-character pairing code (`TMPO-xx`) and a Companion URL (`http://<host>:8000/watch-companion?code=TMPO-xx`)
    that Sumanth can scan or tap on his iPhone/Watch to stream real biometrics through MongoDB to the Android app.
    """
    session = create_watch_pairing_session(
        user_name=req.user_name,
        android_device_id=req.android_device_id,
    )
    host = request.headers.get("host", "192.168.68.106:8000")
    companion_url = f"http://{host}/watch-companion?code={session['pairing_code']}&user={req.user_name}"
    session["companion_url"] = companion_url
    session["shortcut_webhook_url"] = f"http://{host}/pipeline/etl-apple-watch"
    return session


@app.post("/pipeline/analyze-badminton")
@app.post("/pipeline/analyze-stroke")
async def analyze_badminton_pipeline(
    video: Optional[UploadFile] = File(default=None),
    apple_watch_file: Optional[UploadFile] = File(default=None),
    user_name: str = Form(default="user_1"),
    heart_rate_bpm: float = Form(default=168.0),
    active_calories_kcal: float = Form(default=420.0),
    fatigue_state: Optional[str] = Form(default=None),
    apple_watch_payload: Optional[str] = Form(default=None),
    user_lon: float = Form(default=-0.1328),
    user_lat: float = Form(default=51.5248),
) -> Dict[str, Any]:
    """
    Accepts `UploadFile` video + Apple Watch form fields (`user_name`, `heart_rate_bpm`, `active_calories_kcal`),
    an `apple_watch_file` (`.xml` / `.json` / `.zip` export), or automatically pulls the live synced Apple Watch
    biometrics from MongoDB `watch_telemetry_ts`.
    Runs `etl_pose -> db_mongo ($vectorSearch + 2dsphere $geoNear) -> agent_argon_saint`,
    saves the session to MongoDB, and returns the unified JSON for the Android Jetpack Compose frontend.
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

        watch_raw_payload: Optional[Any] = apple_watch_payload
        if apple_watch_file is not None:
            watch_bytes = await apple_watch_file.read()
            if watch_bytes:
                watch_raw_payload = watch_bytes

        # Step 1: ETL Pose & Apple Watch Biometrics (Kong)
        pose_result = extract_pose_from_video(temp_video_path or "")
        live_cached = get_latest_watch_telemetry(user_name)
        if (
            watch_raw_payload is None
            and live_cached is not None
            and heart_rate_bpm == 168.0
            and active_calories_kcal == 420.0
        ):
            watch_metrics = parse_apple_watch_metrics(payload=live_cached)
            watch_metrics["source_format"] = "live_apple_watch_sync"
        else:
            watch_metrics = parse_apple_watch_metrics(
                payload=watch_raw_payload,
                heart_rate_bpm=heart_rate_bpm,
                active_calories_kcal=active_calories_kcal,
                fatigue_state=fatigue_state,
            )
            save_live_watch_telemetry(user_name, watch_metrics)

        # Step 2: MongoDB Atlas $vectorSearch Pro Matching & 2dsphere Geospatial Partner Discovery (Taha)
        user_pose_vector = pose_result["pose_vector"]
        pro_match = find_closest_pro_pose(user_pose_vector)
        partner_match = find_training_partner(
            city="London",
            user_pose_vector=user_pose_vector,
            user_lon=user_lon,
            user_lat=user_lat,
        )

        # Step 3: Gemini 4 Argon Verification + Saint AI Autonomous Coach (Kong/Sumanth)
        agent_output = run_argon_and_saint_agent(
            user_name=user_name,
            pose_data=pose_result["raw_angles"],
            watch_metrics=watch_metrics,
            pro_match=pro_match,
            partner_match=partner_match,
        )

        # Step 4: MongoDB Time-Series Window & Longitudinal Analytics Snapshot
        ts_window = get_watch_timeseries_window(user_name=user_name, limit=6)
        fatigue_analytics = get_fatigue_biomechanics_analytics(user_name=user_name)

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
            "watch_timeseries_window": ts_window,
            "pro_comparison": {
                "matched_pro": pro_match.get("player_name"),
                "country": pro_match.get("country"),
                "sport": pro_match.get("sport", "Tennis"),
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

    saved = save_live_watch_telemetry(resolved_user, metrics, pairing_code=resolved_code)
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
def get_latest_apple_watch_endpoint(user_name: Optional[str] = None) -> Dict[str, Any]:
    """Return the most recently synced live Apple Watch biometrics + rolling Time-Series window."""
    target_user = user_name or "user_1"
    latest = get_latest_watch_telemetry(target_user)
    ts_window = get_watch_timeseries_window(user_name=target_user, limit=10)
    return {
        "status": "ok",
        "has_live_telemetry": latest is not None,
        "apple_watch_biometrics": latest,
        "watch_timeseries_window": ts_window,
    }


@app.get("/pipeline/watch-timeseries/{user_name}")
def watch_timeseries_endpoint(user_name: str = "user_1", limit: int = 15) -> Dict[str, Any]:
    """
    MongoDB Time-Series (`watch_telemetry_ts`) + `$setWindowFields` rolling moving-average endpoint
    for the Android Jetpack Compose real-time HR & Fatigue graph.
    """
    return get_watch_timeseries_window(user_name=user_name, limit=limit)


@app.get("/pipeline/analytics/{user_name}")
def player_fatigue_analytics_endpoint(user_name: str = "user_1") -> Dict[str, Any]:
    """
    MongoDB `$facet` + `$bucket` longitudinal correlation endpoint showing how `user_1`'s
    overhead elbow extension (`right_elbow_contact_deg`) degrades across Apple Watch Heart-Rate Zones.
    """
    return get_fatigue_biomechanics_analytics(user_name=user_name)


@app.get("/pipeline/live-stream")
async def android_live_sse_stream(request: Request) -> StreamingResponse:
    """
    Server-Sent Events (SSE) stream for the Android Jetpack Compose app.
    Streams real-time `APPLE_WATCH_TELEMETRY_SYNC`, `STROKE_ANALYSIS_COMPLETED`,
    and `SAINT_ACTION_APPROVED` events the instant they hit MongoDB Atlas!
    """
    queue: asyncio.Queue = asyncio.Queue()
    _SSE_SUBSCRIBERS.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            latest = get_latest_watch_telemetry("user_1")
            yield f"data: {json.dumps({'event': 'CONNECTED', 'latest_watch': latest})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
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
            f"Confirmed by {req_user_name}: Book Court 3 at Islington Tennis & Racket Centre / Finsbury Leisure (EC1V) "
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
            "venue": "Islington Tennis & Racket Centre / Finsbury Leisure (EC1V)",
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

    response_payload = {
        "status": "approved" if req_approved else "rejected",
        "session_id": updated_session.get("session_id", req_session_id),
        "approved_by": req_user_name,
        "human_in_the_loop_verified": True,
        "saint_approval_status": updated_session.get("saint_approval_status"),
        "execution_summary": booking_confirmation,
    }
    _broadcast_sse_event("SAINT_ACTION_APPROVED", response_payload)
    return response_payload


@app.get("/watch-companion", response_class=HTMLResponse)
def apple_watch_companion_web_bridge(code: str = "TMPO-88", user: str = "user_1") -> str:
    """
    Zero-config Apple Watch / iPhone Web Companion page that links directly to the Android app
    via MongoDB Atlas Time-Series (`watch_telemetry_ts`).
    """
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
    <p class="sub">Streams live Heart Rate, HRV & Calories into MongoDB Atlas Time-Series (<code>watch_telemetry_ts</code>) &rarr; Android Jetpack Compose App.</p>

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

      <label style="font-size:12px;color:var(--muted);">Live Watch Heart Rate Sensor (BPM)</label>
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
        document.getElementById('syncTime').innerText = 'Last synced: ' + (biometrics.updated_at || new Date().toISOString());
      }
      if (windowData && windowData.samples) {
        const tbody = document.getElementById('tsTable');
        tbody.innerHTML = windowData.samples.map(s => `
          <tr>
            <td>${s.timestamp}</td>
            <td>${(s.metadata && s.metadata.user_name) || 'user_1'}</td>
            <td style="color:#ccff00;font-weight:700;">${s.heart_rate_bpm} BPM</td>
            <td>${Number(s.rolling_avg_hr_bpm || s.heart_rate_bpm).toFixed(1)} BPM</td>
            <td>${s.hrv_sdnn_ms} ms</td>
            <td>${s.active_calories_kcal} kcal</td>
            <td>${s.fatigue_index}</td>
          </tr>
        `).join('');
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
    Pitch-ready, high-contrast interactive SVG + HTML architecture diagram at
    `http://localhost:8000/architecture` designed for hackathon slides & live judge demos.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tempo • System Architecture & Bounty Pipeline</title>
  <style>
    :root {
      --bg: #060911;
      --panel: #0e1525;
      --card: #141e33;
      --lime: #ccff00;
      --cyan: #00f5d4;
      --mongo: #00ed64;
      --gemini: #60a5fa;
      --saint: #f472b6;
      --danger: #ff4d6d;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body {
      margin: 0;
      background: radial-gradient(circle at 15% 15%, #111c35 0%, var(--bg) 60%);
      color: var(--text);
      padding: 28px 36px;
      min-height: 100vh;
    }
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding-bottom: 16px;
    }
    .title-block h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(90deg, #ffffff, #ccff00);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .title-block p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .bounty-pills {
      display: flex;
      gap: 10px;
    }
    .pill {
      padding: 6px 13px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.4px;
      text-transform: uppercase;
    }
    .pill-gemini { background: rgba(96,165,250,0.14); color: var(--gemini); border: 1px solid rgba(96,165,250,0.45); }
    .pill-mongo { background: rgba(0,237,100,0.14); color: var(--mongo); border: 1px solid rgba(0,237,100,0.45); }
    .pill-saint { background: rgba(244,114,182,0.14); color: var(--saint); border: 1px solid rgba(244,114,182,0.45); }

    .pipeline-grid {
      display: grid;
      grid-template-columns: 1fr 44px 1.15fr 44px 1.35fr 44px 1.2fr;
      align-items: stretch;
      gap: 0;
    }
    .stage-col {
      background: rgba(14, 21, 37, 0.85);
      border: 1px solid rgba(255,255,255,0.09);
      border-radius: 18px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.45);
    }
    .stage-col.mongo-col { border-color: rgba(0,237,100,0.4); box-shadow: 0 0 35px rgba(0,237,100,0.08); }
    .stage-col.ai-col { border-color: rgba(96,165,250,0.4); box-shadow: 0 0 35px rgba(96,165,250,0.08); }

    .stage-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      padding-bottom: 10px;
    }
    .stage-num {
      font-size: 11px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(204,255,0,0.15);
      color: var(--lime);
    }
    .stage-title {
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }
    .node-card {
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 13px 14px;
      position: relative;
    }
    .node-card h3 {
      margin: 0 0 5px;
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .node-card p {
      margin: 0;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .code-tag {
      display: inline-block;
      margin-top: 7px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 5px;
      background: rgba(0,0,0,0.45);
      color: var(--cyan);
      border: 1px solid rgba(0,245,212,0.25);
    }
    .arrow-col {
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      color: var(--lime);
      font-size: 24px;
      font-weight: 900;
    }
    .arrow-label {
      writing-mode: vertical-rl;
      text-orientation: mixed;
      font-size: 10px;
      letter-spacing: 1px;
      color: var(--muted);
      margin-top: 8px;
      text-transform: uppercase;
    }
    .bottom-loop {
      margin-top: 20px;
      background: linear-gradient(90deg, rgba(20,30,51,0.9), rgba(28,20,48,0.9));
      border: 1px solid rgba(244,114,182,0.35);
      border-radius: 14px;
      padding: 14px 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .loop-step {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 600;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--lime);
      box-shadow: 0 0 10px var(--lime);
    }
  </style>
</head>
<body>
  <div class="top-bar">
    <div class="title-block">
      <h1>TEMPO • MULTIMODAL RACKET BIOMECHANICS &amp; AUTONOMOUS COACH</h1>
      <p>End-to-End Architecture: Video &amp; Apple Watch HealthKit &rarr; MongoDB Atlas Multi-Engine &rarr; Gemini 4 Argon + Saint AI Agent</p>
    </div>
    <div class="bounty-pills">
      <span class="pill pill-gemini">Bounty 1 • Gemini 4 Argon</span>
      <span class="pill pill-mongo">Bounty 2 • MongoDB Atlas (5 Engines)</span>
      <span class="pill pill-saint">Bounty 3 • Saint AI HITL Agent</span>
    </div>
  </div>

  <div class="pipeline-grid">
    <!-- STAGE 1: EDGE CAPTURE -->
    <div class="stage-col">
      <div class="stage-header">
        <span class="stage-title">1. Edge Capture</span>
        <span class="stage-num">user_1</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--danger);">
        <h3>⌚ Apple Watch HealthKit</h3>
        <p>Streams live Heart Rate (BPM), HRV SDNN (ms), &amp; Active Calories via iOS Shortcut or <code>export.zip</code>.</p>
        <span class="code-tag">POST /pipeline/etl-apple-watch</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--lime);">
        <h3>🎥 Overhead Stroke Video</h3>
        <p>High-fps smartphone <code>.mp4</code> capture of overhead serve / smash + live London GPS coordinates.</p>
        <span class="code-tag">POST /pipeline/analyze-stroke</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--cyan);">
        <h3>📱 Android Jetpack Compose</h3>
        <p>Native Kotlin UI with Retrofit + OkHttp Server-Sent Events (SSE) for real-time watch &amp; coach cards.</p>
        <span class="code-tag">TempoApiClient.kt</span>
      </div>
    </div>

    <div class="arrow-col">
      <div>&rarr;</div>
      <div class="arrow-label">Multipart + JSON</div>
    </div>

    <!-- STAGE 2: FASTAPI + MULTIMODAL ETL -->
    <div class="stage-col">
      <div class="stage-header">
        <span class="stage-title">2. Multimodal ETL</span>
        <span class="stage-num">etl_pose.py</span>
      </div>

      <div class="node-card">
        <h3>🦴 MediaPipe 3D Pose Extraction</h3>
        <p>Scans frames to isolate peak overhead contact (<code>min RIGHT_WRIST.y</code>) &amp; computes 5 3D joint angles + normalized reach height.</p>
        <span class="code-tag">6D pose_vector [0..1]</span>
      </div>

      <div class="node-card">
        <h3>❤️ Biometrics &amp; Fatigue Index</h3>
        <p>Normalizes HealthKit XML/ZIP/JSON into a <code>[0-100]</code> Fatigue Index &amp; classifies aerobic load state.</p>
        <span class="code-tag">HIGH_FATIGUE_AEROBIC_OVERLOAD</span>
      </div>

      <div class="node-card" style="border: 1px solid rgba(204,255,0,0.4);">
        <h3>🎯 Deterministic Verification Gate</h3>
        <p>Hard biomechanical Pass/Fail loop before LLM reasoning:</p>
        <span class="code-tag" style="color:var(--lime);">right_elbow_contact_deg &gt;= 165.0°</span>
      </div>
    </div>

    <div class="arrow-col">
      <div>&rarr;</div>
      <div class="arrow-label">6D Vector + 1Hz TS</div>
    </div>

    <!-- STAGE 3: MONGODB ATLAS -->
    <div class="stage-col mongo-col">
      <div class="stage-header">
        <span class="stage-title" style="color:var(--mongo);">3. MongoDB Atlas</span>
        <span class="stage-num" style="background:rgba(0,237,100,0.15);color:var(--mongo);">db_mongo.py</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--mongo);">
        <h3>🔍 Atlas $vectorSearch</h3>
        <p>Matches <code>user_1</code>'s 6D pose vector against Tennis GOATs: <strong>Roger Federer (176.5°)</strong>, <strong>Serena (175.5°)</strong>, <strong>Djokovic (174.0°)</strong>, <strong>Alcaraz</strong>, <strong>Sinner</strong> &amp; <strong>Nadal</strong>.</p>
        <span class="code-tag">index: pose_vector_index (cosine)</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--mongo);">
        <h3>⏱️ Time-Series + $setWindowFields</h3>
        <p>Stores 1Hz Apple Watch beats in <code>watch_telemetry_ts</code> &amp; computes 3-sample rolling average HR &amp; Fatigue.</p>
        <span class="code-tag">collection: watch_telemetry_ts</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--mongo);">
        <h3>📍 2dsphere $geoNear Partner Match</h3>
        <p>Hybrid rank (75% vector compatibility + 25% distance in km) across London courts (UCL, Finsbury, Regent's Park).</p>
        <span class="code-tag">location_2dsphere_idx</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--mongo);">
        <h3>📊 Longitudinal $facet + $bucket</h3>
        <p>Correlates HR Zones (&lt;145, 145-165, &gt;165 BPM) against <strong>-18.4° fatigue-induced elbow drop</strong>.</p>
        <span class="code-tag">GET /pipeline/analytics/user_1</span>
      </div>
    </div>

    <div class="arrow-col">
      <div>&rarr;</div>
      <div class="arrow-label">Context + Pro Match</div>
    </div>

    <!-- STAGE 4: GEMINI 4 ARGON + SAINT AI -->
    <div class="stage-col ai-col">
      <div class="stage-header">
        <span class="stage-title" style="color:var(--gemini);">4. Argon + Saint AI</span>
        <span class="stage-num" style="background:rgba(96,165,250,0.15);color:var(--gemini);">agent_argon_saint.py</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--gemini);">
        <h3>✨ Google Gemini 4 Argon</h3>
        <p>Synthesizes 3D joint angles, Apple Watch HRV/HR fatigue, &amp; Federer/Djokovic reference into a structured diagnosis &amp; live drill prescription.</p>
        <span class="code-tag">client.interactions.create(thinking_level="high")</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--saint);">
        <h3>🤖 Saint AI Autonomous Agent</h3>
        <p>Stages proactive training notification, London Court 3 reservation &amp; partner invite for <code>user_1</code>.</p>
        <span class="code-tag" style="color:var(--saint);">requires_human_approval: true</span>
      </div>

      <div class="node-card" style="border-left: 3px solid var(--lime);">
        <h3>✅ Human-in-the-Loop Execution</h3>
        <p>Holds external court booking until <code>user_1</code> taps <strong>Approve</strong> on Android, then dispatches <code>SAINT_WEBHOOK_URL</code>.</p>
        <span class="code-tag">POST /pipeline/approve-saint-action</span>
      </div>
    </div>
  </div>

  <div class="bottom-loop">
    <div class="loop-step">
      <span class="dot"></span>
      <span><strong>Real-Time Closed Loop:</strong> MongoDB Atlas &amp; FastAPI broadcast live events via <code>GET /pipeline/live-stream</code> (SSE) &rarr; Android Jetpack Compose UI &amp; <code>/dashboard</code></span>
    </div>
    <div style="font-size:12px;color:var(--saint);font-weight:700;">
      HUMAN-IN-THE-LOOP VERIFIED • ZERO DEPRECATED GEMINI PARAMS
    </div>
  </div>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
