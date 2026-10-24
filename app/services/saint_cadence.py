"""
app/services/saint_cadence.py - Saint (Thea) Coach Cadence Engine & Proactive Dispatcher
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from app.core.config import get_settings
from app.models.schedule import CadenceEventType, SaintNotificationPayload, UserSchedule
from app.models.session import SessionRecord, SessionStatus

logger = logging.getLogger(__name__)


class SaintCadenceService:
    """
    Evaluates athlete practice schedules against logged sessions and dispatches
    proactive coaching priming, debriefs, and recovery check-ins via Saint (Thea).
    """

    @classmethod
    def evaluate_user_cadence(
        cls,
        schedule: UserSchedule,
        recent_sessions: List[SessionRecord],
        current_time: Optional[datetime] = None,
        athlete_name: str = "Sumanth",
    ) -> SaintNotificationPayload:
        """
        Evaluates training cadence and produces a contextual SaintNotificationPayload:
        1. POST_SESSION_DEBRIEF if a session completed in the last 60 minutes.
        2. PRE_SESSION_PRIMING if within priming_lead_minutes of scheduled practice.
        3. MISSED_SESSION_CHECKIN if the practice window closed without a session.
        4. RECOVERY_ADVICE as default rest/priming guidance.
        """
        now = current_time or datetime.now(timezone.utc)
        current_weekday = now.strftime("%A")

        # 1. Check for recent completed session (within 60 minutes)
        if recent_sessions:
            latest_session = recent_sessions[0]
            if latest_session.status == SessionStatus.COMPLETED:
                session_time = latest_session.updated_at
                delta_minutes = (now - session_time).total_seconds() / 60.0
                if 0 <= delta_minutes <= 60.0:
                    feedback = latest_session.gemini_feedback or {}
                    overall_score = feedback.get("overall_score", 82)
                    archetype = feedback.get("matched_archetype", "Viktor Axelsen")
                    cue = feedback.get("concise_audio_cue", "Maintain full reach at impact.")

                    message = (
                        f"Great hustle on court, {athlete_name}! You recorded an overall form fidelity score of "
                        f"{overall_score}/100 benchmarked against {archetype}. "
                        f"Key focus for next time: '{cue}'. Take 10 minutes to stretch your shoulders and hydrate."
                    )
                    return SaintNotificationPayload(
                        event_type=CadenceEventType.POST_SESSION_DEBRIEF,
                        user_id=schedule.user_id,
                        recipient_name=athlete_name,
                        plain_text_message=message,
                        call_to_action="Tap to review your full biomechanical breakdown and remedial drills.",
                        session_id=latest_session.session_id,
                        dispatched_at=now,
                        metadata={
                            "overall_score": overall_score,
                            "matched_archetype": archetype,
                            "delta_minutes": round(delta_minutes, 1),
                        },
                    )

        # 2. Check scheduled practice days
        is_practice_day = current_weekday in schedule.days_of_week
        if is_practice_day and schedule.is_active:
            try:
                target_hour, target_minute = map(int, schedule.target_time_utc.split(":"))
                scheduled_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                diff_minutes = (scheduled_dt - now).total_seconds() / 60.0

                # Pre-session priming: within priming lead time (e.g. 0 to 30 mins before)
                if 0 <= diff_minutes <= schedule.priming_lead_minutes:
                    message = (
                        f"Hey {athlete_name}! Your scheduled {schedule.sport} session starts in {int(diff_minutes)} minutes "
                        f"({schedule.target_time_utc} UTC). Today's technical objective: full elbow reach on your "
                        f"{schedule.stroke_type.replace('_', ' ')}. Lock in your earbuds before stepping on court!"
                    )
                    return SaintNotificationPayload(
                        event_type=CadenceEventType.PRE_SESSION_PRIMING,
                        user_id=schedule.user_id,
                        recipient_name=athlete_name,
                        plain_text_message=message,
                        call_to_action="Launch CourtVision edge session",
                        dispatched_at=now,
                        metadata={"target_time": schedule.target_time_utc, "sport": schedule.sport},
                    )

                # Missed session check-in: window closed (> 30 mins after scheduled time) and no session logged today
                has_session_today = any(s.created_at.date() == now.date() for s in recent_sessions)
                if diff_minutes < -30.0 and not has_session_today:
                    message = (
                        f"Hey {athlete_name}, we missed you at practice today! Noticed we didn't record a practice set "
                        f"for your scheduled {schedule.sport} session at {schedule.target_time_utc} UTC. "
                        f"Rest and recovery are crucial parts of the process. Would you like me to reschedule today's "
                        f"{schedule.stroke_type.replace('_', ' ')} drill for tomorrow?"
                    )
                    return SaintNotificationPayload(
                        event_type=CadenceEventType.MISSED_SESSION_CHECKIN,
                        user_id=schedule.user_id,
                        recipient_name=athlete_name,
                        plain_text_message=message,
                        call_to_action="Reply YES to reschedule or REST to log an active recovery day.",
                        dispatched_at=now,
                        metadata={"scheduled_time": schedule.target_time_utc},
                    )
            except Exception as parse_err:
                logger.debug("Could not parse schedule time %s: %s", schedule.target_time_utc, parse_err)

        # 3. Default: General recovery guidance
        default_message = (
            f"Hey {athlete_name}, keep up your active recovery today. Maintain mobility in your thoracic spine "
            f"and shoulders to prepare for your upcoming {schedule.sport} session."
        )
        return SaintNotificationPayload(
            event_type=CadenceEventType.RECOVERY_ADVICE,
            user_id=schedule.user_id,
            recipient_name=athlete_name,
            plain_text_message=default_message,
            call_to_action="Review upcoming practice roadmap",
            dispatched_at=now,
        )

    @classmethod
    def format_thea_dispatch(cls, payload: SaintNotificationPayload) -> str:
        """
        Formats a natural conversational executive brief suitable for WhatsApp dispatch
        via the Saint (Thea) autonomous coaching agent.
        """
        header_emoji = {
            CadenceEventType.PRE_SESSION_PRIMING: "⚡️ *PRE-SESSION PRIMING*",
            CadenceEventType.POST_SESSION_DEBRIEF: "🏸 *SESSION DEBRIEF*",
            CadenceEventType.MISSED_SESSION_CHECKIN: "🗓 *TRAINING CHECK-IN*",
            CadenceEventType.RECOVERY_ADVICE: "🌿 *RECOVERY & MOBILITY*",
        }.get(payload.event_type, "🏆 *TEMPO COACH*")

        cta_str = f"\n\n👉 _{payload.call_to_action}_" if payload.call_to_action else ""

        return (
            f"{header_emoji}\n\n"
            f"{payload.plain_text_message}"
            f"{cta_str}"
        )

    @classmethod
    def dispatch_notification(
        cls,
        payload: SaintNotificationPayload,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches Saint notification payload to external Saint/Thea webhook if configured,
        or stages it locally.
        """
        settings = get_settings()
        target_webhook = webhook_url or settings.SAINT_WEBHOOK_URL

        thea_formatted_text = cls.format_thea_dispatch(payload)

        if not target_webhook:
            logger.info("Saint webhook not configured; staged notification locally for %s", payload.user_id)
            return {
                "dispatched": False,
                "status": "STAGED_LOCALLY",
                "event_type": payload.event_type.value,
                "thea_message": thea_formatted_text,
                "detail": "SAINT_WEBHOOK_URL not configured; message ready for WhatsApp dispatch.",
            }

        try:
            resp = requests.post(
                target_webhook,
                json={
                    "event_type": payload.event_type.value,
                    "user_id": payload.user_id,
                    "message": thea_formatted_text,
                    "raw_payload": payload.model_dump(mode="json"),
                },
                timeout=5.0,
            )
            is_success = resp.status_code in (200, 201, 202)
            logger.info("Dispatched Saint webhook to %s (status=%d)", target_webhook, resp.status_code)
            return {
                "dispatched": is_success,
                "status": "SENT" if is_success else "FAILED",
                "status_code": resp.status_code,
                "thea_message": thea_formatted_text,
            }
        except Exception as exc:
            logger.warning("Failed to dispatch Saint webhook: %s", exc)
            return {
                "dispatched": False,
                "status": "ERROR",
                "error": str(exc),
                "thea_message": thea_formatted_text,
            }
