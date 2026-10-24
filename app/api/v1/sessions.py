"""
app/api/v1/sessions.py - Asynchronous Session Ingestion & Data Pipeline Endpoints
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.db.mongodb import get_database
from app.models.session import (
    BiometricDataPoint,
    SessionIngestRequest,
    SessionIngestResponse,
    SessionRecord,
    SessionStatus,
)
from app.services.storage import StorageService, get_storage_service
from app.services.tasks import process_session_biomechanics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def parse_session_metadata(
    metadata: str = Form(
        ...,
        description="JSON string containing SessionIngestRequest payload",
        examples=['{"user_id": "usr_01", "sport": "badminton", "stroke_type": "overhead_clear", "telemetry": []}'],
    ),
) -> SessionIngestRequest:
    """
    FastAPI dependency that parses and validates multipart JSON metadata using Pydantic v2.
    Translates parsing and validation errors into standard FastAPI 422 RequestValidationError.
    """
    try:
        return SessionIngestRequest.model_validate_json(metadata)
    except ValidationError as exc:
        enriched_errors = []
        for err in exc.errors():
            err_dict = dict(err)
            raw_loc = err.get("loc", ())
            err_dict["loc"] = ("body", "metadata") + tuple(raw_loc)
            enriched_errors.append(err_dict)
        raise RequestValidationError(errors=enriched_errors) from exc
    except (ValueError, TypeError) as exc:
        raise RequestValidationError(
            errors=[
                {
                    "type": "json_invalid",
                    "loc": ("body", "metadata"),
                    "msg": f"Malformed JSON in metadata: {exc}",
                    "input": metadata,
                }
            ]
        ) from exc


def _compute_telemetry_summary(telemetry: List[BiometricDataPoint]) -> Optional[Dict[str, Any]]:
    """Calculates aggregate statistics from raw wearable telemetry points."""
    if not telemetry:
        return None

    heart_rates = [p.heart_rate for p in telemetry]
    active_calories = [p.active_energy_burned for p in telemetry if p.active_energy_burned is not None]
    cadences = [p.cadence for p in telemetry if p.cadence is not None]

    return {
        "sample_count": len(telemetry),
        "min_heart_rate": min(heart_rates),
        "max_heart_rate": max(heart_rates),
        "avg_heart_rate": round(sum(heart_rates) / len(heart_rates), 1),
        "total_active_calories": round(sum(active_calories), 2) if active_calories else None,
        "avg_cadence": round(sum(cadences) / len(cadences), 1) if cadences else None,
    }


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SessionIngestResponse,
    summary="Ingest a practice video set and biometric telemetry",
    description=(
        "Receives a practice video (MP4/MOV upload or signed cloud URL) with accompanying Android Health Connect "
        "biometric time-series data. Validates payload, persists session record and telemetry to MongoDB Atlas, "
        "stores video via non-blocking storage, and enqueues the session for Gemini Argon biomechanical reasoning."
    ),
)
async def ingest_session(
    background_tasks: BackgroundTasks,
    video: Optional[UploadFile] = File(
        default=None,
        description="Recorded practice set video file (MP4, QuickTime)",
    ),
    video_url: Optional[str] = Form(
        default=None,
        description="Signed cloud storage URL to practice set video if uploaded out-of-band",
    ),
    metadata: SessionIngestRequest = Depends(parse_session_metadata),
    storage: StorageService = Depends(get_storage_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SessionIngestResponse:
    """
    Ingest endpoint accepting practice video and Health Connect biometrics.
    """
    # 1. Enforce that at least one video source is provided
    if video is None and not video_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a video file upload or a valid video_url must be provided.",
        )

    session_id = str(uuid4())
    stored_video_path: Optional[str] = None

    # 2. Validate and store uploaded video file if provided
    if video is not None:
        content_type = video.content_type or ""
        filename = video.filename or ""

        # Validate MIME type and common extension
        is_allowed_mime = any(content_type.lower() == allowed.lower() for allowed in settings.ALLOWED_VIDEO_MIME_TYPES)
        has_video_ext = any(filename.lower().endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".webm"])

        if not (is_allowed_mime or has_video_ext):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported video MIME type '{content_type}'. "
                    f"Allowed formats: {settings.ALLOWED_VIDEO_MIME_TYPES}"
                ),
            )

        # Store file asynchronously with aiofiles chunked writer
        stored_video_path = await storage.store_file(file=video, session_id=session_id)

    # 3. Compute telemetry summary
    telemetry_summary = _compute_telemetry_summary(metadata.telemetry)

    # 4. Construct MongoDB SessionRecord
    session_record = SessionRecord(
        session_id=session_id,
        user_id=metadata.user_id,
        sport=metadata.sport,
        stroke_type=metadata.stroke_type,
        target_archetype=metadata.target_archetype,
        status=SessionStatus.PENDING,
        video_storage_path=stored_video_path,
        video_url=video_url,
        telemetry_count=len(metadata.telemetry),
        telemetry_summary=telemetry_summary,
    )

    # 5. Persist Session Document to MongoDB Atlas
    sessions_collection = db[settings.SESSIONS_COLLECTION]
    await sessions_collection.insert_one(session_record.to_mongo())
    logger.info("Persisted session record %s for user %s", session_id, metadata.user_id)

    # 6. Persist Raw Telemetry Time-Series to MongoDB
    if metadata.telemetry:
        telemetry_collection = db[settings.TELEMETRY_COLLECTION]
        telemetry_docs = [
            {
                "session_id": session_id,
                "user_id": metadata.user_id,
                "sport": metadata.sport,
                **point.model_dump(),
            }
            for point in metadata.telemetry
        ]
        await telemetry_collection.insert_many(telemetry_docs)
        logger.info("Persisted %d biometric readings for session %s", len(telemetry_docs), session_id)

    # 7. Enqueue Gemini Argon Biomechanical Processing Background Task
    background_tasks.add_task(
        process_session_biomechanics,
        session_id=session_id,
        video_storage_path=stored_video_path,
        video_url=video_url,
        telemetry=[p.model_dump() for p in metadata.telemetry],
        db=db,
    )

    # 8. Return 202 Accepted response
    return SessionIngestResponse(
        session_id=session_id,
        status=SessionStatus.PENDING,
        estimated_analysis_time_sec=settings.ESTIMATED_ANALYSIS_TIME_SEC,
        message="Session ingestion accepted. Biomechanical analysis initiated.",
    )


@router.get(
    "/{session_id}",
    status_code=status.HTTP_200_OK,
    response_model=SessionRecord,
    summary="Retrieve session analysis state and SDUI widgets",
    description="Retrieves a session document including current processing status, Gemini 4 Argon biomechanical report, and active SDUI widgets.",
)
async def get_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SessionRecord:
    """
    Retrieves the complete session state, biomechanical feedback, and SDUI widgets.
    """
    sessions_collection = db[settings.SESSIONS_COLLECTION]
    doc = await sessions_collection.find_one({"session_id": session_id})
    if not doc:
        doc = await sessions_collection.find_one({"_id": session_id})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Practice session '{session_id}' not found.",
        )

    # Ensure session_id is populated from _id if missing
    if "session_id" not in doc and "_id" in doc:
        doc["session_id"] = str(doc["_id"])

    return SessionRecord.model_validate(doc)
