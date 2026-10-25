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
import math
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
    from . import argon_analysis, db_mongo, kinematics_engine, saint_events, sports_config
    from .api.v1 import onboarding as onboarding_api
    from .auth import own, principal, authenticate
    from .telemetry_time import require_recent
else:
    import argon_analysis, db_mongo, kinematics_engine, saint_events, sports_config
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


# --- Live camera drill mode: on-device 33-landmark pose -> RepTracker -> per-rep coaching -------
#
# Inbound:  keypoints (alias: pose), start_drill, voice_query, complete_session, hello/refresh,
#           plus the legacy bare {heart_rate} packet.
# Outbound: session, phase_update, metrics, rep_completed, voice_reply, drill_fulfilled, cue (framing).

OVERHEAD_SKILLS = {'overhead_clear', 'jump_smash'}
LIVE_MAX_FPS = 30
LIVE_METRICS_INTERVAL_MS = 500
LIVE_FRAMING_CUE_INTERVAL_MS = 10_000
LIVE_SIDE_LOCK_FRAMES = 20        # frames used to decide which hand is hitting
LIVE_DEFAULT_TARGET_REPS = 10
LIVE_PASS_MEAN_QUALITY = 75       # finishing a set early still completes the lesson at this mean
LIVE_MIN_REPS_FOR_EARLY_PASS = 3


class LivePoseFrame(BaseModel):
    type: Literal['pose', 'keypoints']
    timestamp_ms: int = Field(ge=0)
    # 33 x [x, y, z, visibility] in normalized image coordinates.
    landmarks: list[list[float]] = Field(min_length=33, max_length=33)
    aspect: float = Field(default=0.75, gt=0.1, lt=10)  # image width / height
    heart_rate: float | None = Field(default=None, ge=20, le=250)

    model_config = ConfigDict(allow_inf_nan=False)


def _short_fix(message: str | None) -> str:
    """Spoken cue from a deviation: the actionable sentence, at most ~10 words."""
    if not message:
        return 'Good rep.'
    parts = [p.strip() for p in message.split('.') if p.strip()]
    fix = parts[-1] if len(parts) > 1 else parts[0]
    words = fix.split()
    return ' '.join(words[:10]).rstrip(',') + '.'


