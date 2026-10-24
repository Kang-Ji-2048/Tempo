"""Shared athlete memory + unified Coach Thea converse endpoint (Phase B).

Runs against MongoDB Atlas when MONGODB_URI is reachable (backend/.env), otherwise the
in-process fallback store. Gemini is faked with real google.genai function-call objects;
set TEMPO_LIVE_LLM_TESTS=1 to also exercise live gemini-4-argon tool calling.
"""
import os
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai import types

from backend import coach_converse, db_mongo, llm_config

MESSAGE = "Switch my sport to badminton, I want to train competitively 4x a week"


@pytest.fixture
def user_id():
    uid = f"test_converse_{uuid.uuid4().hex[:10]}"
    yield uid
    db = db_mongo.get_db()
    if db is not None:
        for col in (db_mongo.ATHLETE_MEMORY_COLLECTION, db_mongo.SAINT_QUEUE_COLLECTION):
            db[col].delete_many({"user_id": uid})
        db["user_schedules"].delete_many({"_id": uid})
    db_mongo._MEMORY_ATHLETES.pop(uid, None)


@pytest.fixture
def client(user_id):
    app = FastAPI()
    app.include_router(coach_converse.router)
    app.dependency_overrides[coach_converse._identity] = lambda: {"user_id": user_id, "role": "player"}
    return TestClient(app)


def stored_memory(user_id):
    """Read athlete_memory straight from MongoDB when connected, else from the fallback store."""
    db = db_mongo.get_db()
    if db is not None:
        return db[db_mongo.ATHLETE_MEMORY_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
    return db_mongo._MEMORY_ATHLETES.get(user_id)


def model_turn(*parts):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))])


