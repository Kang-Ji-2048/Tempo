"""Tempo -> Saint pushes: things nobody asked for at that moment. Saint reacts by calling /command.

Side effects never travel in an event. An event may carry a signed proposal (read-only, from plan()),
but booking still goes through POST /api/v1/saint/actions/decision and the executor.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

if __package__:
    from . import saint_commands as saint
    from .auth import own, saint_may_call
else:
    import saint_commands as saint
    from auth import own, saint_may_call


class Event(saint.StrictModel):
    """The canonical event schema. Add event types here; Saint decides whether to act or ask."""
    type: Literal['court_slot_opened', 'argon_verdict', 'coaching_job', 'coaching_message']
    event_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    user: str
    summary: str = Field(min_length=1, max_length=600)
    # Plain-English text Saint can send to POST /command if the attached proposal has expired.
    suggested_command: str | None = Field(default=None, max_length=1000)
    proposal: saint.Proposal | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


def signature(body: bytes) -> str | None:
    secret = os.environ.get('TEMPO_WEBHOOK_SECRET', '').strip()
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else None


def push(event: Event) -> dict:
    """POST the event to SAINT_WEBHOOK_URL, or stage it when no URL is configured. Logged either way."""
    body = json.dumps(event.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()
    url = os.environ.get('SAINT_WEBHOOK_URL', '').strip()
    outcome = {'status': 'staged', 'detail': 'SAINT_WEBHOOK_URL not set'}
    if url:
        headers = {'Content-Type': 'application/json'}
        sig = signature(body)
        if sig:
            headers['X-Tempo-Signature'] = sig
            # The loopback receipt endpoint authenticates with the shared secret itself.
            headers['X-Tempo-Webhook-Secret'] = os.environ['TEMPO_WEBHOOK_SECRET'].strip()
        try:
            response = requests.post(url, data=body, headers=headers, timeout=5.0)
            outcome = {'status': 'sent' if response.ok else 'failed', 'status_code': response.status_code}
        except requests.RequestException as exc:
            outcome = {'status': 'failed', 'detail': type(exc).__name__}
    saint.put_record('saint_event_log', event.event_id, {'event': event.model_dump(mode='json'), **outcome})
    return {'event': event.model_dump(mode='json'), **outcome}


def _prefs(user):
    saved = saint.get_record('saint_preferences', user)
    return saint.Preferences.model_validate(saved['preferences']) if saved else saint.Preferences()


def _event(type_, user, summary, command, data):
    planned = saint.plan(user, command, _prefs(user))
    return Event(type=type_, event_id=uuid4().hex, user=user, summary=summary, suggested_command=command,
                 proposal=planned['proposal'] if planned['kind'] == 'proposal' else None,
                 data={**data, **({'question': planned['question']} if planned['kind'] == 'question' else {})},
                 occurred_at=saint.now())


def court_slot_opened(user: str) -> Event:
    """Mock provider event: a court opened at 10:00 on the next Saturday in the player's home area."""
    today = saint.now().astimezone(ZoneInfo('Europe/London')).date()
    saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    command = 'book an indoor court Saturday at 10:00 for 60 minutes'
    return _event('court_slot_opened', user,
                  f"A mock indoor court opened on Saturday {saturday:%d %b} at 10:00. Ask the player whether to book it.",
                  command, {'provider': 'mock', 'slot_date': saturday.isoformat(), 'slot_time': '10:00'})


def argon_verdict(user: str, verdict: dict) -> Event | None:
    """An Argon FAIL becomes a proposal for a practice court, with the drill in the summary. PASS pushes nothing."""
    if verdict.get('verification_status') != 'FAIL':
        return None
    prefs = _prefs(user)
    drill = str(verdict.get('live_drill_prescription') or 'the assigned drill')[:300]
    return _event('argon_verdict', user,
                  f"Argon check failed. Drill: {drill} Propose a practice court and ask the player before booking.",
                  f"book an indoor {prefs.sport} court tomorrow at {prefs.preferred_time} for 60 minutes",
                  {'verification_status': 'FAIL', 'drill': drill,
                   'right_elbow_contact_deg': verdict.get('right_elbow_contact_deg')})


def coaching_job(user: str, job: dict, stage: str, metadata: dict | None = None) -> Event:
    """An Argon coaching job: staged after analysis, or executed after the player's approval."""
    summary = str(job.get('proactive_training_notification') or job.get('plain_english_instruction') or stage)[:600]
    return Event(type='coaching_job', event_id=uuid4().hex, user=user, summary=summary,
                 data={'event_type': stage, 'saint_agent_job': job, 'metadata': metadata or {}},
                 occurred_at=saint.now())


def coaching_message(user: str, event_type: str, message: str, to: str | None, channel: str,
                     extra: dict | None = None) -> Event:
    """A proactive coaching message (cadence nudge or live debrief) for Saint to deliver."""
    return Event(type='coaching_message', event_id=uuid4().hex, user=user, summary=message[:600],
                 data={'event_type': event_type, 'message': message, 'to': to, 'channel': channel, **(extra or {})},
                 occurred_at=saint.now())


# Status words older callers store in saint_notifications.
LEGACY_STATUS = {'sent': 'SENT', 'staged': 'STAGED_LOCALLY', 'failed': 'FAILED'}


router = APIRouter(tags=['saint-events'])


@router.post('/api/v1/saint/events/mock-slot-opened/{user}')
async def mock_slot_opened(user: str, request: Request):
    """Demo trigger standing in for a real venue provider's availability feed."""
    own(request, user)
    return await run_in_threadpool(lambda: push(court_slot_opened(user)))


@router.get('/api/v1/saint/tools')
async def tools(request: Request):
    """OpenAPI document limited to the routes a Saint credential may call, for loading as tools."""
    spec = request.app.openapi()
    return {**spec, 'paths': {path: ops for path, ops in spec['paths'].items() if saint_may_call(path)}}
