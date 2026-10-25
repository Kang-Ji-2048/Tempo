"""
app/services/saint_cadence.py - Saint (Thea) Coach Cadence Engine & Proactive Dispatcher
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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
    def evaluate_memory_cadence(
        cls,
        memory: Dict[str, Any],
        recent_sessions: List[Dict[str, Any]],
        athlete_name: str,
        current_time: Optional[datetime] = None,
    ) -> SaintNotificationPayload:
        """
        Cadence from the shared `athlete_memory` document (the one every channel edits), in priority order:
        1. POST_SESSION_DEBRIEF for an analysed clip in the last 60 minutes.
        2. PRE_SESSION_PRIMING inside the lead window before today's session (per-day times honoured).
        3. MISSED_SESSION_CHECKIN when today's session window closed with no clip recorded.
        4. MISSED_SESSION_CHECKIN (kind=missed_drill) for a remedial drill assigned over 24h ago.
        5. RECOVERY_ADVICE previewing the next scheduled session (or asking to set one up).
        """
        now = current_time or datetime.now(timezone.utc)
        user_id = memory["user_id"]
        sport = (memory.get("sport") or "training").replace("_", " ")
        schedule = memory.get("reminder_schedule") or {}
        nodes = memory.get("curriculum_nodes") or []
        lesson = next((n for n in nodes if n.get("status") == "active"), None)
        lesson_title = lesson.get("title") if lesson else None
        cue = None
        if lesson:
            cue = (lesson.get("drill_spec") or {}).get("focus_cue") or next(
                (t for t in lesson.get("tips") or [] if not t.startswith("Phases:")), None)
        focus = memory.get("focus_note")

        def payload(event: CadenceEventType, message: str, cta: Optional[str], kind: str, **meta: Any):
            return SaintNotificationPayload(
                event_type=event, user_id=user_id, recipient_name=athlete_name, plain_text_message=message,
                call_to_action=cta, dispatched_at=now,
                session_id=meta.pop("session_id", None),
                metadata={"kind": kind, "active_lesson": lesson_title, **meta},
            )

        def parse(ts: Any) -> Optional[datetime]:
            try:
                value = datetime.fromisoformat(str(ts))
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return None

        def session_time(day: datetime) -> Optional[datetime]:
            weekday = day.strftime("%A")
            if weekday not in (schedule.get("days_of_week") or []):
                return None
            hhmm = (schedule.get("day_times") or {}).get(weekday) or schedule.get("time_utc") or "18:00"
            hour, minute = map(int, hhmm.split(":"))
            return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

        completed = [s for s in recent_sessions if str(s.get("status", "")).upper() == "COMPLETED"]
        latest = max(completed, key=lambda s: str(s.get("updated_at") or ""), default=None)
        finished = parse(latest.get("updated_at")) if latest else None
        if latest and finished and timedelta(0) <= now - finished <= timedelta(minutes=60):
            adaptation = latest.get("adaptation") or {}
            score = latest.get("overall_score")
            if adaptation.get("action") == "lesson_completed":
                outcome = f"You passed {adaptation.get('node_title')}" + (
                    f" and unlocked {adaptation['next_node_title']}." if adaptation.get("next_node_title") else ".")
            elif adaptation.get("action") == "remedial_assigned":
                outcome = f"I added a fix-it drill for {adaptation.get('node_title')}; nail it, then record again."
            else:
                outcome = latest.get("primary_flaw") or "Your breakdown is ready."
            return payload(CadenceEventType.POST_SESSION_DEBRIEF,
                           f"Nice work, {athlete_name}! Score {score}/100. {outcome}",
                           "Open Tempo to review the breakdown.", "debrief",
                           session_id=latest.get("session_id"), overall_score=score)

        today = session_time(now)
        lead = int(schedule.get("priming_lead_minutes") or 30)
        if today is not None:
            minutes = (today - now).total_seconds() / 60
            if 0 <= minutes <= lead:
                focus_line = f" Today's focus: {lesson_title}" + (f": {cue}." if cue else ".") if lesson_title else ""
                return payload(CadenceEventType.PRE_SESSION_PRIMING,
                               f"Hey {athlete_name}, your {sport} session starts in {int(minutes)} min "
                               f"({today:%H:%M} UTC).{focus_line}",
                               "Pop your earbuds in and open Live mode.", "pre_session",
                               scheduled_for=today.isoformat())
            recorded_today = any((parse(s.get("created_at")) or now - timedelta(days=2)).date() == now.date()
                                 for s in recent_sessions)
            if minutes < -30 and not recorded_today:
                return payload(CadenceEventType.MISSED_SESSION_CHECKIN,
                               f"Hey {athlete_name}, I didn't see a clip from today's {today:%H:%M} UTC session. "
                               "Rest counts too. Want me to move it to tomorrow?",
                               "Reply with a new day and time, e.g. 'move it to tomorrow 7pm'.", "missed_session",
                               scheduled_for=today.isoformat())

        stale = [d for d in memory.get("assigned_drills") or []
                 if (parse(d.get("assigned_at")) or now) <= now - timedelta(hours=24)]
        if stale:
            drill = stale[-1]
            return payload(CadenceEventType.MISSED_SESSION_CHECKIN,
                           f"{athlete_name}, '{drill.get('title')}' is still waiting: {drill.get('target_reps')} reps, "
                           f"cue: {drill.get('focus_cue')}.",
                           "Do it, then mark it done in Tempo or reply DONE.", "missed_drill",
                           drill_id=drill.get("id"))

        upcoming = next((t for t in (session_time(now + timedelta(days=i)) for i in range(0, 8))
                         if t is not None and t > now), None)
        if upcoming is None:
            return payload(CadenceEventType.RECOVERY_ADVICE,
                           f"Hey {athlete_name}, you don't have training days set yet. Tell me when you can play "
                           "and I'll build your week.", "Reply e.g. 'train me 3x a week at 6pm'.", "no_schedule")
        focus_line = f" Focus: {focus}." if focus else (f" Up next: {lesson_title}." if lesson_title else "")
        return payload(CadenceEventType.RECOVERY_ADVICE,
                       f"Hey {athlete_name}, next {sport} session is {upcoming:%A %H:%M} UTC.{focus_line} "
                       "Keep shoulders and hips mobile until then.",
                       "Reply to change the time or ask me anything.", "next_session",
                       scheduled_for=upcoming.isoformat())

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
            f"\n\n— Thea, your Tempo coach (thea@saint.work)"
        )

    @classmethod
    def dispatch_notification(
        cls,
        payload: SaintNotificationPayload,
        webhook_url: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches Saint notification payload to external Saint/Thea webhook if configured,
        or stages it locally.
        """
        # None -> fall back to settings; an explicit "" means "not configured" (caller read the env itself).
        target_webhook = get_settings().SAINT_WEBHOOK_URL if webhook_url is None else webhook_url

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
                    # e.g. {"to": "+44...", "channel": "whatsapp"} so Saint knows where to deliver.
                    **(extra or {}),
                },
                headers=headers or {},
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
