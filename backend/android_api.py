"""Android branch contracts backed by the existing, verified Tempo pipeline.

BackgroundTasks is process-local, not a durable job queue. Records share the
canonical Mongo database and use explicit volatile fallback when it is offline.
"""
from __future__ import annotations

import asyncio
import hashlib
import copy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import Request, APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

if __package__:
    from . import db_mongo
    from .auth import own, principal, authenticate
    from .telemetry_time import require_recent
else:
    import db_mongo
    from auth import own, principal, authenticate
    from telemetry_time import require_recent

logger = logging.getLogger(__name__)
_MEMORY: dict[str, dict[str, Any]] = {}
_LOCK = Lock()
MAX_UPLOAD_BYTES = 250 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BiometricPoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    timestamp_ms: int = Field(ge=0)
    heart_rate: float = Field(ge=20, le=250)
    cadence: int | None = Field(default=None, ge=0)
    active_energy_burned: float | None = Field(default=None, ge=0)


class SessionMetadata(BaseModel):
    session_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
    user_intent: str | None = Field(default=None, max_length=2000)
    user_id: str = Field(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")
    sport: Literal['badminton', 'tennis']
    stroke_type: Literal['overhead_clear', 'jump_smash', 'smash', 'serve', 'overhead_serve', 'overhead_smash']
    target_archetype: str | None = None
    telemetry: list[BiometricPoint] = Field(default_factory=list, max_length=10000)


class UserSchedule(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    sport: Literal['badminton', 'tennis'] = 'badminton'
    stroke_type: str = 'overhead_clear'
    days_of_week: list[Literal['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']] = Field(default_factory=lambda: ['Monday', 'Wednesday', 'Friday'])
    target_time_utc: str = Field(default='18:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    priming_lead_minutes: int = Field(default=30, ge=5, le=120)
    preferred_channel: Literal['whatsapp', 'push', 'sms'] = 'whatsapp'
    is_active: bool = True


def _put(collection: str, key: str, record: dict[str, Any]) -> None:
    snapshot = copy.deepcopy(record)
    mode = 'in_memory_fallback'
    db = db_mongo.get_db()
    if db is not None:
        try:
            db[collection].replace_one({'_id': key}, {'_id': key, **snapshot}, upsert=True)
            mode = 'mongodb_atlas'
        except Exception:
            logger.warning('Android record write used volatile fallback', exc_info=True)
    snapshot['storage_mode'] = mode
    with _LOCK:
        _MEMORY[f'{collection}:{key}'] = snapshot


def _get(collection: str, key: str) -> dict[str, Any] | None:
    # Prefer the current process copy if an Atlas write had to fall back.
    with _LOCK:
        cached = copy.deepcopy(_MEMORY.get(f'{collection}:{key}'))
    if cached is not None:
        return cached
    db = db_mongo.get_db()
    if db is not None:
        try:
            record = db[collection].find_one({'_id': key}, {'_id': 0})
            if record is not None:
                return {**record, 'storage_mode': 'mongodb_atlas'}
        except Exception:
            logger.warning('Android record lookup failed', exc_info=True)
    return None


def _feedback(payload: dict[str, Any]) -> dict[str, Any]:
    # Do not invent the branch's overall score: no calibrated scoring model exists.
    pose = payload['pose_analysis']
    timestamp = pose.get('peak_contact_timestamp_ms')
    phases = []
    if isinstance(timestamp, int) and timestamp >= 0 and not pose.get('used_fallback', True):
        phases.append({
            'phase_name': 'Peak reach (contact proxy)', 'timestamp_ms': timestamp,
            'form_accuracy_score': None, 'joint_angles': pose.get('raw_angles', {}),
            'observation': 'Highest detected overhead reach; this is not verified racket impact.',
        })
    return {
        'kinetic_phases': phases,
        'model_version': payload['coaching_model'],
        'matched_archetype': payload['pro_comparison']['matched_pro'] if payload['pro_comparison'].get('validation_status') == 'validated' else None,
        'reference_status': payload['pro_comparison'].get('validation_status', 'unvalidated'),
        'coaching_status': payload.get('coaching_status', 'unknown'),
        'analysis_limitations': payload.get('analysis_limitations', []),
        'primary_flaw': payload['biomechanical_diagnosis'],
        'concise_audio_cue': 'Maintain comfortable overhead reach.',
        'coach_voice_note_script': payload['biomechanical_diagnosis'],
        'verification_status': payload['verification_status'],
        'pose_analysis': payload['pose_analysis'],
        'demo_mode': payload['demo_mode'],
    }


def create_android_router(analyze: Callable[..., Any], broadcast: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix='/api/v1', tags=['android-compatibility'])
    # Single-worker admission lock: retrying an upload must not run analysis twice.
    admission = asyncio.Lock()

    async def process(session_id: str, path: str, filename: str, metadata: SessionMetadata, request: Request) -> None:
        record = await run_in_threadpool(_get, 'android_sessions', session_id)
        if record is None:
            Path(path).unlink(missing_ok=True)
            return
        record.update(status='ANALYZING', updated_at=_now())
        await run_in_threadpool(_put, 'android_sessions', session_id, record)
        try:
            telemetry = metadata.telemetry
            heart_rate = sum(p.heart_rate for p in telemetry) / len(telemetry) if telemetry else None
            energies = [p.active_energy_burned for p in telemetry if p.active_energy_burned is not None]
            with open(path, 'rb') as stream:
                payload = await analyze(
                    request=request,
                    sampled_at=datetime.fromtimestamp(max(p.timestamp_ms for p in telemetry) / 1000, timezone.utc).isoformat() if telemetry else None,
                    video=UploadFile(file=stream, filename=filename), apple_watch_file=None,
                    user_name=metadata.user_id, heart_rate_bpm=heart_rate,
                    active_calories_kcal=sum(energies) if energies else None, fatigue_state=None,
                    apple_watch_payload=None, user_lon=-0.1328, user_lat=51.5248,
                )
            record.update(status='COMPLETED', gemini_feedback=_feedback(payload),
                          kinematic_vector=payload['pose_analysis']['pose_vector'],
                          pipeline_session_id=payload['session_id'],
                          apple_watch_biometrics=payload.get('apple_watch_biometrics'),
                          active_widgets=[{
                              'widget_type': 'DrillCardWidget', 'id': f'{session_id}-drill',
                              'title': 'Practice focus', 'instruction': payload['live_drill_prescription'],
                              'focus_cue': payload['verification_status'], 'target_reps': 10,
                          }], error_message=None)
        except HTTPException as exc:
            record.update(status='FAILED', error_message=json.dumps(exc.detail) if isinstance(exc.detail, dict) else str(exc.detail),
                          error_code=exc.status_code)
        except Exception:
            logger.exception('Android session processing failed: %s', session_id)
            record.update(status='FAILED', error_message='Analysis failed. Check server logs.', error_code=500)
        finally:
            Path(path).unlink(missing_ok=True)
            record['updated_at'] = _now()
            await run_in_threadpool(_put, 'android_sessions', session_id, record)
            broadcast('ANDROID_SESSION_UPDATED', {'session_id': session_id, 'user_name': metadata.user_id, 'status': record['status']})

    @router.post('/sessions/ingest', status_code=202)
    async def ingest(request: Request, background_tasks: BackgroundTasks, metadata: str = Form(...), video: UploadFile = File(...)) -> dict[str, Any]:
        try:
            parsed = SessionMetadata.model_validate_json(metadata)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
        own(request, parsed.user_id)
        for point in parsed.telemetry:
            try:
                require_recent(datetime.fromtimestamp(point.timestamp_ms / 1000, timezone.utc).isoformat())
            except (ValueError, OverflowError, OSError) as exc:
                raise HTTPException(status_code=422, detail='Upload telemetry must contain recent sensor sample timestamps') from exc
        suffix = Path(video.filename or '').suffix.lower()
        if suffix not in {'.mp4', '.mov', '.mkv', '.webm'}:
            raise HTTPException(status_code=415, detail='Upload an MP4, MOV, MKV, or WebM video')
        path = None
        try:
            size = 0
            video_digest = hashlib.sha256()
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as target:
                path = target.name
                while chunk := await video.read(1024 * 1024):
                    size += len(chunk)
                    video_digest.update(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail='Video exceeds the 250 MB upload limit')
                    await run_in_threadpool(target.write, chunk)
            if not size:
                raise HTTPException(status_code=422, detail='Video is empty')
            session_id = parsed.session_id or str(uuid4())
            fingerprint = hashlib.sha256((parsed.model_dump_json() + video_digest.hexdigest()).encode()).hexdigest()
            record = {'session_id': session_id, 'user_id': parsed.user_id,
                      'sport': parsed.sport, 'stroke_type': parsed.stroke_type,
                      'target_archetype': parsed.target_archetype, 'user_intent': parsed.user_intent,
                      'request_fingerprint': fingerprint, 'status': 'PENDING',
                      'telemetry_count': len(parsed.telemetry), 'created_at': _now(), 'updated_at': _now(),
                      'gemini_feedback': None, 'active_widgets': [], 'error_message': None,
                      'telemetry': [p.model_dump() for p in parsed.telemetry]}
            async with admission:
                existing = await run_in_threadpool(_get, 'android_sessions', session_id)
                if existing is not None:
                    if existing.get('request_fingerprint') != fingerprint:
                        raise HTTPException(status_code=409, detail='Session ID already belongs to a different upload')
                    Path(path).unlink(missing_ok=True)
                    return {'session_id': session_id, 'status': existing['status'],
                            'estimated_analysis_time_sec': 8, 'message': 'Existing upload; analysis was not duplicated.'}
                await run_in_threadpool(_put, 'android_sessions', session_id, record)
                background_tasks.add_task(process, session_id, path, video.filename or f'practice{suffix}', parsed, request)
            return {'session_id': session_id, 'status': 'PENDING', 'estimated_analysis_time_sec': 8,
                    'message': 'Accepted. Poll the session endpoint for analysis status.'}
        except BaseException:
            if path:
                Path(path).unlink(missing_ok=True)
            raise

    @router.get('/sessions/{session_id}')
    async def get_session(request: Request, session_id: str) -> dict[str, Any]:
        record = await run_in_threadpool(_get, 'android_sessions', session_id)
        if record is None:
            raise HTTPException(status_code=404, detail='Unknown session')
        own(request, record['user_id'])
        # Raw telemetry remains stored server-side; Android consumes the summary and feedback.
        return {k: v for k, v in record.items() if k not in {'telemetry', 'request_fingerprint'}}

    @router.get('/cadence/schedule/{user_id}')
    async def get_schedule(request: Request, user_id: str) -> dict[str, Any]:
        own(request, user_id)
        saved = await run_in_threadpool(_get, 'user_schedules', user_id)
        return saved or UserSchedule(user_id=user_id).model_dump()

    @router.post('/cadence/schedule')
    async def update_schedule(request: Request, schedule: UserSchedule) -> dict[str, Any]:
        own(request, schedule.user_id)
        await run_in_threadpool(_put, 'user_schedules', schedule.user_id, schedule.model_dump())
        return await run_in_threadpool(_get, 'user_schedules', schedule.user_id)

    @router.websocket('/live/stream')
    async def live(websocket: WebSocket) -> None:
        try:
            identity = authenticate(websocket.headers, websocket.cookies)
        except HTTPException:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            while True:
                packet = await websocket.receive_json()
                try:
                    authenticate(websocket.headers, websocket.cookies)
                except HTTPException:
                    await websocket.close(code=4401)
                    return
                if not isinstance(packet, dict):
                    await websocket.send_json({'error': 'Expected a telemetry object'})
                    continue
                try:
                    # The branch's keyframe packets have no timestamp field requirement.
                    point = BiometricPoint.model_validate({'timestamp_ms': 0, **packet})
                except (ValidationError, TypeError):
                    await websocket.send_json({'error': 'A valid heart_rate is required'})
                    continue
                await websocket.send_json({
                    'cue': 'Pause and recover if you feel tired.' if point.heart_rate >= 170 else 'Maintain comfortable overhead reach.',
                    'timestamp_ms': int(datetime.now(timezone.utc).timestamp() * 1000),
                    'source': 'heart_rate_rule_only', 'vision_analyzed': False,
                })
        except WebSocketDisconnect:
            return

    return router
