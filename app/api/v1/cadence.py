"""
app/api/v1/cadence.py - Athlete Training Schedule & Saint (Thea) Cadence REST Endpoints
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings, get_settings
from app.db.mongodb import get_database
from app.models.schedule import SaintNotificationPayload, UserSchedule
from app.models.session import SessionRecord
from app.services.saint_cadence import SaintCadenceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cadence", tags=["cadence"])

SCHEDULES_COLLECTION = "user_schedules"


@router.post(
    "/schedule",
    status_code=status.HTTP_200_OK,
    response_model=UserSchedule,
    summary="Create or update athlete practice schedule",
)
async def update_user_schedule(
    schedule: UserSchedule,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserSchedule:
    """
    Persists or updates an athlete's target practice schedule and reminder preferences.
    """
    collection = db[SCHEDULES_COLLECTION]
    schedule_data = schedule.model_dump()
    schedule_data["_id"] = schedule.user_id

    await collection.update_one(
        {"_id": schedule.user_id},
        {"$set": schedule_data},
        upsert=True,
    )
    logger.info("Saved practice schedule for user %s (%s at %s UTC)", schedule.user_id, schedule.days_of_week, schedule.target_time_utc)
    return schedule


@router.get(
    "/schedule/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=UserSchedule,
    summary="Get athlete practice schedule",
)
async def get_user_schedule(
    user_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserSchedule:
    """Retrieves an athlete's practice schedule."""
    collection = db[SCHEDULES_COLLECTION]
    doc = await collection.find_one({"_id": user_id})
    if not doc:
        # Return default schedule if none exists
        return UserSchedule(user_id=user_id)
    return UserSchedule.model_validate(doc)


@router.post(
    "/evaluate/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=SaintNotificationPayload,
    summary="Evaluate cadence and generate Saint (Thea) notification",
)
async def evaluate_athlete_cadence(
    user_id: str,
    athlete_name: str = "Sumanth",
    db: AsyncIOMotorDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> SaintNotificationPayload:
    """
    Evaluates athlete practice cadence against recent completed sessions and emits
    a contextual Saint (Thea) WhatsApp dispatch payload.
    """
    # 1. Fetch user schedule
    schedules_col = db[SCHEDULES_COLLECTION]
    sched_doc = await schedules_col.find_one({"_id": user_id})
    schedule = UserSchedule.model_validate(sched_doc) if sched_doc else UserSchedule(user_id=user_id)

    # 2. Fetch recent sessions
    sessions_col = db[settings.SESSIONS_COLLECTION]
    cursor = sessions_col.find({"user_id": user_id}).sort("created_at", -1).limit(5)
    recent_docs = await cursor.to_list(length=5)
    recent_sessions = [SessionRecord.model_validate(doc) for doc in recent_docs]

    # 3. Evaluate cadence
    notification = SaintCadenceService.evaluate_user_cadence(
        schedule=schedule,
        recent_sessions=recent_sessions,
        athlete_name=athlete_name,
    )

    # 4. Trigger dispatch to Saint webhook if configured
    SaintCadenceService.dispatch_notification(notification)

    return notification
