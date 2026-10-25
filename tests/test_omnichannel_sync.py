"""Phase F: WhatsApp and Gemini adapters edit the same athlete_memory the app reads.

Runs the full backend.main app (real auth middleware) with a freshly registered athlete, against
MongoDB Atlas when reachable, else the in-process fallback stores. Thea runs on the rule-based
fallback unless a test scripts Gemini.
"""
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from backend import android_api, coach_converse, db_mongo, llm_config
from backend.main import app
from test_auth_helpers import auth_headers

GEMINI_DEMO = "I want to focus on my backhand net clearance and move my Tuesday session to 7pm"
SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    monkeypatch.setenv("TEMPO_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("SAINT_WEBHOOK_URL", raising=False)


@pytest.fixture
def athlete():
    """A real registered tennis player on Mon/Tue/Thu 18:00 with a linked WhatsApp number."""
    client = TestClient(app)
    email = f"omni_{uuid.uuid4().hex[:10]}@tempo.app"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "OmniChannel2026!",
                                                     "display_name": "Omni Athlete"})
    assert reg.status_code == 201, reg.text
    user_id, token = reg.json()["user_id"], reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    toolbox = coach_converse.TheaToolbox(user_id)
    toolbox.run("set_sport_and_goals", {"sport": "tennis", "intensity": "regular"})
    toolbox.run("set_athlete_level_and_generate_plan", {"level": "intermediate"})
    toolbox.run("update_training_schedule", {"days": ["Monday", "Tuesday", "Thursday"], "time_utc": "18:00"})
    phone = "+44" + str(uuid.uuid4().int)[:10]
    linked = client.post("/api/v1/coach/whatsapp/link", headers=headers, json={"phone_number": phone})
    assert linked.status_code == 200, linked.text
    yield {"client": client, "user_id": user_id, "email": email, "headers": headers, "phone": phone}
    db = db_mongo.get_db()
    if db is not None:
        for col, key in ((db_mongo.ATHLETE_MEMORY_COLLECTION, "user_id"), (db_mongo.SAINT_QUEUE_COLLECTION, "user_id"),
                         ("users", "user_id"), ("user_schedules", "_id")):
            db[col].delete_many({key: user_id})
    db_mongo._MEMORY_ATHLETES.pop(user_id, None)


def stored(user_id):
    """athlete_memory exactly as persisted (Atlas document, or the fallback store's copy)."""
    db = db_mongo.get_db()
    if db is not None:
        return db[db_mongo.ATHLETE_MEMORY_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
    return db_mongo._MEMORY_ATHLETES[user_id]


def saint_log(user_id):
    db = db_mongo.get_db()
    if db is not None:
        return list(db[db_mongo.SAINT_QUEUE_COLLECTION].find({"user_id": user_id}))
    return [n for n in db_mongo._MEMORY_SAINT_QUEUE if n["user_id"] == user_id]


def test_whatsapp_and_gemini_edit_the_same_memory_the_app_reads(athlete):
    client, headers, user_id = athlete["client"], athlete["headers"], athlete["user_id"]

    # 1. Saint relays a WhatsApp message: only the sender's number identifies the athlete.
    wa = client.post("/api/v1/webhooks/whatsapp", headers={"X-Tempo-Webhook-Secret": SECRET},
                     json={"from_number": f"whatsapp:{athlete['phone']}", "body": "I'm training competitively now"})
    assert wa.status_code == 200, wa.text
    wa_body = wa.json()
    assert (wa_body["linked"], wa_body["user_id"], wa_body["channel"]) == (True, user_id, "whatsapp")
    assert wa_body["tool_actions_taken"] == ["set_sport_and_goals"]
    assert wa_body["outbound"] == {"to": athlete["phone"], "body": wa_body["reply_text"]}

    # 2. The athlete tells Gemini (via the adapter, with their own token) to change focus and move a day.
    gm = client.post("/api/v1/webhooks/gemini", headers=headers, json={"message": GEMINI_DEMO})
    assert gm.status_code == 200, gm.text
    assert gm.json()["tool_actions_taken"] == ["set_skill_focus", "update_training_schedule"]

    # 3. One MongoDB document carries both edits...
    doc = stored(user_id)
    assert doc["intensity"] == "competitive"
    assert (doc["skill_focus"], doc["focus_note"]) == ("one_hand_backhand", "backhand net clearance")
    schedule = doc["reminder_schedule"]
    assert schedule["days_of_week"] == ["Monday", "Tuesday", "Thursday"] and schedule["time_utc"] == "18:00"
    assert schedule["day_times"] == {"Tuesday": "19:00"}
    assert [t["channel"] for t in doc["chat_history"]] == ["whatsapp", "gemini"]

    # 4. ...and the app's home feed shows it.
    home = client.get("/api/v1/coach/memory", headers=headers).json()
    assert home["athlete_memory"]["focus_note"] == "backhand net clearance"
    assert home["athlete_memory"]["intensity"] == "competitive"
    assert home["header"]["focus_note"] == "backhand net clearance"
    assert home["header"]["cadence_label"] == "3x/week · 18:00 UTC · Tue 19:00"
    # The Saint cadence mirror the existing schedule screen reads picks up the move too.
    cadence = android_api._get("user_schedules", user_id)
    assert cadence["stroke_type"] == "one_hand_backhand"


def test_gemini_model_tool_calls_through_the_adapter(athlete, monkeypatch):
    """Same sentence, but Thea runs as (scripted) Gemini and chooses the tools herself."""
    turns = [
        types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[
            types.Part.from_function_call(name="set_skill_focus",
                                          args={"focus": "backhand net clearance", "skill_id": "one_hand_backhand"}),
            types.Part.from_function_call(name="update_training_schedule",
                                          args={"day_times": [{"day": "Tuesday", "time_utc": "19:00"}]}),
        ]))]),
        types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[
            types.Part(text="Done: backhand net clearance is your focus, and Tuesday moves to 7pm.")]))]),
    ]
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(coach_converse, "_gemini_generate", lambda contents, config: turns.pop(0))

    body = athlete["client"].post("/api/v1/webhooks/gemini", headers=athlete["headers"],
                                  json={"message": GEMINI_DEMO}).json()
    assert body["llm_source"] == "gemini" and body["reply_text"].startswith("Done:")
    doc = stored(athlete["user_id"])
    assert doc["skill_focus"] == "one_hand_backhand"
    assert doc["reminder_schedule"]["day_times"] == {"Tuesday": "19:00"}


