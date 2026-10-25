"""Phase E: /api/v1/live/stream grades streamed 33-landmark poses against the active skill.

Frames are synthetic but geometric: the arm and leg are built with exact elbow/knee angles,
so the measured angles and the cue chosen for each rep are deterministic.
"""
import math
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import android_api, db_mongo
from test_auth_helpers import auth_headers

SHOULDER, HIP = (0.5, 0.35), (0.5, 0.6)


def frame(ts, elbow_deg=180.0, knee_deg=175.0, arm_up=True, wrist_dx=0.0, visibility=0.99, hip_dx=0.0):
    lm = [[0.5, 0.5, 0.0, visibility] for _ in range(33)]
    sx, sy = SHOULDER
    bend = math.radians(180.0 - elbow_deg)
    if arm_up:
        ex, ey = sx, sy - 0.1
        wx, wy = ex + 0.1 * math.sin(bend), ey - 0.1 * math.cos(bend)
    else:
        ex, ey = sx, sy + 0.1
        wx, wy = ex + 0.1 * math.sin(bend), ey + 0.1 * math.cos(bend)
    hx, hy = HIP[0] + hip_dx, HIP[1]
    kx, ky = hx, hy + 0.15
    flex = math.radians(180.0 - knee_deg)
    ax, ay = kx + 0.15 * math.sin(flex), ky + 0.15 * math.cos(flex)
    for idx, (x, y) in {12: (sx, sy), 14: (ex, ey), 16: (wx + wrist_dx, wy), 24: (hx, hy), 23: (hx, hy),
                        26: (kx, ky), 28: (ax, ay)}.items():
        lm[idx] = [x, y, 0.0, visibility]
    return {"type": "pose", "timestamp_ms": ts, "landmarks": lm, "aspect": 1.0}


def overhead_rep(start_ms, elbow_deg, knee_deg=140.0):
    """Load with bent knees, cock the arm, reach to contact at elbow_deg (the highest wrist point), come down."""
    frames = [frame(start_ms, knee_deg=knee_deg, arm_up=False)]
    frames += [frame(start_ms + 100 * i, elbow_deg=elbow_deg if i == 3 else 120.0, knee_deg=knee_deg if i < 3 else 175.0)
               for i in range(1, 6)]
    frames.append(frame(start_ms + 700, arm_up=False))
    return frames


def collect_cues(ws, frames):
    """Send frames; each message type is pulled by sending a refresh marker and draining until the session echo."""
    messages = []
    for f in frames:
        ws.send_json(f)
    ws.send_json({"type": "refresh"})
    while True:
        msg = ws.receive_json()
        if msg.get("type") == "session":
            return messages
        messages.append(msg)


@pytest.fixture
def user_id():
    uid = f"test_live_{uuid.uuid4().hex[:10]}"
    yield uid
    db = db_mongo.get_db()
    if db is not None:
        db[db_mongo.ATHLETE_MEMORY_COLLECTION].delete_many({"user_id": uid})
    db_mongo._MEMORY_ATHLETES.pop(uid, None)


@pytest.fixture
def client(user_id):
    db_mongo.update_athlete_memory(user_id, {"sport": "badminton", "skill_focus": "overhead_clear",
                                             "level": "intermediate"})
    app = FastAPI()
    app.include_router(android_api.create_android_router(AsyncMock(), lambda *a: None))
    return TestClient(app, headers=auth_headers(user_id=user_id, role="player"))


def connect(client, user_id):
    return client.websocket_connect(f"/api/v1/live/stream?user_id={user_id}")


def test_hello_describes_active_skill_from_memory(client, user_id):
    with connect(client, user_id) as ws:
        ws.send_json({"type": "hello"})
        session = ws.receive_json()
    assert session == {"type": "session", "sport": "badminton", "skill": "overhead_clear", "level": "intermediate",
                       "threshold_deg": 165.0, "active_lesson": None, "mode": "overhead_peak"}


