"""Multi-stroke kinematics, live set fulfillment, and never-fail uploads.

a) RepTracker phases/classification/grading for badminton + tennis (and left-handers), drift, combos.
b) /api/v1/live/stream v2: keypoints -> rep_completed -> drill_fulfilled marks the lesson complete,
   unlocks the next node and writes a session record; voice_query answers mid-set.
c) Thea's tool suite (see the tool tests at the bottom).
d) Non-overhead uploads complete instead of failing with fallback_no_reliable_overhead_pose.

Pose sequences come from tests/support/swing_synth.py: geometric keyframes with exact joint angles.
"""
import json
import uuid
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import android_api, coach_converse, db_mongo, kinematics_engine as ke, llm_config
from test_auth_helpers import auth_headers
from tests.support import swing_synth as synth

HOLD = [(0.6, synth.pose())]
STANCE = synth.interpolate([(2.0, synth.pose())])  # side-lock + baseline before the set


def track(frames, sport, target, aspect=1.0):
    side = ke.detect_side([lm for _, lm in frames], aspect)
    tracker = ke.RepTracker(target, sport, side)
    transitions = []
    for t, lm in frames:
        tracker.feed(ke.frame_features(lm, t, side, aspect))
        transitions += tracker.transitions
    return side, transitions, tracker.reps


# ---------------------------------------------------------------------------
# a) Kinematic engine
# ---------------------------------------------------------------------------

def test_overhead_clear_passes_all_four_phases_and_grades_extension():
    _, transitions, reps = track(synth.sequence(synth.overhead_clear(), synth.overhead_clear(150) + HOLD),
                                 "badminton", "overhead_clear")
    assert transitions[:5] == ["PREPARATION", "LOADING", "IMPACT", "FOLLOW_THROUGH", "READY"]
    assert [r.detected_stroke for r in reps] == ["overhead_clear", "overhead_clear"]
    good, bent = reps
    assert good.rep_counted and good.quality_score >= 90
    assert [k.phase for k in good.keyframes] == ["Preparation", "Loading", "Impact", "Follow-Through"]
    assert bent.phase_angles["impact_elbow_deg"] == pytest.approx(150, abs=1)
    assert bent.primary_deviation.startswith("Elbow at contact: 150°")
    assert len(good.pose_vector_6d) == 6 and all(0 <= v <= 1 for v in good.pose_vector_6d)


@pytest.mark.parametrize("keys,sport,target,stroke", [
    (synth.overhead_clear(jump=0.06), "badminton", "jump_smash", "jump_smash"),
    (synth.lunge(), "badminton", "net_lunge_defense", "net_lunge_defense"),
    (synth.forehand(), "tennis", "forehand_topspin", "forehand_topspin"),
    (synth.one_handed_backhand(), "tennis", "one_handed_backhand", "one_handed_backhand"),
])
def test_each_stroke_archetype_is_detected(keys, sport, target, stroke):
    _, transitions, reps = track(synth.sequence(keys + HOLD), sport, target)
    assert "IMPACT" in transitions and transitions[-1] == "READY"
    assert [r.detected_stroke for r in reps] == [stroke]
    assert reps[0].rep_counted


def test_faults_are_named_with_numbers():
    _, _, reps = track(synth.sequence(synth.forehand(drop=False, contact_x=0.55, high_finish=False) + HOLD),
                       "tennis", "forehand_topspin")
    assert reps[0].quality_score < 60 and not reps[0].rep_counted
    assert "body heights" in reps[0].primary_deviation or "racket drop" in reps[0].primary_deviation
    _, _, lunges = track(synth.sequence(synth.lunge(knee_deg=150, lean_deg=40) + HOLD), "badminton", "net_lunge_defense")
    assert "Trunk lean: 40°" in lunges[0].primary_deviation


def test_wrong_stroke_does_not_count():
    _, _, reps = track(synth.sequence(synth.forehand() + HOLD), "tennis", "one_handed_backhand")
    assert reps[0].detected_stroke == "forehand_topspin" and not reps[0].rep_counted
    assert "not a one-handed backhand" in reps[0].primary_deviation


