"""
app/services/tasks.py - Biomechanics Pipeline Execution & Gemini 4 Argon Orchestration
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.db.mongodb import get_database
from app.models.session import SessionStatus
from app.services.gemini_analyzer import get_gemini_analyzer
from app.services.sdui_generator import SDUIGenerator

logger = logging.getLogger(__name__)


async def process_session_biomechanics(
    session_id: str,
    video_storage_path: Optional[str] = None,
    video_url: Optional[str] = None,
    telemetry: Optional[List[Dict[str, Any]]] = None,
    db: Optional[AsyncIOMotorDatabase] = None,
) -> None:
    """
    Background worker orchestrating the Gemini 4 Argon multimodal reasoning pipeline:
    1. Sets session status to ANALYZING.
    2. Queries session metadata (sport, stroke_type, archetype, user_id).
    3. Analyzes video and wearable telemetry via GeminiAnalyzer.
    4. Generates dynamic SDUI widgets via SDUIGenerator.
    5. Persists report, SDUI widgets, and COMPLETED status to MongoDB Atlas.
    6. Captures exceptions and flags status as FAILED with error details.
    """
    target_db = db if db is not None else get_database()
    settings = get_settings()
    collection = target_db[settings.SESSIONS_COLLECTION]

    logger.info("Initiating biomechanics pipeline for session: %s", session_id)

    try:
        # 1. Update session status to ANALYZING
        await collection.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.ANALYZING.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        logger.info("Session %s transitioned to ANALYZING", session_id)

        # 2. Retrieve session context from database
        session_doc = await collection.find_one({"_id": session_id})
        user_id = session_doc.get("user_id", "usr_unknown") if session_doc else "usr_unknown"
        sport = session_doc.get("sport", "badminton") if session_doc else "badminton"
        stroke_type = session_doc.get("stroke_type", "overhead_clear") if session_doc else "overhead_clear"
        target_archetype = session_doc.get("target_archetype") if session_doc else None

        # 3. Invoke Gemini 4 Argon reasoning engine
        analyzer = get_gemini_analyzer()
        report = await analyzer.analyze_session(
            video_path=video_storage_path,
            video_url=video_url,
            telemetry=telemetry,
            sport=sport,
            stroke_type=stroke_type,
            target_archetype=target_archetype,
        )
        logger.info("Received BiomechanicalReport for session %s (overall_score=%d)", session_id, report.overall_score)

        # 4. Generate adaptive Server-Driven UI (SDUI) payload
        sdui_payload = SDUIGenerator.generate_payload(
            report=report,
            user_id=user_id,
            sport=sport,
            stroke_type=stroke_type,
        )

        # 5. Extract representative kinematic pose vector from kinetic phases for Atlas vector matching
        kinematic_vector: List[float] = []
        for phase in report.kinetic_phases:
            for angle_val in phase.joint_angles.values():
                # Normalize angles around 180 deg
                kinematic_vector.append(round(float(angle_val) / 180.0, 4))
        if not kinematic_vector:
            kinematic_vector = [0.94, 0.88, 0.95, 0.82, 0.77, 0.91]

        # 6. MongoDB Atlas Vector Matching against pro/textbook archetypes
        from app.services.vector_matcher import VectorMatcher

        vector_match = await VectorMatcher.find_closest_archetype(
            kinematic_vector=kinematic_vector[:6],
            sport=sport,
            stroke_type=stroke_type,
            db=target_db,
        )
        # Enrich report with matched player and similarity
        report.matched_archetype = vector_match.get("matched_player", report.matched_archetype)

        # 7. Update session record to COMPLETED with enriched feedback, widgets, and vector match
        await collection.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.COMPLETED.value,
                    "gemini_feedback": report.model_dump(),
                    "active_widgets": sdui_payload.widgets,
                    "kinematic_vector": kinematic_vector[:6],
                    "vector_match": vector_match,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        logger.info(
            "Session %s successfully finalized with status COMPLETED (matched: %s, sim=%.4f).",
            session_id,
            vector_match.get("matched_player"),
            vector_match.get("similarity_score", 0.0),
        )

    except Exception as exc:
        logger.error("Failed biomechanics processing for session %s: %s", session_id, exc, exc_info=True)
        try:
            await collection.update_one(
                {"_id": session_id},
                {
                    "$set": {
                        "status": SessionStatus.FAILED.value,
                        "error_message": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            logger.info("Session %s marked as FAILED with error message", session_id)
        except Exception as inner_exc:
            logger.error("Could not write failure state for session %s: %s", session_id, inner_exc)
