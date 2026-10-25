"""Tempo -> Saint pushes: things nobody asked for at that moment. Saint reacts by calling /command.

Side effects never travel in an event. An event may carry a signed proposal (read-only, from plan()),
but booking still goes through POST /api/v1/saint/actions/decision and the executor.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
from email.message import EmailMessage
import html
import json
import os
import smtplib
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
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
    type: Literal['court_slot_opened', 'argon_verdict', 'fix_verified', 'coaching_job', 'coaching_message']
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
    outcome['email'] = email(event)
    saint.put_record('saint_event_log', event.event_id, {'event': event.model_dump(mode='json'), **outcome})
    return {'event': event.model_dump(mode='json'), **outcome}


def _link_token(key: str) -> str:
    return hmac.new(saint.signing_key(), b'approve:' + key.encode(), hashlib.sha256).hexdigest()


def approval_url(proposal: saint.Proposal) -> str:
    """A one-time link for the player's yes or no. Saint never holds a credential: the player taps this."""
    key = proposal.action.idempotency_key
    saint.put_record('saint_approval_links', key, {'proposal': proposal.model_dump(mode='json')})
    base = os.environ.get('TEMPO_PUBLIC_URL', 'http://localhost:8000').strip().rstrip('/')
    return f"{base}/approve/{key}/{_link_token(key)}"


def email(event: Event) -> str:
    """Email the event to the player (TEMPO_EMAIL_TO) over SMTP, with an approval link when there is a proposal.
    Saint, working in the player's own inbox, picks it up from there."""
    host, to = os.environ.get('SMTP_HOST', '').strip(), os.environ.get('TEMPO_EMAIL_TO', '').strip()
    if not host or not to:
        return 'not_configured'
    lines = [event.summary, '']
    if event.proposal:
        action = event.proposal.action
        lines += [action.summary, '', f"Approve or decline (works once, until {action.expires_at:%H:%M} UTC):",
                  approval_url(event.proposal)]
    lines += ['', f"Tempo event {event.type} ({event.event_id})"]
    message = EmailMessage()
    message['Subject'] = f"Tempo: {event.summary[:90]}"
    message['From'] = os.environ.get('TEMPO_EMAIL_FROM', os.environ.get('SMTP_USER', 'tempo@localhost'))
    message['To'] = to
    message.set_content('\n'.join(lines))
    try:
        with smtplib.SMTP(host, int(os.environ.get('SMTP_PORT', '587')), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get('SMTP_USER'):
                smtp.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
            smtp.send_message(message)
        return 'sent'
    except (OSError, smtplib.SMTPException):
        return 'failed'


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
    """Turn an Argon verdict into a Saint event, closing the loop across sessions.

    FAIL: a proposal for a practice court, with the drill in the summary.
    PASS right after a FAIL: `fix_verified`, with the before and after angles. Any other PASS pushes nothing.
    NOT_MEASURED is ignored and does not reset the loop.
    """
    status = verdict.get('verification_status')
    if status not in ('PASS', 'FAIL'):
        return None
    elbow = verdict.get('right_elbow_contact_deg')
    previous = saint.get_record('saint_last_verdict', user)
    saint.put_record('saint_last_verdict', user, {'status': status, 'right_elbow_contact_deg': elbow,
                                                  'at': saint.now().isoformat()})
    if status == 'PASS':
        if not previous or previous.get('status') != 'FAIL':
            return None
        before, target = previous.get('right_elbow_contact_deg'), verdict.get('threshold_deg')
        change = (f"elbow at contact {before:.0f}° to {elbow:.0f}°" if isinstance(before, (int, float))
                  and isinstance(elbow, (int, float)) else 'elbow at contact now passes')
        return Event(type='fix_verified', event_id=uuid4().hex, user=user,
                     summary=(f"Fix verified by Argon: {change}"
                              + (f" (target {target:.0f}°)." if isinstance(target, (int, float)) else ".")
                              + " Tell the player, and ask whether to move on to the next skill."),
                     data={'before_deg': before, 'after_deg': elbow, 'threshold_deg': target,
                           'failed_at': previous.get('at')},
                     occurred_at=saint.now())
    prefs = _prefs(user)
    drill = str(verdict.get('live_drill_prescription') or 'the assigned drill')[:300]
    return _event('argon_verdict', user,
                  f"Argon check failed. Drill: {drill} Propose a practice court and ask the player before booking.",
                  f"book an indoor {prefs.sport} court tomorrow at {prefs.preferred_time} for 60 minutes",
                  {'verification_status': 'FAIL', 'drill': drill, 'right_elbow_contact_deg': elbow,
                   'threshold_deg': verdict.get('threshold_deg')})


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


UNDELIVERED = ('staged', 'failed')


def pending(user: str, limit: int = 20) -> list[dict]:
    """Events for `user` that never reached Saint, oldest first. Each is marked `pulled` as it is returned,
    so Saint sees it once. For a Saint with no inbound URL: it polls this instead of receiving pushes."""
    db = saint.db_mongo.get_db()
    if db is not None:
        try:
            rows = list(db['saint_event_log'].find({'event.user': user, 'status': {'$in': list(UNDELIVERED)}})
                        .sort('event.occurred_at', 1).limit(limit))
        except Exception:
            raise HTTPException(503, 'Event storage unavailable')
    else:
        with saint._LOCK:
            rows = [dict(r) for k, r in saint._MEMORY.items() if k.startswith('saint_event_log:')
                    and r['event']['user'] == user and r['status'] in UNDELIVERED]
        rows = sorted(rows, key=lambda r: r['event']['occurred_at'])[:limit]
    for row in rows:
        saint.put_record('saint_event_log', row['event']['event_id'],
                         {'event': row['event'], 'status': 'pulled', 'pulled_at': saint.now().isoformat()})
    return [row['event'] for row in rows]


# Status words older callers store in saint_notifications.
LEGACY_STATUS = {'sent': 'SENT', 'staged': 'STAGED_LOCALLY', 'failed': 'FAILED'}


router = APIRouter(tags=['saint-events'])


@router.post('/api/v1/saint/events/mock-slot-opened/{user}')
async def mock_slot_opened(user: str, request: Request):
    """Demo trigger standing in for a real venue provider's availability feed."""
    own(request, user)
    return await run_in_threadpool(lambda: push(court_slot_opened(user)))


@router.get('/api/v1/saint/events/pending/{user}')
async def pending_events(user: str, request: Request):
    """Saint polls this for events it has not seen yet (it has no inbound URL for Tempo to push to)."""
    own(request, user)
    return {'events': await run_in_threadpool(pending, user)}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta name=viewport content='width=device-width'><title>{html.escape(title)}</title>"
                        f"<body style='font-family:system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem'>"
                        f"<h1 style='font-size:1.4rem'>{html.escape(title)}</h1>{body}</body>")