def test_left_handed_player_is_measured_on_the_left_arm():
    side, _, reps = track(synth.mirror(synth.sequence(synth.overhead_clear(155) + HOLD)), "badminton", "overhead_clear")
    assert side == "left"
    assert reps[0].side == "left" and reps[0].phase_angles["impact_elbow_deg"] == pytest.approx(155, abs=1)


def test_standing_still_is_never_a_rep():
    assert track(synth.sequence([(3.0, synth.pose())]), "badminton", "overhead_clear")[2] == []


def test_drift_and_heart_rate_fatigue_correlation():
    good = [synth.overhead_clear(172, 130) for _ in range(3)]
    tired = [synth.overhead_clear(152, 165) for _ in range(3)]
    frames = synth.sequence(*good, *tired[:-1], tired[-1] + HOLD)
    tracker = ke.RepTracker("overhead_clear", "badminton", "right")
    for t, lm in frames:
        tracker.feed(ke.frame_features(lm, t, "right", 1.0), heart_rate=150 if t < 6000 else 172)
    analysis = ke.session_analysis(tracker.reps)
    assert analysis["drift"]["detected"] and analysis["drift"]["knee_bend_loss_deg"] >= 8
    assert "legs are getting tired" in analysis["drift"]["message"]
    assert analysis["fatigue_correlated"] is True


def test_combo_drill_sequence_compliance():
    frames = synth.sequence(synth.overhead_clear(), synth.lunge(), synth.overhead_clear(), synth.lunge() + HOLD)
    multi = ke.MultiTracker(["overhead_clear", "net_lunge_defense"], "badminton", "right")
    for t, lm in frames:
        multi.feed(ke.frame_features(lm, t, "right", 1.0))
    assert [r.detected_stroke for r in multi.reps] == ["overhead_clear", "net_lunge_defense"] * 2
    compliance = ke.session_analysis(multi.reps, multi.sequence)["sequence_compliance"]
    assert compliance["ratio"] == 1.0 and compliance["next_expected"] == "overhead_clear"


# ---------------------------------------------------------------------------
# b) Live stream v2 + fulfillment
# ---------------------------------------------------------------------------

@pytest.fixture
def user_id():
    uid = f"test_live2_{uuid.uuid4().hex[:10]}"
    yield uid
    db = db_mongo.get_db()
    if db is not None:
        db[db_mongo.ATHLETE_MEMORY_COLLECTION].delete_many({"user_id": uid})
        db["android_sessions"].delete_many({"user_id": uid})
        db[db_mongo.SAINT_QUEUE_COLLECTION].delete_many({"user_id": uid})
        db["user_schedules"].delete_many({"_id": uid})
    db_mongo._MEMORY_ATHLETES.pop(uid, None)


@pytest.fixture
def athlete(user_id, monkeypatch):
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    monkeypatch.delenv("SAINT_WEBHOOK_URL", raising=False)
    box = coach_converse.TheaToolbox(user_id)
    box.run("set_sport_and_goals", {"sport": "badminton"})
    box.run("set_athlete_level_and_generate_plan", {"level": "intermediate"})
    # A short live drill so the set completes in a handful of reps.
    db_mongo.update_athlete_memory(user_id, {"assigned_drills": [{
        "id": "drill_live_three", "title": "3 Clean Clears", "instruction": "Three full-extension clears.",
        "target_reps": 3, "focus_cue": "Reach tall", "stroke_type": "overhead_clear"}]})
    return user_id


def saint_log(user_id):
    db = db_mongo.get_db()
    if db is not None:
        return list(db[db_mongo.SAINT_QUEUE_COLLECTION].find({"user_id": user_id}))
    return [n for n in db_mongo._MEMORY_SAINT_QUEUE if n.get("user_id") == user_id]


def client_for(user_id):
    app = FastAPI()
    app.include_router(android_api.create_android_router(AsyncMock(), lambda *a: None))
    return TestClient(app, headers=auth_headers(user_id=user_id, role="player"))


