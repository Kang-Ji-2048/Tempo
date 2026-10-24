"""Opaque bearer credentials, hashed server-side and scoped to one player."""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse


def identities():
    try:
        raw = os.environ.get('TEMPO_AUTH_TOKENS')
        if raw is None:
            path = Path(os.environ.get('TEMPO_AUTH_FILE', Path(__file__).with_name('.tempo-auth.json')))
            raw = path.read_text(encoding='utf-8')
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def authenticate(headers, cookies=None):
    table = identities()
    if not table:
        raise HTTPException(503, 'Configure Tempo authentication before using this API')
    authorization = headers.get('authorization', '')
    token = authorization[7:] if authorization.startswith('Bearer ') else (cookies or {}).get('tempo_session', '')
    if not 32 <= len(token) <= 512:
        raise HTTPException(401, 'A valid Tempo access token is required')
    digest = hashlib.sha256(token.encode()).hexdigest()
    record = table.get(digest)
    if not isinstance(record, dict) or not record.get('user_id') or record.get('disabled'):
        raise HTTPException(401, 'A valid Tempo access token is required')
    from datetime import datetime, timezone
    try:
        expiry = datetime.fromisoformat(record['expires_at'])
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise HTTPException(401, 'Credential expired or lacks an expiry date')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}', record['user_id']) or record.get('role', 'player') not in {'player', 'admin'}:
        raise HTTPException(503, 'Invalid authentication record')
    return {'user_id': record['user_id'], 'role': record.get('role', 'player')}


def principal(request):
    return getattr(request.state, 'identity', None) or authenticate(request.headers, request.cookies)


def own(request, user_id):
    identity = principal(request)
    if identity['role'] != 'admin' and identity['user_id'] != user_id:
        raise HTTPException(403, 'This resource belongs to another player')
    return user_id


def event_visible(identity, event):
    if identity['role'] == 'admin':
        return True
    data = event.get('data', {})
    owner = data.get('user_name') or data.get('user_id') or data.get('approved_by')
    if not owner:
        owner = data.get('apple_watch_biometrics', {}).get('user_name')
    return owner == identity['user_id']


def install_auth(app):
    @app.middleware('http')
    async def protect(request: Request, call_next):
        path = request.url.path
        if path not in {'/health', '/login', '/auth/session'}:
            try:
                request.state.identity = authenticate(request.headers, request.cookies)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not request.headers.get('authorization'):
                    origin = request.headers.get('origin')
                    if origin != str(request.base_url).rstrip('/'):
                        raise HTTPException(403, 'Same-origin browser request required')
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, exc.status_code,
                                    headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})
        elif path == '/health' and (request.headers.get('authorization') or request.cookies.get('tempo_session')):
            try:
                request.state.identity = authenticate(request.headers, request.cookies)
            except HTTPException:
                pass
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/login', response_class=HTMLResponse)
    def login():
        return HTMLResponse('''<!doctype html><meta name="viewport" content="width=device-width"><title>Tempo sign in</title>
<h1>Tempo sign in</h1><form id="login"><label>Access token <input id="token" type="password" autocomplete="off" required></label><button>Sign in</button></form><p id="status"></p>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();const r=await fetch('/auth/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:document.querySelector('input').value})});if(r.ok)location.href='/dashboard';else document.querySelector('#status').textContent='Sign in failed';};</script>''', headers={'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"})

    @app.post('/auth/session')
    async def session(request: Request):
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Same-origin browser request required')
        if len(await request.body()) > 2048:
            raise HTTPException(413, 'Request too large')
        try:
            token = (await request.json())['token']
            identity = authenticate({'authorization': 'Bearer ' + token})
        except (ValueError, KeyError, TypeError):
            raise HTTPException(401, 'Invalid sign-in')
        response = JSONResponse({'user_id': identity['user_id']})
        response.set_cookie('tempo_session', token, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=3600, path='/')
        return response

    @app.delete('/auth/session')
    def logout():
        response = JSONResponse({'status': 'signed_out'})
        response.delete_cookie('tempo_session')
        return response
