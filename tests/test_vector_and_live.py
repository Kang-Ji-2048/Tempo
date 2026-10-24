"""
tests/test_vector_and_live.py - Test Suite for Vector Matcher, Real-Time WebSocket & Saint Cadence
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.models.schedule import CadenceEventType, SaintNotificationPayload, UserSchedule
from app.models.session import SessionRecord, SessionStatus
from app.services.saint_cadence import SaintCadenceService
from app.services.vector_matcher import (
    REFERENCE_POSE_ARCHETYPES,
    VectorMatcher,
    compute_cosine_similarity,
)
from tests.conftest import MockAsyncDatabase


# ============================================================================
# 1. Vector Matcher & Cosine Similarity Tests
# ============================================================================


def test_cosine_similarity_safe_guards():
    """
    Test 1: Validates cosine similarity computation and zero-norm safety guards.
    """
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    assert compute_cosine_similarity(v1, v2) == pytest.approx(1.0, abs=1e-4)

    # Orthogonal vectors
    v3 = [1.0, 0.0]
    v4 = [0.0, 1.0]
    assert compute_cosine_similarity(v3, v4) == pytest.approx(0.0, abs=1e-4)

    # Zero-norm guards to prevent division by zero
    zero_vec = [0.0, 0.0, 0.0]
    assert compute_cosine_similarity(zero_vec, v1) == 0.0
    assert compute_cosine_similarity(v1, zero_vec) == 0.0
    assert compute_cosine_similarity([], v1) == 0.0


@pytest.mark.asyncio
async def test_vector_matcher_seeding_and_matching(mock_db: MockAsyncDatabase):
    """
    Test 2: Validates reference archetype seeding and similarity matching against
    pro profiles (Viktor Axelsen for badminton, Roger Federer for tennis).
    """
    seeded_count = await VectorMatcher.seed_reference_archetypes(db=mock_db)  # type: ignore
    assert seeded_count == len(REFERENCE_POSE_ARCHETYPES)
    assert len(mock_db["pose_archetypes"].documents) >= seeded_count

    # 1. Badminton overhead jump smash pose vector -> should match Viktor Axelsen or Lee Zii Jia
    badminton_test_vector = [
        round(174.0 / 180.0, 4),
        round(166.0 / 180.0, 4),
        round(171.0 / 180.0, 4),
        round(162.0 / 180.0, 4),
        round(144.0 / 180.0, 4),
        0.93,
    ]
    match_badminton = await VectorMatcher.find_closest_archetype(
        kinematic_vector=badminton_test_vector,
        sport="badminton",
        stroke_type="overhead_clear",
        db=mock_db,  # type: ignore
    )
    assert match_badminton["matched_player"] in ("Viktor Axelsen", "Lee Zii Jia")
    assert match_badminton["similarity_score"] >= 0.95

    # 2. Tennis one-handed backhand pose vector -> should match Roger Federer
    tennis_test_vector = [
        round(171.0 / 180.0, 4),
        round(156.0 / 180.0, 4),
        round(165.0 / 180.0, 4),
        round(146.0 / 180.0, 4),
        round(134.0 / 180.0, 4),
        0.88,
    ]
    match_tennis = await VectorMatcher.find_closest_archetype(
        kinematic_vector=tennis_test_vector,
        sport="tennis",
        stroke_type="one_handed_backhand",
        db=mock_db,  # type: ignore
    )
    assert match_tennis["matched_player"] == "Roger Federer"
    assert match_tennis["similarity_score"] >= 0.95


# ============================================================================
# 2. Real-Time Edge WebSocket Tests
# ============================================================================


def test_websocket_live_stream_cues(app):
    """
    Test 3: Validates live WebSocket connection, frame packet ingestion,
    frame-skipping concurrency guard, and real-time audio cue responses.
    """
    client = TestClient(app)

    with client.websocket_connect("/api/v1/live/stream") as websocket:
        # 1. Normal heart rate badminton frame
        packet_normal = {
            "heart_rate": 156,
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "timestamp_ms": 1729734000,
        }
        websocket.send_json(packet_normal)
        resp1 = websocket.receive_json()
        assert "cue" in resp1
        assert "elbow" in resp1["cue"].lower()
        assert len(resp1["cue"].split()) <= 10

        # 2. High cardiovascular load frame (HR >= 170)
        packet_elevated_load = {
            "heart_rate": 176,
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "timestamp_ms": 1729734001,
        }
        websocket.send_json(packet_elevated_load)
        resp2 = websocket.receive_json()
        assert "heart rate" in resp2["cue"].lower() or "reach" in resp2["cue"].lower()

        # 3. Tennis backhand frame
        packet_tennis = {
            "heart_rate": 158,
            "sport": "tennis",
            "stroke_type": "one_handed_backhand",
            "timestamp_ms": 1729734002,
        }
        websocket.send_json(packet_tennis)
        resp3 = websocket.receive_json()
        assert "coil" in resp3["cue"].lower() or "hip" in resp3["cue"].lower()


# ============================================================================
# 3. Saint Coach Cadence Engine Tests
# ============================================================================


def test_saint_cadence_post_session_debrief():
    """
    Test 4: Validates post-session debrief notification triggered within 60 minutes
    of a completed practice session.
    """
    now = datetime.now(timezone.utc)
    recent_session = SessionRecord(
        session_id="sess_recent_001",
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="overhead_clear",
        status=SessionStatus.COMPLETED,
        gemini_feedback={
            "overall_score": 86,
            "matched_archetype": "Viktor Axelsen",
            "concise_audio_cue": "Accelerate forearm pronation at peak reach.",
        },
        created_at=now - timedelta(minutes=15),
        updated_at=now - timedelta(minutes=10),
    )

    schedule = UserSchedule(
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="overhead_clear",
    )

    payload = SaintCadenceService.evaluate_user_cadence(
        schedule=schedule,
        recent_sessions=[recent_session],
        current_time=now,
        athlete_name="Sumanth",
    )

    assert payload.event_type == CadenceEventType.POST_SESSION_DEBRIEF
    assert payload.session_id == "sess_recent_001"
    assert "86/100" in payload.plain_text_message
    assert "Viktor Axelsen" in payload.plain_text_message

    # Verify Thea WhatsApp formatted text
    thea_text = SaintCadenceService.format_thea_dispatch(payload)
    assert "*SESSION DEBRIEF*" in thea_text
    assert "Sumanth" in thea_text


def test_saint_cadence_pre_session_priming():
    """
    Test 5: Validates pre-session priming notification triggered within 30 minutes
    before scheduled practice on an active training day.
    """
    # Current time: Monday at 17:40 UTC
    # Scheduled practice: Monday at 18:00 UTC (20 mins away, within 30 min lead)
    monday_time = datetime(2026, 10, 26, 17, 40, tzinfo=timezone.utc)  # 2026-10-26 is Monday
    assert monday_time.strftime("%A") == "Monday"

    schedule = UserSchedule(
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="overhead_clear",
        days_of_week=["Monday", "Wednesday", "Friday"],
        target_time_utc="18:00",
        priming_lead_minutes=30,
    )

    payload = SaintCadenceService.evaluate_user_cadence(
        schedule=schedule,
        recent_sessions=[],
        current_time=monday_time,
        athlete_name="Sumanth",
    )

    assert payload.event_type == CadenceEventType.PRE_SESSION_PRIMING
    assert "20 minutes" in payload.plain_text_message
    assert "18:00 UTC" in payload.plain_text_message

    thea_text = SaintCadenceService.format_thea_dispatch(payload)
    assert "*PRE-SESSION PRIMING*" in thea_text


def test_saint_cadence_missed_session_checkin():
    """
    Test 6: Validates missed session check-in notification when scheduled practice
    passed without a logged session.
    """
    # Monday at 19:15 UTC (75 minutes after 18:00 scheduled session, no sessions logged)
    monday_evening = datetime(2026, 10, 26, 19, 15, tzinfo=timezone.utc)

    schedule = UserSchedule(
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="overhead_clear",
        days_of_week=["Monday"],
        target_time_utc="18:00",
    )

    payload = SaintCadenceService.evaluate_user_cadence(
        schedule=schedule,
        recent_sessions=[],
        current_time=monday_evening,
        athlete_name="Sumanth",
    )

    assert payload.event_type == CadenceEventType.MISSED_SESSION_CHECKIN
    assert "missed" in payload.plain_text_message.lower()

    thea_text = SaintCadenceService.format_thea_dispatch(payload)
    assert "*TRAINING CHECK-IN*" in thea_text


def test_saint_notification_dispatch_local_and_webhook():
    """
    Test 7: Validates Saint webhook dispatch helper for local staging and external POST.
    """
    payload = SaintNotificationPayload(
        event_type=CadenceEventType.RECOVERY_ADVICE,
        user_id="usr_sumanth_001",
        recipient_name="Sumanth",
        plain_text_message="Take 10 mins to stretch.",
    )

    # 1. Local staging when webhook URL is None
    res_local = SaintCadenceService.dispatch_notification(payload, webhook_url=None)
    assert res_local["status"] == "STAGED_LOCALLY"
    assert "RECOVERY" in res_local["thea_message"]

    # 2. External webhook mock
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        res_webhook = SaintCadenceService.dispatch_notification(payload, webhook_url="https://thea.saint.ai/webhook")
        assert res_webhook["dispatched"] is True
        assert res_webhook["status"] == "SENT"
        mock_post.assert_called_once()


# ============================================================================
# 4. Cadence REST Endpoints Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cadence_rest_endpoints(
    async_client: AsyncClient,
    mock_db: MockAsyncDatabase,
):
    """
    Test 8: Validates POST /api/v1/cadence/schedule and POST /api/v1/cadence/evaluate/{user_id}.
    """
    # 1. Update athlete schedule
    schedule_data = {
        "user_id": "usr_cadence_001",
        "sport": "badminton",
        "stroke_type": "overhead_clear",
        "days_of_week": ["Monday", "Wednesday"],
        "target_time_utc": "18:00",
        "priming_lead_minutes": 30,
        "preferred_channel": "whatsapp",
    }
    resp_sched = await async_client.post("/api/v1/cadence/schedule", json=schedule_data)
    assert resp_sched.status_code == 200
    assert resp_sched.json()["user_id"] == "usr_cadence_001"

    # 2. Get athlete schedule
    resp_get = await async_client.get("/api/v1/cadence/schedule/usr_cadence_001")
    assert resp_get.status_code == 200
    assert resp_get.json()["target_time_utc"] == "18:00"

    # 3. Evaluate athlete cadence
    resp_eval = await async_client.post("/api/v1/cadence/evaluate/usr_cadence_001?athlete_name=Sumanth")
    assert resp_eval.status_code == 200
    eval_json = resp_eval.json()
    assert "event_type" in eval_json
    assert eval_json["user_id"] == "usr_cadence_001"
    assert "Sumanth" in eval_json["plain_text_message"]
