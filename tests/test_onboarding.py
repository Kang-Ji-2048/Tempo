"""
tests/test_onboarding.py - Shared-memory onboarding assessment (Phase C).

sport -> level_q1 -> level_q2 -> goal -> intensity -> schedule -> complete, with every answer
written to athlete_memory (MongoDB Atlas when reachable) and a 5-node plan from Gemini 4 Argon
(faked here; TEMPO_LIVE_LLM_TESTS=1 runs it live) or the catalog fallback.
"""
import json
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai import types

from backend import coach_converse, db_mongo, llm_config
from backend.api.v1 import onboarding

NEXT = "/api/v1/onboarding/next"


@pytest.fixture
def user_id():
    uid = f"test_onboarding_{uuid.uuid4().hex[:10]}"
    yield uid
    db = db_mongo.get_db()
    if db is not None:
        db[db_mongo.ATHLETE_MEMORY_COLLECTION].delete_many({"user_id": uid})
        db["user_schedules"].delete_many({"_id": uid})
    db_mongo._MEMORY_ATHLETES.pop(uid, None)


@pytest.fixture
def client(user_id):
    app = FastAPI()
    app.include_router(onboarding.router)
    app.dependency_overrides[coach_converse._identity] = lambda: {"user_id": user_id, "role": "player"}
    return TestClient(app)


@pytest.fixture
def no_gemini(monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")


def stored_memory(user_id):
    db = db_mongo.get_db()
    if db is not None:
        return db[db_mongo.ATHLETE_MEMORY_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
    return db_mongo._MEMORY_ATHLETES.get(user_id)


class Flow:
    """Drives the step machine the way the Android OnboardingViewModel does."""

    def __init__(self, client):
        self.client = client
        self.answers = {}

    def send(self, step_id="", answer=""):
        if step_id and answer:
            self.answers[step_id] = answer
        res = self.client.post(NEXT, json={"step_id": step_id, "answer": answer, "answers": self.answers})
        assert res.status_code == 200, res.text
        return res.json()


def run_to_schedule(client, sport="badminton", q1="1", q2="0"):
    flow = Flow(client)
    flow.send("sport", sport)
    flow.send("level_q1", q1)
    flow.send("level_q2", q2)
    flow.send("goal", "tournament_mastery")
    data = flow.send("intensity", "competitive_5x")
    return flow, data


def test_full_onboarding_writes_memory_and_builds_five_node_plan(client, user_id, no_gemini):
    flow = Flow(client)
    data = flow.send()
    assert data["step_id"] == "sport" and data["widget"]["widget_type"] == "ChoiceWidget"
    assert {"badminton", "tennis"} <= {o["id"] for o in data["widget"]["options"]}

    data = flow.send("sport", "badminton")
    assert data["step_id"] == "level_q1" and data["widget"]["widget_type"] == "ConceptQuizWidget"
    assert len(data["widget"]["options"]) == 4
    assert stored_memory(user_id)["sport"] == "badminton"
    assert stored_memory(user_id)["skill_focus"] == "overhead_clear"

    data = flow.send("level_q1", "1")
    assert data["step_id"] == "level_q2" and data["widget"]["id"] == "level_q2"

    data = flow.send("level_q2", "0")  # one of two correct
    assert data["step_id"] == "goal" and data["widget"]["widget_type"] == "ChoiceWidget"
    assert [o["id"] for o in data["widget"]["options"]] == [
        "fitness", "social_match_play", "tournament_mastery", "technique_refinement"]
    assert stored_memory(user_id)["level"] == "intermediate"

    data = flow.send("goal", "tournament_mastery")
    assert data["step_id"] == "intensity"
    assert [o["label"] for o in data["widget"]["options"]] == ["2x / week", "3x / week", "5x / week"]
    assert stored_memory(user_id)["motivation_why"] == "tournament_mastery"

    data = flow.send("intensity", "competitive_5x")
    assert data["step_id"] == "schedule" and data["widget"]["widget_type"] == "CheckInScheduleWidget"
    assert len(data["widget"]["days_of_week"]) == 5 and data["widget"]["slots"]
    assert stored_memory(user_id)["intensity"] == "competitive"

    picked = {"days_of_week": ["Monday", "Tuesday", "Wednesday", "Friday", "Saturday"],
              "target_time_utc": "07:00", "preferred_channel": "whatsapp"}
    data = flow.send("schedule", json.dumps(picked))
    assert data["step_id"] == "complete" and data["is_completed"] and data["progress"] == 1.0
    assert data["llm_source"] == "fallback"
    assert data["widget"]["widget_type"] == "PathProgressWidget"
    assert data["user_profile"] == {
        "user_id": user_id, "sport": "badminton", "level": "intermediate", "goal": "tournament_mastery",
        "playstyle": "competitive", "injuries": "none", "target_archetype": "Viktor Axelsen",
        "calibration_completed": True}

    doc = stored_memory(user_id)
    nodes = doc["curriculum_nodes"]
    assert len(nodes) == onboarding.PLAN_NODE_COUNT == 5
    assert [n["status"] for n in nodes] == ["active", "locked", "locked", "locked", "locked"]
    assert all(n["youtube_url"] and n["tips"] for n in nodes)
    assert doc["reminder_schedule"]["days_of_week"] == picked["days_of_week"]
    assert doc["reminder_schedule"]["time_utc"] == "07:00"
    if db_mongo.get_db() is not None:
        cadence = db_mongo.get_db()["user_schedules"].find_one({"_id": user_id})
        assert cadence["target_time_utc"] == "07:00" and cadence["sport"] == "badminton"


@pytest.mark.parametrize("q1,q2,level", [("1", "1", "advanced"), ("0", "2", "beginner"), ("", "1", "intermediate")])
def test_level_scoring(q1, q2, level):
    assert onboarding.score_level("badminton", {"level_q1": q1, "level_q2": q2}) == level


def test_plan_generated_by_argon_with_catalog_drills(client, user_id, monkeypatch):
    sent = {}

    def fake_generate(contents, config):
        sent["prompt"], sent["config"] = contents[0], config
        nodes = [{"title": f"Lesson {i}", "tips": [f"Tip {i}"]} for i in range(1, 6)]
        nodes[1]["drill_id"] = "drill_shadow_reach"
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
            role="model", parts=[types.Part(text=json.dumps({"nodes": nodes, "coach_message": "Let's go, champ."}))]))])

    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(coach_converse, "_gemini_generate", fake_generate)
    flow, _ = run_to_schedule(client, q1="1", q2="1")
    data = flow.send("schedule", "next")

    assert data["llm_source"] == "gemini"
    assert data["coach_message"].startswith("Let's go, champ.")
    assert "advanced Badminton player" in sent["prompt"] and "Tournament Mastery" in sent["prompt"]
    schema = sent["config"].response_json_schema
    assert schema["properties"]["nodes"]["minItems"] == 5
    assert "drill_shadow_reach" in schema["properties"]["nodes"]["items"]["properties"]["drill_id"]["enum"]

    nodes = stored_memory(user_id)["curriculum_nodes"]
    assert [n["title"] for n in nodes] == [f"Lesson {i}" for i in range(1, 6)]
    assert nodes[1]["drill_spec"]["drill_id"] == "drill_shadow_reach"
    # Default 5x schedule kept when the athlete just taps Continue.
    assert len(stored_memory(user_id)["reminder_schedule"]["days_of_week"]) == 5


