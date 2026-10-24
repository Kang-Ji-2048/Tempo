"""
tests/test_gemini_analysis.py - Test suite for Gemini 4 Argon Biomechanics & SDUI Pipeline
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import AsyncClient

from app.models.feedback import BiomechanicalReport, KineticPhase
from app.models.sdui import (
    ConceptQuizWidget,
    DrillCardWidget,
    PathProgressWidget,
    SDUIPayload,
)
from app.models.session import SessionRecord, SessionStatus
from app.services.gemini_analyzer import GeminiAnalyzer
from app.services.sdui_generator import SDUIGenerator
from app.services.tasks import process_session_biomechanics
from tests.conftest import MockAsyncDatabase


def test_biomechanical_report_schema_validation():
    """
    Test 1: Validates that BiomechanicalReport and KineticPhase conform to Pydantic v2 schemas.
    """
    phase = KineticPhase(
        phase_name="Impact",
        timestamp_ms=1320,
        joint_angles={"right_elbow_deg": 171.4, "shoulder_abduction_deg": 164.0},
        form_accuracy_score=85,
        observation="Clean extension at contact point.",
    )
    assert phase.phase_name == "Impact"
    assert phase.joint_angles["right_elbow_deg"] == 171.4

    report = BiomechanicalReport(
        overall_score=84,
        matched_archetype="Viktor Axelsen",
        primary_flaw="Slightly late pronation",
        fatigue_correlation="Heart rate reached 168 BPM on rep 10",
        kinetic_phases=[phase],
        concise_audio_cue="Drive hips before elbow extension.",
        coach_voice_note_script="Solid work! Your loading was explosive. Keep your reach high.",
    )
    assert report.overall_score == 84
    assert len(report.kinetic_phases) == 1
    # Ensure concise audio cue is punchy (<= 12 words)
    assert len(report.concise_audio_cue.split()) <= 12


def test_sdui_widget_schemas():
    """
    Test 2: Validates Android Jetpack Compose SDUI widget models.
    """
    path_widget = PathProgressWidget(
        widget_type="PathProgressWidget",
        current_streak=6,
        active_node_id="node_pronation_03",
        nodes=[{"node_id": "node_01", "status": "COMPLETED"}],
    )
    assert path_widget.widget_type == "PathProgressWidget"
    assert path_widget.current_streak == 6

    drill = DrillCardWidget(
        widget_type="DrillCardWidget",
        id="drill_01",
        title="Pronation Drill",
        instruction="Wall taps for 30 seconds",
        target_reps=15,
        focus_cue="Full reach",
    )
    assert drill.target_reps == 15

    quiz = ConceptQuizWidget(
        widget_type="ConceptQuizWidget",
        question="What is the benefit of full elbow extension?",
        options=["Steeper smash angle", "Lower heart rate"],
        correct_index=0,
        explanation="Geometrical contact vertex is higher.",
    )
    assert quiz.correct_index == 0

    payload = SDUIPayload(
        screen="post_session_analysis",
        coach_summary="Great session",
        widgets=[path_widget.model_dump(), drill.model_dump(), quiz.model_dump()],
    )
    assert len(payload.widgets) == 3


@pytest.mark.asyncio
async def test_gemini_analyzer_deterministic_mock_mode():
    """
    Test 3: Validates deterministic mock output when GEMINI_API_KEY is not configured.
    """
    analyzer = GeminiAnalyzer(mock_mode=True)
    report = await analyzer.analyze_session(
        video_path=None,
        video_url="https://example.com/badminton_clip.mp4",
        telemetry=[{"heart_rate": 168, "timestamp_ms": 1729724400000}],
        sport="badminton",
        stroke_type="overhead_clear",
        target_archetype="Viktor Axelsen",
    )

    assert isinstance(report, BiomechanicalReport)
    assert report.overall_score >= 0 and report.overall_score <= 100
    assert report.matched_archetype == "Viktor Axelsen"
    assert "elbow" in report.primary_flaw.lower()
    assert report.fatigue_correlation is not None
    assert len(report.kinetic_phases) == 4
    assert len(report.concise_audio_cue.split()) <= 12
    assert len(report.coach_voice_note_script) > 20


@pytest.mark.asyncio
async def test_gemini_analyzer_async_client_with_polling(tmp_path):
    """
    Test 4: Validates real async Google GenAI client flow:
    - client.aio.files.upload
    - client.aio.files.get state polling until ACTIVE
    - client.aio.models.generate_content with response_schema=BiomechanicalReport
    - reading from response.parsed
    """
    # Create a dummy temporary video file
    test_video = tmp_path / "test_overhead.mp4"
    test_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 100)

    # Mock File Object
    mock_file_upload = MagicMock()
    mock_file_upload.name = "files/test_video_123"

    # Mock File State Polling: 1st call PROCESSING, 2nd call ACTIVE
    mock_state_processing = MagicMock()
    mock_state_processing.state = "PROCESSING"
    mock_state_active = MagicMock()
    mock_state_active.state = "ACTIVE"

    # Mock Generated Content Response
    expected_report = BiomechanicalReport(
        overall_score=87,
        matched_archetype="Viktor Axelsen",
        primary_flaw="Late pronation under heavy cardiovascular fatigue",
        fatigue_correlation="Heart rate spiked to 174 BPM",
        kinetic_phases=[
            KineticPhase(
                phase_name="Impact",
                timestamp_ms=1200,
                joint_angles={"right_elbow_deg": 174.2},
                form_accuracy_score=89,
                observation="Strong reach at contact.",
            )
        ],
        concise_audio_cue="Snap wrist at highest contact reach.",
        coach_voice_note_script="Outstanding effort today. Your contact height was elite.",
    )

    mock_response = MagicMock()
    mock_response.parsed = expected_report
    mock_response.text = json.dumps(expected_report.model_dump())

    # Build Mock GenAI Client
    mock_client = MagicMock()
    mock_client.aio.files.upload = AsyncMock(return_value=mock_file_upload)
    mock_client.aio.files.get = AsyncMock(side_effect=[mock_state_processing, mock_state_active])
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    analyzer = GeminiAnalyzer(
        api_key="fake_key_for_test",
        mock_mode=False,
        client=mock_client,
    )

    result = await analyzer.analyze_session(
        video_path=str(test_video),
        telemetry=[{"heart_rate": 172}],
        sport="badminton",
        stroke_type="overhead_clear",
    )

    assert result.overall_score == 87
    assert result.matched_archetype == "Viktor Axelsen"

    # Assert async file upload was invoked
    mock_client.aio.files.upload.assert_awaited_once()

    # Assert state was polled until ACTIVE
    assert mock_client.aio.files.get.await_count == 2

    # Assert generate_content was called asynchronously
    mock_client.aio.models.generate_content.assert_awaited_once()
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].response_schema == BiomechanicalReport


def test_sdui_generator_adaptive_flaw_selection():
    """
    Test 5: Verifies that SDUIGenerator adapts widgets based on score and flaw.
    """
    report_elbow = BiomechanicalReport(
        overall_score=70,  # Below 75 -> reinforces current node
        matched_archetype="Viktor Axelsen",
        primary_flaw="Collapsed elbow extension",
        kinetic_phases=[],
        concise_audio_cue="Keep elbow high at contact.",
        coach_voice_note_script="Focus on extension.",
    )

    payload = SDUIGenerator.generate_payload(
        report=report_elbow,
        user_id="usr_001",
        sport="badminton",
        streak_days=7,
    )

    assert payload.screen == "post_session_analysis"
    assert len(payload.widgets) == 3

    # Check PathProgressWidget: score < 75 keeps active node on node_impact_02
    path_w = payload.widgets[0]
    assert path_w["widget_type"] == "PathProgressWidget"
    assert path_w["current_streak"] == 7
    assert path_w["active_node_id"] == "node_impact_02"

    # Check DrillCardWidget: elbow flaw maps to pronation wall drill
    drill_w = payload.widgets[1]
    assert drill_w["widget_type"] == "DrillCardWidget"
    assert "pronation" in drill_w["title"].lower()

    # Check high score: advances active node
    report_high = BiomechanicalReport(
        overall_score=88,  # >= 75 -> advances
        matched_archetype="Viktor Axelsen",
        primary_flaw="Hip rotation lagging",
        kinetic_phases=[],
        concise_audio_cue="Drive hips early.",
        coach_voice_note_script="Great hip coil.",
    )
    payload_high = SDUIGenerator.generate_payload(report_high, user_id="usr_001", sport="tennis")
    assert payload_high.widgets[0]["active_node_id"] == "node_pronation_03"
    assert "hip" in payload_high.widgets[1]["title"].lower()


@pytest.mark.asyncio
async def test_process_session_biomechanics_end_to_end(mock_db: MockAsyncDatabase):
    """
    Test 6: Validates that process_session_biomechanics executes the full pipeline,
    transitions state from PENDING -> ANALYZING -> COMPLETED, and populates
    gemini_feedback, active_widgets, and kinematic_vector in MongoDB.
    """
    session_id = "test_sess_full_001"

    # Seed initial PENDING session record in mock DB
    await mock_db["sessions"].insert_one(
        {
            "_id": session_id,
            "session_id": session_id,
            "user_id": "usr_sumanth_001",
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "target_archetype": "Viktor Axelsen",
            "status": SessionStatus.PENDING.value,
        }
    )

    # Execute background worker
    await process_session_biomechanics(
        session_id=session_id,
        video_storage_path=None,
        video_url="https://storage.googleapis.com/test.mp4",
        telemetry=[{"heart_rate": 168}],
        db=mock_db,  # type: ignore
    )

    # Retrieve and verify updated document
    doc = await mock_db["sessions"].find_one({"session_id": session_id})
    assert doc is not None
    assert doc["status"] == SessionStatus.COMPLETED.value
    assert doc.get("gemini_feedback") is not None
    assert "overall_score" in doc["gemini_feedback"]
    assert doc.get("active_widgets") is not None
    assert len(doc["active_widgets"]) == 3
    assert doc.get("kinematic_vector") is not None
    assert len(doc["kinematic_vector"]) == 6


@pytest.mark.asyncio
async def test_get_session_endpoint_success_and_404(
    async_client: AsyncClient,
    mock_db: MockAsyncDatabase,
):
    """
    Test 7: Validates GET /api/v1/sessions/{session_id}:
    - Returns 200 OK with full SessionRecord when found.
    - Returns 404 Not Found when session does not exist.
    """
    session_id = "test_get_sess_001"

    # Seed a completed session record with feedback and widgets
    record = SessionRecord(
        session_id=session_id,
        user_id="usr_sumanth_001",
        sport="badminton",
        stroke_type="overhead_clear",
        target_archetype="Viktor Axelsen",
        status=SessionStatus.COMPLETED,
        gemini_feedback={
            "overall_score": 85,
            "matched_archetype": "Viktor Axelsen",
            "primary_flaw": "Minor elbow drop",
            "concise_audio_cue": "Stay tall at contact.",
            "coach_voice_note_script": "Great set!",
            "kinetic_phases": [],
        },
        active_widgets=[
            {"widget_type": "PathProgressWidget", "current_streak": 5, "active_node_id": "node_01", "nodes": []}
        ],
        kinematic_vector=[0.95, 0.90, 0.93, 0.88, 0.78, 0.89],
    )
    await mock_db["sessions"].insert_one(record.to_mongo())

    # 1. Successful retrieval (200 OK)
    response = await async_client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "COMPLETED"
    assert data["gemini_feedback"]["overall_score"] == 85
    assert len(data["active_widgets"]) == 1

    # 2. Non-existent session retrieval (404 Not Found)
    non_existent_id = "does_not_exist_999"
    resp_404 = await async_client.get(f"/api/v1/sessions/{non_existent_id}")
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["detail"].lower()


@pytest.mark.asyncio
async def test_process_session_biomechanics_error_handling(mock_db: MockAsyncDatabase):
    """
    Test 8: Validates that exceptions during processing transition session status
    to FAILED and capture the error message.
    """
    session_id = "test_sess_failure_001"

    await mock_db["sessions"].insert_one(
        {
            "_id": session_id,
            "session_id": session_id,
            "user_id": "usr_sumanth_001",
            "status": SessionStatus.PENDING.value,
        }
    )

    # Build an analyzer that raises an exception
    faulty_analyzer = MagicMock()
    faulty_analyzer.analyze_session = AsyncMock(side_effect=RuntimeError("Simulated Gemini API quota exhaustion"))

    from app.services import set_gemini_analyzer, get_gemini_analyzer
    original_analyzer = get_gemini_analyzer()
    set_gemini_analyzer(faulty_analyzer)

    try:
        await process_session_biomechanics(
            session_id=session_id,
            db=mock_db,  # type: ignore
        )

        doc = await mock_db["sessions"].find_one({"session_id": session_id})
        assert doc is not None
        assert doc["status"] == SessionStatus.FAILED.value
        assert "Simulated Gemini API quota exhaustion" in doc["error_message"]
    finally:
        set_gemini_analyzer(original_analyzer)