def keypoints(frames, heart_rate=None):
    return [{"type": "keypoints", "timestamp_ms": t, "landmarks": lm, "aspect": 1.0,
             **({"heart_rate": heart_rate} if heart_rate else {})} for t, lm in frames]


def send_all(ws, packets):
    """Send packets, then drain everything the server produced up to a ping/pong marker."""
    for packet in packets:
        ws.send_json(packet)
    nonce = uuid.uuid4().hex
    ws.send_json({"type": "ping", "nonce": nonce})
    out = []
    while True:
        message = ws.receive_json()
        if message.get("type") == "pong" and message.get("nonce") == nonce:
            return out
        out.append(message)


def test_live_set_reaching_target_completes_lesson_and_saves_session(athlete):
    first_node = db_mongo.get_athlete_memory(athlete)["curriculum_nodes"][0]
    client = client_for(athlete)
    with client.websocket_connect(f"/api/v1/live/stream?user_id={athlete}") as ws:
        ws.send_json({"type": "hello"})
        session = ws.receive_json()
        assert (session["drill_id"], session["target_reps"], session["target_stroke"]) == (
            "drill_live_three", 3, "overhead_clear")
        frames = synth.sequence([(2.0, synth.pose())], synth.overhead_clear(), synth.overhead_clear(),
                                synth.overhead_clear() + HOLD)
        messages = send_all(ws, keypoints(frames, heart_rate=150))

    types = [m.get("type") for m in messages]
    phases = [m["phase"] for m in messages if m.get("type") == "phase_update"]
    assert {"PREPARATION", "LOADING", "IMPACT", "FOLLOW_THROUGH"} <= set(phases)
    reps = [m for m in messages if m.get("type") == "rep_completed"]
    assert [r["rep_index"] for r in reps] == [1, 2, 3] and all(r["rep_counted"] for r in reps)
    assert reps[-1]["cue_text"].endswith("Set complete!") and reps[0]["detected_stroke"] == "overhead_clear"
    assert reps[0]["pro_match"] and "%" in reps[0]["pro_match"]  # Atlas $vectorSearch per rep
    done = next(m for m in messages if m.get("type") == "drill_fulfilled")
    assert types.index("drill_fulfilled") > types.index("rep_completed")
    assert done["passed"] and done["completed_node_title"] == first_node["title"] and done["unlocked_next_node"]
    assert "I've marked" in done["summary_speak"]

    memory = db_mongo.get_athlete_memory(athlete)
    nodes = memory["curriculum_nodes"]
    assert [nodes[0]["status"], nodes[1]["status"]] == ["completed", "active"]
    assert memory["last_completed_node"]["id"] == first_node["id"]
    assert all(d["id"] != "drill_live_three" for d in memory.get("assigned_drills") or [])
    record = android_api._get("android_sessions", done["session_id"])
    assert record["status"] == "COMPLETED" and record["source"] == "live" and len(record["rep_log"]) == 3
    assert record["adaptation"]["action"] == "lesson_completed"
    assert [p["phase_name"] for p in record["gemini_feedback"]["kinetic_phases"]] == [
        "Preparation", "Loading", "Impact", "Follow-Through"]
    debrief = [n for n in saint_log(athlete) if n.get("type") == "post_session_debrief"]
    assert debrief and debrief[0]["event_type"] == "POST_SESSION_DEBRIEF"


def test_finishing_a_weak_set_saves_it_and_assigns_remedial_work(athlete):
    client = client_for(athlete)
    with client.websocket_connect(f"/api/v1/live/stream?user_id={athlete}") as ws:
        frames = synth.sequence([(2.0, synth.pose())], synth.overhead_clear(140), synth.overhead_clear(142) + HOLD)
        send_all(ws, keypoints(frames))
        ws.send_json({"type": "complete_session"})
        done = ws.receive_json()
    assert done["type"] == "drill_fulfilled" and not done["passed"] and done["action"] == "remedial_assigned"
    memory = db_mongo.get_athlete_memory(athlete)
    assert memory["curriculum_nodes"][0]["status"] == "active" and memory["curriculum_nodes"][0]["attempts"] == 1
    assert any(d.get("source_session_id") == done["session_id"] for d in memory["assigned_drills"])
    assert android_api._get("android_sessions", done["session_id"])["adaptation"]["action"] == "remedial_assigned"


