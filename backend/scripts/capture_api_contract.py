#!/usr/bin/env python3
"""Capture real backend responses for the Android DTO contract test.

Drives a fresh athlete through sign-up -> POST /profile -> GET /auth/me -> every
/onboarding/next step ("Build my plan") -> GET /coach/memory -> POST /coach/converse,
writing each response body to android/app/src/test/resources/contract/. ApiContractTest
decodes them with the app's Json config, so a backend shape change fails a unit test
instead of the app on a 200.

    uv run python backend/scripts/capture_api_contract.py   # needs the server on :8000
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "android" / "app" / "src" / "test" / "resources" / "contract"
BASE = os.environ.get("TEMPO_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def save(name: str, res: requests.Response) -> dict:
    assert res.status_code in (200, 201), f"{name}: HTTP {res.status_code} {res.text[:200]}"
    body = res.json()
    # Fixtures are committed: never write a live credential.
    stored = {**body, "access_token": "redacted-test-token"} if isinstance(body, dict) and "access_token" in body else body
    (OUT / f"{name}.json").write_text(json.dumps(stored, indent=2, default=str) + "\n")
    print(f"  {name}.json")
    return body


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    email = f"contract_{int(time.time())}@tempo.app"
    reg = save("auth_register", requests.post(f"{BASE}/api/v1/auth/register", timeout=15, json={
        "email": email, "password": "ContractTest2026!", "display_name": "Contract Athlete"}))
    h = {"Authorization": f"Bearer {reg['access_token']}"}

    save("auth_me_fresh", requests.get(f"{BASE}/api/v1/auth/me", headers=h, timeout=15))
    save("sports", requests.get(f"{BASE}/api/v1/sports", timeout=15))
    # Exactly what SportSelectionViewModel sends for Tennis + one-handed backhand.
    save("profile_update", requests.post(f"{BASE}/api/v1/profile", headers=h, timeout=15, json={
        "sport": "tennis", "skill": "one_hand_backhand", "level": "intermediate", "goal": "technique_refinement",
        "playstyle": "all_court", "injuries": [], "reference_player": None}))
    save("auth_me_after_profile", requests.get(f"{BASE}/api/v1/auth/me", headers=h, timeout=15))

    answers: dict = {}
    steps = [("sport", "tennis"), ("level_q1", "1"), ("level_q2", "0"), ("goal", "social_match_play"),
             ("intensity", "regular_3x"),
             ("schedule", json.dumps({"days_of_week": ["Monday", "Wednesday", "Saturday"],
                                      "target_time_utc": "18:00", "preferred_channel": "whatsapp"}))]
    for step_id, answer in steps:
        answers[step_id] = answer
        body = save(f"onboarding_after_{step_id}", requests.post(
            f"{BASE}/api/v1/onboarding/next", headers=h, timeout=120,
            json={"step_id": step_id, "answer": answer, "answers": answers}))
    assert body["is_completed"], "onboarding did not complete"

    memory = save("coach_memory", requests.get(f"{BASE}/api/v1/coach/memory", headers=h, timeout=15))
    assert memory["athlete_memory"]["skill_focus"] == "one_hand_backhand", "picked skill was not kept"
    save("coach_converse", requests.post(f"{BASE}/api/v1/coach/converse", headers=h, timeout=120,
                                         json={"message": "What's my first lesson?", "channel": "app"}))
    print(f"Captured contract fixtures for {reg['user_id']} into {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