def test_twilio_form_webhook_is_signature_checked_and_answers_with_twiml(athlete, monkeypatch):
    url = "http://testserver/api/v1/webhooks/whatsapp"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "twilio-test-token")
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", url)
    form = {"From": f"whatsapp:{athlete['phone']}", "Body": "Train me 5 times a week", "ProfileName": "Omni"}
    signature = base64.b64encode(hmac.new(b"twilio-test-token",
                                          (url + "".join(k + form[k] for k in sorted(form))).encode(),
                                          hashlib.sha1).digest()).decode()
    client = athlete["client"]
    ok = client.post("/api/v1/webhooks/whatsapp", content=urlencode(form),
                     headers={"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": signature})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("application/xml")
    assert ok.text.startswith('<?xml') and "<Message>" in ok.text
    assert len(stored(athlete["user_id"])["reminder_schedule"]["days_of_week"]) == 5

    forged = client.post("/api/v1/webhooks/whatsapp", content=urlencode(form),
                         headers={"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": "bad"})
    assert forged.status_code == 401
    anonymous = client.post("/api/v1/webhooks/whatsapp", json={"from_number": athlete["phone"], "body": "hi"})
    assert anonymous.status_code == 401


def test_unknown_numbers_and_number_ownership(athlete):
    client = athlete["client"]
    unknown = client.post("/api/v1/webhooks/whatsapp", headers={"X-Tempo-Webhook-Secret": SECRET},
                          json={"from_number": "+15550000000", "body": "hello"}).json()
    assert unknown["linked"] is False and "Link & Message on WhatsApp" in unknown["reply_text"]

    other = auth_headers(user_id=f"other{uuid.uuid4().hex[:8]}", role="player")
    taken = client.post("/api/v1/coach/whatsapp/link", headers=other, json={"phone_number": athlete["phone"]})
    assert taken.status_code == 409
    bad = client.post("/api/v1/coach/whatsapp/link", headers=athlete["headers"], json={"phone_number": "call me maybe"})
    assert bad.status_code == 422
    # A player's token can't speak for someone else on either channel.
    assert client.post("/api/v1/webhooks/whatsapp", headers=other,
                       json={"user_id": athlete["user_id"], "body": "hi"}).status_code == 403
    assert client.post("/api/v1/webhooks/gemini", headers=other,
                       json={"message": "hi", "email": athlete["email"]}).status_code == 403