def test_voice_query_answers_mid_set_and_reloads_the_drill(athlete):
    client = client_for(athlete)
    with client.websocket_connect(f"/api/v1/live/stream?user_id={athlete}") as ws:
        ws.send_json({"type": "voice_query", "text": "I'm advanced now"})
        reply = ws.receive_json()
        assert reply["type"] == "voice_reply" and reply["bypass_rate_limit"] is True
        assert reply["speak_text"] and "set_athlete_level_and_generate_plan" in reply["tool_actions_taken"]
        session = ws.receive_json()
        assert session["type"] == "session" and session["threshold_deg"] == 172.0  # advanced rubric


def test_start_drill_binds_a_lesson_node(athlete):
    node = db_mongo.get_athlete_memory(athlete)["curriculum_nodes"][1]
    client = client_for(athlete)
    with client.websocket_connect(f"/api/v1/live/stream?user_id={athlete}") as ws:
        ws.send_json({"type": "start_drill", "node_id": node["id"], "drill_id": "drill_lunge_recover"})
        session = ws.receive_json()
    assert session["node_id"] == node["id"] and session["drill_id"] == "drill_lunge_recover"
    assert session["target_stroke"] == "net_lunge_defense" and session["mode"] == "footwork"


def test_framing_cue_is_throttled_and_bad_packets_keep_the_socket(athlete):
    client = client_for(athlete)
    hidden = [(1_000 + 100 * i, synth.landmarks(synth.pose(), visibility=0.1)) for i in range(30)] + [
        (11_500, synth.landmarks(synth.pose(), visibility=0.1))]
    with client.websocket_connect(f"/api/v1/live/stream?user_id={athlete}") as ws:
        messages = send_all(ws, keypoints(hidden))
        ws.send_json({"type": "keypoints", "timestamp_ms": 1, "landmarks": [[0.5, 0.5]]})
        assert "error" in ws.receive_json()
        ws.send_json({"heart_rate": 140})
        assert ws.receive_json()["source"] == "heart_rate_rule_only"
    assert [m["focus"] for m in messages if m.get("type") == "cue"] == ["framing", "framing"]
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/live/stream?user_id=someone_else") as ws:
            ws.receive_json()
    assert exc.value.code == 4403


# ---------------------------------------------------------------------------
# d) Uploads of non-overhead strokes complete
# ---------------------------------------------------------------------------

def _mp_frames(frames):
    """Turn synth frames into fake MediaPipe results for etl_pose's VIDEO loop."""
    out = []
    for _, lm in frames:
        image = [NS(x=p[0], y=p[1], z=p[2], visibility=p[3], presence=p[3]) for p in lm]
        world = [NS(x=p[0], y=p[1], z=p[2]) for p in lm]
        out.append(NS(pose_landmarks=[image], pose_world_landmarks=[world]))
    return out


