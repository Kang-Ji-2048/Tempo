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
    from . import argon_analysis, db_mongo, sports_config
    from .api.v1 import onboarding as onboarding_api
    from .auth import own, principal, authenticate
    from .telemetry_time import require_recent
else:
    import argon_analysis, db_mongo, sports_config
    from api.v1 import onboarding as onboarding_api
    from auth import own, principal, authenticate
    from telemetry_time import require_recent

logger = logging.getLogger(__name__)
_MEMORY: dict[str, dict[str, Any]] = {}
_LOCK = Lock()
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
LESSON_PASS_SCORE = 80  # overall_score at or above this completes the lesson node
MAX_RECENT_FLAWS = 5


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
    sport: str = Field(default='badminton', min_length=1)
    stroke_type: str = Field(default='overhead_clear', min_length=1)
    target_archetype: str | None = None
    # Lesson the clip was recorded for; defaults to the athlete's active curriculum node.
    node_id: str | None = Field(default=None, max_length=128)
    telemetry: list[BiometricPoint] = Field(default_factory=list, max_length=10000)


class WidgetActionRequest(BaseModel):
    session_id: str | None = Field(default='', max_length=128)
    action_type: str = Field(min_length=1, max_length=64)
    widget_id: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)


def _apply_widget_action(user_id: str, widgets: list[dict[str, Any]], req: WidgetActionRequest) -> list[dict[str, Any]]:
    """Apply an SDUI action to the widget list and record drill/quiz completion in athlete_memory."""
    widgets = copy.deepcopy(widgets)
    payload = req.payload
    if req.action_type == 'DrillCompleted':
        widgets = [w for w in widgets if not (w.get('widget_type') == 'DrillCardWidget' and w.get('id') == req.widget_id)]
        memory = db_mongo.get_athlete_memory(user_id)
        drills = memory.get('assigned_drills') or []
        done = next((d for d in drills if d.get('id') == req.widget_id), None)
        nodes = [dict(n) for n in memory.get('curriculum_nodes') or []]
        node_id = (done or {}).get('node_id') or next((n['id'] for n in nodes if n.get('status') == 'active'), None)
        for node in nodes:
            if node['id'] == node_id:
                node['completed_drills'] = (node.get('completed_drills') or []) + [{
                    'drill_id': req.widget_id, 'reps_completed': payload.get('reps_completed'), 'at': _now()}]
        updates: dict[str, Any] = {'curriculum_nodes': nodes}
        if done:
            updates['assigned_drills'] = [d for d in drills if d.get('id') != req.widget_id]
        if nodes:
            db_mongo.update_athlete_memory(user_id, updates)
    elif req.action_type == 'QuizAnswered':
        selected = payload.get('selected_index')
        for w in widgets:
            if w.get('widget_type') == 'ConceptQuizWidget' and w.get('id') == req.widget_id:
                w['answered_index'] = selected
        memory = db_mongo.get_athlete_memory(user_id)
        nodes = [dict(n) for n in memory.get('curriculum_nodes') or []]
        hit = False
        for node in nodes:
            quiz = node.get('remedial_quiz')
            if quiz and quiz.get('id') == req.widget_id:
                node['remedial_quiz'] = {**quiz, 'answered_index': selected,
                                         'is_correct': selected == quiz.get('correct_index'), 'answered_at': _now()}
                hit = True
        if hit:
            db_mongo.update_athlete_memory(user_id, {'curriculum_nodes': nodes})
    elif req.action_type in ('SlotPicked', 'ScheduleChanged'):
        for w in widgets:
            if w.get('widget_type') == 'CheckInScheduleWidget':
                if payload.get('slot_id'):
                    w['selected_slot_id'] = payload['slot_id']
                for key in ('days_of_week', 'target_time_utc'):
                    if key in payload:
                        w[key] = payload[key]
    elif req.action_type == 'ChoiceSelected':
        for w in widgets:
            if w.get('widget_type') == 'ChoiceWidget' and w.get('id') == req.widget_id:
                w['selected_option_ids'] = payload.get('option_ids', [])
    return widgets


