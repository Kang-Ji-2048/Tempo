"""
tests/test_onboarding.py - Test suite for Backend-Driven Onboarding
Verifies step progression from sport selection to profile summary & permissions.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_onboarding_scripted_flow(async_client: AsyncClient):
    """
    Tests the complete scripted onboarding flow:
    sport -> level -> goal -> playstyle -> injuries -> archetype -> capture_prompt -> summary_permissions
    """
    # Step 0: Initial call
    resp = await async_client.post("/api/v1/onboarding/next", json={"step_id": "", "answer": "", "answers": {}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "sport"
    assert data["widget"]["widget_type"] == "ChoiceWidget"
    assert len(data["widget"]["options"]) >= 4

    # Step 1: Sport selected -> Level
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={"step_id": "sport", "answer": "badminton", "answers": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "level"
    assert data["widget"]["widget_type"] == "ChoiceWidget"

    # Step 2: Level selected -> Goal
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={"step_id": "level", "answer": "intermediate", "answers": {"sport": "badminton"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "goal"
    assert data["widget"]["widget_type"] == "ChoiceWidget"

    # Step 3: Goal selected -> Playstyle
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={
            "step_id": "goal",
            "answer": "overhead_power",
            "answers": {"sport": "badminton", "level": "intermediate"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "playstyle"
    assert data["widget"]["widget_type"] == "ChoiceWidget"

    # Step 4: Playstyle selected -> Injuries
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={
            "step_id": "playstyle",
            "answer": "aggressive",
            "answers": {"sport": "badminton", "level": "intermediate", "goal": "overhead_power"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "injuries"
    assert data["widget"]["widget_type"] == "ChoiceWidget"

    # Step 5: Injuries selected -> Archetype
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={
            "step_id": "injuries",
            "answer": "none",
            "answers": {
                "sport": "badminton",
                "level": "intermediate",
                "goal": "overhead_power",
                "playstyle": "aggressive",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "archetype"
    assert data["widget"]["widget_type"] == "ChoiceWidget"
    # Contains Viktor Axelsen
    options = [opt["id"] for opt in data["widget"]["options"]]
    assert "Viktor Axelsen" in options

    # Step 6: Archetype selected -> 5s Capture Prompt
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={
            "step_id": "archetype",
            "answer": "Viktor Axelsen",
            "answers": {
                "sport": "badminton",
                "level": "intermediate",
                "goal": "overhead_power",
                "playstyle": "aggressive",
                "injuries": "none",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "capture_prompt"
    assert data["widget"]["widget_type"] == "CapturePromptWidget"
    assert data["widget"]["duration_s"] == 5

    # Step 7: Capture completed -> Summary & Permissions
    resp = await async_client.post(
        "/api/v1/onboarding/next",
        json={
            "step_id": "capture_prompt",
            "answer": "captured",
            "answers": {
                "sport": "badminton",
                "level": "intermediate",
                "goal": "overhead_power",
                "playstyle": "aggressive",
                "injuries": "none",
                "archetype": "Viktor Axelsen",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "summary_permissions"
    assert data["is_completed"] is True
    assert data["user_profile"] is not None
    assert data["user_profile"]["sport"] == "badminton"
    assert data["user_profile"]["target_archetype"] == "Viktor Axelsen"
    assert data["user_profile"]["playstyle"] == "aggressive"