class LiveCoachSession:
    """One athlete's live set: drill resolution from athlete_memory, rep tracking, fulfillment."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.session_id = f'live-{uuid4().hex[:12]}'
        self.started_at = _now()
        self.explicit: dict[str, Any] = {}
        self.side: str | None = None
        self._side_buffer: list[list[list[float]]] = []
        self.tracker: kinematics_engine.MultiTracker | None = None
        self.reps: list[kinematics_engine.CompletedRep] = []
        self.heart_rate: float | None = None
        self.last_ts: int | None = None
        self.last_metrics_ms = -LIVE_METRICS_INTERVAL_MS
        self.last_framing_cue_ms = -LIVE_FRAMING_CUE_INTERVAL_MS
        self.fulfilled = False
        self.frames_received = 0
        self.reload()

    # -- drill resolution -------------------------------------------------------------------------
    def reload(self) -> dict[str, Any]:
        memory = db_mongo.get_athlete_memory(self.user_id)
        self.memory = memory
        self.sport = memory.get('sport') or 'badminton'
        self.skill = memory.get('skill_focus') or ('overhead_clear' if self.sport == 'badminton' else 'forehand')
        self.level = memory.get('level')
        nodes = memory.get('curriculum_nodes') or []
        node = next((n for n in nodes if n.get('id') == self.explicit.get('node_id')), None) \
            or next((n for n in nodes if n.get('status') == 'active'), None)
        self.node = node
        drill = self._resolve_drill(memory, node)
        self.drill = drill
        stroke = kinematics_engine.stroke_for_skill(drill.get('stroke_type')) if drill else None
        self.sequence = [kinematics_engine.stroke_for_skill(s) or s for s in (drill or {}).get('sequence') or []] or \
            [stroke or kinematics_engine.stroke_for_skill(self.skill) or 'overhead_clear']
        self.target_stroke = self.sequence[0] if len(self.sequence) == 1 else None
        self.target_reps = int((drill or {}).get('target_reps') or LIVE_DEFAULT_TARGET_REPS)
        self.threshold = argon_analysis.level_threshold(self.sport, self.skill, self.level)
        self.tracker = kinematics_engine.MultiTracker(self.sequence, self.sport, self.side or 'right') if self.side else None
        return self.session_message()

    def _resolve_drill(self, memory: dict[str, Any], node: dict[str, Any] | None) -> dict[str, Any] | None:
        drill_id = self.explicit.get('drill_id')
        assigned = memory.get('assigned_drills') or []
        if drill_id:
            found = next((d for d in assigned if d.get('id') == drill_id), None)
            if found:
                return found
            catalog = {d['drill_id']: d for d in db_mongo.build_drills_catalog()}
            if drill_id in catalog:
                d = catalog[drill_id]
                return {'id': d['drill_id'], 'title': d['title'], 'instruction': d['instruction'],
                        'target_reps': d['target_reps'], 'focus_cue': d['focus_cue'], 'stroke_type': d['skill_id']}
            spec = (node or {}).get('drill_spec') or {}
            if spec.get('drill_id') == drill_id:
                return {'id': drill_id, **spec, 'stroke_type': spec.get('stroke_type') or self.skill}
        # Live queue head: the newest drill Thea assigned (custom or remedial), else the lesson's drill.
        if assigned:
            return assigned[-1]
        spec = (node or {}).get('drill_spec')
        if spec:
            return {'id': spec.get('drill_id') or node['id'], **spec}
        return None

    def session_message(self) -> dict[str, Any]:
        node, drill = self.node or {}, self.drill or {}
        counted = sum(r.rep_counted for r in self.reps)
        return {'type': 'session', 'session_id': self.session_id, 'sport': self.sport, 'skill': self.skill,
                'level': self.level, 'threshold_deg': self.threshold, 'active_lesson': node.get('title'),
                'node_id': node.get('id'), 'drill_id': drill.get('id'), 'drill_title': drill.get('title'),
                'target_stroke': self.target_stroke, 'sequence': self.sequence, 'target_reps': self.target_reps,
                'valid_reps': counted, 'reps': len(self.reps),
                'mode': 'footwork' if self.target_stroke in kinematics_engine.FOOTWORK_STROKES else 'stroke',
                'handedness': self.side}

    def start_drill(self, node_id: str | None, drill_id: str | None) -> dict[str, Any]:
        self.explicit = {'node_id': node_id, 'drill_id': drill_id}
        self.reps, self.fulfilled = [], False
        self.session_id = f'live-{uuid4().hex[:12]}'
        self.started_at = _now()
        return self.reload()

    # -- frames -------------------------------------------------------------------------------------
    def ingest(self, frame: LivePoseFrame) -> list[dict[str, Any]]:
        if self.last_ts is not None and frame.timestamp_ms - self.last_ts < 1000 // LIVE_MAX_FPS:
            return []
        self.last_ts = frame.timestamp_ms
        self.frames_received += 1
        if frame.heart_rate is not None:
            self.heart_rate = frame.heart_rate
        now, out = frame.timestamp_ms, []
        if self.side is None:
            self._side_buffer.append(frame.landmarks)
            if len(self._side_buffer) >= LIVE_SIDE_LOCK_FRAMES:
                self.side = kinematics_engine.detect_side(self._side_buffer, frame.aspect)
                self.tracker = kinematics_engine.MultiTracker(self.sequence, self.sport, self.side)
                out.append(self.session_message())
            side = self.side or 'right'
        else:
            side = self.side
        features = kinematics_engine.frame_features(frame.landmarks, now, side, frame.aspect)
        if features is None:
            if now - self.last_framing_cue_ms >= LIVE_FRAMING_CUE_INTERVAL_MS:
                self.last_framing_cue_ms = now
                out.append({'type': 'cue', 'cue': 'Step back so your whole body is visible.', 'focus': 'framing',
                            'should_speak': True, 'timestamp_ms': now, 'source': 'live_pose_rules',
                            'vision_analyzed': True})
            return out
        if self.tracker is None:
            return out
        completed = self.tracker.feed(features, self.heart_rate)
        live_angles = {'elbow_deg': round(features.elbow_deg, 1), 'knee_deg': round(features.lead_knee_deg, 1),
                       'shoulder_deg': round(features.shoulder_deg, 1), 'trunk_lean_deg': round(features.trunk_lean_deg, 1),
                       'reach_ratio': round(features.reach_ratio, 2)}
        for phase in self.tracker.transitions:
            out.append({'type': 'phase_update', 'phase': phase, 'live_angles': live_angles, 'timestamp_ms': now})
        for rep in completed:
            out.append(self._rep_message(rep))
        if now - self.last_metrics_ms >= LIVE_METRICS_INTERVAL_MS:
            self.last_metrics_ms = now
            out.append({'type': 'metrics', **live_angles, 'phase': self.tracker.phase, 'reps': len(self.reps),
                        'valid_reps': sum(r.rep_counted for r in self.reps), 'pose_visible': True, 'timestamp_ms': now})
        if not self.fulfilled and sum(r.rep_counted for r in self.reps) >= self.target_reps:
            out.append(self.fulfill(reason='target_reached'))
        return out

    def _rep_message(self, rep: kinematics_engine.CompletedRep) -> dict[str, Any]:
        kinematics_engine.grade_rep(rep, elbow_target=self.threshold if rep.target_stroke in
                                    ('overhead_clear', 'one_handed_backhand', 'first_serve') else None)
        try:
            match = db_mongo.find_closest_pro_pose(rep.pose_vector_6d, sport=self.sport)
            rep.pro_match = {'player_name': match.get('player_name'),
                             'similarity': round(float(match.get('similarity_score') or 0.0), 4),
                             'search_method': match.get('search_method')}
        except Exception:
            logger.warning('Live pro match failed', exc_info=True)
        self.reps.append(rep)
        counted = sum(r.rep_counted for r in self.reps)
        remaining = max(0, self.target_reps - counted)
        label = kinematics_engine.STROKE_LABELS.get(rep.detected_stroke, rep.detected_stroke)
        if rep.rep_counted:
            cue = (f'Good {label}, {rep.quality_score} percent. Set complete!' if remaining == 0 else
                   f'Good {label}, {rep.quality_score} percent. {remaining} to go.')
        else:
            cue = _short_fix(rep.primary_deviation)
        pro = rep.pro_match or {}
        drift = kinematics_engine.session_analysis(self.reps)['drift'] if len(self.reps) >= 6 else None
        return {'type': 'rep_completed', 'rep_index': rep.rep_index, 'target_reps': self.target_reps,
                'valid_reps': counted, 'rep_counted': rep.rep_counted, 'quality_score': rep.quality_score,
                'detected_stroke': rep.detected_stroke, 'target_stroke': rep.target_stroke,
                'pro_match': f"{pro['player_name']} ({pro['similarity'] * 100:.0f}%)" if pro.get('player_name') else None,
                'primary_deviation': rep.primary_deviation, 'phase_angles': rep.phase_angles,
                'cue_text': cue, 'should_speak': (not rep.rep_counted) or remaining == 0 or counted % 3 == 0,
                'drift': drift if drift and drift.get('detected') else None, 'timestamp_ms': rep.ended_ms}

    # -- fulfillment ----------------------------------------------------------------------------------
    def fulfill(self, reason: str) -> dict[str, Any]:
        """Persist the set like an upload and apply curriculum progression (complete or remediate)."""
        self.fulfilled = True
        reps = self.reps
        counted = sum(r.rep_counted for r in reps)
        analysis = kinematics_engine.session_analysis(reps, self.sequence if len(self.sequence) > 1 else None)
        mean_q = analysis['mean_quality']
        passed = counted >= self.target_reps or (
            mean_q is not None and mean_q >= LIVE_PASS_MEAN_QUALITY and len(reps) >= LIVE_MIN_REPS_FOR_EARLY_PASS)
        node = self.node
        best = max(reps, key=lambda r: (r.rep_counted, r.quality_score), default=None)
        deviations = [r.primary_deviation for r in reps if r.primary_deviation]
        top_flaw = max(set(deviations), key=deviations.count) if deviations else None
        memory = db_mongo.get_athlete_memory(self.user_id)
        widgets: list[dict[str, Any]] = []
        nxt = None
        if node and passed:
            if node.get('status') != 'completed':
                memory = db_mongo.set_lesson_node_status(self.user_id, node['id'], 'completed')
            nodes = [dict(n) for n in memory.get('curriculum_nodes') or []]
            for n in nodes:
                if n['id'] == node['id']:
                    n['completed_drills'] = (n.get('completed_drills') or []) + [{
                        'drill_id': (self.drill or {}).get('id'), 'reps_completed': counted, 'source': 'live',
                        'session_id': self.session_id, 'at': _now()}]
            drills = [d for d in memory.get('assigned_drills') or [] if d.get('id') != (self.drill or {}).get('id')]
            memory = db_mongo.update_athlete_memory(self.user_id, {'curriculum_nodes': nodes, 'assigned_drills': drills})
            nxt = next((n for n in memory['curriculum_nodes'] if n.get('status') == 'active'), None)
            action = 'lesson_completed'
        elif node and reps:
            action = 'remedial_assigned'
            drill = {'id': f'remedial_drill_{self.session_id[-12:]}', 'title': f"Fix for {node['title']}"[:120],
                     'instruction': top_flaw or 'Repeat the drill slowly with full range, then build speed.',
                     'target_reps': self.target_reps, 'focus_cue': _short_fix(top_flaw),
                     'stroke_type': self.target_stroke or self.skill, 'node_id': node['id'],
                     'source_session_id': self.session_id, 'assigned_at': _now()}
            nodes = [dict(n) for n in memory.get('curriculum_nodes') or []]
            for n in nodes:
                if n['id'] == node['id']:
                    n['attempts'] = int(n.get('attempts') or 0) + 1
                    n['remedial_drill_id'] = drill['id']
            assigned = ([d for d in memory.get('assigned_drills') or [] if d.get('node_id') != node['id']] + [drill])[-10:]
            memory = db_mongo.update_athlete_memory(self.user_id, {'curriculum_nodes': nodes, 'assigned_drills': assigned})
        else:
            action = 'not_measured' if not reps else 'no_active_lesson'
        if reps:
            flaw = {'session_id': self.session_id, 'node_id': (node or {}).get('id'), 'source': 'live',
                    'primary_flaw': top_flaw, 'overall_score': int(round(mean_q or 0)), 'at': _now(),
                    'measured': best.phase_angles if best else {}}
            db_mongo.update_athlete_memory(self.user_id, {
                'recent_flaws': ([flaw] + list(db_mongo.get_athlete_memory(self.user_id).get('recent_flaws') or []))[:MAX_RECENT_FLAWS]})
        memory = db_mongo.get_athlete_memory(self.user_id)
        widgets = onboarding_api.home_widgets(memory) if memory.get('curriculum_nodes') else []
        label = kinematics_engine.STROKE_LABELS.get(self.target_stroke or '', 'reps')
        if action == 'lesson_completed':
            summary = (f"Set complete! You averaged {mean_q:.0f}% across {len(reps)} {label}s. I've marked "
                       f"{node['title']} complete" + (f" and unlocked {nxt['title']} on your path." if nxt else
                                                      " and you've finished the path!"))
        elif action == 'remedial_assigned':
            summary = (f"Set saved: {counted} of {self.target_reps} reps counted, {mean_q:.0f}% average. "
                       f"Main fix: {_short_fix(top_flaw)} I've added a drill for it on Home.")
        else:
            summary = 'No complete reps were detected. Step back so your whole body and swing are in frame.'
        best_pro = best.pro_match if best and best.pro_match else {}
        record = {
            'session_id': self.session_id, 'user_id': self.user_id, 'source': 'live', 'sport': self.sport,
            'stroke_type': self.target_stroke or self.skill, 'status': 'COMPLETED', 'created_at': self.started_at,
            'updated_at': _now(), 'telemetry_count': self.frames_received, 'overall_score': int(round(mean_q)) if reps else None,
            'primary_flaw': top_flaw or ('Clean set' if reps else 'No reps detected'),
            'llm_source': 'live_kinematics', 'llm_model': 'tempo-rep-tracker', 'video_used': False, 'latency_ms': 0,
            'error_message': None, 'adaptation': {'action': action, 'overall_score': int(round(mean_q)) if reps else None,
                                                  'pass_score': LIVE_PASS_MEAN_QUALITY, 'node_id': (node or {}).get('id'),
                                                  'node_title': (node or {}).get('title'),
                                                  'next_node_id': (nxt or {}).get('id'), 'next_node_title': (nxt or {}).get('title'),
                                                  'reason': reason},
            'rep_log': [r.to_dict() for r in reps], 'session_analysis': analysis,
            'active_widgets': widgets,
            'gemini_feedback': {
                'kinetic_phases': [{'phase_name': k.phase, 'timestamp_ms': k.t_ms, 'form_accuracy_score': None,
                                    'joint_angles': k.angles, 'observation': ''} for k in (best.keyframes if best else [])],
                'model_version': 'tempo-rep-tracker', 'coaching_status': 'live_rules',
                'matched_archetype': None, 'reference_status': 'illustrative_unvalidated',
                'analysis_limitations': ['Live 2D pose estimate; racket and shuttle/ball are not tracked.'],
                'primary_flaw': top_flaw or 'Clean set', 'concise_audio_cue': _short_fix(top_flaw),
                'coach_voice_note_script': summary, 'verification_status': 'PASS' if passed else 'FAIL',
                'overall_score': int(round(mean_q)) if reps else None, 'adaptation': None, 'demo_mode': False,
                'pose_analysis': {'source': 'live', 'reps': len(reps), 'counted_reps': counted},
                'pro_comparison_card': {'matched_pro': best_pro.get('player_name'), 'sport': self.sport,
                                        'similarity_score': best_pro.get('similarity'),
                                        'search_method': best_pro.get('search_method'),
                                        'validation_status': 'illustrative_unvalidated', 'angles': []},
            },
        }
        record['gemini_feedback']['adaptation'] = record['adaptation']
        _put('android_sessions', self.session_id, record)
        if reps:
            _dispatch_live_debrief(self.user_id, memory, summary, record)
        return {'type': 'drill_fulfilled', 'passed': passed, 'action': action, 'reason': reason,
                'node_id': (node or {}).get('id'), 'completed_node_title': (node or {}).get('title') if passed else None,
                'unlocked_next_node': (nxt or {}).get('title'), 'session_id': self.session_id,
                'valid_reps': counted, 'target_reps': self.target_reps, 'reps': len(reps),
                'mean_quality': mean_q, 'drift': analysis.get('drift'), 'summary_speak': summary,
                'should_speak': True}


def _dispatch_live_debrief(user_id: str, memory: dict[str, Any], summary: str, record: dict[str, Any]) -> None:
    """Queue (and, when SAINT_WEBHOOK_URL is set, deliver) Saint's POST_SESSION_DEBRIEF for a live set."""
    from app.models.schedule import CadenceEventType, SaintNotificationPayload
    from app.services.saint_cadence import SaintCadenceService

    payload = SaintNotificationPayload(
        event_type=CadenceEventType.POST_SESSION_DEBRIEF, user_id=user_id, recipient_name='there',
        plain_text_message=summary, call_to_action='Open Tempo to review the set.',
        session_id=record['session_id'], metadata={'kind': 'live_debrief', 'overall_score': record['overall_score']})
    message = SaintCadenceService.format_thea_dispatch(payload)
    outcome = saint_events.push(saint_events.coaching_message(
        user_id, 'POST_SESSION_DEBRIEF', message, memory.get('phone_number'), 'whatsapp',
        {'kind': 'live_debrief', 'session_id': record['session_id'], 'overall_score': record['overall_score']}))
    db_mongo.queue_saint_notification({
        'user_id': user_id, 'type': 'post_session_debrief', 'event_type': 'POST_SESSION_DEBRIEF',
        'session_id': record['session_id'], 'message': message,
        'channel': 'whatsapp', 'phone_number': memory.get('phone_number'),
        'status': saint_events.LEGACY_STATUS[outcome['status']], 'dispatched': outcome['status'] == 'sent'})


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
                      overall_score: int | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Complete the lesson on a passing score, otherwise attach a remedial drill and quiz to it.

    Unmeasured clips (no reliable body) and swings that missed the overhead contact an overhead skill
    needs leave the curriculum untouched; the session still returns Thea's guidance.
    """
    pose = payload['pose_analysis']
    if overall_score is None or pose.get('used_fallback') or not pose.get('raw_angles'):
        return {'overall_score': None, 'pass_score': LESSON_PASS_SCORE, 'action': 'not_measured',
                'reason': pose.get('status')}, []
    memory = db_mongo.get_athlete_memory(user_id)
    skill = memory.get('skill_focus') or metadata.stroke_type
    if skill in OVERHEAD_SKILLS and pose.get('overhead_contact_detected') is False:
        return {'overall_score': overall_score, 'pass_score': LESSON_PASS_SCORE, 'action': 'overhead_not_captured',
                'reason': 'No overhead contact was visible, so this clip did not grade the overhead lesson.'}, []
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
    rep_phases = (pose.get('rep_analysis') or {}).get('kinetic_phases') or []
    if rep_phases and not pose.get('used_fallback', True):
        best_pro = next(iter(payload['pro_comparison'].get('all_pro_matches') or []), {})
        pro_name = payload['pro_comparison'].get('matched_pro')
        for phase in rep_phases:
            angles = phase.get('joint_angles') or {}
            observation = ', '.join(f"{k.replace('_deg', '').replace('_', ' ')} {v:.0f}°"
                                    for k, v in angles.items() if k.endswith('_deg'))
            if phase['phase_name'] == 'Impact' and best_pro.get('right_elbow_contact_deg') is not None:
                gap = angles.get('elbow_deg', 0.0) - best_pro['right_elbow_contact_deg']
                observation = (f"Your elbow: {angles.get('elbow_deg', 0):.0f}° | {pro_name}: "
                               f"{best_pro['right_elbow_contact_deg']:.0f}° ({gap:+.0f}° gap). " + observation)
            phases.append({'phase_name': phase['phase_name'], 'timestamp_ms': phase['timestamp_ms'],
                           'form_accuracy_score': None, 'joint_angles': angles, 'observation': observation})
    elif isinstance(timestamp, int) and timestamp >= 0 and not pose.get('used_fallback', True):
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
            measured = not payload['pose_analysis'].get('used_fallback') and bool(payload['pose_analysis'].get('raw_angles'))
            if overall_score is None and measured:
                overall_score = 88 if payload.get('verification_status') == 'PASS' else 68
            primary_flaw = payload.get('primary_flaw') or payload.get('biomechanical_diagnosis')

            adaptation, adapted_widgets = await run_in_threadpool(
                _adapt_curriculum, metadata.user_id, session_id, metadata, payload,
                int(overall_score) if overall_score is not None else None)
            widgets = adapted_widgets or [{
                'widget_type': 'DrillCardWidget',
                'id': f'{session_id}-drill',
                'title': 'Practice focus' if measured else 'Re-film tip',
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
                gemini_feedback=_feedback(payload, int(overall_score) if overall_score is not None else None, adaptation),
                kinematic_vector=payload['pose_analysis']['pose_vector'],
                pipeline_session_id=payload['session_id'],
                apple_watch_biometrics=payload.get('apple_watch_biometrics'),
                adaptation=adaptation,
                active_widgets=widgets,
                error_message=None
            )
        except HTTPException as exc:
            # Store a sentence the app can show; the structured detail stays in error_detail.
            record.update(status='FAILED', error_message=(exc.detail.get('message') if isinstance(exc.detail, dict)
                                                          else str(exc.detail)) or 'Analysis failed. Record a new clip.',
                          error_detail=exc.detail if isinstance(exc.detail, dict) else None,
                          error_code=exc.status_code)
        except Exception:
            logger.exception('Android session processing failed: %s', session_id)
            record.update(status='FAILED', error_message='Something went wrong analysing this clip. Record it again, '
                          'side-on with your full body in frame.', error_code=500)
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
        """Live drill stream (v2). See LiveCoachSession for the packet protocol; bare {heart_rate}
        packets keep the legacy heart-rate rule."""
        try:
            identity = authenticate(websocket.headers, websocket.cookies)
        except HTTPException:
            await websocket.close(code=4401)
            return
        user_id = websocket.query_params.get('user_id') or identity['user_id']
        if identity['role'] != 'admin' and user_id != identity['user_id']:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        coach: LiveCoachSession | None = None

        async def ensure_coach() -> LiveCoachSession:
            nonlocal coach
            if coach is None:
                coach = await run_in_threadpool(LiveCoachSession, user_id)
            return coach

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
                kind = packet.get('type')
                if kind == 'ping':
                    # Ordering marker: everything sent before this ping has been answered.
                    await websocket.send_json({'type': 'pong', 'nonce': packet.get('nonce')})
                    continue
                if kind in ('hello', 'refresh'):
                    session = await ensure_coach()
                    # refresh: re-read athlete_memory after a voice command changed level, skill or drill.
                    await websocket.send_json(await run_in_threadpool(session.reload))
                    continue
                if kind == 'start_drill':
                    session = await ensure_coach()
                    await websocket.send_json(await run_in_threadpool(
                        session.start_drill, packet.get('node_id'), packet.get('drill_id')))
                    continue
                if kind in ('pose', 'keypoints'):
                    session = await ensure_coach()
                    try:
                        frame = LivePoseFrame.model_validate(packet)
                    except ValidationError:
                        await websocket.send_json({'error': 'keypoints needs 33 [x, y, z, visibility] landmarks'})
                        continue
                    for message in await run_in_threadpool(session.ingest, frame):
                        await websocket.send_json(message)
                    continue
                if kind == 'voice_query':
                    session = await ensure_coach()
                    text = str(packet.get('text') or '').strip()[:2000]
                    if not text:
                        await websocket.send_json({'error': 'voice_query needs text'})
                        continue
                    if __package__:
                        from . import coach_converse
                    else:
                        import coach_converse
                    reply = await run_in_threadpool(lambda: coach_converse.converse(
                        coach_converse.ConverseRequest(user_id=user_id, channel='live', message=text),
                        {'user_id': user_id, 'role': 'player'}).model_dump())
                    await websocket.send_json({
                        'type': 'voice_reply', 'reply_text': reply['reply_text'], 'speak_text': reply['speak_text'],
                        'tool_actions_taken': reply['tool_actions_taken'], 'updated_memory': reply['athlete_memory'],
                        'should_speak': True, 'bypass_rate_limit': True})
                    if set(reply['tool_actions_taken']) & {'assign_custom_drill', 'set_sport_and_goals', 'set_skill_focus',
                                                           'set_athlete_level_and_generate_plan', 'update_lesson_progress'}:
                        await websocket.send_json(await run_in_threadpool(session.reload))
                    continue
                if kind == 'complete_session':
                    session = await ensure_coach()
                    if session.fulfilled:
                        await websocket.send_json({'type': 'drill_fulfilled', 'already_saved': True,
                                                   'session_id': session.session_id})
                    else:
                        await websocket.send_json(await run_in_threadpool(session.fulfill, 'finished_by_athlete'))
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
