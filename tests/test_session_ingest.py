"""
tests/test_session_ingest.py - Asynchronous Session Ingestion & Pipeline Test Suite
"""

import json
import os
from typing import Any, Dict
import pytest
from httpx import AsyncClient

from app.models.session import SessionRecord, SessionStatus
from app.services.tasks import process_session_biomechanics
from tests.conftest import MockAsyncDatabase


@pytest.mark.asyncio
async def test_session_ingest_successful_file_upload(
    async_client: AsyncClient,
    mock_db: MockAsyncDatabase,
    valid_metadata_json: str,
    mock_mp4_bytes: bytes,
):
    """
    Test 1: Successful upload of a mock MP4 file and valid Health Connect telemetry.
    Verifies 202 Accepted response, database persistence in courtvision_db.sessions,
    and storage of biometric time-series documents.
    """
    files = {
        "video": ("practice_swing_1080p.mp4", mock_mp4_bytes, "video/mp4"),
    }
    data = {
        "metadata": valid_metadata_json,
    }

    response = await async_client.post("/api/v1/sessions/ingest", data=data, files=files)

    assert response.status_code == 202, f"Expected 202 Accepted, got: {response.text}"
    resp_json = response.json()

    # Validate response schema
    assert "session_id" in resp_json
    assert resp_json["status"] == "PENDING"
    assert resp_json["estimated_analysis_time_sec"] == 8
    assert "accepted" in resp_json["message"].lower()

    session_id = resp_json["session_id"]

    # Verify session document in MongoDB
    session_doc = await mock_db["sessions"].find_one({"session_id": session_id})
    assert session_doc is not None, "Session record was not inserted into MongoDB"
    assert session_doc["user_id"] == "usr_sumanth_001"
    assert session_doc["sport"] == "badminton"
    assert session_doc["stroke_type"] == "overhead_clear"
    assert session_doc["target_archetype"] == "Axelsen"
    assert session_doc["status"] in (SessionStatus.PENDING.value, SessionStatus.COMPLETED.value)
    assert session_doc["telemetry_count"] == 3

    # Verify telemetry summary
    summary = session_doc["telemetry_summary"]
    assert summary is not None
    assert summary["sample_count"] == 3
    assert summary["min_heart_rate"] == 158
    assert summary["max_heart_rate"] == 172
    assert summary["avg_heart_rate"] == 165.0
    assert summary["avg_cadence"] == 41.3

    # Verify video file persistence on local storage
    stored_path = session_doc["video_storage_path"]
    assert stored_path is not None
    assert os.path.exists(stored_path)
    with open(stored_path, "rb") as f:
        stored_bytes = f.read()
    assert stored_bytes == mock_mp4_bytes

    # Verify raw telemetry time-series collection insertion
    telemetry_docs = [doc for doc in mock_db["telemetry_timeseries"].list_docs if doc.get("session_id") == session_id]
    assert len(telemetry_docs) == 3
    assert telemetry_docs[0]["heart_rate"] == 158
    assert telemetry_docs[1]["heart_rate"] == 165
    assert telemetry_docs[2]["heart_rate"] == 172


@pytest.mark.asyncio
async def test_session_ingest_successful_video_url(
    async_client: AsyncClient,
    mock_db: MockAsyncDatabase,
    valid_metadata_json: str,
):
    """
    Test 2: Successful ingestion when a signed video URL is provided instead of file upload.
    """
    test_url = "https://storage.googleapis.com/tempo-raw-videos/practice_set_99.mp4"
    data = {
        "metadata": valid_metadata_json,
        "video_url": test_url,
    }

    response = await async_client.post("/api/v1/sessions/ingest", data=data)

    assert response.status_code == 202
    resp_json = response.json()
    session_id = resp_json["session_id"]

    session_doc = await mock_db["sessions"].find_one({"session_id": session_id})
    assert session_doc is not None
    assert session_doc["video_url"] == test_url
    assert session_doc["video_storage_path"] is None


@pytest.mark.asyncio
async def test_session_ingest_validation_corrupted_biometrics(
    async_client: AsyncClient,
    mock_mp4_bytes: bytes,
):
    """
    Test 3: Validation error handling for corrupted biometrics (e.g. negative heart rate).
    Expects standard FastAPI 422 Unprocessable Entity.
    """
    corrupted_metadata = json.dumps(
        {
            "user_id": "usr_sumanth_001",
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "telemetry": [
                {
                    "timestamp_ms": 1729724400000,
                    "heart_rate": -15,  # Invalid: heart rate must be > 0
                    "cadence": 30,
                }
            ],
        }
    )

    files = {"video": ("practice.mp4", mock_mp4_bytes, "video/mp4")}
    data = {"metadata": corrupted_metadata}

    response = await async_client.post("/api/v1/sessions/ingest", data=data, files=files)

    assert response.status_code == 422, f"Expected 422, got: {response.text}"
    error_detail = response.json().get("detail", [])
    assert any("heart_rate" in str(err) for err in error_detail)


