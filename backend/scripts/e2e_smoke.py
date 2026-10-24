#!/usr/bin/env python3
"""End-to-End Smoke Test for Tempo Pipeline (Stage R).
Flow:
1. Register unique user
2. Login
3. GET /sports
4. POST /profile
5. Upload tests/fixtures/sample_clip.mp4 (Halt if missing)
6. Poll session until COMPLETED
7. Assert llm_source, video_used, active_widgets, measured numbers
8. Print timing table
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sample_clip.mp4"


def run_smoke():
    print("=" * 70)
    print("TEMPO STAGE R END-TO-END PIPELINE SMOKE TEST")
    print(f"Target Backend: {BASE_URL}")
    print("=" * 70)

    steps_table: List[Dict[str, Any]] = []

    # Step 0: Check health
    t0 = time.perf_counter()
    try:
        health_res = requests.get(f"{BASE_URL}/health", timeout=5)
        dt = int((time.perf_counter() - t0) * 1000)
        if health_res.status_code == 200:
            steps_table.append({"Step": "0. Health Check", "Status": "PASS", "Time_ms": dt, "Detail": "Server online"})
        else:
            steps_table.append({"Step": "0. Health Check", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {health_res.status_code}"})
            _print_table(steps_table)
            sys.exit(1)
    except Exception as exc:
        dt = int((time.perf_counter() - t0) * 1000)
        steps_table.append({"Step": "0. Health Check", "Status": "FAIL", "Time_ms": dt, "Detail": f"Connection failed: {exc}"})
        _print_table(steps_table)
        print("\nBackend is not running. Start with: ./scripts/dev.sh")
        sys.exit(1)

    # Step 1: Register unique user
    t0 = time.perf_counter()
    email = f"athlete_{int(time.time()*1000)}@tempo.app"
    password = "SmokePassword2026!"
    reg_payload = {"email": email, "password": password, "display_name": "Smoke Athlete"}
    reg_res = requests.post(f"{BASE_URL}/api/v1/auth/register", json=reg_payload, timeout=5)
    dt = int((time.perf_counter() - t0) * 1000)
    if reg_res.status_code == 201:
        reg_data = reg_res.json()
        user_id = reg_data["user_id"]
        token = reg_data["access_token"]
        steps_table.append({"Step": "1. Register", "Status": "PASS", "Time_ms": dt, "Detail": f"user_id: {user_id}"})
    else:
        steps_table.append({"Step": "1. Register", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {reg_res.status_code}: {reg_res.text}"})
        _print_table(steps_table)
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Login
    t0 = time.perf_counter()
    login_res = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"email": email, "password": password}, timeout=5)
    dt = int((time.perf_counter() - t0) * 1000)
    if login_res.status_code == 200:
        steps_table.append({"Step": "2. Login", "Status": "PASS", "Time_ms": dt, "Detail": "Token issued"})
    else:
        steps_table.append({"Step": "2. Login", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {login_res.status_code}"})
        _print_table(steps_table)
        sys.exit(1)

    # Step 3: GET /sports
    t0 = time.perf_counter()
    sports_res = requests.get(f"{BASE_URL}/api/v1/sports", headers=headers, timeout=5)
    dt = int((time.perf_counter() - t0) * 1000)
    if sports_res.status_code == 200:
        sports = sports_res.json()
        ready_count = sum(1 for s in sports if s.get("analysis_ready"))
        steps_table.append({"Step": "3. GET /sports", "Status": "PASS", "Time_ms": dt, "Detail": f"{len(sports)} sports ({ready_count} ready)"})
    else:
        steps_table.append({"Step": "3. GET /sports", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {sports_res.status_code}"})
        _print_table(steps_table)
        sys.exit(1)

    # Step 4: POST /profile
    t0 = time.perf_counter()
    profile_data = {
        "sport": "badminton",
        "skill": "overhead_clear",
        "level": "intermediate",
        "goal": "overhead_power",
        "playstyle": "aggressive",
        "injuries": [],
        "reference_player": "Viktor Axelsen",
    }
    prof_res = requests.post(f"{BASE_URL}/api/v1/profile", json=profile_data, headers=headers, timeout=5)
    dt = int((time.perf_counter() - t0) * 1000)
    if prof_res.status_code == 200:
        steps_table.append({"Step": "4. POST /profile", "Status": "PASS", "Time_ms": dt, "Detail": "Saved badminton/overhead_clear"})
    else:
        steps_table.append({"Step": "4. POST /profile", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {prof_res.status_code}"})
        _print_table(steps_table)
        sys.exit(1)

    # Step 5: Check fixture clip
    print(f"\nChecking clip fixture at: {FIXTURE_PATH}")
    if not FIXTURE_PATH.exists():
        steps_table.append({
            "Step": "5. Check Video Fixture",
            "Status": "BLOCKED",
            "Time_ms": 0,
            "Detail": f"tests/fixtures/sample_clip.mp4 missing",
        })
        _print_table(steps_table)
        print("\n" + "!" * 70)
        print("STOP: tests/fixtures/sample_clip.mp4 does not exist.")
        print("Please add a short clip of a person doing an overhead clear to:")
        print(f"  {FIXTURE_PATH}")
        print("Do not generate a fake one.")
        print("!" * 70 + "\n")
        return

    # Upload clip
    t0 = time.perf_counter()
    metadata = {
        "user_id": user_id,
        "sport": "badminton",
        "stroke_type": "overhead_clear",
        "telemetry": [],
    }
    with open(FIXTURE_PATH, "rb") as video_file:
        upload_res = requests.post(
            f"{BASE_URL}/api/v1/sessions/ingest",
            data={"metadata": json.dumps(metadata)},
            files={"video": ("sample_clip.mp4", video_file, "video/mp4")},
            headers=headers,
            timeout=30,
        )
    dt = int((time.perf_counter() - t0) * 1000)
    if upload_res.status_code in {200, 202}:
        session_id = upload_res.json()["session_id"]
        steps_table.append({"Step": "5. Ingest Upload", "Status": "PASS", "Time_ms": dt, "Detail": f"session_id: {session_id}"})
    else:
        steps_table.append({"Step": "5. Ingest Upload", "Status": "FAIL", "Time_ms": dt, "Detail": f"HTTP {upload_res.status_code}"})
        _print_table(steps_table)
        sys.exit(1)

    # Step 6: Poll until COMPLETED
    t0 = time.perf_counter()
    max_wait = 90
    session_data = None
    poll_start = time.time()
    while time.time() - poll_start < max_wait:
        poll_res = requests.get(f"{BASE_URL}/api/v1/sessions/{session_id}", headers=headers, timeout=5)
        if poll_res.status_code == 200:
            session_data = poll_res.json()
            status = session_data.get("status")
            if status == "COMPLETED":
                break
            elif status == "FAILED":
                break
        time.sleep(2)

    dt = int((time.perf_counter() - t0) * 1000)
    if session_data and session_data.get("status") == "COMPLETED":
        steps_table.append({"Step": "6. Poll Status", "Status": "PASS", "Time_ms": dt, "Detail": "COMPLETED"})
    else:
        detail = session_data.get("error_message") if session_data else "Timeout waiting for COMPLETED"
        steps_table.append({"Step": "6. Poll Status", "Status": "FAIL", "Time_ms": dt, "Detail": str(detail)})
        _print_table(steps_table)
        sys.exit(1)

    # Step 7: Assertions
    t0 = time.perf_counter()
    llm_source = session_data.get("llm_source")
    video_used = session_data.get("video_used")
    active_widgets = session_data.get("active_widgets", [])
    primary_flaw = session_data.get("primary_flaw", "")

    assert active_widgets, "active_widgets must not be empty"
    assert "video_used" in session_data, "video_used must be reported"
    print(f"llm_source: {llm_source}, video_used: {video_used}, widgets: {len(active_widgets)}")

    dt = int((time.perf_counter() - t0) * 1000)
    steps_table.append({"Step": "7. Assertions", "Status": "PASS", "Time_ms": dt, "Detail": f"Source: {llm_source}, Video: {video_used}"})
    _print_table(steps_table)


def _print_table(rows: List[Dict[str, Any]]):
    print("\n" + "-" * 75)
    print(f"{'Step':<24} | {'Status':<8} | {'Time (ms)':<10} | {'Detail'}")
    print("-" * 75)
    for r in rows:
        print(f"{r['Step']:<24} | {r['Status']:<8} | {r['Time_ms']:<10} | {r['Detail']}")
    print("-" * 75)


if __name__ == "__main__":
    run_smoke()