def test_gemini_failure_falls_back_to_catalog_plan(client, user_id, monkeypatch):
    def broken(contents, config):
        raise RuntimeError("quota")

    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(coach_converse, "_gemini_generate", broken)
    flow, _ = run_to_schedule(client, sport="tennis")
    data = flow.send("schedule", "18:00")
    assert data["llm_source"] == "fallback" and data["user_profile"]["target_archetype"] == "Roger Federer"
    assert len(stored_memory(user_id)["curriculum_nodes"]) == 5


def test_resume_skips_sport_when_memory_has_it(client, user_id, no_gemini):
    db_mongo.update_athlete_memory(user_id, {"sport": "tennis", "skill_focus": "forehand"})
    data = Flow(client).send()
    assert data["step_id"] == "level_q1"
    assert "forehand" in data["widget"]["question"].lower()


def test_invalid_answers_are_rejected(client, no_gemini):
    assert client.post(NEXT, json={"step_id": "sport", "answer": "curling"}).status_code == 422
    client.post(NEXT, json={"step_id": "sport", "answer": "badminton"})
    assert client.post(NEXT, json={"step_id": "goal", "answer": "fame"}).status_code == 422
    assert client.post(NEXT, json={"step_id": "bogus", "answer": "x"}).status_code == 422


def test_coach_memory_feeds_home(client, user_id, no_gemini):
    empty = client.get("/api/v1/coach/memory").json()
    assert empty["onboarding_complete"] is False and empty["widgets"] == []

    flow, _ = run_to_schedule(client)
    flow.send("schedule", "next")
    body = client.get("/api/v1/coach/memory").json()
    assert body["onboarding_complete"] is True
    assert (body["header"]["sport_display"], body["header"]["level"], body["header"]["intensity"]) == (
        "Badminton", "intermediate", "competitive")
    assert body["header"]["cadence_label"] == "5x/week · 18:00 UTC"
    assert body["header"]["total_nodes"] == 5
    types_ = [w["widget_type"] for w in body["widgets"]]
    assert types_[0] == "PathProgressWidget" and types_[-1] == "ConceptQuizWidget"
    path = body["widgets"][0]
    assert path["title"] == "Badminton Intermediate Path"
    assert path["active_node_id"] == body["athlete_memory"]["curriculum_nodes"][0]["id"]
    assert [n["status"] for n in path["nodes"]] == ["ACTIVE", "LOCKED", "LOCKED", "LOCKED", "LOCKED"]


@pytest.mark.skipif(os.environ.get("TEMPO_LIVE_LLM_TESTS") != "1" or not llm_config.GEMINI_API_KEY,
                    reason="set TEMPO_LIVE_LLM_TESTS=1 to call live Gemini")
def test_live_argon_plan(client, user_id):
    flow, _ = run_to_schedule(client)
    data = flow.send("schedule", "next")
    print(data["llm_source"], [n["title"] for n in data["athlete_memory"]["curriculum_nodes"]], data["coach_message"])
    assert data["llm_source"] == "gemini" and len(data["athlete_memory"]["curriculum_nodes"]) == 5