def test_forehand_clip_is_segmented_into_reps_and_phases(tmp_path):
    from backend import etl_pose
    frames = synth.sequence(synth.forehand(), synth.forehand() + HOLD)
    results = _mp_frames(frames)
    runtime = NS(tasks=NS(vision=NS(PoseLandmarker=NS(create_from_options=None),
                                    PoseLandmarkerOptions=lambda **k: None, RunningMode=NS(VIDEO="VIDEO")),
                          BaseOptions=lambda **k: None),
                 Image=lambda **k: None, ImageFormat=NS(SRGB="SRGB"))
    detector = NS(detect_for_video=lambda image, ts, it=iter(results): next(it))
    runtime.tasks.vision.PoseLandmarker.create_from_options = lambda o: NS(
        __enter__=lambda: detector, __exit__=lambda *a: False)

    class Ctx:
        def __enter__(self):
            return detector

        def __exit__(self, *a):
            return False
    runtime.tasks.vision.PoseLandmarker.create_from_options = lambda o: Ctx()

    import numpy as np
    stamps = iter([t for t, _ in frames])

    class Cap:
        def __init__(self):
            self.left = len(frames)

        def isOpened(self):
            return True

        def read(self):
            if self.left == 0:
                return False, None
            self.left -= 1
            return True, np.zeros((100, 100, 3), dtype=np.uint8)

        def get(self, prop):
            return 15.0 if prop == etl_pose.cv2.CAP_PROP_FPS else float(next(stamps))

        def release(self):
            pass

    video = tmp_path / "forehand.mp4"
    video.write_bytes(b"x")
    model = tmp_path / "pose.task"
    model.write_bytes(b"x")
    with patch.object(etl_pose, "mp", runtime), patch.object(etl_pose, "_ensure_mediapipe_loaded", return_value=True), \
            patch.object(etl_pose, "pose_model_path", return_value=model), \
            patch.object(etl_pose.cv2, "VideoCapture", return_value=Cap()):
        result = etl_pose.extract_pose_from_video(str(video), "tennis", "forehand_topspin")
    assert result["status"] == "detected" and not result["used_fallback"]
    assert result["contact_selection"] == "rep_tracker_impact" and result["overhead_contact_detected"] is False
    reps = result["rep_analysis"]
    assert reps["rep_count"] == 2 and reps["detected_stroke"] == "forehand_topspin"
    assert [p["phase_name"] for p in reps["kinetic_phases"]] == ["Preparation", "Loading", "Impact", "Follow-Through"]


def test_non_overhead_upload_completes_instead_of_failing(user_id, monkeypatch):
    """Ingest + analysis of a non-overhead clip: COMPLETED, phases published, never the old 422."""
    monkeypatch.setattr(llm_config, "GEMINI_API_KEY", "")
    coach_converse.TheaToolbox(user_id).run("set_sport_and_goals", {"sport": "tennis"})
    phases = [{"phase_name": n, "timestamp_ms": 100 * i, "joint_angles": {"elbow_deg": 150.0 + i}}
              for i, n in enumerate(["Preparation", "Loading", "Impact", "Follow-Through"])]
    payload = {
        "session_id": "pipeline", "coaching_model": "gemini-4-argon", "coaching_status": "live", "llm_source": "gemini",
        "overall_score": 72, "verification_status": "FAIL", "primary_flaw": "Cramped contact",
        "biomechanical_diagnosis": "Cramped contact.", "live_drill_prescription": "Drop-feed extension drill.",
        "concise_audio_cue": "Space from the body", "demo_mode": False, "video_used": True,
        "pose_analysis": {"status": "detected", "used_fallback": False, "overhead_contact_detected": False,
                          "raw_angles": {"right_elbow_contact_deg": 152.0}, "pose_vector": [0.8] * 6,
                          "rep_analysis": {"kinetic_phases": phases, "detected_stroke": "forehand_topspin"}},
        "pro_comparison": {"matched_pro": "Roger Federer", "all_pro_matches": [
            {"player_name": "Roger Federer", "right_elbow_contact_deg": 176.5}]},
    }
    app = FastAPI()
    app.include_router(android_api.create_android_router(AsyncMock(return_value=payload), lambda *a: None))
    client = TestClient(app, headers=auth_headers(user_id=user_id, role="player"))
    meta = {"user_id": user_id, "sport": "tennis", "stroke_type": "forehand", "telemetry": []}
    res = client.post("/api/v1/sessions/ingest", data={"metadata": json.dumps(meta)},
                      files={"video": ("fh.mp4", b"video-" + uuid.uuid4().bytes, "video/mp4")})
    record = client.get(f"/api/v1/sessions/{res.json()['session_id']}").json()
    assert record["status"] == "COMPLETED", record.get("error_message")
    names = [p["phase_name"] for p in record["gemini_feedback"]["kinetic_phases"]]
    assert names == ["Preparation", "Loading", "Impact", "Follow-Through"]
    impact = record["gemini_feedback"]["kinetic_phases"][2]["observation"]
    assert impact.startswith("Your elbow: 152° | Roger Federer: 176° (-24° gap)")


