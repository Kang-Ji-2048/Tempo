"""
app/api/v1/sdui.py - Server-Driven UI (SDUI) Feed & Actions Endpoints
Provides:
- GET  /api/v1/sdui/feed/{session_id}
- POST /api/v1/sdui/actions
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

try:
    from backend import db_mongo
    from backend.auth import authenticate
except ImportError:
    import db_mongo
    from auth import authenticate

logger = logging.getLogger("tempo.api.sdui")

router = APIRouter(prefix="/sdui", tags=["sdui"])


class WidgetActionRequest(BaseModel):
    session_id: Optional[str] = Field(default="", description="Target session identifier")
    action_type: str = Field(..., description="Action type: DrillCompleted, QuizAnswered, SlotPicked, ChoiceSelected, etc.")
    widget_id: str = Field(..., description="Target widget identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Action payload")


class WidgetFeedResponse(BaseModel):
    session_id: Optional[str] = None
    widgets: List[Dict[str, Any]] = Field(default_factory=list)


def _get_session_record(session_id: str) -> Optional[Dict[str, Any]]:
    db = db_mongo.get_db()
    if db is not None:
        try:
            return db["android_sessions"].find_one({"_id": session_id}) or db["sessions"].find_one({"_id": session_id})
        except Exception:
            pass
    return None


def _save_session_widgets(session_id: str, widgets: List[Dict[str, Any]]) -> None:
    db = db_mongo.get_db()
    if db is not None:
        try:
            db["android_sessions"].update_one(
                {"_id": session_id},
                {"$set": {"active_widgets": widgets}},
                upsert=False,
            )
            db["sessions"].update_one(
                {"_id": session_id},
                {"$set": {"active_widgets": widgets}},
                upsert=False,
            )
        except Exception as exc:
            logger.warning("Failed updating MongoDB active_widgets for %s: %s", session_id, exc)


def _build_default_widgets(session_id: str = "default") -> List[Dict[str, Any]]:
    return [
        {
            "widget_type": "PathProgressWidget",
            "title": "Badminton Overhead Clear Path",
            "current_streak": 5,
            "active_node_id": "node_reach_02",
            "nodes": [
                {"node_id": "node_setup_01", "title": "Unit Turn & Setup", "status": "COMPLETED", "xp_reward": 50},
                {"node_id": "node_reach_02", "title": "Peak Reach Extension", "status": "ACTIVE", "xp_reward": 75},
                {"node_id": "node_pronation_03", "title": "Forearm Pronation Speed", "status": "LOCKED", "xp_reward": 100},
                {"node_id": "node_smash_04", "title": "High-Tempo Jump Smash", "status": "LOCKED", "xp_reward": 150},
            ],
        },
        {
            "widget_type": "DrillCardWidget",
            "id": f"{session_id}-drill",
            "title": "30s Rapid Pronation Drill",
            "instruction": "Stand 1 meter from a wall. Rapidly rotate forearm inward hitting shuttlecock target maintaining elbow extension.",
            "target_reps": 15,
            "focus_cue": "Full elbow extension at contact before the forearm snaps inward.",
        },
        {
            "widget_type": "ConceptQuizWidget",
            "id": f"{session_id}-quiz",
            "question": "Why does full elbow extension generate a steeper downward smash angle?",
            "options": [
                "It raises the geometrical contact vertex above net height, maximizing downward angular trajectory.",
                "It bends the racket shaft backward to store elastic tension.",
                "It reduces cardiovascular heart rate demand.",
                "It delays opponent split step.",
            ],
            "correct_index": 0,
            "explanation": "Every 5cm of contact height elevation steepens the smash vector by approximately 3.8 degrees, preventing the shuttle from floating.",
            "answered_index": None,
        },
    ]


@router.get(
    "/feed/{session_id}",
    response_model=WidgetFeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active SDUI widgets for a session",
)
async def get_feed(session_id: str) -> WidgetFeedResponse:
    sess = _get_session_record(session_id)
    widgets = sess.get("active_widgets") if sess else None
    if not widgets:
        widgets = _build_default_widgets(session_id)
    return WidgetFeedResponse(session_id=session_id, widgets=widgets)


@router.post(
    "/actions",
    response_model=WidgetFeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle SDUI widget action and return updated feed",
)
async def post_action(req: WidgetActionRequest) -> WidgetFeedResponse:
    session_id = req.session_id or "default"
    sess = _get_session_record(session_id)
    widgets = copy.deepcopy(sess.get("active_widgets", [])) if sess else []
    if not widgets:
        widgets = _build_default_widgets(session_id)

    action_type = req.action_type
    widget_id = req.widget_id
    payload = req.payload

    logger.info("Processing SDUI action %s on widget %s (session %s)", action_type, widget_id, session_id)

    if action_type == "DrillCompleted":
        # Remove the completed drill or mark completed
        widgets = [w for w in widgets if w.get("id") != widget_id]
        # Advance path progression
        for w in widgets:
            if w.get("widget_type") == "PathProgressWidget":
                w["current_streak"] = w.get("current_streak", 0) + 1
                nodes = w.get("nodes", [])
                active_idx = next((i for i, n in enumerate(nodes) if n.get("node_id") == w.get("active_node_id")), -1)
                if active_idx != -1:
                    nodes[active_idx]["status"] = "COMPLETED"
                    if active_idx + 1 < len(nodes):
                        nodes[active_idx + 1]["status"] = "ACTIVE"
                        w["active_node_id"] = nodes[active_idx + 1]["node_id"]

    elif action_type == "QuizAnswered":
        selected_index = payload.get("selected_index")
        for w in widgets:
            if w.get("widget_type") == "ConceptQuizWidget":
                if w.get("id") == widget_id or not widget_id or widget_id.startswith("quiz_"):
                    w["answered_index"] = selected_index

    elif action_type in ("SlotPicked", "ScheduleChanged"):
        slot_id = payload.get("slot_id")
        for w in widgets:
            if w.get("widget_type") == "CheckInScheduleWidget":
                if slot_id:
                    w["selected_slot_id"] = slot_id
                if "days_of_week" in payload:
                    w["days_of_week"] = payload["days_of_week"]
                if "target_time_utc" in payload:
                    w["target_time_utc"] = payload["target_time_utc"]

    elif action_type == "ChoiceSelected":
        option_ids = payload.get("option_ids", [])
        for w in widgets:
            if w.get("widget_type") == "ChoiceWidget" and w.get("id") == widget_id:
                w["selected_option_ids"] = option_ids

    # Persist updated widgets to session in MongoDB
    if sess:
        _save_session_widgets(session_id, widgets)

    return WidgetFeedResponse(session_id=session_id, widgets=widgets)