@pytest.mark.parametrize("elbow,knee,expected,focus", [
    (150.0, 140.0, "Straighten your elbow and reach higher at contact.", "elbow"),
    (161.0, 140.0, "Almost there. Extend a little more at contact.", "elbow"),
    (170.0, 172.0, "Bend your knees more before you swing.", "knee"),
    (170.0, 140.0, "Great rep. Keep that full extension.", "positive"),
])
def test_each_rep_gets_one_short_cue(client, user_id, elbow, knee, expected, focus):
    with connect(client, user_id) as ws:
        messages = collect_cues(ws, overhead_rep(10_000, elbow_deg=elbow, knee_deg=knee))
    cues = [m for m in messages if m["type"] == "cue"]
    assert len(cues) == 1
    cue = cues[0]
    assert (cue["cue"], cue["focus"], cue["rep"], cue["vision_analyzed"]) == (expected, focus, 1, True)
    assert len(cue["cue"].split()) <= 10
    assert cue["metrics"]["elbow_at_contact_deg"] == pytest.approx(elbow, abs=0.5)
    assert cue["metrics"]["threshold_deg"] == 165.0
    metrics = [m for m in messages if m["type"] == "metrics"]
    assert metrics and all("elbow_deg" in m and "knee_deg" in m for m in metrics)  # ~2 Hz live readout


def test_slow_recovery_is_cued_on_the_next_rep(client, user_id):
    rep1 = overhead_rep(10_000, elbow_deg=172.0)
    drift = [frame(10_800 + 200 * i, arm_up=False, hip_dx=0.2) for i in range(10)]  # stays off base for 2s
    rep2 = overhead_rep(13_000, elbow_deg=172.0)
    with connect(client, user_id) as ws:
        cues = [m["cue"] for m in collect_cues(ws, rep1 + drift + rep2) if m["type"] == "cue"]
    assert cues == ["Great rep. Keep that full extension.", "Recover to base faster after each shot."]


def test_hidden_body_gets_one_framing_cue_per_ten_seconds(client, user_id):
    hidden = [frame(1_000 + 100 * i, visibility=0.1) for i in range(30)] + [frame(11_500, visibility=0.1)]
    with connect(client, user_id) as ws:
        cues = [m for m in collect_cues(ws, hidden) if m["type"] == "cue"]
    assert [c["focus"] for c in cues] == ["framing", "framing"]
    assert cues[0]["cue"] == "Step back so your whole body is visible."


def test_refresh_picks_up_voice_driven_level_change(client, user_id):
    with connect(client, user_id) as ws:
        ws.send_json({"type": "hello"})
        assert ws.receive_json()["threshold_deg"] == 165.0
        db_mongo.update_athlete_memory(user_id, {"level": "advanced"})
        ws.send_json({"type": "refresh"})
        assert ws.receive_json()["threshold_deg"] == 172.0
        cues = [m for m in collect_cues(ws, overhead_rep(20_000, elbow_deg=168.0)) if m["type"] == "cue"]
    assert cues[0]["focus"] == "elbow"  # 168 passes intermediate (165) but not advanced (172)


def test_groundstroke_reps_use_wrist_speed(client, user_id):
    db_mongo.update_athlete_memory(user_id, {"sport": "tennis", "skill_focus": "forehand", "level": "beginner"})
    swing = [frame(5_000 + 40 * i, elbow_deg=150.0, arm_up=False, wrist_dx=0.12 * i) for i in range(6)]
    settle = [frame(5_240 + 100 * i, elbow_deg=150.0, arm_up=False, wrist_dx=0.6) for i in range(1, 4)]
    with connect(client, user_id) as ws:
        ws.send_json({"type": "hello"})
        assert ws.receive_json()["mode"] == "swing_speed"
        cues = [m for m in collect_cues(ws, swing + settle) if m["type"] == "cue"]
    assert len(cues) == 1 and cues[0]["skill"] == "forehand"
    assert cues[0]["metrics"]["threshold_deg"] == 160.0


def test_malformed_pose_keeps_connection_and_other_users_are_rejected(client, user_id):
    with connect(client, user_id) as ws:
        ws.send_json({"type": "pose", "timestamp_ms": 1, "landmarks": [[0.5, 0.5]]})
        assert "error" in ws.receive_json()
        ws.send_json({"heart_rate": 140})
        assert ws.receive_json()["source"] == "heart_rate_rule_only"
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/live/stream?user_id=someone_else") as ws:
            ws.receive_json()
    assert exc.value.code == 4403