# ---------------------------------------------------------------------------
# c) Thea's tool suite
# ---------------------------------------------------------------------------

SPEC_TOOLS = {"get_full_athlete_status", "set_sport_and_goals", "set_athlete_level_and_generate_plan",
              "update_lesson_progress", "assign_custom_drill", "update_training_schedule",
              "find_nearby_courts_and_weather", "draft_partner_or_coach_message", "manage_gear_reorder_list"}


def test_gemini_is_offered_the_full_tool_suite():
    declared = {d["name"] for d in coach_converse.TOOL_DECLARATIONS}
    assert SPEC_TOOLS <= declared and declared == set(coach_converse.TOOL_IMPLEMENTATIONS)


def stored_memory(user_id):
    db = db_mongo.get_db()
    if db is not None:
        return db[db_mongo.ATHLETE_MEMORY_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
    return db_mongo._MEMORY_ATHLETES[user_id]


def test_every_tool_reads_or_mutates_athlete_memory(athlete, monkeypatch):
    rainy = {"available": True, "source": "open-meteo", "max_rain_probability_pct": 80, "max_wind_kmh": 12}
    monkeypatch.setattr(coach_converse, "fetch_weather", lambda lat, lng: rainy)
    box = coach_converse.TheaToolbox(athlete)

    status = box.run("get_full_athlete_status", {})
    assert status["ok"] and status["profile"]["sport"] == "badminton"
    assert status["plan"]["total"] == len(stored_memory(athlete)["curriculum_nodes"]) > 0

    switched = box.run("set_sport_and_goals", {"sport": "tennis", "skill_focus": "first_serve", "intensity": "competitive"})
    assert switched["ok"] and switched["plan_regenerated"]
    assert (stored_memory(athlete)["sport"], stored_memory(athlete)["skill_focus"]) == ("tennis", "first_serve")
    assert not box.run("set_sport_and_goals", {"sport": "tennis", "skill_focus": "jump_smash"})["ok"]

    assert box.run("set_athlete_level_and_generate_plan", {"level": "advanced"})["ok"]
    assert stored_memory(athlete)["level"] == "advanced"

    first = stored_memory(athlete)["curriculum_nodes"][0]["id"]
    assert box.run("update_lesson_progress", {"node_id": first, "status": "completed"})["ok"]
    assert stored_memory(athlete)["curriculum_nodes"][1]["status"] == "active"

    drill = box.run("assign_custom_drill", {"title": "5-rep Jump Smash", "instruction": "Split-jump smashes.",
                                            "target_reps": 5, "focus_cue": "Hit in front", "stroke_type": "jump_smash"})
    assert drill["ok"] and stored_memory(athlete)["assigned_drills"][-1]["stroke_type"] == "jump_smash"
    combo = box.run("assign_custom_drill", {"title": "Clear + Lunge", "instruction": "Alternate.", "target_reps": 6,
                                            "focus_cue": "Recover", "sequence": ["overhead_clear", "net_lunge_defense"]})
    assert combo["ok"] and combo["drill"]["sequence"] == ["overhead_clear", "net_lunge_defense"]
    assert not box.run("assign_custom_drill", {"title": "x", "instruction": "x", "target_reps": 3, "focus_cue": "x",
                                               "stroke_type": "bicycle_kick"})["ok"]

    sched = box.run("update_training_schedule", {"days": ["Monday", "Thursday"], "time_utc": "19:00", "duration_min": 75})
    assert sched["ok"] and stored_memory(athlete)["reminder_schedule"]["duration_min"] == 75

    courts = box.run("find_nearby_courts_and_weather", {"lat": 51.5265, "lng": -0.0982, "sport": "tennis"})
    assert courts["ok"] and courts["courts"]
    assert courts["play_call"]["decision"] == "play_indoor" and "80% chance of rain" in courts["play_call"]["reason"]
    assert courts["play_call"]["venue"] and all(isinstance(c["indoor"], bool) for c in courts["courts"])
    if db_mongo.get_db() is not None:
        assert courts["search_method"] == "mongodb_nearSphere_2dsphere"
    shuttle = box.run("find_nearby_courts_and_weather", {"sport": "badminton"})
    assert shuttle["play_call"]["decision"] == "play_indoor" and "indoor game" in shuttle["play_call"]["reason"]
    monkeypatch.setattr(coach_converse, "fetch_weather", lambda lat, lng: {
        "available": True, "max_rain_probability_pct": 5, "max_wind_kmh": 8})
    assert box.run("find_nearby_courts_and_weather", {"sport": "tennis"})["play_call"]["decision"] == "play_outdoor"

    draft = box.run("draft_partner_or_coach_message", {"purpose": "hitting_partner", "partner_name": "Priya",
                                                       "proposed_time": "Thursday 7pm", "tone": "friendly"})
    assert draft["ok"] and draft["sent"] is False and draft["draft"]["text"].startswith("Hey Priya!")
    assert "Thursday 7pm" in draft["draft"]["text"]
    assert stored_memory(athlete)["message_drafts"][-1]["status"] == "draft_awaiting_approval"

    assert box.run("manage_gear_reorder_list", {"action": "add", "item_name": "Restring", "notes": "Drop to 24 lbs"})["ok"]
    assert box.run("manage_gear_reorder_list", {"action": "add", "item_name": "Overgrips", "quantity": 3})["ok"]
    assert box.run("manage_gear_reorder_list", {"action": "mark_ordered", "item_name": "restring"})["ok"]
    gear = box.run("manage_gear_reorder_list", {"action": "list"})
    assert gear["needed"] == ["Overgrips"]
    assert [g["status"] for g in stored_memory(athlete)["gear_list"]] == ["ordered", "needed"]

    assert box.run("set_skill_focus", {"focus": "serve toss height"})["ok"]
    assert stored_memory(athlete)["focus_note"] == "serve toss height"
    assert box.run("find_nearby_courts", {"lat": 51.5, "lng": -0.1})["ok"]  # legacy name still accepted


def test_fallback_routes_plain_language_to_the_new_tools(athlete, monkeypatch):
    monkeypatch.setattr(coach_converse, "fetch_weather", lambda lat, lng: {"available": False})
    app = FastAPI()
    app.include_router(coach_converse.router)
    app.dependency_overrides[coach_converse._identity] = lambda: {"user_id": athlete, "role": "player"}
    client = TestClient(app)
    gear = client.post("/api/v1/coach/converse", json={"message": "I need to reorder overgrips"}).json()
    assert gear["tool_actions_taken"] == ["manage_gear_reorder_list"] and "overgrips" in gear["reply_text"]
    draft = client.post("/api/v1/coach/converse", json={"message": "Draft a message to Sam for a hitting partner session"}).json()
    assert draft["tool_actions_taken"] == ["draft_partner_or_coach_message"] and "Sam" in draft["reply_text"]
    status = client.post("/api/v1/coach/converse", json={"message": "How am I doing?"}).json()
    assert status["tool_actions_taken"] == ["get_full_athlete_status"] and "lessons" in status["reply_text"]


def test_context_brief_and_saint_alias(athlete):
    from backend.api.v1 import omnichannel
    app = FastAPI()
    app.include_router(omnichannel.router)
    app.dependency_overrides[coach_converse._identity] = lambda: {"user_id": athlete, "role": "player"}
    client = TestClient(app)
    brief = client.get("/api/v1/coach/brief/me").json()
    assert brief["brief_text"].startswith("Hi Thea [Tempo Sync | User: ")
    assert "Sport: Badminton (Intermediate)" in brief["brief_text"] and "Active Node:" in brief["brief_text"]
    assert brief["whatsapp_link"].startswith("https://wa.me/447985791437?text=Hi%20Thea")
    assert brief["status"]["plan"]["total"] == len(db_mongo.get_athlete_memory(athlete)["curriculum_nodes"])
    assert client.get("/api/v1/coach/brief/someone_else").status_code == 403
    assert "/api/v1/webhooks/saint" in {r.path for r in omnichannel.router.routes}