@pytest.mark.asyncio
async def test_session_ingest_validation_malformed_json_metadata(
    async_client: AsyncClient,
    mock_mp4_bytes: bytes,
):
    """
    Test 4: Validation error handling for malformed JSON string in metadata.
    Expects 422 Unprocessable Entity.
    """
    files = {"video": ("practice.mp4", mock_mp4_bytes, "video/mp4")}
    data = {"metadata": "{broken_json_not_valid: true"}

    response = await async_client.post("/api/v1/sessions/ingest", data=data, files=files)

    assert response.status_code == 422
    assert "metadata" in str(response.json())


@pytest.mark.asyncio
async def test_session_ingest_validation_missing_sport_metadata(
    async_client: AsyncClient,
    mock_mp4_bytes: bytes,
):
    """
    Test 5: Validation error handling for missing sports metadata (missing sport & stroke_type).
    Expects 422 Unprocessable Entity.
    """
    incomplete_metadata = json.dumps(
        {
            "user_id": "usr_sumanth_001",
            # missing 'sport' and 'stroke_type'
            "telemetry": [],
        }
    )

    files = {"video": ("practice.mp4", mock_mp4_bytes, "video/mp4")}
    data = {"metadata": incomplete_metadata}

    response = await async_client.post("/api/v1/sessions/ingest", data=data, files=files)

    assert response.status_code == 422
    error_str = str(response.json())
    assert "sport" in error_str
    assert "stroke_type" in error_str


@pytest.mark.asyncio
async def test_session_ingest_validation_invalid_mime_type(
    async_client: AsyncClient,
    valid_metadata_json: str,
):
    """
    Test 6: Validation error handling for invalid video file MIME type (e.g. text/plain).
    Expects 400 Bad Request.
    """
    invalid_file = ("script.txt", b"plain text content not a video", "text/plain")
    files = {"video": invalid_file}
    data = {"metadata": valid_metadata_json}

    response = await async_client.post("/api/v1/sessions/ingest", data=data, files=files)

    assert response.status_code == 400
    assert "video MIME type" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_session_ingest_validation_missing_video_source(
    async_client: AsyncClient,
    valid_metadata_json: str,
):
    """
    Test 7: Validation error handling when neither video upload nor video_url is provided.
    Expects 400 Bad Request.
    """
    data = {"metadata": valid_metadata_json}

    response = await async_client.post("/api/v1/sessions/ingest", data=data)

    assert response.status_code == 400
    assert "video" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_session_record_future_proof_schema():
    """
    Test 8: Future-proof session schema validation.
    Verifies that gemini_feedback, kinematic_vector, and active_widgets fields
    exist and can be stored cleanly.
    """
    record = SessionRecord(
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="jump_smash",
        target_archetype="Lee Zii Jia",
        gemini_feedback={
            "audio_cue": "Pronate earlier",
            "elbow_deg": 172.5,
        },
        kinematic_vector=[0.95, 0.91, 0.88, 0.76, 0.82, 0.93],
        active_widgets=[
            {"widget_type": "PathNodeWidget", "title": "Pronation Acceleration"},
        ],
    )

    mongo_data = record.to_mongo()
    assert mongo_data["_id"] == record.session_id
    assert mongo_data["gemini_feedback"]["audio_cue"] == "Pronate earlier"
    assert len(mongo_data["kinematic_vector"]) == 6
    assert len(mongo_data["active_widgets"]) == 1


@pytest.mark.asyncio
async def test_background_task_processing_stub(mock_db: MockAsyncDatabase):
    """
    Test 9: Background task execution stub (simulating Gemini Argon handoff).
    Verifies transition from PENDING -> ANALYZING -> COMPLETED, and population of
    biomechanical feedback and Server-Driven UI widgets.
    """
    session_id = "test_sess_task_001"

    # Seed initial PENDING session record
    await mock_db["sessions"].insert_one(
        {
            "_id": session_id,
            "session_id": session_id,
            "user_id": "usr_sumanth_001",
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "status": SessionStatus.PENDING.value,
        }
    )

    # Execute background worker task
    await process_session_biomechanics(
        session_id=session_id,
        video_storage_path="/tmp/test.mp4",
        telemetry=[{"heart_rate": 165}],
        db=mock_db,  # type: ignore
    )

    # Verify updated session status and enriched fields
    updated_session = await mock_db["sessions"].find_one({"session_id": session_id})
    assert updated_session is not None
    assert updated_session["status"] == SessionStatus.COMPLETED.value
    assert updated_session.get("gemini_feedback") is not None
    assert updated_session["gemini_feedback"]["model_version"] == "gemini-4-argon"
    assert updated_session.get("kinematic_vector") is not None
    assert len(updated_session["kinematic_vector"]) == 6
    assert updated_session.get("active_widgets") is not None
    assert len(updated_session["active_widgets"]) >= 2


def test_health_check_endpoint():
    """Health belongs to the shared runtime and reports a degraded offline state."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.test_auth_helpers import auth_headers
    with patch('backend.main.check_mongo_health', return_value={'connected': False}), \
         patch('backend.main.get_pose_runtime_status', return_value={'configured': False}):
        response = TestClient(app, headers=auth_headers()).get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'degraded'
    assert data['service'] == 'tempo-biomechanics-backend'
    assert data['mongodb']['connected'] is False
