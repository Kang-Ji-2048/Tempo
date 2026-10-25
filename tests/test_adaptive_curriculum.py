"""Phase D: clip ingest -> pro comparison -> adaptive curriculum in athlete_memory.

The heavy pose/vector pipeline is stubbed with a measured payload; athlete_memory and session
records go to MongoDB Atlas when reachable (backend/.env), else the in-process fallback.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import android_api, argon_analysis, coach_converse, db_mongo, llm_config
from test_auth_helpers import auth_headers

AXELSEN = next(p for p in db_mongo.PRO_REFERENCE_STROKES if p["player_name"] == "Viktor Axelsen")


def pipeline_payload(elbow, score, status):
    raw = {"right_elbow_contact_deg": elbow, "right_shoulder_abduction_deg": 150.0, "trunk_arch_deg": 160.0,
           "right_knee_flexion_deg": 145.0, "left_arm_balance_deg": 130.0, "contact_height_norm": 0.9}
    return {
        "session_id": "pipeline-id", "coaching_model": "gemini-4-argon", "coaching_status": "live",
        "llm_source": "gemini", "overall_score": score, "verification_status": status,
        "primary_flaw": f"Elbow at {elbow} deg", "biomechanical_diagnosis": f"Elbow measured {elbow} deg.",
        "live_drill_prescription": "3x10 shadow swings reaching to full extension.",
        "concise_audio_cue": "Reach tall", "demo_mode": False, "video_used": True,
        "pose_analysis": {"raw_angles": raw, "pose_vector": [0.9] * 6, "used_fallback": False},
        "pro_comparison": {"matched_pro": "Viktor Axelsen", "sport": "badminton", "similarity_score": 0.97,
                           "search_method": "mongodb_atlas_vector_search", "all_pro_matches": [AXELSEN]},
    }


@pytest.fixture
def user_id():
    uid = f"test_adapt_{uuid.uuid4().hex[:10]}"
    yield uid
    db = db_mongo.get_db()
    if db is not None:
        db[db_mongo.ATHLETE_MEMORY_COLLECTION].delete_many({"user_id": uid})
        db["android_sessions"].delete_many({"user_id": uid})
        db[db_mongo.SAINT_QUEUE_COLLECTION].delete_many({"user_id": uid})
        db["user_schedules"].delete_many({"_id": uid})
    db_mongo._MEMORY_ATHLETES.pop(uid, None)


@pytest.fixture
def athlete(user_id):
    """An onboarded intermediate badminton player with a catalog curriculum."""
    coach_converse.TheaToolbox(user_id).run("set_sport_and_goals", {"sport": "badminton"})
    coach_converse.TheaToolbox(user_id).run("set_athlete_level_and_generate_plan", {"level": "intermediate"})
    return user_id


def make_client(user_id, payload):
    analyze = AsyncMock(return_value=payload)
    app = FastAPI()
    app.include_router(android_api.create_android_router(analyze, lambda *a: None))
    return TestClient(app, headers=auth_headers(user_id=user_id, role="player")), analyze


def ingest(client, user_id, **extra):
    meta = {"user_id": user_id, "sport": "badminton", "stroke_type": "overhead_clear", "telemetry": [], **extra}
    res = client.post("/api/v1/sessions/ingest", data={"metadata": json.dumps(meta)},
                      files={"video": ("clip.mp4", b"video-bytes-" + uuid.uuid4().bytes, "video/mp4")})
    assert res.status_code == 202, res.text
    record = client.get(f"/api/v1/sessions/{res.json()['session_id']}").json()
    assert record["status"] == "COMPLETED", record.get("error_message")
    return record


def nodes_of(user_id):
    return db_mongo.get_athlete_memory(user_id)["curriculum_nodes"]


def test_passing_clip_completes_lesson_and_unlocks_next(athlete):
    first, second = nodes_of(athlete)[:2]
    client, analyze = make_client(athlete, pipeline_payload(elbow=171.0, score=86, status="PASS"))
    record = ingest(client, athlete)

    adaptation = record["adaptation"]
    assert adaptation["action"] == "lesson_completed"
    assert (adaptation["node_id"], adaptation["next_node_id"]) == (first["id"], second["id"])
    nodes = nodes_of(athlete)
    assert [nodes[0]["status"], nodes[1]["status"]] == ["completed", "active"]
    memory = db_mongo.get_athlete_memory(athlete)
    assert memory["last_completed_node"]["id"] == first["id"]
    assert memory["recent_flaws"][0]["overall_score"] == 86

    card = record["gemini_feedback"]["pro_comparison_card"]
    elbow = next(a for a in card["angles"] if a["metric"] == "right_elbow_contact_deg")
    assert (card["matched_pro"], elbow["athlete_deg"], elbow["pro_deg"], elbow["delta_deg"]) == (
        "Viktor Axelsen", 171.0, 176.0, -5.0)
    assert record["gemini_feedback"]["overall_score"] == 86
    path = record["active_widgets"][0]
    assert path["widget_type"] == "PathProgressWidget" and path["active_node_id"] == second["id"]
    assert analyze.await_args.kwargs["sport"] == "badminton"


def test_failing_clip_injects_remedial_drill_and_quiz(athlete):
    first = nodes_of(athlete)[0]
    client, _ = make_client(athlete, pipeline_payload(elbow=150.0, score=62, status="FAIL"))
    record = ingest(client, athlete)

    adaptation = record["adaptation"]
    assert adaptation["action"] == "remedial_assigned" and adaptation["node_id"] == first["id"]
    assert adaptation["threshold_deg"] == 165.0  # intermediate rubric
    assert [w["widget_type"] for w in record["active_widgets"]] == [
        "PathProgressWidget", "DrillCardWidget", "ConceptQuizWidget"]
    drill, quiz = record["active_widgets"][1], record["active_widgets"][2]
    assert drill["instruction"] == "3x10 shadow swings reaching to full extension."
    assert quiz["options"][quiz["correct_index"]].startswith("165 deg or more")
    assert "150 deg" in quiz["question"]

    memory = db_mongo.get_athlete_memory(athlete)
    node = memory["curriculum_nodes"][0]
    assert node["status"] == "active" and node["attempts"] == 1
    assert node["remedial_drill_id"] == drill["id"] and node["remedial_quiz"]["id"] == quiz["id"]
    assert [d["id"] for d in memory["assigned_drills"]] == [drill["id"]]

    # A second failed attempt replaces (not stacks) the lesson's remedial drill.
    client2, _ = make_client(athlete, pipeline_payload(elbow=152.0, score=64, status="FAIL"))
    ingest(client2, athlete)
    memory = db_mongo.get_athlete_memory(athlete)
    assert len(memory["assigned_drills"]) == 1 and memory["curriculum_nodes"][0]["attempts"] == 2


def test_locked_node_hint_falls_back_to_active_lesson(athlete):
    locked = nodes_of(athlete)[3]
    client, _ = make_client(athlete, pipeline_payload(elbow=171.0, score=90, status="PASS"))
    record = ingest(client, athlete, node_id=locked["id"])
    assert record["adaptation"]["node_id"] == nodes_of(athlete)[0]["id"]
    assert nodes_of(athlete)[3]["status"] == "locked"


def test_no_curriculum_records_flaw_only(user_id):
    client, _ = make_client(user_id, pipeline_payload(elbow=150.0, score=60, status="FAIL"))
    record = ingest(client, user_id)
    assert record["adaptation"]["action"] == "no_active_lesson"
    assert record["active_widgets"][0]["title"] == "Practice focus"
    assert db_mongo.get_athlete_memory(user_id)["recent_flaws"][0]["overall_score"] == 60


def test_sdui_actions_record_quiz_and_drill_completion(athlete):
    client, _ = make_client(athlete, pipeline_payload(elbow=150.0, score=62, status="FAIL"))
    record = ingest(client, athlete)
    drill, quiz = record["active_widgets"][1], record["active_widgets"][2]
    sid = record["session_id"]

    res = client.post("/api/v1/sdui/actions", json={"session_id": sid, "action_type": "QuizAnswered",
                                                    "widget_id": quiz["id"],
                                                    "payload": {"selected_index": quiz["correct_index"]}})
    assert res.status_code == 200
    answered = next(w for w in res.json()["widgets"] if w.get("id") == quiz["id"])
    assert answered["answered_index"] == quiz["correct_index"]
    assert nodes_of(athlete)[0]["remedial_quiz"]["is_correct"] is True

    res = client.post("/api/v1/sdui/actions", json={"session_id": sid, "action_type": "DrillCompleted",
                                                    "widget_id": drill["id"], "payload": {"reps_completed": 10}})
    assert drill["id"] not in [w.get("id") for w in res.json()["widgets"]]
    memory = db_mongo.get_athlete_memory(athlete)
    assert memory["assigned_drills"] == []
    assert memory["curriculum_nodes"][0]["completed_drills"][0]["reps_completed"] == 10
    stored = client.get(f"/api/v1/sessions/{sid}").json()
    assert drill["id"] not in [w.get("id") for w in stored["active_widgets"]]

    intruder = TestClient(client.app, headers=auth_headers(user_id="someone_else", role="player"))
    res = intruder.post("/api/v1/sdui/actions", json={"session_id": sid, "action_type": "DrillCompleted",
                                                      "widget_id": drill["id"]})
    assert res.status_code == 403


def test_home_feed_action_without_session_uses_memory(athlete):
    client, _ = make_client(athlete, pipeline_payload(elbow=150.0, score=62, status="FAIL"))
    res = client.post("/api/v1/sdui/actions", json={"session_id": "home_session", "action_type": "QuizAnswered",
                                                    "widget_id": "home_quiz_0", "payload": {"selected_index": 1}})
    assert res.status_code == 200
    widgets = res.json()["widgets"]
    assert widgets[0]["widget_type"] == "PathProgressWidget"
    assert next(w for w in widgets if w["widget_type"] == "ConceptQuizWidget")["answered_index"] == 1


@pytest.mark.parametrize("elbow,threshold,sim,expected", [
    (170.0, 165.0, 0.99, 98), (165.0, 165.0, 0.80, 80), (164.0, 165.0, 1.0, 79), (150.0, 165.0, 0.97, 56)])
def test_measured_score_agrees_with_pass_fail(elbow, threshold, sim, expected):
    assert argon_analysis.measured_score(elbow, threshold, sim) == expected


def test_argon_uses_memory_sport_level_and_clamps_inconsistent_gemini_score(user_id, monkeypatch):
    db_mongo.update_athlete_memory(user_id, {"sport": "tennis", "skill_focus": "forehand", "level": "advanced"})
    pose = {"right_elbow_contact_deg": 168.0, "right_shoulder_abduction_deg": 150.0, "trunk_arch_deg": 165.0}
    federer = next(p for p in db_mongo.PRO_REFERENCE_STROKES if p["player_name"] == "Roger Federer")
    sent = {}

    def generate_content(model, contents, config):
        sent["prompt"] = contents[0]
        return SimpleNamespace(text=json.dumps({
            "overall_score": 95, "verification_status": "PASS", "primary_flaw": "x", "biomechanical_diagnosis": "x",
            "live_drill_prescription": "x", "concise_audio_cue": "x", "coach_voice_note_script": "x",
            "saint_agent_job": {"plain_english_instruction": "x", "proactive_training_notification": "x",
                                "requires_human_approval": True, "approval_action_summary": "x"}}))

    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm_config, "get_client", lambda: SimpleNamespace(models=SimpleNamespace(
        generate_content=generate_content)))
    import asyncio
    result = asyncio.run(argon_analysis.run_biomechanical_analysis(
        user_name=user_id, sport_id="badminton", skill_id="overhead_clear", pose_data=pose,
        watch_metrics={}, pro_match={**federer, "similarity_score": 0.98}))

    assert (result["sport_id"], result["skill_id"], result["threshold_deg"]) == ("tennis", "forehand", 172.0)
    # 168 < 172 (advanced): measured FAIL wins over Gemini's PASS, and the score is pulled below 80.
    assert result["verification_status"] == "FAIL" and result["overall_score"] == 79
    assert "Pro Deltas" in sent["prompt"] and '"level": "advanced"' in sent["prompt"]
    elbow = next(d for d in result["pro_deltas"] if d["metric"] == "right_elbow_contact_deg")
    assert elbow["delta_deg"] == round(168.0 - federer["right_elbow_contact_deg"], 1)
