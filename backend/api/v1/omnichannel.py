"""WhatsApp (Saint / Twilio / Meta) and Gemini adapters onto the one Coach Thea brain.

Every adapter resolves an athlete, then calls the same `coach_converse.converse` with its channel,
so a WhatsApp message and a Gemini chat edit the same `athlete_memory` document the app renders.

- `POST /api/v1/webhooks/whatsapp`: inbound messages. Public to the auth middleware (Twilio can't send
  a Bearer token); the handler itself accepts a Bearer token, `X-Tempo-Webhook-Secret`, or a valid
  `X-Twilio-Signature`. Twilio form posts get TwiML back; JSON posts get the converse payload.
- `POST /api/v1/coach/whatsapp/link`: registers the caller's phone so inbound messages find them.
- `POST /api/v1/cadence/trigger`: Saint proactive cadence from athlete_memory, logged and dispatched.
- `POST /api/v1/webhooks/gemini` (+ `GET .../tools`): plain, OpenAI chat-completions, or Gemini
  functionCall shaped requests.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.services.saint_cadence import SaintCadenceService

if __package__ == "backend.api.v1":
    from ... import coach_converse, db_mongo, llm_config, user_auth
    from ...auth import authenticate
else:
    import coach_converse, db_mongo, llm_config, user_auth
    from auth import authenticate

logger = logging.getLogger("tempo.omnichannel")

router = APIRouter(prefix="/api/v1", tags=["omnichannel"])

WHATSAPP_WEBHOOK_PATH = "/api/v1/webhooks/whatsapp"
SERVICE_IDENTITY = {"user_id": "saint_webhook", "role": "admin"}
GEMINI_TOOL_NAME = "tempo_coach_converse"
UNLINKED_REPLY = ("Hi! I'm Thea, your Tempo coach. I don't recognise this number yet. In the Tempo app, tap "
                  "'Link & Message on WhatsApp' and I'll know it's you.")


def normalize_phone(raw: Any) -> Optional[str]:
    """'whatsapp:+44 7700-900123' -> '+447700900123'; None if it isn't a plausible number."""
    digits = re.sub(r"[^\d+]", "", str(raw or "").replace("whatsapp:", ""))
    digits = "+" + digits.lstrip("+")
    return digits if re.fullmatch(r"\+[0-9]{6,16}", digits) else None


def _converse(user_id: str, message: str, channel: str, phone: Optional[str] = None) -> Dict[str, Any]:
    """Run the shared Thea brain as the resolved athlete."""
    req = coach_converse.ConverseRequest(user_id=user_id, phone_number=phone, channel=channel, message=message[:4000])
    return coach_converse.converse(req, {"user_id": user_id, "role": "player"}).model_dump()


# ---------------------------------------------------------------------------
# WhatsApp inbound
# ---------------------------------------------------------------------------

def _twilio_signature_ok(request: Request, params: Dict[str, str]) -> bool:
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    signature = request.headers.get("x-twilio-signature", "")
    if not token or not signature:
        return False
    # Behind a tunnel the public URL Twilio signed can differ from request.url.
    url = os.environ.get("TWILIO_WEBHOOK_URL", "").strip() or str(request.url)
    signed = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def _webhook_caller(request: Request, params: Dict[str, str]) -> Dict[str, Any]:
    if request.headers.get("authorization") or request.cookies.get("tempo_session"):
        return authenticate(request.headers, request.cookies)
    secret = os.environ.get("TEMPO_WEBHOOK_SECRET", "").strip()
    if secret and hmac.compare_digest(secret, request.headers.get("x-tempo-webhook-secret", "")):
        return SERVICE_IDENTITY
    if _twilio_signature_ok(request, params):
        return SERVICE_IDENTITY
    raise HTTPException(401, "WhatsApp webhook needs a Bearer token, X-Tempo-Webhook-Secret, or a Twilio signature")


