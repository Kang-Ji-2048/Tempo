"""POST /api/v1/profile (SportSelectionScreen) feeds athlete_memory, and onboarding keeps the picked skill."""
import uuid

from fastapi.testclient import TestClient

from backend import db_mongo, llm_config
from backend.main import app


def test_profile_syncs_sport_and_skill_into_onboarding(monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    client = TestClient(app)
    reg = client.post("/api/v1/auth/register", json={
        "email": f"profile_{uuid.uuid4().hex[:10]}@tempo.app", "password": "ProfileSync2026!", "display_name": "P"})
    assert reg.status_code == 201, reg.text
    user_id, headers = reg.json()["user_id"], {"Authorization": f"Bearer {reg.json()['access_token']}"}
    try:
        saved = client.post("/api/v1/profile", headers=headers, json={
            "sport": "tennis", "skill": "one_hand_backhand", "level": "intermediate", "goal": "technique_refinement",
            "playstyle": "all_court", "injuries": [], "reference_player": None})
        assert saved.status_code == 200
        memory = db_mongo.get_athlete_memory(user_id)
        assert (memory["sport"], memory["skill_focus"]) == ("tennis", "one_hand_backhand")

        step = client.post("/api/v1/onboarding/next", headers=headers,
                           json={"step_id": "sport", "answer": "tennis", "answers": {}}).json()
        assert step["step_id"] == "level_q1"
        assert db_mongo.get_athlete_memory(user_id)["skill_focus"] == "one_hand_backhand"
    finally:
        db = db_mongo.get_db()
        if db is not None:
            db[db_mongo.ATHLETE_MEMORY_COLLECTION].delete_many({"user_id": user_id})
            db["users"].delete_many({"user_id": user_id})
        db_mongo._MEMORY_ATHLETES.pop(user_id, None)