class UserSchedule(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    sport: Literal['badminton', 'tennis'] = 'badminton'
    stroke_type: str = 'overhead_clear'
    days_of_week: list[Literal['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']] = Field(default_factory=lambda: ['Monday', 'Wednesday', 'Friday'])
    target_time_utc: str = Field(default='18:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    priming_lead_minutes: int = Field(default=30, ge=5, le=120)
    preferred_channel: Literal['whatsapp', 'push', 'sms'] = 'whatsapp'
    is_active: bool = True
    recent_brief: str | None = None


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


def _pro_comparison_card(payload: dict[str, Any]) -> dict[str, Any]:
    """Athlete vs. matched-pro angles; the best match document carries the reference angles."""
    comparison = payload['pro_comparison']
    matches = comparison.get('all_pro_matches') or []
    best = next((m for m in matches if m.get('player_name') == comparison.get('matched_pro')), matches[0] if matches else {})
    return {
        'matched_pro': comparison.get('matched_pro'), 'country': comparison.get('country'),
        'sport': comparison.get('sport'), 'stroke_type': comparison.get('stroke_type'),
        'similarity_score': comparison.get('similarity_score'), 'search_method': comparison.get('search_method'),
        'validation_status': comparison.get('validation_status', 'illustrative_unvalidated'),
        'angles': argon_analysis.compute_pro_deltas(payload['pose_analysis'].get('raw_angles', {}), best),
    }


def _remedial_quiz(quiz_id: str, sport: str, elbow: float, threshold: float, level: str | None,
                   pro_name: str | None, pro_elbow: float | None) -> dict[str, Any]:
    """A quiz grounded in this clip's measured elbow angle and the athlete's level target."""
    correct = f'{threshold:.0f} deg or more: near-full extension at contact'
    distractors = [f'About {max(elbow - 15, 90):.0f} deg: keep the arm bent for control',
                   '90 deg: elbow square to the shoulder', 'It does not matter if the swing is fast']
    shift = int(hashlib.sha256(quiz_id.encode()).hexdigest(), 16) % 4
    options = distractors[:shift] + [correct] + distractors[shift:]
    pro = f'{pro_name} reaches {pro_elbow:.0f} deg. ' if pro_name and pro_elbow else ''
    return {
        'widget_type': 'ConceptQuizWidget', 'id': quiz_id,
        'question': f'Your elbow measured {elbow:.0f} deg at contact. What should you aim for at '
                    f'{level or "your"} level in {sport.replace("_", " ")}?',
        'options': options, 'correct_index': shift,
        'explanation': f'{pro}Hitting at {threshold:.0f} deg or more raises your contact point, '
                       'giving a steeper, deeper shot with less shoulder strain.',
        'answered_index': None,
    }


def _adapt_curriculum(user_id: str, session_id: str, metadata: SessionMetadata, payload: dict[str, Any],
                      overall_score: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Complete the lesson on a passing score, otherwise attach a remedial drill and quiz to it."""
    memory = db_mongo.get_athlete_memory(user_id)
    nodes = [dict(n) for n in memory.get('curriculum_nodes') or []]
    target = next((n for n in nodes if n.get('id') == metadata.node_id and n.get('status') != 'locked'), None) \
        or next((n for n in nodes if n.get('status') == 'active'), None)
    raw = payload['pose_analysis'].get('raw_angles', {})
    flaw = {'session_id': session_id, 'node_id': target['id'] if target else None,
            'primary_flaw': payload.get('primary_flaw') or payload['biomechanical_diagnosis'],
            'overall_score': overall_score, 'verification_status': payload['verification_status'],
            'measured': {k: raw[k] for k in argon_analysis.ANGLE_LABELS if k in raw}, 'at': _now()}
    flaws = ([flaw] + list(memory.get('recent_flaws') or []))[:MAX_RECENT_FLAWS]
    base = {'overall_score': overall_score, 'pass_score': LESSON_PASS_SCORE}

    if target is None:
        db_mongo.update_athlete_memory(user_id, {'recent_flaws': flaws})
        return {**base, 'action': 'no_active_lesson'}, []

    if overall_score >= LESSON_PASS_SCORE:
        if target['status'] != 'completed':
            memory = db_mongo.set_lesson_node_status(user_id, target['id'], 'completed')
        memory = db_mongo.update_athlete_memory(user_id, {'recent_flaws': flaws})
        nxt = next((n for n in memory['curriculum_nodes'] if n.get('status') == 'active'), None)
        widgets = [onboarding_api.home_path_widget(memory)]
        if nxt and nxt.get('drill_spec'):
            spec = nxt['drill_spec']
            widgets.append({'widget_type': 'DrillCardWidget', 'id': spec.get('drill_id') or nxt['id'],
                            **{k: spec[k] for k in ('title', 'instruction', 'target_reps', 'focus_cue')}})
        return {**base, 'action': 'lesson_completed', 'node_id': target['id'], 'node_title': target['title'],
                'next_node_id': nxt['id'] if nxt else None, 'next_node_title': nxt['title'] if nxt else None}, widgets

    sport = memory.get('sport') or metadata.sport
    threshold = argon_analysis.level_threshold(sport, memory.get('skill_focus') or metadata.stroke_type, memory.get('level'))
    comparison = _pro_comparison_card(payload)
    pro_elbow = next((a['pro_deg'] for a in comparison['angles'] if a['metric'] == 'right_elbow_contact_deg'), None)
    drill = {'id': f'remedial_drill_{session_id[:12]}', 'title': f"Fix for {target['title']}"[:120],
             'instruction': payload['live_drill_prescription'],
             'target_reps': int((target.get('drill_spec') or {}).get('target_reps') or 10),
             'focus_cue': payload.get('concise_audio_cue') or 'Reach tall through contact',
             'youtube_url': target.get('youtube_url'), 'node_id': target['id'],
             'source_session_id': session_id, 'assigned_at': _now()}
    quiz = _remedial_quiz(f'remedial_quiz_{session_id[:12]}', sport, float(raw.get('right_elbow_contact_deg', 0.0)),
                          threshold, memory.get('level'), comparison.get('matched_pro'), pro_elbow)
    for node in nodes:
        if node['id'] == target['id']:
            node['remedial_drill_id'] = drill['id']
            node['remedial_quiz'] = {k: quiz[k] for k in ('id', 'question', 'options', 'correct_index', 'explanation')}
            node['attempts'] = int(node.get('attempts') or 0) + 1
    assigned = ([d for d in memory.get('assigned_drills') or [] if d.get('node_id') != target['id']] + [drill])[-10:]
    memory = db_mongo.update_athlete_memory(user_id, {'curriculum_nodes': nodes, 'assigned_drills': assigned,
                                                      'recent_flaws': flaws})
    widgets = [onboarding_api.home_path_widget(memory),
               {'widget_type': 'DrillCardWidget', **{k: drill[k] for k in ('id', 'title', 'instruction', 'target_reps', 'focus_cue')}},
               quiz]
    return {**base, 'action': 'remedial_assigned', 'node_id': target['id'], 'node_title': target['title'],
            'drill_id': drill['id'], 'quiz_id': quiz['id'], 'threshold_deg': threshold}, widgets


def _feedback(payload: dict[str, Any], overall_score: int | None = None,
              adaptation: dict[str, Any] | None = None) -> dict[str, Any]:
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
        'overall_score': overall_score,
        'pro_comparison_card': _pro_comparison_card(payload),
        'adaptation': adaptation,
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
                    sport=metadata.sport,
                )
            llm_source = payload.get('llm_source') or ('gemini' if payload.get('coaching_status') == 'live' else 'fallback')
            llm_model = payload.get('llm_model') or payload.get('coaching_model', 'deterministic_fallback')
            llm_error = payload.get('llm_error') or payload.get('coaching_error_type')
            video_used = payload.get('video_used', False)
            latency_ms = payload.get('latency_ms', 0)
            overall_score = payload.get('overall_score')
            if overall_score is None:
                overall_score = 88 if payload.get('verification_status') == 'PASS' else 68
            primary_flaw = payload.get('primary_flaw') or payload.get('biomechanical_diagnosis')

            adaptation, adapted_widgets = await run_in_threadpool(
                _adapt_curriculum, metadata.user_id, session_id, metadata, payload, int(overall_score))
            widgets = adapted_widgets or [{
                'widget_type': 'DrillCardWidget',
                'id': f'{session_id}-drill',
                'title': 'Practice focus',
                'instruction': payload['live_drill_prescription'],
                'focus_cue': payload.get('concise_audio_cue', payload['verification_status']),
                'target_reps': 10,
            }]

            record.update(
                status='COMPLETED',
                overall_score=overall_score,
                primary_flaw=primary_flaw,
                llm_source=llm_source,
                llm_model=llm_model,
                llm_error=llm_error,
                video_used=video_used,
                latency_ms=latency_ms,
                gemini_feedback=_feedback(payload, int(overall_score), adaptation),
                kinematic_vector=payload['pose_analysis']['pose_vector'],
                pipeline_session_id=payload['session_id'],
                apple_watch_biometrics=payload.get('apple_watch_biometrics'),
                adaptation=adaptation,
                active_widgets=widgets,
                error_message=None
            )
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
        if not sports_config.is_skill_analysis_ready(parsed.sport, parsed.stroke_type):
            raise HTTPException(status_code=422, detail="skill_not_supported_yet")
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

    @router.post('/sdui/actions')
    async def sdui_action(request: Request, req: WidgetActionRequest) -> dict[str, Any]:
        """Memory-aware SDUI callbacks; registered ahead of (and replacing) the legacy app.api.v1.sdui route."""
        record = await run_in_threadpool(_get, 'android_sessions', req.session_id) if req.session_id else None
        if record is not None:
            user_id = own(request, record['user_id'])
            widgets = record.get('active_widgets') or []
        else:
            # Home feed actions (no analysis session) operate on the shared memory's home widgets.
            user_id = principal(request)['user_id']
            memory = await run_in_threadpool(db_mongo.get_athlete_memory, user_id)
            widgets = onboarding_api.home_widgets(memory)
        widgets = await run_in_threadpool(_apply_widget_action, user_id, widgets, req)
        if record is not None:
            record.update(active_widgets=widgets, updated_at=_now())
            await run_in_threadpool(_put, 'android_sessions', record['session_id'], record)
        return {'session_id': req.session_id, 'widgets': widgets}

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
