"""One-reading HTTPS bridge. Write and read permissions use separate keys."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import secrets
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

WRITE_KEY = os.environ.get('TEMPO_WRITE_KEY', '')
READ_KEY = os.environ.get('TEMPO_READ_KEY', '')
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_latest = None
_lock = Lock()


class Reading(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    heart_rate_bpm: float = Field(ge=20, le=250)
    access_key: str | None = None


def authorized(supplied: str | None, expected: str) -> bool:
    return bool(expected and len(expected) >= 32 and isinstance(supplied, str)
                and secrets.compare_digest(supplied.encode(), expected.encode()))


def configured() -> bool:
    return len(WRITE_KEY) >= 32 and len(READ_KEY) >= 32 and WRITE_KEY != READ_KEY


@app.middleware('http')
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'"
    return response


@app.get('/health')
async def health():
    if not configured():
        raise HTTPException(status_code=503, detail='Configure separate read and write keys')
    return {'status': 'ready'}


@app.post('/watch')
async def receive(request: Request):
    if not configured():
        raise HTTPException(status_code=503, detail='Receiver is not configured')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(status_code=413, detail='Request too large')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail='Expected JSON') from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail='Expected a JSON object')
    if not authorized(request.headers.get('X-Tempo-Token') or data.get('access_key'), WRITE_KEY):
        raise HTTPException(status_code=401, detail='Invalid access key')
    try:
        reading = Reading.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail='Enter a heart rate between 20 and 250') from exc
    global _latest
    with _lock:
        _latest = {'reading_id': str(uuid4()), 'heart_rate_bpm': reading.heart_rate_bpm,
                   'received_at': datetime.now(timezone.utc).isoformat(), 'source': 'user_submitted'}
        response = dict(_latest)
    return {'status': 'ok', **response}


@app.get('/reading')
async def latest(request: Request):
    if not configured():
        raise HTTPException(status_code=503, detail='Receiver is not configured')
    supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not authorized(supplied, READ_KEY):
        raise HTTPException(status_code=401, detail='Invalid reader key')
    with _lock:
        reading = dict(_latest) if _latest else None
    if reading:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(reading['received_at'])).total_seconds()
        if age > 3600:
            reading = None
    return {'reading': reading}


@app.get('/', response_class=HTMLResponse)
async def page():
    return HTMLResponse(PAGE)


PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tempo Watch Connection</title>
<style>body{font:17px system-ui;background:#101827;color:#fff;margin:0}main{max-width:500px;margin:auto;padding:28px 22px}section{background:#1c2940;border-radius:16px;padding:20px;margin:24px 0}h1{font-size:30px}p{line-height:1.5}input,button{font:inherit;width:100%;box-sizing:border-box;padding:13px;border-radius:10px;margin-top:12px}input{background:#101827;color:white;border:1px solid #687a94}button{background:#c9ff58;border:0;color:#101827;font-weight:700}code{overflow-wrap:anywhere}</style></head>
<body><main><h1>Tempo Watch Connection</h1><p id="connection">Checking connection…</p><section><h2>Send a reading</h2><p>Find a recent Apple Watch heart-rate reading in Apple Health, then enter its value.</p><label for="hr">Heart rate (beats/min)</label><input id="hr" inputmode="decimal" type="number" min="20" max="250" step="0.1"><button id="send">Send reading</button><p id="result" role="status"></p><p>This sends a manually entered value. It does not read the watch's sensors automatically.</p></section>
<details><summary>Use an iPhone Shortcut</summary><p>Find Health Samples: Heart Rate, latest first, limit 1. Get Details of Health Samples: Value.</p><p>Get Contents of URL: POST, JSON body. URL:</p><input id="endpoint" readonly><p>Add Number field <code>heart_rate_bpm</code> using the Health Value variable. Add Text field <code>access_key</code> using:</p><input id="key" readonly><p>Run the Shortcut and grant Health/network access. Health sync delays can apply.</p></details><p>Temporary test: only the newest reading is retained, for up to one hour and until this service restarts. Tempo's laptop receiver must run to forward readings into the app.</p></main>
<script>const key=new URLSearchParams(location.hash.slice(1)).get('key');if(key){sessionStorage.setItem('tempoKey',key);history.replaceState(null,'',location.pathname);}const accessKey=sessionStorage.getItem('tempoKey')||'';document.getElementById('key').value=accessKey;document.getElementById('endpoint').value=location.origin+'/watch';fetch('/health').then(r=>{if(!r.ok)throw Error();document.getElementById('connection').textContent=accessKey?'Ready for your reading.':'Connection works. Open the private setup link to send.';}).catch(()=>document.getElementById('connection').textContent='Receiver not ready.');document.getElementById('send').onclick=async()=>{const output=document.getElementById('result');const hr=Number(document.getElementById('hr').value);if(!accessKey){output.textContent='Open the private setup link first.';return;}if(!Number.isFinite(hr)||hr<20||hr>250){output.textContent='Enter a heart rate between 20 and 250.';return;}try{const r=await fetch('/watch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({heart_rate_bpm:hr,access_key:accessKey})});const data=await r.json();if(!r.ok)throw Error(data.detail||'Send failed');output.textContent='Cloud receiver accepted '+data.heart_rate_bpm+' beats/min. Tempo can now retrieve it.';}catch(e){output.textContent=e.message;}};</script></body></html>'''