class FakeGemini:
    """Scripted model: tool calls first, then a text reply; records what it was sent."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests = []

    def __call__(self, contents, config):
        self.requests.append((list(contents), config))
        return self.turns.pop(0)


def test_converse_tool_calls_mutate_memory_and_return_lesson_plan(client, user_id, monkeypatch):
    fake = FakeGemini(
        model_turn(
            types.Part.from_function_call(name="set_sport_and_goals",
                                          args={"sport": "badminton", "intensity": "competitive"}),
            types.Part.from_function_call(name="update_training_schedule",
                                          args={"days": ["Monday", "Tuesday", "Thursday", "Saturday"]}),
        ),
        model_turn(types.Part(text="Badminton it is! Four competitive sessions a week, starting with your overhead clear.")),
    )
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(coach_converse, "_gemini_generate", fake)

    res = client.post("/api/v1/coach/converse", json={"message": MESSAGE, "channel": "app"})
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["llm_source"] == "gemini"
    assert body["tool_actions_taken"] == ["set_sport_and_goals", "update_training_schedule"]
    assert body["reply_text"].startswith("Badminton it is!")
    assert body["speak_text"] and "*" not in body["speak_text"]

    # Tool results were handed back to the model as function responses.
    second_contents, _ = fake.requests[1]
    responses = [p.function_response for c in second_contents for p in (c.parts or []) if p.function_response]
    assert [r.name for r in responses] == ["set_sport_and_goals", "update_training_schedule"]
    assert all(r.response["ok"] for r in responses)
    tools_offered = {d.name for d in fake.requests[0][1].tools[0].function_declarations}
    assert tools_offered == set(coach_converse.TOOL_IMPLEMENTATIONS)

    # athlete_memory mutated in MongoDB.
    doc = stored_memory(user_id)
    assert doc["sport"] == "badminton"
    assert doc["intensity"] == "competitive"
    assert doc["skill_focus"] == "overhead_clear"
    assert doc["reminder_schedule"]["days_of_week"] == ["Monday", "Tuesday", "Thursday", "Saturday"]
    assert len(doc["chat_history"]) == 1 and doc["chat_history"][0]["user"] == MESSAGE

    # A lesson plan came back and was persisted.
    nodes = doc["curriculum_nodes"]
    assert len(nodes) >= 3
    assert [n["status"] for n in nodes].count("active") == 1 and nodes[0]["status"] == "active"
    assert all(n["id"].startswith("badminton_") and n["youtube_url"].startswith("https://www.youtube.com/results?")
               for n in nodes)
    assert any(n["drill_spec"] for n in nodes)
    assert body["athlete_memory"]["curriculum_nodes"] == nodes
    widget_types = [w["widget_type"] for w in body["active_widgets"]]
    assert widget_types == ["PathProgressWidget", "CheckInScheduleWidget"]
    assert body["dynamic_widgets"] == body["active_widgets"]


def test_fallback_without_gemini_applies_same_tools(client, user_id, monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    body = client.post("/api/v1/coach/converse", json={"message": MESSAGE, "channel": "whatsapp"}).json()

    assert body["llm_source"] == "fallback"
    assert body["tool_actions_taken"] == ["set_sport_and_goals", "update_training_schedule"]
    doc = stored_memory(user_id)
    assert (doc["sport"], doc["intensity"]) == ("badminton", "competitive")
    assert len(doc["reminder_schedule"]["days_of_week"]) == 4
    assert doc["curriculum_nodes"]
    assert "plan starts with" in body["reply_text"]


def test_level_plan_courts_and_lesson_completion(client, user_id, monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    client.post("/api/v1/coach/converse", json={"message": "I play tennis"})
    body = client.post("/api/v1/coach/converse",
                       json={"message": "I'm advanced, which courts are near me?"}).json()
    assert body["tool_actions_taken"] == ["set_athlete_level_and_generate_plan", "find_nearby_courts"]
    assert body["athlete_memory"]["level"] == "advanced"
    courts = next(w for w in body["active_widgets"] if w["widget_type"] == "CourtListWidget")["courts"]
    assert courts and courts == sorted(courts, key=lambda c: ("tennis" not in c["sports"], c["distance_km"]))

    toolbox = coach_converse.TheaToolbox(user_id)
    first, second = toolbox.memory["curriculum_nodes"][:2]
    result = toolbox.run("update_lesson_progress", {"node_id": first["id"], "status": "completed"})
    assert result["ok"] and result["next_active"] == second["id"]
    doc = stored_memory(user_id)
    assert doc["last_completed_node"]["id"] == first["id"]

    # The change-stream handler queues a Saint cadence notification for the completion.
    queued = db_mongo.handle_athlete_memory_change({
        "operationType": "update", "fullDocument": doc,
        "updateDescription": {"updatedFields": {"last_completed_node": doc["last_completed_node"]}},
    })
    assert queued[0]["type"] == "lesson_completed" and queued[0]["node_id"] == first["id"]
    assert db_mongo.handle_athlete_memory_change({
        "operationType": "update", "fullDocument": doc,
        "updateDescription": {"updatedFields": {"intensity": "casual"}},
    }) == []


def test_assign_custom_drill_and_bad_tool_args(user_id):
    toolbox = coach_converse.TheaToolbox(user_id)
    ok = toolbox.run("assign_custom_drill", {"title": "Wall Pronation", "instruction": "Snap 30s vs wall",
                                             "target_reps": 20, "focus_cue": "Elbow high"})
    assert ok["ok"] and stored_memory(user_id)["assigned_drills"][0]["title"] == "Wall Pronation"
    bad = toolbox.run("set_athlete_level_and_generate_plan", {"level": "expert"})
    assert not bad["ok"] and "level must be one of" in bad["error"]
    assert toolbox.actions == ["assign_custom_drill"]


def test_phone_number_resolution_and_ownership(client, user_id, monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    phone = "+44" + str(uuid.uuid4().int)[:10]
    client.post("/api/v1/coach/converse", json={"message": "I play badminton", "phone_number": phone})
    assert db_mongo.find_athlete_by_phone(phone)["user_id"] == user_id

    admin_app = FastAPI()
    admin_app.include_router(coach_converse.router)
    admin_app.dependency_overrides[coach_converse._identity] = lambda: {"user_id": "saint_bot", "role": "admin"}
    body = TestClient(admin_app).post("/api/v1/coach/converse",
                                      json={"message": "Train me 3 times a week", "phone_number": phone,
                                            "channel": "whatsapp"}).json()
    assert body["athlete_memory"]["user_id"] == user_id
    assert body["athlete_memory"]["reminder_schedule"]["days_of_week"] == ["Monday", "Wednesday", "Friday"]

    res = client.post("/api/v1/coach/converse", json={"message": "hi", "user_id": "someone_else"})
    assert res.status_code == 403


@pytest.mark.skipif(db_mongo.get_db() is None, reason="needs MongoDB Atlas for change streams")
def test_change_stream_watcher_queues_saint_notification(user_id):
    toolbox = coach_converse.TheaToolbox(user_id)
    toolbox.run("set_sport_and_goals", {"sport": "badminton"})
    assert db_mongo.start_athlete_memory_watcher()
    time.sleep(2)  # let the stream open before mutating
    node_id = toolbox.memory["curriculum_nodes"][0]["id"]
    toolbox.run("update_lesson_progress", {"node_id": node_id, "status": "completed"})
    col = db_mongo.get_db()[db_mongo.SAINT_QUEUE_COLLECTION]
    deadline = time.time() + 15
    found = None
    while time.time() < deadline and not found:
        found = col.find_one({"user_id": user_id, "node_id": node_id})
        time.sleep(0.5)
    db_mongo.stop_athlete_memory_watcher()
    assert found and found["type"] == "lesson_completed"


@pytest.mark.skipif(os.environ.get("TEMPO_LIVE_LLM_TESTS") != "1" or not llm_config.GEMINI_API_KEY,
                    reason="set TEMPO_LIVE_LLM_TESTS=1 to call live Gemini")
def test_live_gemini_tool_calling(client, user_id):
    body = client.post("/api/v1/coach/converse", json={"message": MESSAGE}).json()
    print(body["llm_source"], body["tool_actions_taken"], body["reply_text"])
    assert body["llm_source"] == "gemini"
    assert {"set_sport_and_goals", "update_training_schedule"} <= set(body["tool_actions_taken"])
    doc = stored_memory(user_id)
    assert doc["sport"] == "badminton" and doc["intensity"] == "competitive"
    assert len(doc["reminder_schedule"]["days_of_week"]) == 4 and doc["curriculum_nodes"]