def _linked_proposal(key: str, token: str) -> saint.Proposal:
    stored = saint.get_record('saint_approval_links', key)
    if not stored or not hmac.compare_digest(token, _link_token(key)):
        raise HTTPException(404, 'Unknown approval link')
    return saint.Proposal.model_validate(stored['proposal'])


@router.get('/approve/{key}/{token}')
async def approval_page(key: str, token: str):
    """Shows the proposal with Approve and Decline buttons. Opening the link changes nothing,
    so an email client prefetching it can't book anything."""
    proposal = await run_in_threadpool(_linked_proposal, key, token)
    done = await run_in_threadpool(saint.get_record, 'saint_action_log', key)
    if done:
        return _page('Already decided', f"<p>{html.escape(proposal.action.summary)}</p><p>Status: {html.escape(done['status'])}</p>")
    button = "<button name=decision value={0} style='font-size:1.1rem;padding:.6rem 1.2rem;margin-right:.5rem'>{1}</button>"
    return _page('Approve this?', f"<p>{html.escape(proposal.action.summary)}</p><form method=post>"
                 + button.format('yes', 'Approve') + button.format('no', 'Decline') + "</form>")


@router.post('/approve/{key}/{token}')
async def approval_decide(key: str, token: str, decision: str = Form(pattern='^(yes|no)$')):
    proposal = await run_in_threadpool(_linked_proposal, key, token)
    try:
        record = await run_in_threadpool(saint.execute, saint.Decision(proposal=proposal, approved=decision == 'yes'), 'email_link')
    except HTTPException as exc:
        return _page('Not done', f"<p>{html.escape(str(exc.detail))}</p>")
    title = 'Booked (mock)' if record['status'] == 'executed_mock' else 'Declined' if record['status'] == 'declined' else 'Needs review'
    return _page(title, f"<p>{html.escape(proposal.action.summary)}</p><p>Status: {html.escape(record['status'])}</p>")


@router.get('/api/v1/saint/tools')
async def tools(request: Request):
    """OpenAPI document limited to the routes a Saint credential may call, for loading as tools."""
    spec = request.app.openapi()
    return {**spec, 'paths': {path: ops for path, ops in spec['paths'].items() if saint_may_call(path)}}