def test_openai_and_gemini_function_call_shapes(athlete):
    client, admin = athlete["client"], auth_headers(user_id="saint-admin", role="admin")
    tools = client.get("/api/v1/webhooks/gemini/tools", headers=admin).json()
    assert tools["function_declarations"][0]["name"] == "tempo_coach_converse"
    assert tools["openai_tools"][0]["type"] == "function"

    chat = client.post("/api/v1/webhooks/gemini", headers=admin, json={
        "model": "gpt-4o", "user": athlete["email"],
        "messages": [{"role": "system", "content": "be brief"}, {"role": "user", "content": "I'm advanced"}]}).json()
    assert chat["object"] == "chat.completion" and chat["choices"][0]["message"]["role"] == "assistant"
    assert stored(athlete["user_id"])["level"] == "advanced"

    fn = client.post("/api/v1/webhooks/gemini", headers=admin, json={"functionCall": {
        "name": "tempo_coach_converse", "args": {"user_id": athlete["user_id"], "message": "Train me 2 times a week"}}}).json()
    response = fn["functionResponse"]["response"]
    assert fn["functionResponse"]["name"] == "tempo_coach_converse"
    assert response["athlete_memory"]["reminder_schedule"]["days_of_week"] == ["Tuesday", "Thursday"]


def test_cadence_trigger_reads_memory_and_logs(athlete):
    client, headers, user_id = athlete["client"], athlete["headers"], athlete["user_id"]
    coach_converse.TheaToolbox(user_id).run("update_training_schedule", {"day_times": {"Tuesday": "19:00"}})
    tuesday = datetime(2026, 10, 27, 18, 45, tzinfo=timezone.utc)  # a Tuesday, 15 min before the moved session

    priming = client.post("/api/v1/cadence/trigger", headers=headers,
                          json={"now": tuesday.isoformat(), "dispatch": False}).json()["results"][0]
    assert (priming["event_type"], priming["kind"]) == ("PRE_SESSION_PRIMING", "pre_session")
    assert "19:00 UTC" in priming["message"] and "Omni" in priming["message"]

    missed = client.post("/api/v1/cadence/trigger", headers=headers,
                         json={"now": (tuesday + timedelta(hours=2)).isoformat(), "dispatch": False}).json()["results"][0]
    assert missed["kind"] == "missed_session"

    drill = {"id": "drill_custom_stale", "title": "Wall Rally", "instruction": "x", "target_reps": 30, "focus_cue": "Low to high",
             "assigned_at": (tuesday - timedelta(days=2)).isoformat()}
    db_mongo.update_athlete_memory(user_id, {"assigned_drills": [drill]})
    wednesday = tuesday + timedelta(days=1)
    nudge = client.post("/api/v1/cadence/trigger", headers=headers,
                        json={"now": wednesday.isoformat()}).json()["results"][0]
    assert nudge["kind"] == "missed_drill" and "Wall Rally" in nudge["message"]
    assert nudge["dispatch"]["status"] == "STAGED_LOCALLY"  # no SAINT_WEBHOOK_URL in tests
    logged = saint_log(user_id)
    assert {entry["type"] for entry in logged} >= {"cadence_pre_session", "cadence_missed_drill"}
    assert any(entry["phone_number"] == athlete["phone"] for entry in logged)

    assert client.post("/api/v1/cadence/trigger", headers=headers, json={"all": True}).status_code == 403
    assert client.post("/api/v1/cadence/trigger", headers=headers, json={"user_id": "someone_else"}).status_code == 403


def test_saint_delivery_receipt_requires_secret_and_records():
    client = TestClient(app)
    payload = {"event_type": "PRE_SESSION_PRIMING", "user_id": f"receipt{uuid.uuid4().hex[:8]}",
               "to": "+447700900123", "channel": "whatsapp", "message": "Session in 15 min"}
    assert client.post("/api/v1/webhooks/saint-delivery-receipt", json=payload).status_code == 401
    assert client.post("/api/v1/webhooks/saint-delivery-receipt", json=payload,
                       headers={"X-Tempo-Webhook-Secret": "wrong"}).status_code == 401
    ok = client.post("/api/v1/webhooks/saint-delivery-receipt", json=payload,
                     headers={"X-Tempo-Webhook-Secret": SECRET})
    assert ok.status_code == 200 and ok.json()["received"] is True
    db = db_mongo.get_db()
    if db is not None:
        stored = db["saint_deliveries"].find_one({"receipt_id": ok.json()["receipt_id"]})
        assert (stored["to"], stored["message"]) == ("+447700900123", "Session in 15 min")
        db["saint_deliveries"].delete_many({"user_id": payload["user_id"]})
