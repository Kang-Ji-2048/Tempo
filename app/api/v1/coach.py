"""
app/api/v1/coach.py - Coach Thea Conversational API Endpoint
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.thea_coach import TheaCoach

try:
    from backend.auth import authenticate, own
except ImportError:
    from auth import authenticate, own

logger = logging.getLogger("tempo.api.coach")

router = APIRouter(prefix="/coach", tags=["coach-thea"])


class CoachConverseRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="Athlete user identifier")
    message: str = Field(..., min_length=1, description="Message to Coach Thea")
    session_id: Optional[str] = Field(default=None, description="Active or latest session context")


class CoachConverseResponse(BaseModel):
    reply_text: str
    audio_cue_url: Optional[str] = None
    audio_cue_text: Optional[str] = None
    dynamic_widgets: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: Optional[int] = None


@router.post(
    "/converse",
    response_model=CoachConverseResponse,
    status_code=status.HTTP_200_OK,
    summary="Converse with Coach Thea (Gemini 4 Argon & Saint)",
)
async def converse(request: Request, req: CoachConverseRequest) -> CoachConverseResponse:
    """Conversational loop with Coach Thea. Assembles athlete profile, historical biomechanics,

    latest session metrics, and fatigue index, invoking Gemini 4 Argon with Thea persona.
    """
    user_id = req.user_id
    if not user_id:
        try:
            ident = authenticate(request.headers, request.cookies)
            user_id = ident.get("user_id", "user_1")
        except Exception:
            user_id = "user_1"

    try:
        result = await TheaCoach.converse(
            user_id=user_id,
            message=req.message,
            session_id=req.session_id,
        )
        return CoachConverseResponse(
            reply_text=result["reply_text"],
            audio_cue_url=result.get("audio_cue_url"),
            audio_cue_text=result.get("audio_cue_text"),
            dynamic_widgets=result.get("dynamic_widgets", []),
            latency_ms=result.get("latency_ms"),
        )
    except Exception as exc:
        logger.exception("Failed conversation with Coach Thea: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Coach Thea service error: {exc}",
        ) from exc
