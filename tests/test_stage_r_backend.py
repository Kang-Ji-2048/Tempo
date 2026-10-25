"""Backend tests for Stage R:
- Gemini 4 Argon analysis with mocked client (success, error, retry, video fallback, /ai/status)
- Authentication (register, duplicate 409, login ok/fail, rate limit 429, me, logout revocation, user separation 403)
- Sports Catalog & Profile (GET /sports, POST /profile, GET /profile, not ready skill 422)
"""
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

# Add backend directory
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import argon_analysis
import auth
import llm_config
import sports_config
import user_auth
from argon_analysis import run_biomechanical_analysis
from main import app

client = TestClient(app)


# ==============================================================================
# R2: Gemini Argon Mocked Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_analysis_success_sets_llm_source_gemini():
    """R2 g) (1) Success sets llm_source=gemini."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "overall_score": 92,
        "verification_status": "PASS",
        "primary_flaw": "Clean high contact reach",
        "biomechanical_diagnosis": "High elbow apex matched pro reference.",
        "live_drill_prescription": "Continue 3x10 target clears.",
        "concise_audio_cue": "High reach apex",
        "coach_voice_note_script": "Great extension today.",
        "saint_agent_job": {
            "plain_english_instruction": "Book court",
            "proactive_training_notification": "Great session",
            "requires_human_approval": True,
            "approval_action_summary": "Court booking staged",
        }
    })

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(llm_config, "get_client", return_value=mock_client), \
         patch.object(llm_config, "GEMINI_API_KEY", "mock_key"):
        result = await run_biomechanical_analysis(
            user_name="test_athlete",
            sport_id="badminton",
            skill_id="overhead_clear",
            pose_data={"right_elbow_contact_deg": 172.0},
            watch_metrics={"heart_rate_bpm": 150.0},
            pro_match={"player_name": "Viktor Axelsen", "right_elbow_contact_deg": 176.0},
        )

        assert result["llm_source"] == "gemini"
        assert result["llm_model"] == "gemini-4-argon"
        assert result["llm_error"] is None
        assert result["overall_score"] == 92
        assert result["verification_status"] == "PASS"


@pytest.mark.asyncio
async def test_gemini_analysis_429_sets_fallback_and_logs_error(caplog):
    """R2 g) (2) 429/403/404 error sets llm_source=fallback with llm_error populated and ERROR logged."""
    mock_client = MagicMock()
    error_response = errors.ClientError(
        429,
        {"error": {"code": 429, "message": "Monthly spending cap exceeded", "status": "RESOURCE_EXHAUSTED"}},
        MagicMock(status_code=429),
    )
    mock_client.models.generate_content.side_effect = error_response

    with patch.object(llm_config, "get_client", return_value=mock_client), \
         patch.object(llm_config, "GEMINI_API_KEY", "mock_key"), \
         caplog.at_level("ERROR"):
        result = await run_biomechanical_analysis(
            user_name="test_athlete",
            sport_id="badminton",
            skill_id="overhead_clear",
            pose_data={"right_elbow_contact_deg": 155.0},
            watch_metrics={"heart_rate_bpm": 165.0},
            pro_match={"player_name": "Viktor Axelsen", "right_elbow_contact_deg": 176.0},
        )

        assert result["llm_source"] == "fallback"
        assert result["llm_model"] == "deterministic_fallback"
        assert "ClientError" in result["llm_error"]
        assert result["verification_status"] == "FAIL"
        # Verify ERROR logged
        assert any(r.levelname == "ERROR" for r in caplog.records)


@pytest.mark.asyncio
async def test_gemini_analysis_invalid_json_retries_once():
    """R2 g) (3) Invalid JSON retries once."""
    mock_bad = MagicMock()
    mock_bad.text = "NOT JSON OUTPUT"

    mock_good = MagicMock()
    mock_good.text = json.dumps({
        "overall_score": 85,
        "verification_status": "PASS",
        "primary_flaw": "Full reach",
        "biomechanical_diagnosis": "Good reach.",
        "live_drill_prescription": "Drill.",
        "concise_audio_cue": "Cue.",
        "coach_voice_note_script": "Voice.",
        "saint_agent_job": {
            "plain_english_instruction": "Instruction",
            "proactive_training_notification": "Notification",
            "requires_human_approval": True,
            "approval_action_summary": "Summary",
        }
    })

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [mock_bad, mock_good]

    with patch.object(llm_config, "get_client", return_value=mock_client), \
         patch.object(llm_config, "GEMINI_API_KEY", "mock_key"):
        result = await run_biomechanical_analysis(
            user_name="test_athlete",
            sport_id="badminton",
            skill_id="overhead_clear",
            pose_data={"right_elbow_contact_deg": 170.0},
            watch_metrics={"heart_rate_bpm": 140.0},
            pro_match={"player_name": "Viktor Axelsen"},
        )

        assert result["llm_source"] == "gemini"
        # Two coach attempts, then the auditor's call (which finds no response left and records an error).
        coach_calls = [c for c in mock_client.models.generate_content.call_args_list
                       if c.kwargs["config"].system_instruction != argon_analysis.AUDIT_INSTRUCTION]
        assert len(coach_calls) == 2
        assert result["argon_audit"]["status"] == "error"


def _coach_reply(diagnosis):
    reply = MagicMock()
    reply.text = json.dumps({
        "overall_score": 60, "verification_status": "FAIL", "primary_flaw": "Bent elbow",
        "biomechanical_diagnosis": diagnosis, "live_drill_prescription": "Drill.",
        "concise_audio_cue": "Cue.", "coach_voice_note_script": "Voice.",
        "saint_agent_job": {"plain_english_instruction": "I", "proactive_training_notification": "N",
                            "requires_human_approval": True, "approval_action_summary": "S"}})
    return reply


def _audit_reply(grounded, claims, corrected):
    reply = MagicMock()
    reply.text = json.dumps({"grounded": grounded, "unsupported_claims": claims, "corrected_diagnosis": corrected})
    return reply


async def _analyse(*replies):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = list(replies)
    with patch.object(llm_config, "get_client", return_value=mock_client), \
         patch.object(llm_config, "GEMINI_API_KEY", "mock_key"):
        return await run_biomechanical_analysis(
            user_name="test_athlete", sport_id="badminton", skill_id="overhead_clear",
            pose_data={"right_elbow_contact_deg": 152.0}, watch_metrics={"heart_rate_bpm": 140.0},
            pro_match={"player_name": "Viktor Axelsen"})


@pytest.mark.asyncio
async def test_argon_auditor_passes_a_grounded_diagnosis():
    result = await _analyse(_coach_reply("Elbow at 152° is short of full extension."),
                            _audit_reply(True, [], "Elbow at 152° is short of full extension."))
    assert result["argon_audit"]["status"] == "passed"
    assert result["biomechanical_diagnosis"] == "Elbow at 152° is short of full extension."


@pytest.mark.asyncio
async def test_argon_auditor_corrects_unsupported_claims():
    result = await _analyse(_coach_reply("Elbow at 152°, and fatigue clearly caused the drop."),
                            _audit_reply(False, ["fatigue caused the drop"], "Elbow at 152° at contact."))
    assert result["argon_audit"]["status"] == "corrected"
    assert result["argon_audit"]["unsupported_claims"] == ["fatigue caused the drop"]
    assert result["biomechanical_diagnosis"] == "Elbow at 152° at contact."


@pytest.mark.asyncio
async def test_invented_angle_never_reaches_the_athlete():
    # The auditor misses it, but the deterministic check catches an angle the pose engine never measured.
    result = await _analyse(_coach_reply("Elbow at 152° and knee bent to 131°."),
                            _audit_reply(True, [], "Elbow at 152° and knee bent to 131°."))
    assert result["argon_audit"]["status"] == "replaced_with_measured_baseline"
    assert result["argon_audit"]["ungrounded_angles"] == ["131"]
    assert "131" not in result["biomechanical_diagnosis"]


@pytest.mark.asyncio
async def test_gemini_video_upload_failure_returns_text_analysis(tmp_path):
    """R2 g) (4) Video upload failure still returns a text-only analysis with video_used=false."""
    fake_video = tmp_path / "clip.mp4"
    fake_video.write_bytes(b"dummy_video_bytes")

    mock_client = MagicMock()
    mock_client.files.upload.side_effect = RuntimeError("Files API unavailable")

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "overall_score": 75,
        "verification_status": "FAIL",
        "primary_flaw": "Elbow dropped",
        "biomechanical_diagnosis": "Diagnosis text.",
        "live_drill_prescription": "Prescription.",
        "concise_audio_cue": "Cue.",
        "coach_voice_note_script": "Voice.",
        "saint_agent_job": {
            "plain_english_instruction": "Instruction",
            "proactive_training_notification": "Notification",
            "requires_human_approval": True,
            "approval_action_summary": "Summary",
        }
    })
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(llm_config, "get_client", return_value=mock_client), \
         patch.object(llm_config, "GEMINI_API_KEY", "mock_key"), \
         patch.object(llm_config, "GEMINI_SEND_VIDEO", True):
        result = await run_biomechanical_analysis(
            user_name="test_athlete",
            sport_id="badminton",
            skill_id="overhead_clear",
            pose_data={"right_elbow_contact_deg": 150.0},
            watch_metrics={"heart_rate_bpm": 155.0},
            pro_match={"player_name": "Viktor Axelsen"},
            video_path=str(fake_video),
        )

        assert result["llm_source"] == "gemini"
        assert result["video_used"] is False
        assert "RuntimeError" in (result["video_error"] or "")


def test_ai_status_endpoint_reflects_last_call():
    """R2 g) (5) /ai/status reflects the last call."""
    with patch.object(llm_config, "GEMINI_API_KEY", "mock_key_present"):
        llm_config.update_ai_status(True, latency_ms=450)

        token = auth.issue_token(user_id="ai_test_user")
        res = client.get("/api/v1/ai/status", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["last_call_ok"] is True
        assert data["last_latency_ms"] == 450
        assert data["configured"] is True


# ==============================================================================
# R3: Real Authentication Tests
# ==============================================================================

def test_auth_register_and_login_flow():
    """R3: register, duplicate 409, login ok/fail, me, logout."""
    unique_email = f"user_{int(time.time()*1000)}@tempo.app"
    password = "SecurePassword123!"

    # 1. Register
    reg_res = client.post("/api/v1/auth/register", json={
        "email": unique_email,
        "password": password,
        "display_name": "Test Runner"
    })
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    user_id = reg_data["user_id"]
    token = reg_data["access_token"]
    assert token and len(token) >= 32

    # 2. Duplicate registration returns 409
    dup_res = client.post("/api/v1/auth/register", json={
        "email": unique_email,
        "password": password,
        "display_name": "Test Runner"
    })
    assert dup_res.status_code == 409

    # 3. Login with wrong password returns 401
    bad_login = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401

    # 4. Login with correct password returns 200 and access_token
    good_login = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    assert good_login.status_code == 200
    login_token = good_login.json()["access_token"]

    # 5. GET /api/v1/auth/me returns profile
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["user_id"] == user_id

    # 6. POST /api/v1/auth/logout invalidates token
    logout_res = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {login_token}"})
    assert logout_res.status_code == 200

    # 7. Using invalidated token returns 401
    expired_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login_token}"})
    assert expired_res.status_code == 401


def test_auth_rate_limiting():
    """R3: 5 failed logins within 10 minutes triggers 429."""
    email = f"rate_limit_{int(time.time()*1000)}@tempo.app"

    # Register first
    client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "display_name": "Rate Limit Test"
    })

    # Fail 5 times
    for _ in range(5):
        res = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert res.status_code == 401

    # 6th attempt should return 429
    rate_res = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    assert rate_res.status_code == 429


def test_user_separation_enforces_403():
    """R3: User A cannot read or access User B's resources."""
    token_a = auth.issue_token(user_id="user_alpha")
    token_b = auth.issue_token(user_id="user_beta")

    # Ingest a session owned by user_beta
    metadata_b = json.dumps({
        "user_id": "user_beta",
        "sport": "badminton",
        "stroke_type": "overhead_clear",
        "telemetry": [],
    })
    upload_res = client.post(
        "/api/v1/sessions/ingest",
        data={"metadata": metadata_b},
        files={"video": ("test.mp4", io.BytesIO(b"fake_mp4_bytes"), "video/mp4")},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert upload_res.status_code in {202, 200}
    session_id = upload_res.json()["session_id"]

    # User A attempts to access User B's session -> must be 403
    forbidden_res = client.get(
        f"/api/v1/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert forbidden_res.status_code == 403


# ==============================================================================
# R4: Sports Catalog & Profile Tests
# ==============================================================================

def test_get_sports_catalog_returns_analysis_ready_flags():
    """R4: GET /api/v1/sports returns sports with analysis_ready flags."""
    res = client.get("/api/v1/sports")
    assert res.status_code == 200
    sports = res.json()
    assert isinstance(sports, list)
    sport_map = {s["id"]: s for s in sports}

    assert "badminton" in sport_map
    assert sport_map["badminton"]["analysis_ready"] is True

    assert "tennis" in sport_map
    assert sport_map["tennis"]["analysis_ready"] is True

    assert "padel" in sport_map
    assert sport_map["padel"]["analysis_ready"] is False


def test_profile_update_and_get():
    """R4: POST /api/v1/profile and GET /api/v1/profile."""
    token = auth.issue_token(user_id="profile_athlete")
    profile_payload = {
        "sport": "tennis",
        "skill": "forehand",
        "level": "advanced",
        "goal": "heavy_topspin",
        "playstyle": "aggressive",
        "injuries": ["left_wrist"],
        "reference_player": "Carlos Alcaraz",
    }

    post_res = client.post(
        "/api/v1/profile",
        json=profile_payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert post_res.status_code == 200

    get_res = client.get(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["sport"] == "tennis"
    assert data["skill"] == "forehand"
    assert data["level"] == "advanced"


def test_upload_clip_for_unsupported_skill_returns_422():
    """R4: Uploading clip for skill that is not analysis_ready returns 422 skill_not_supported_yet."""
    token = auth.issue_token(user_id="padel_user")
    metadata = json.dumps({
        "user_id": "padel_user",
        "sport": "padel",
        "stroke_type": "bandeja",
        "telemetry": [],
    })
    res = client.post(
        "/api/v1/sessions/ingest",
        data={"metadata": metadata},
        files={"video": ("test.mp4", io.BytesIO(b"fake_mp4_bytes"), "video/mp4")},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 422
    assert "skill_not_supported_yet" in str(res.json())