def parse_whatsapp_inbound(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Normalise Saint `{from_number, body, user_id}`, Twilio `{From, Body}` and Meta Cloud API payloads."""
    if payload.get("entry"):
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            msg = value["messages"][0]
            return {"from_number": msg.get("from"), "body": (msg.get("text") or {}).get("body"),
                    "user_id": None, "profile_name": ((value.get("contacts") or [{}])[0].get("profile") or {}).get("name")}
        except (KeyError, IndexError, TypeError):
            return {"from_number": None, "body": None, "user_id": None, "profile_name": None}
    return {
        "from_number": payload.get("from_number") or payload.get("From") or payload.get("from"),
        "body": payload.get("body") or payload.get("Body") or payload.get("message") or payload.get("text"),
        "user_id": payload.get("user_id"),
        "profile_name": payload.get("ProfileName") or payload.get("profile_name"),
    }


def _twiml(text: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>',
                    media_type="application/xml")


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request) -> Any:
    content_type = request.headers.get("content-type", "")
    is_form = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
    if is_form:
        params = {k: str(v) for k, v in (await request.form()).items()}
        payload: Dict[str, Any] = params
    else:
        params = {}
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(422, "Expected a JSON or form-encoded WhatsApp message") from exc
        if not isinstance(payload, dict):
            raise HTTPException(422, "Expected a JSON object")
    caller = _webhook_caller(request, params)
    inbound = parse_whatsapp_inbound(payload)
    body = (inbound["body"] or "").strip()
    phone = normalize_phone(inbound["from_number"])
    if not body:
        return {"ignored": True, "reason": "no message text (status callback or media-only)"}

    is_service = caller.get("role") == "admin"
    user_id = (inbound["user_id"] or "").strip() or None
    owner = await run_in_threadpool(db_mongo.find_athlete_by_phone, phone) if phone else None
    if user_id and not is_service and user_id != caller["user_id"]:
        raise HTTPException(403, "This athlete belongs to another player")
    if not user_id:
        user_id = owner["user_id"] if owner else (None if is_service else caller["user_id"])
    if owner and owner["user_id"] != user_id:
        phone = None  # never re-assign a number that's linked to someone else
    if user_id is None:
        logger.info("WhatsApp message from unlinked number %s", phone)
        return _twiml(UNLINKED_REPLY) if is_form else {
            "linked": False, "reply_text": UNLINKED_REPLY, "speak_text": UNLINKED_REPLY,
            "outbound": {"to": phone, "body": UNLINKED_REPLY}}

    result = await run_in_threadpool(_converse, user_id, body, "whatsapp", phone)
    if is_form:
        return _twiml(result["reply_text"])
    return {**result, "linked": True, "user_id": user_id, "channel": "whatsapp",
            "outbound": {"to": phone or result["athlete_memory"].get("phone_number"), "body": result["reply_text"]}}


class WhatsAppLinkRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=32)


@router.post("/coach/whatsapp/link")
def link_whatsapp(req: WhatsAppLinkRequest, identity: Dict[str, Any] = Depends(coach_converse._identity)) -> Dict[str, Any]:
    phone = normalize_phone(req.phone_number)
    if phone is None:
        raise HTTPException(422, "Enter the number in international format, e.g. +44 7700 900123")
    owner = db_mongo.find_athlete_by_phone(phone)
    if owner and owner["user_id"] != identity["user_id"]:
        raise HTTPException(409, "That number is already linked to another Tempo account")
    memory = db_mongo.update_athlete_memory(identity["user_id"], {"phone_number": phone})
    thea = re.sub(r"\D", "", os.environ.get("THEA_NUMBER", ""))
    text = "Hi Thea! I just linked my Tempo account."
    return {"phone_number": phone, "thea_number": thea or None, "prefill_text": text,
            "wa_link": f"https://wa.me/{thea}?text={quote(text)}" if thea else None,
            "athlete_memory": memory}


# ---------------------------------------------------------------------------
# Saint proactive cadence
# ---------------------------------------------------------------------------

class CadenceTriggerRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, max_length=128)
    all: bool = False
    dispatch: bool = True
    now: Optional[datetime] = None


def _recent_sessions(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    db = db_mongo.get_db()
    if db is None:
        return []
    try:
        return list(db["android_sessions"].find({"user_id": user_id}, {"_id": 0, "telemetry": 0})
                    .sort("updated_at", -1).limit(limit))
    except Exception:
        return []


def _display_name(user_id: str) -> str:
    user = None
    db = db_mongo.get_db()
    if db is not None:
        try:
            user = db["users"].find_one({"user_id": user_id}, {"display_name": 1})
        except Exception:
            user = None
    user = user or next((u for u in user_auth._USERS_MEMORY.values() if u.get("user_id") == user_id), None)
    name = (user or {}).get("display_name")
    return str(name).split()[0] if name else "there"


def run_cadence(user_id: str, now: Optional[datetime], dispatch: bool) -> Dict[str, Any]:
    memory = db_mongo.get_athlete_memory(user_id)
    payload = SaintCadenceService.evaluate_memory_cadence(
        memory, _recent_sessions(user_id), _display_name(user_id), current_time=now)
    message = SaintCadenceService.format_thea_dispatch(payload)
    channel = (memory.get("reminder_schedule") or {}).get("preferred_channel", "whatsapp")
    result = SaintCadenceService.dispatch_notification(
        payload, extra={"to": memory.get("phone_number"), "channel": channel}) if dispatch else {
        "dispatched": False, "status": "PREVIEW", "thea_message": message}
    db_mongo.queue_saint_notification({
        "user_id": user_id, "type": f"cadence_{payload.metadata.get('kind')}", "event_type": payload.event_type.value,
        "message": message, "channel": channel, "phone_number": memory.get("phone_number"),
        "status": result["status"], "dispatched": result["dispatched"]})
    return {"user_id": user_id, "event_type": payload.event_type.value, "kind": payload.metadata.get("kind"),
            "message": message, "call_to_action": payload.call_to_action, "dispatch": result}


@router.post("/cadence/trigger")
def trigger_cadence(req: CadenceTriggerRequest,
                    identity: Dict[str, Any] = Depends(coach_converse._identity)) -> Dict[str, Any]:
    is_admin = identity.get("role") == "admin"
    if req.all:
        if not is_admin:
            raise HTTPException(403, "Only the Saint service can trigger cadence for every athlete")
        db = db_mongo.get_db()
        users = [d["user_id"] for d in db[db_mongo.ATHLETE_MEMORY_COLLECTION].find(
            {"reminder_schedule": {"$ne": None}}, {"user_id": 1})] if db is not None else [
            uid for uid, m in db_mongo._MEMORY_ATHLETES.items() if m.get("reminder_schedule")]
    else:
        target = req.user_id or identity["user_id"]
        if not is_admin and target != identity["user_id"]:
            raise HTTPException(403, "This athlete belongs to another player")
        users = [target]
    return {"results": [run_cadence(uid, req.now, req.dispatch) for uid in users]}


# ---------------------------------------------------------------------------
# Gemini / OpenAI-compatible adapter
# ---------------------------------------------------------------------------

TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "What the athlete said, verbatim"},
        "user_id": {"type": "string", "description": "Tempo user id (defaults to the caller)"},
        "email": {"type": "string", "description": "Tempo account email, instead of user_id"},
    },
    "required": ["message"],
}
TOOL_DESCRIPTION = ("Talk to Coach Thea, the athlete's Tempo coach. Thea reads and updates their shared training "
                    "memory: sport, level, focus, lesson plan, drills and weekly schedule.")


@router.get("/webhooks/gemini/tools")
def gemini_tools() -> Dict[str, Any]:
    """Declarations for registering Tempo as a tool in Gemini or an OpenAI-compatible client."""
    return {
        "function_declarations": [{"name": GEMINI_TOOL_NAME, "description": TOOL_DESCRIPTION,
                                   "parameters": TOOL_PARAMETERS}],
        "openai_tools": [{"type": "function", "function": {"name": GEMINI_TOOL_NAME, "description": TOOL_DESCRIPTION,
                                                           "parameters": TOOL_PARAMETERS}}],
    }


def _resolve_gemini_target(identity: Dict[str, Any], user_id: Optional[str], email: Optional[str]) -> str:
    target = (user_id or "").strip() or None
    if not target and email:
        user = user_auth._get_user_by_email(email)
        if user is None:
            raise HTTPException(404, "No Tempo account with that email")
        target = user["user_id"]
    target = target or identity["user_id"]
    if identity.get("role") != "admin" and target != identity["user_id"]:
        raise HTTPException(403, "This athlete belongs to another player")
    return target


@router.post("/webhooks/gemini")
def gemini_webhook(payload: Dict[str, Any], identity: Dict[str, Any] = Depends(coach_converse._identity)) -> Dict[str, Any]:
    call = payload.get("functionCall") or payload.get("function_call")
    if isinstance(call, dict):
        style, args = "gemini_function", call.get("args") or {}
    elif isinstance(payload.get("messages"), list):
        style = "openai_chat"
        user_turns = [m for m in payload["messages"] if isinstance(m, dict) and m.get("role") == "user"]
        content = user_turns[-1].get("content") if user_turns else ""
        if isinstance(content, list):  # OpenAI content parts
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        user_ref = str(payload.get("user") or "")
        args = {"message": content, "email" if "@" in user_ref else "user_id": user_ref or None}
    else:
        style, args = "tempo", payload
    message = str(args.get("message") or "").strip()
    if not message:
        raise HTTPException(422, "message is required")
    target = _resolve_gemini_target(identity, args.get("user_id"), args.get("email"))
    result = _converse(target, message, "gemini")

    if style == "gemini_function":
        return {"functionResponse": {"name": call.get("name") or GEMINI_TOOL_NAME, "response": {
            "reply_text": result["reply_text"], "tool_actions_taken": result["tool_actions_taken"],
            "athlete_memory": {k: result["athlete_memory"].get(k) for k in (
                "user_id", "sport", "level", "skill_focus", "focus_note", "intensity", "reminder_schedule")},
        }}}
    if style == "openai_chat":
        return {"id": f"chatcmpl-{uuid.uuid4().hex[:24]}", "object": "chat.completion",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": f"tempo-thea/{llm_config.GEMINI_MODEL}",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": result["reply_text"]}}],
                "tempo": result}
    return {**result, "user_id": target, "channel": "gemini"}
