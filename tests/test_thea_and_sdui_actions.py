"""
tests/test_thea_and_sdui_actions.py - Tests for the SDUI action feedback loop (Coach Thea is tested via backend coach_converse)
"""

import pytest
from httpx import AsyncClient
from app.models.sdui import (
    PathProgressWidget,
    DrillCardWidget,
    ConceptQuizWidget,
    CheckInScheduleWidget,
    QuestionWidget,
    ChoiceWidget,
    CapturePromptWidget,
)


@pytest.mark.asyncio
async def test_sdui_get_feed(async_client: AsyncClient):
    """Verifies GET /api/v1/sdui/feed/{session_id} returns populated widget feed."""
    response = await async_client.get("/api/v1/sdui/feed/test_session_abc")
    assert response.status_code == 200
    data = response.json()
    assert "widgets" in data
    assert len(data["widgets"]) >= 2
    widget_types = [w.get("widget_type") for w in data["widgets"]]
    assert "DrillCardWidget" in widget_types or "PathProgressWidget" in widget_types


@pytest.mark.asyncio
async def test_sdui_action_drill_completed(async_client: AsyncClient):
    """Verifies POST /api/v1/sdui/actions handles DrillCompleted, removes drill and advances streak."""
    action_req = {
        "session_id": "test_session_drill",
        "action_type": "DrillCompleted",
        "widget_id": "test_session_drill-drill",
        "payload": {"reps_completed": 15},
    }
    response = await async_client.post("/api/v1/sdui/actions", json=action_req)
    assert response.status_code == 200
    data = response.json()
    widgets = data["widgets"]

    # Verify completed drill is removed from active feed
    drill_ids = [w.get("id") for w in widgets if w.get("widget_type") == "DrillCardWidget"]
    assert "test_session_drill-drill" not in drill_ids

    # Verify PathProgressWidget streak incremented
    path_widget = next((w for w in widgets if w.get("widget_type") == "PathProgressWidget"), None)
    assert path_widget is not None
    assert path_widget["current_streak"] >= 6


@pytest.mark.asyncio
async def test_sdui_action_quiz_answered(async_client: AsyncClient):
    """Verifies POST /api/v1/sdui/actions handles QuizAnswered and marks answered_index."""
    action_req = {
        "session_id": "test_session_quiz",
        "action_type": "QuizAnswered",
        "widget_id": "test_session_quiz-quiz",
        "payload": {"selected_index": 0, "is_correct": True},
    }
    response = await async_client.post("/api/v1/sdui/actions", json=action_req)
    assert response.status_code == 200
    data = response.json()
    widgets = data["widgets"]

    quiz_widget = next((w for w in widgets if w.get("widget_type") == "ConceptQuizWidget"), None)
    assert quiz_widget is not None
    assert quiz_widget["answered_index"] == 0


def test_all_seven_sdui_widgets_instantiation():
    """Verifies all 7 SDUI widget models serialize with exact discriminator matching Kotlin."""
    path = PathProgressWidget(current_streak=5, active_node_id="node_1", nodes=[])
    assert path.widget_type == "PathProgressWidget"

    drill = DrillCardWidget(id="d1", title="Drill", instruction="Inst", target_reps=10, focus_cue="Reach")
    assert drill.widget_type == "DrillCardWidget"

    quiz = ConceptQuizWidget(question="Q?", options=["A", "B"], correct_index=0, explanation="Exp")
    assert quiz.widget_type == "ConceptQuizWidget"

    schedule = CheckInScheduleWidget(id="s1", title="Schedule", days_of_week=["Monday"])
    assert schedule.widget_type == "CheckInScheduleWidget"

    question = QuestionWidget(id="q1", prompt="What is your goal?")
    assert question.widget_type == "QuestionWidget"

    choice = ChoiceWidget(id="c1", title="Select Sport", options=[{"id": "badminton", "label": "Badminton"}])
    assert choice.widget_type == "ChoiceWidget"

    capture = CapturePromptWidget(title="Record Stroke", instruction="Hit clear", camera_hint="Rear view", duration_s=15)
    assert capture.widget_type == "CapturePromptWidget"
