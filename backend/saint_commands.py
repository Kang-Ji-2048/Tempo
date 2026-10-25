"""Tempo-owned Saint command prototype. Planning is read-only; execution is mock-only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
from threading import Lock
from typing import Literal, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

if __package__:
    from . import db_mongo
    from .auth import own, principal
else:
    import db_mongo
    from auth import own, principal


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Preferences(StrictModel):
    home_area: str = Field(default='', max_length=120)
    preferred_time: str = Field(default='09:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    sport: Literal['badminton', 'tennis'] = 'badminton'
    level: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'


class Command(StrictModel):
    user: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1000)


class CourtParams(StrictModel):
    area: str = Field(min_length=1, max_length=120)
    sport: Literal['badminton', 'tennis']
    indoor: bool | None = None
    starts_at: datetime
    duration_minutes: Literal[30, 60, 90] = 60
    venue_id: Literal['mock-indoor', 'mock-outdoor']
    provider: Literal['mock'] = 'mock'


class Action(StrictModel):
    """The canonical action schema. Add capabilities here and to the executor registry."""
    type: Literal['search_venues', 'book_court']
    params: CourtParams
    summary: str = Field(min_length=1, max_length=600)
    requires_approval: Literal[True] = True
    idempotency_key: str = Field(pattern=r'^[a-f0-9]{32}$')
    user: str
    expires_at: datetime


class Proposal(StrictModel):
    action: Action
    signature: str = Field(pattern=r'^[a-f0-9]{64}$')


class Decision(StrictModel):
    proposal: Proposal
    approved: bool


class VenueAdapter(Protocol):
    def search(self, params: CourtParams) -> list[dict]: ...
    def book(self, params: CourtParams, idempotency_key: str) -> dict: ...


class MockVenueAdapter:
    def search(self, params):
        return [{'id': params.venue_id, 'name': 'Demo Indoor Centre' if params.venue_id == 'mock-indoor' else 'Demo Outdoor Courts',
                 'area': params.area, 'sport': params.sport, 'starts_at': params.starts_at.isoformat(),
                 'duration_minutes': params.duration_minutes, 'demo': True}]

    def book(self, params, idempotency_key):
        return {'booking_reference': 'DEMO-' + idempotency_key[:10], 'venue': self.search(params)[0],
                'demo': True, 'message': 'Mock reservation only. No real court has been booked and no payment was made.'}


ADAPTER: VenueAdapter = MockVenueAdapter()
_MEMORY: dict[str, dict] = {}
_LOCK = Lock()
_EPHEMERAL_KEY = secrets.token_bytes(32)


def now():
    return datetime.now(timezone.utc)


def signing_key():
    configured = os.environ.get('TEMPO_ACTION_SIGNING_KEY', '')
    if configured and len(configured) < 32:
        raise HTTPException(503, 'Action signing configuration is invalid')
    # Safe for a single-process mock demo. Restart invalidates outstanding proposals.
    return configured.encode() if configured else _EPHEMERAL_KEY


def sign(action):
    canonical = json.dumps(action.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
    return hmac.new(signing_key(), canonical.encode(), hashlib.sha256).hexdigest()


def get_record(collection, key):
    db = db_mongo.get_db()
    if db is not None:
        try:
            found = db[collection].find_one({'_id': key}, {'_id': 0})
            if found:
                return {**found, 'storage_mode': 'mongodb_atlas'}
        except Exception:
            raise HTTPException(503, 'Action storage unavailable')
    with _LOCK:
        return copy.deepcopy(_MEMORY.get(f'{collection}:{key}'))


def put_record(collection, key, record):
    record = copy.deepcopy(record)
    db = db_mongo.get_db()
    record['storage_mode'] = 'mongodb_atlas' if db is not None else 'in_memory_demo'
    if db is not None:
        try:
            db[collection].replace_one({'_id': key}, {'_id': key, **record}, upsert=True)
            record['storage_mode'] = 'mongodb_atlas'
        except Exception:
            raise HTTPException(503, 'Action storage unavailable')
    with _LOCK:
        _MEMORY[f'{collection}:{key}'] = record
    return record


def claim(key, record):
    """Atomic unique action admission; an ambiguous execution is never auto-retried."""
    db = db_mongo.get_db()
    if db is not None:
        try:
            db['saint_action_log'].insert_one({'_id': key, **record})
        except Exception as exc:
            from pymongo.errors import DuplicateKeyError
            if isinstance(exc, DuplicateKeyError):
                return False
            raise HTTPException(503, 'Action storage unavailable')
        return True
    with _LOCK:
        memory_key = f'saint_action_log:{key}'
        if memory_key in _MEMORY:
            return False
        _MEMORY[memory_key] = copy.deepcopy(record)
        return True


def plan(user: str, text: str, prefs: Preferences, clock=None):
    """Conservative deterministic planner; no model/API calls, writes or venue side effects."""
    t = text.lower().strip()
    def question(message):
        return {'kind': 'question', 'question': message, 'planner': 'deterministic_demo', 'demo': True}
    if not t:
        return question('What would you like to practise or arrange?')
    if re.search(r'\b(not|don.t|do not)\s+(indoor|outdoor|inside|outside)', t) or ('today' in t and 'tomorrow' in t):
        return question('Please name one day and whether you want an indoor or outdoor court.')
    if re.search(r'\bat\b.*\bor\b',t):
        return question('Which one time should I use for this proposal?')
    if re.search(r'\b(cancel|pay|invite|message|refund|reschedule|change my|delete)\b', t):
        return question('This prototype supports court search and mock booking. Which of those would you like?')
    booking = bool(re.search(r'\b(book|reserve|reservation)\b', t))
    searching = bool(re.search(r'\b(find|search|look|show|something|court)\b', t))
    if not (booking or searching):
        return question('Would you like to find a court or prepare a mock booking?')
    if re.search(r'\b(not|don.t|do not|never)\s+(book|reserve)\b', t):
        booking = False
    if re.search(r'\b(cheapest|under|budget|nearer|nearest|accessible|wheelchair|free)\b|[£$€]', t):
        return question('The mock venues have no verified price, distance or accessibility data. Shall we search without that requirement?')
    if re.search(r'\b(football|squash|padel|basketball)\b', t) or ('tennis' in t and 'badminton' in t):
        return question('Choose one supported sport: badminton or tennis.')
    sport = 'tennis' if 'tennis' in t else 'badminton' if 'badminton' in t else prefs.sport
    # Location is deliberately taken from explicit saved preferences rather than guessed.
    if not prefs.home_area.strip():
        return question('Save your home area in preferences first, then ask again.')
    if re.search(r'\b(in|near|around)\s+[a-z]', t) and not any(x in t for x in ['in the morning', 'in the afternoon', 'in the evening', 'in 2 days']):
        return question('This demo searches your saved home area. Update it in preferences to use another area.')
    indoor = True if re.search(r'indoor|inside|rain', t) else False if re.search(r'outdoor|outside', t) else None
    if indoor is True and re.search(r'outdoor|outside', t):
        return question('Would you prefer an indoor court or an outdoor court?')
    current = (clock or now()).astimezone(ZoneInfo('Europe/London'))
    date = None
    weekdays = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    mentioned = [i for i,d in enumerate(weekdays) if d in t]
    if len(mentioned) > 1:
        return question('Which one day should I use for this proposal?')
    if 'tomorrow' in t:
        date = current.date() + timedelta(days=1)
    elif 'today' in t:
        date = current.date()
    elif mentioned:
        date = current.date() + timedelta(days=(mentioned[0]-current.weekday()) % 7 or 7)
    elif 'weekend' in t:
        return question('Would you prefer Saturday or Sunday?')
    if date is None:
        return question('Which day would you like? Include it in your next request, for example Saturday morning.')
    hour, minute = map(int, prefs.preferred_time.split(':'))
    if 'morning' in t: hour,minute = 9,0
    if 'afternoon' in t: hour,minute = 14,0
    if 'evening' in t: hour,minute = 18,0
    match = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', t)
    if match:
        hour,minute = int(match[1]),int(match[2] or 0)
        if match[3]:
            if not 1 <= hour <= 12: return question('Please use a valid time, such as 10:00 or 7pm.')
            hour = hour % 12 + (12 if match[3]=='pm' else 0)
        if hour>23 or minute>59: return question('Please use a valid time, such as 10:00 or 7pm.')
    starts = datetime(date.year,date.month,date.day,hour,minute,tzinfo=current.tzinfo)
    if starts <= current:
        return question('That time has passed. Which future day and time would you like?')
    # Refuse ambiguous/nonexistent local clock times around daylight-saving transitions.
    if starts.utcoffset() != starts.replace(fold=1).utcoffset() or starts.astimezone(timezone.utc).astimezone(current.tzinfo).replace(tzinfo=None) != starts.replace(tzinfo=None):
        return question('That local time falls on a clock change. Please choose a different time.')
    duration = 60
    m = re.search(r'\b(\d+)\s*(minutes?|mins?|hours?)\b',t)
    if m:
        duration=int(m[1])*(60 if m[2].startswith('hour') else 1)
        if duration not in (30,60,90): return question('This demo supports 30, 60 or 90 minutes. Which duration would you like?')
    params = CourtParams(area=prefs.home_area.strip(),sport=sport,indoor=indoor,starts_at=starts,
                         duration_minutes=duration,venue_id='mock-outdoor' if indoor is False else 'mock-indoor')
    mode='outdoor' if indoor is False else 'indoor' if indoor else 'indoor demo'
    action = Action(type='book_court' if booking else 'search_venues',params=params,user=user,
        idempotency_key=uuid4().hex,expires_at=(clock or now())+timedelta(minutes=15),
        summary=f"{'Mock book' if booking else 'Search'} {mode} {sport} in {params.area} on {starts.strftime('%a %d %b %Y at %H:%M %Z')} for {duration} minutes. No real reservation or payment.")
    return {'kind':'proposal','proposal':Proposal(action=action,signature=sign(action)).model_dump(mode='json'),
            'planner':'deterministic_demo','demo':True}


def execute(decision: Decision, approved_via: Literal['player', 'saint_relay'] = 'player'):
    action=decision.proposal.action
    if not hmac.compare_digest(decision.proposal.signature, sign(action)):
        raise HTTPException(400, 'Proposal was changed or server restarted. Request a fresh proposal.')
    key=action.idempotency_key
    existing=get_record('saint_action_log',key)
    if existing:
        if existing['approved'] != decision.approved:
            raise HTTPException(409,'This action already has a different decision')
        return existing
    if action.expires_at.tzinfo is None or action.expires_at <= now() or action.params.starts_at <= now():
        raise HTTPException(410,'Proposal expired. Request a fresh proposal.')
    record={'user':action.user,'action':action.model_dump(mode='json'),'approved':decision.approved,
            'status':'processing' if decision.approved else 'declined','approved_via':approved_via,'created_at':now().isoformat(),'demo':True}
    if not claim(key,record):
        winner=get_record('saint_action_log',key)
        if winner and winner['approved'] == decision.approved: return winner
        raise HTTPException(409,'Action already claimed; inspect its status before retrying')
    if decision.approved:
        try:
            record['result'] = ADAPTER.book(action.params,key) if action.type=='book_court' else {'venues':ADAPTER.search(action.params),'demo':True}
            record['status']='executed_mock'
        except Exception:
            record.update(status='needs_review',result={'message':'Execution outcome is uncertain; no automatic retry.'})
    record['updated_at']=now().isoformat()
    return put_record('saint_action_log',key,record)


router=APIRouter(tags=['saint-commands'])

@router.post('/command')
async def command(body: Command,request: Request):
    own(request,body.user)
    saved=await run_in_threadpool(get_record,'saint_preferences',body.user)
    prefs=Preferences.model_validate(saved['preferences']) if saved else Preferences()
    return plan(body.user,body.text,prefs)

@router.get('/api/v1/saint/preferences/{user}')
async def preferences(user: str,request: Request):
    own(request,user)
    saved=await run_in_threadpool(get_record,'saint_preferences',user)
    return saved or {'user':user,'preferences':Preferences().model_dump(),'storage_mode':'not_saved'}

@router.put('/api/v1/saint/preferences/{user}')
async def save_preferences(user: str,body: Preferences,request: Request):
    own(request,user)
    return await run_in_threadpool(put_record,'saint_preferences',user,{'user':user,'preferences':body.model_dump()})

@router.post('/api/v1/saint/actions/decision')
async def decide(body: Decision,request: Request):
    own(request,body.proposal.action.user)
    # A Saint credential relays the player's chat reply; the log records that Tempo did not see the approval itself.
    via='saint_relay' if principal(request)['role']=='saint' else 'player'
    return await run_in_threadpool(execute,body,via)

@router.get('/api/v1/saint/actions/{key}')
async def status(key: str,request: Request):
    principal(request)
    record=await run_in_threadpool(get_record,'saint_action_log',key)
    if record is None: raise HTTPException(404,'Action not found')
    own(request,record['user'])
    return record
