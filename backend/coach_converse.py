"""Unified omnichannel Coach Thea brain: `POST /api/v1/coach/converse`.

Every channel (app, live, WhatsApp, Gemini) reads and writes the same `athlete_memory`
document. Gemini 4 Argon runs as Coach Thea with function calling; each tool mutates
`athlete_memory` in MongoDB. Without Gemini, a rule-based planner calls the same tools.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import requests
from urllib.parse import quote

if __package__:
    from . import db_mongo, kinematics_engine, llm_config, sports_config
    from .auth import principal
else:
    import db_mongo, kinematics_engine, llm_config, sports_config
    from auth import principal

logger = logging.getLogger("tempo.coach_converse")

router = APIRouter(prefix="/api/v1/coach", tags=["coach-thea"])

Channel = Literal["app", "live", "whatsapp", "gemini"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SPREADS = {
    1: ["Wednesday"],
    2: ["Tuesday", "Thursday"],
    3: ["Monday", "Wednesday", "Friday"],
    4: ["Monday", "Tuesday", "Thursday", "Saturday"],
    5: ["Monday", "Tuesday", "Wednesday", "Friday", "Saturday"],
    6: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    7: WEEKDAYS,
}
DEFAULT_LAT, DEFAULT_LNG = 51.5248, -0.1328  # Central London / UCL
DEFAULT_TIME_UTC = "18:00"
MAX_TOOL_ROUNDS = 5
MAX_ASSIGNED_DRILLS = 10
MAX_CURRICULUM_NODES = 8


class ConverseRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, max_length=128)
    phone_number: Optional[str] = Field(default=None, pattern=r"^\+?[0-9]{6,16}$")
    channel: Channel = "app"
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=128)


class ConverseResponse(BaseModel):
    reply_text: str
    speak_text: str
    tool_actions_taken: List[str]
    athlete_memory: Dict[str, Any]
    active_widgets: List[Dict[str, Any]]
    llm_source: str
    llm_model: str
    latency_ms: int
    # Legacy fields still read by the Android CoachConverseResponseDto.
    audio_cue_text: Optional[str] = None
    dynamic_widgets: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def _drill_spec(drill: Any) -> Dict[str, Any]:
    return {"drill_id": drill.id, "title": drill.title, "instruction": drill.instruction,
            "target_reps": drill.target_reps, "focus_cue": drill.focus_cue}


def _skill_order(sport: sports_config.SportDefinition, skill_focus: Optional[str]) -> List[Any]:
    return sorted(sport.skills, key=lambda s: (s.id != skill_focus, not s.analysis_ready))


def _default_nodes(sport_id: str, level: str, skill_focus: Optional[str]) -> List[Dict[str, Any]]:
    sport = sports_config.get_sport(sport_id)
    nodes: List[Dict[str, Any]] = []
    for skill in _skill_order(sport, skill_focus):
        target = skill.rubric_by_level.get(level, {})
        tips = [f"Phases: {' -> '.join(skill.phases)}"]
        if target.get("elbow_target_deg"):
            tips.append(f"{level.title()} target: elbow extension of at least {target['elbow_target_deg']:.0f} deg at contact")
        tips += [f"Avoid: {fault.name}" for fault in skill.common_faults]
        nodes.append({"title": f"{skill.name}: Mechanics", "tips": tips, "drill_spec": None,
                      "skill_id": skill.id})
        for drill in skill.drills:
            fault = next((f.name for f in skill.common_faults if drill.id in f.drill_ids), None)
            nodes.append({"title": drill.title, "tips": [drill.focus_cue] + ([f"Fixes: {fault}"] if fault else []),
                          "drill_spec": _drill_spec(drill), "skill_id": skill.id})
    return nodes


def build_curriculum(sport_id: str, level: str, skill_focus: Optional[str] = None,
                     proposed_nodes: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Normalize LLM-proposed nodes (or catalog defaults) into LessonNode objects; first is active."""
    sport = sports_config.get_sport(sport_id)
    raw = [n for n in (proposed_nodes or []) if str(n.get("title") or "").strip()] or _default_nodes(
        sport_id, level, skill_focus)
    nodes = []
    for i, node in enumerate(raw[:MAX_CURRICULUM_NODES]):
        title = str(node["title"]).strip()[:120]
        tips = node.get("tips") or []
        if isinstance(tips, str):
            tips = [tips]
        drill_spec = node.get("drill_spec")
        if not drill_spec and proposed_nodes:
            match = db_mongo.search_drills(title, sport=sport_id, limit=1)["drills"]
            if match:
                d = match[0]
                drill_spec = {k: d.get(k) for k in ("drill_id", "title", "instruction", "target_reps", "focus_cue")}
        nodes.append({
            "id": f"{sport_id}_{i + 1:02d}_{_slug(title)}",
            "title": title,
            "status": "active" if i == 0 else "locked",
            "youtube_url": db_mongo.youtube_search_url(sport.display_name, title, level),
            "tips": [str(t)[:240] for t in tips][:5],
            "drill_spec": drill_spec,
        })
    return nodes


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

def path_widget(memory: Dict[str, Any]) -> Dict[str, Any]:
    nodes = memory.get("curriculum_nodes") or []
    active = next((n["id"] for n in nodes if n.get("status") == "active"), nodes[0]["id"] if nodes else "")
    return {
        "widget_type": "PathProgressWidget",
        "current_streak": 0,
        "active_node_id": active,
        "sport": memory.get("sport"),
        "level": memory.get("level"),
        "nodes": [{"node_id": n["id"], "title": n["title"], "status": n["status"].upper(),
                   "youtube_url": n.get("youtube_url"), "tips": n.get("tips", []),
                   "drill_spec": n.get("drill_spec")} for n in nodes],
    }


def schedule_widget(schedule: Dict[str, Any]) -> Dict[str, Any]:
    return {"widget_type": "CheckInScheduleWidget", "id": "schedule", "title": "Weekly Practice Cadence",
            "subtitle": f"{len(schedule['days_of_week'])}x per week",
            "days_of_week": schedule["days_of_week"], "target_time_utc": schedule["time_utc"],
            "priming_lead_minutes": schedule["priming_lead_minutes"],
            "preferred_channel": schedule["preferred_channel"]}


# ---------------------------------------------------------------------------
# Tools (each mutates athlete_memory)
# ---------------------------------------------------------------------------

def _normalize_days(days: Any) -> List[str]:
    if isinstance(days, str):
        days = re.split(r"[,\s/]+", days)
    out = []
    for day in days or []:
        key = str(day).strip().lower()[:3]
        match = next((d for d in WEEKDAYS if d.lower().startswith(key)), None) if len(key) == 3 else None
        if match is None:
            raise ValueError(f"Unknown weekday: {day}")
        if match not in out:
            out.append(match)
    if not out:
        raise ValueError("days must name at least one weekday")
    return sorted(out, key=WEEKDAYS.index)


def _normalize_day_times(day_times: Any) -> Dict[str, str]:
    """Accept [{day, time_utc}] (tool schema) or {day: time}; returns {Weekday: "HH:MM"}."""
    if not day_times:
        return {}
    pairs = day_times.items() if isinstance(day_times, dict) else [
        (d.get("day"), d.get("time_utc") or d.get("time")) for d in day_times if isinstance(d, dict)]
    out = {}
    for day, value in pairs:
        time_value = str(value or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
            raise ValueError(f"time for {day} must be HH:MM (24h, UTC)")
        out[_normalize_days([day])[0]] = time_value
    return out


class TheaToolbox:
    """Executes Coach Thea's tools for one athlete, recording actions and widgets."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.actions: List[str] = []
        self.widgets: Dict[str, Dict[str, Any]] = {}
        self.memory = db_mongo.get_athlete_memory(user_id)

    def _save(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.memory = db_mongo.update_athlete_memory(self.user_id, updates)
        return self.memory

    def run(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        name = TOOL_ALIASES.get(name, name)
        tool = TOOL_IMPLEMENTATIONS.get(name)
        if tool is None:
            return {"ok": False, "error": f"Unknown tool {name}"}
        try:
            result = tool(self, **args)
            self.actions.append(name)
            return {"ok": True, **result}
        except (TypeError, ValueError) as exc:
            logger.info("Thea tool %s rejected args %s: %s", name, args, exc)
            return {"ok": False, "error": str(exc)}

    def _plan(self, sport: str, level: str, skill_focus: Optional[str],
              proposed: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        nodes = build_curriculum(sport, level, skill_focus, proposed)
        self._save({"level": level, "curriculum_nodes": nodes})
        self.widgets["path"] = path_widget(self.memory)
        return {"curriculum_nodes": [{"id": n["id"], "title": n["title"], "status": n["status"]} for n in nodes]}

    def set_sport_and_goals(self, sport: str, motivation_why: Optional[str] = None,
                            intensity: Optional[str] = None, skill_focus: Optional[str] = None) -> Dict[str, Any]:
        sport_id = str(sport).strip().lower()
        definition = sports_config.get_sport(sport_id)
        if definition is None:
            raise ValueError(f"Unsupported sport {sport}; choose one of {list(sports_config.SPORTS_CATALOG)}")
        if skill_focus and not any(s.id == skill_focus for s in definition.skills):
            raise ValueError(f"{skill_focus} is not a {sport_id} skill; choose one of {[s.id for s in definition.skills]}")
        switched = sport_id != self.memory.get("sport")
        refocused = bool(skill_focus) and skill_focus != self.memory.get("skill_focus")
        updates: Dict[str, Any] = {"sport": sport_id}
        if motivation_why:
            updates["motivation_why"] = str(motivation_why).strip()[:500]
        if intensity:
            updates["intensity"] = str(intensity).strip().lower()
        if switched:
            updates["skill_focus"] = next((s.id for s in definition.skills if s.analysis_ready),
                                          definition.skills[0].id if definition.skills else None)
            updates["recent_flaws"] = []
        if skill_focus:
            updates["skill_focus"] = skill_focus
        self._save(updates)
        result: Dict[str, Any] = {"sport": sport_id, "intensity": self.memory.get("intensity"),
                                  "motivation_why": self.memory.get("motivation_why"),
                                  "skill_focus": self.memory.get("skill_focus")}
        if switched or refocused or not self.memory.get("curriculum_nodes"):
            # A new sport always gets a starter plan; the coach can refine it with the level tool.
            result["plan"] = self._plan(sport_id, self.memory.get("level") or "beginner",
                                        self.memory.get("skill_focus"))
            result["plan_regenerated"] = True
        return result

    def set_athlete_level_and_generate_plan(self, level: str,
                                            curriculum_nodes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        level = str(level).strip().lower()
        if level not in db_mongo.LEVELS:
            raise ValueError(f"level must be one of {db_mongo.LEVELS}")
        sport = self.memory.get("sport")
        if not sport:
            raise ValueError("Set the athlete's sport with set_sport_and_goals before generating a plan")
        return {"level": level, **self._plan(sport, level, self.memory.get("skill_focus"), curriculum_nodes)}

    def update_lesson_progress(self, node_id: str, status: str) -> Dict[str, Any]:
        self.memory = db_mongo.set_lesson_node_status(self.user_id, str(node_id), str(status).strip().lower())
        self.widgets["path"] = path_widget(self.memory)
        return {"node_id": node_id, "status": status,
                "next_active": next((n["id"] for n in self.memory["curriculum_nodes"] if n["status"] == "active"), None)}

    def assign_custom_drill(self, title: str, instruction: str, target_reps: int, focus_cue: str,
                            stroke_type: Optional[str] = None, sequence: Optional[List[str]] = None) -> Dict[str, Any]:
        """Push a drill to Home and to the head of the Live queue (stroke_type picks the live tracker)."""
        reps = int(target_reps)
        if not 1 <= reps <= 500:
            raise ValueError("target_reps must be between 1 and 500")
        for stroke in [stroke_type, *(sequence or [])]:
            if stroke and kinematics_engine.stroke_for_skill(stroke) is None:
                raise ValueError(f"Unknown stroke_type {stroke}; choose one of {sorted(kinematics_engine.SKILL_TO_STROKE)}")
        sport = sports_config.get_sport(self.memory.get("sport") or "")
        drill = {"id": f"drill_custom_{uuid.uuid4().hex[:8]}", "title": str(title).strip()[:120],
                 "instruction": str(instruction).strip()[:1000], "target_reps": reps,
                 "focus_cue": str(focus_cue).strip()[:240],
                 "stroke_type": stroke_type or self.memory.get("skill_focus"),
                 **({"sequence": list(sequence)} if sequence else {}),
                 "youtube_url": db_mongo.youtube_search_url(sport.display_name if sport else "", str(title), "drill"),
                 "assigned_at": datetime.now(timezone.utc).isoformat()}
        drills = (self.memory.get("assigned_drills") or []) + [drill]
        self._save({"assigned_drills": drills[-MAX_ASSIGNED_DRILLS:]})
        self.widgets[drill["id"]] = {"widget_type": "DrillCardWidget", **drill}
        return {"drill": drill}

    def update_training_schedule(self, days: Any = None, time_utc: Optional[str] = None,
                                 preferred_channel: Optional[str] = None, day_times: Any = None,
                                 duration_min: Optional[int] = None) -> Dict[str, Any]:
        current = self.memory.get("reminder_schedule") or {}
        time_value = (time_utc or current.get("time_utc") or DEFAULT_TIME_UTC).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
            raise ValueError("time_utc must be HH:MM (24h, UTC)")
        channel = (preferred_channel or current.get("preferred_channel") or "whatsapp").strip().lower()
        if channel not in {"whatsapp", "push", "sms"}:
            raise ValueError("preferred_channel must be whatsapp, push or sms")
        overrides = _normalize_day_times(day_times)
        base_days = _normalize_days(days) if days else list(current.get("days_of_week") or [])
        if not base_days and not overrides:
            raise ValueError("Give training days, or a day_times change for an existing schedule")
        all_days = sorted(set(base_days) | set(overrides), key=WEEKDAYS.index)
        # Per-day times survive for days still trained; a new global time_utc clears them.
        kept = {} if time_utc else {d: t for d, t in (current.get("day_times") or {}).items() if d in all_days}
        merged = {d: t for d, t in {**kept, **overrides}.items() if t != time_value}
        duration = int(duration_min) if duration_min is not None else int(current.get("duration_min") or 60)
        if not 15 <= duration <= 240:
            raise ValueError("duration_min must be between 15 and 240")
        schedule = {"days_of_week": all_days, "time_utc": time_value, "day_times": merged, "duration_min": duration,
                    "preferred_channel": channel, "priming_lead_minutes": current.get("priming_lead_minutes", 30)}
        self._save({"reminder_schedule": schedule})
        self._sync_cadence_schedule(schedule)
        self.widgets["schedule"] = schedule_widget(schedule)
        return {"reminder_schedule": schedule}

    def _sync_cadence_schedule(self, schedule: Dict[str, Any]) -> None:
        """Mirror into `user_schedules` so the existing Saint cadence/SDUI schedule reads it."""
        if self.memory.get("sport") not in {"badminton", "tennis"}:
            return
        if __package__:
            from . import android_api
        else:
            import android_api
        record = android_api.UserSchedule(
            user_id=self.user_id, sport=self.memory["sport"], stroke_type=self.memory.get("skill_focus") or "overhead_clear",
            days_of_week=schedule["days_of_week"], target_time_utc=schedule["time_utc"],
            priming_lead_minutes=schedule["priming_lead_minutes"], preferred_channel=schedule["preferred_channel"],
        )
        android_api._put("user_schedules", self.user_id, record.model_dump())

    def set_skill_focus(self, focus: str, skill_id: Optional[str] = None) -> Dict[str, Any]:
        """Record what the athlete wants to work on; maps it to a catalog skill of their sport when one fits."""
        sport = sports_config.get_sport(self.memory.get("sport") or "")
        if sport is None:
            raise ValueError("Set the athlete's sport with set_sport_and_goals before choosing a focus")
        note = str(focus).strip()[:300]
        if not note:
            raise ValueError("focus must describe what to work on")
        skill = next((s for s in sport.skills if s.id == skill_id), None) if skill_id else None
        if skill_id and skill is None:
            raise ValueError(f"{skill_id} is not a {sport.id} skill; choose one of {[s.id for s in sport.skills]}")
        if skill is None:
            words = set(re.findall(r"[a-z]+", note.lower()))
            skill = next((s for s in sport.skills
                          if words & (set(s.id.split("_")) | set(s.name.lower().replace("-", " ").split())) - {"one", "the"}),
                         None)
        updates: Dict[str, Any] = {"focus_note": note}
        if skill is not None:
            updates["skill_focus"] = skill.id
        self._save(updates)
        return {"focus_note": note, "skill_focus": self.memory.get("skill_focus"),
                "matched_skill": skill.name if skill else None}

    def get_full_athlete_status(self) -> Dict[str, Any]:
        """Everything Thea needs in one read: profile, plan, schedule, gear, recent sessions and HR trend."""
        m = self.memory
        nodes = m.get("curriculum_nodes") or []
        active = next((n for n in nodes if n.get("status") == "active"), None)
        return {
            "profile": {k: m.get(k) for k in ("sport", "skill_focus", "focus_note", "level", "motivation_why",
                                              "intensity", "phone_number")},
            "plan": {"completed": sum(n.get("status") == "completed" for n in nodes), "total": len(nodes),
                     "active_lesson": {k: active.get(k) for k in ("id", "title", "attempts")} if active else None},
            "schedule": m.get("reminder_schedule"),
            "assigned_drills": [{k: d.get(k) for k in ("id", "title", "target_reps", "stroke_type")}
                                for d in (m.get("assigned_drills") or [])[-5:]],
            "gear_list": m.get("gear_list") or [],
            "recent_flaws": (m.get("recent_flaws") or [])[:3],
            "recent_sessions": recent_sessions(self.user_id),
            "heart_rate": heart_rate_stats(self.user_id),
        }

    def find_nearby_courts_and_weather(self, lat: float = DEFAULT_LAT, lng: float = DEFAULT_LNG,
                                       sport: Optional[str] = None) -> Dict[str, Any]:
        """$nearSphere courts plus a play/postpone call from the next hours' forecast (indoor vs outdoor)."""
        lat, lng = float(lat), float(lng)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("lat/lng out of range")
        sport = (sport or self.memory.get("sport") or "").strip().lower() or None
        found = db_mongo.find_nearby_facilities(lat, lng, limit=8)
        courts = sorted(found["facilities"], key=lambda f: (sport not in (f.get("sports") or []), f["distance_km"]))
        courts = [{k: f.get(k) for k in ("facility_id", "name", "postcode", "sports", "indoor", "outdoor", "distance_km")}
                  for f in courts][:5]
        weather = fetch_weather(lat, lng)
        call = play_call(sport, weather, courts)
        self.widgets["courts"] = {"widget_type": "CourtListWidget", "title": "Courts near you",
                                  "search_method": found["method"], "courts": courts, "play_call": call,
                                  "weather": weather}
        return {"courts": courts, "search_method": found["method"], "weather": weather, "play_call": call,
                "booking_note": "Live prices and slots change: check the venue's booking page, or ask me to "
                                "draft the booking request for Saint to send."}

    def draft_partner_or_coach_message(self, purpose: str, partner_name: Optional[str] = None,
                                       proposed_time: Optional[str] = None, tone: Optional[str] = None) -> Dict[str, Any]:
        """Ready-to-send WhatsApp text. Saved as a draft; Saint only sends it with the athlete's approval."""
        purpose = str(purpose).strip().lower()
        if purpose not in DRAFT_PURPOSES:
            raise ValueError(f"purpose must be one of {sorted(DRAFT_PURPOSES)}")
        tone = (tone or "friendly").strip().lower()
        if tone not in ("friendly", "formal", "brief"):
            raise ValueError("tone must be friendly, formal or brief")
        m = self.memory
        sport = (m.get("sport") or "a hit").replace("_", " ")
        who = (partner_name or "").strip() or ("Coach" if purpose == "coach_update" else "there")
        when = (proposed_time or "").strip() or _next_session_label(m.get("reminder_schedule"))
        focus = m.get("focus_note") or (m.get("skill_focus") or "").replace("_", " ")
        body = DRAFT_PURPOSES[purpose].format(sport=sport, when=when or "this week", focus=focus or "my game",
                                              level=m.get("level") or "club")
        greeting = {"friendly": f"Hey {who}! ", "formal": f"Hello {who}, ", "brief": f"Hi {who}, "}[tone]
        closing = {"friendly": " Let me know!", "formal": " Kind regards.", "brief": ""}[tone]
        text = (greeting + body + closing)[:600]
        draft = {"id": f"draft_{uuid.uuid4().hex[:8]}", "purpose": purpose, "to": partner_name, "text": text,
                 "status": "draft_awaiting_approval", "created_at": datetime.now(timezone.utc).isoformat()}
        self._save({"message_drafts": ((m.get("message_drafts") or []) + [draft])[-5:]})
        return {"draft": draft, "share_link": "https://wa.me/?text=" + quote(text), "sent": False}

    def manage_gear_reorder_list(self, action: str, item_name: Optional[str] = None,
                                 notes: Optional[str] = None, quantity: Optional[int] = None) -> Dict[str, Any]:
        """Maintain athlete_memory.gear_list (restrings, shuttle tubes, overgrips, shoes). Never places an order."""
        action = str(action).strip().lower()
        if action not in ("add", "remove", "mark_ordered", "list"):
            raise ValueError("action must be add, remove, mark_ordered or list")
        gear = [dict(g) for g in self.memory.get("gear_list") or []]
        item = (item_name or "").strip()[:80]
        key = item.lower()
        if action != "list" and not item:
            raise ValueError("item_name is required for add, remove and mark_ordered")
        existing = next((g for g in gear if g["item"].lower() == key), None)
        if action == "add":
            if existing:
                existing.update({k: v for k, v in (("notes", (notes or "").strip()[:200] or None),
                                                    ("quantity", quantity)) if v is not None})
                existing["status"] = "needed"
            else:
                gear.append({"item": item, "notes": (notes or "").strip()[:200] or None, "quantity": int(quantity or 1),
                             "status": "needed", "added_at": datetime.now(timezone.utc).isoformat()})
        elif action == "remove":
            if not existing:
                raise ValueError(f"{item} isn't on the gear list")
            gear.remove(existing)
        elif action == "mark_ordered":
            if not existing:
                raise ValueError(f"{item} isn't on the gear list")
            existing["status"] = "ordered"
            existing["ordered_at"] = datetime.now(timezone.utc).isoformat()
        if action != "list":
            self._save({"gear_list": gear[-25:]})
        return {"gear_list": gear, "needed": [g["item"] for g in gear if g["status"] == "needed"]}


DRAFT_PURPOSES = {
    "hitting_partner": "Fancy a {sport} session {when}? I'm working on {focus} and would love a hitting partner.",
    "availability": "I'm free for {sport} {when}. Does that work for you?",
    "reschedule": "Something's come up. Could we move our {sport} session to {when}? Sorry for the shuffle.",
    "coach_update": "Quick update: I'm training {sport} at {level} level, focusing on {focus}. "
                    "Next session {when}. Any drills you'd add?",
    "court_booking": "Hi, I'd like to book a {sport} court {when}, please. Is anything available?",
}


def _next_session_label(schedule: Optional[Dict[str, Any]]) -> Optional[str]:
    if not schedule or not schedule.get("days_of_week"):
        return None
    today = datetime.now(timezone.utc).strftime("%A")
    days = schedule["days_of_week"]
    order = WEEKDAYS[WEEKDAYS.index(today) + 1:] + WEEKDAYS[:WEEKDAYS.index(today) + 1]
    day = next((d for d in order if d in days), days[0])
    hhmm = (schedule.get("day_times") or {}).get(day) or schedule.get("time_utc")
    return f"{day} at {hhmm} UTC"


def recent_sessions(user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Latest live sets and uploads, newest first, summarised."""
    db = db_mongo.get_db()
    rows: List[Dict[str, Any]] = []
    if db is not None:
        try:
            rows = list(db["android_sessions"].find({"user_id": user_id, "status": "COMPLETED"},
                                                    {"_id": 0, "telemetry": 0}).sort("updated_at", -1).limit(limit))
        except Exception:
            rows = []
    out = []
    for r in rows:
        log = r.get("rep_log") or []
        out.append({"session_id": r.get("session_id"), "source": r.get("source", "upload"),
                    "stroke_type": r.get("stroke_type"), "overall_score": r.get("overall_score"),
                    "primary_flaw": r.get("primary_flaw"), "updated_at": r.get("updated_at"),
                    "adaptation": (r.get("adaptation") or {}).get("action"),
                    "reps": len(log), "counted_reps": sum(1 for x in log if x.get("rep_counted")),
                    "avg_impact_elbow_deg": round(sum(x["phase_angles"]["impact_elbow_deg"] for x in log) / len(log), 1)
                    if log else None,
                    "pro_match": next((x["pro_match"] for x in log if x.get("pro_match")), None)})
    return out


def fetch_weather(lat: float, lng: float) -> Dict[str, Any]:
    """Next 6 hours from Open-Meteo (free, no key). Returns {"available": False} on any failure."""
    try:
        res = requests.get("https://api.open-meteo.com/v1/forecast", timeout=4, params={
            "latitude": round(lat, 3), "longitude": round(lng, 3), "timezone": "UTC", "forecast_days": 1,
            "hourly": "precipitation_probability,wind_speed_10m,temperature_2m"})
        res.raise_for_status()
        hourly = res.json()["hourly"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
        start = next((i for i, t in enumerate(hourly["time"]) if t >= now), 0)
        window = slice(start, start + 6)
        rain = [v for v in hourly["precipitation_probability"][window] if v is not None]
        wind = [v for v in hourly["wind_speed_10m"][window] if v is not None]
        temp = [v for v in hourly["temperature_2m"][window] if v is not None]
        return {"available": True, "source": "open-meteo", "hours": len(rain),
                "max_rain_probability_pct": max(rain) if rain else None,
                "max_wind_kmh": max(wind) if wind else None,
                "temp_c_range": [min(temp), max(temp)] if temp else None}
    except Exception as exc:
        logger.info("Weather lookup failed: %s", exc)
        return {"available": False, "source": "open-meteo"}


def play_call(sport: Optional[str], weather: Dict[str, Any], courts: List[Dict[str, Any]]) -> Dict[str, Any]:
    indoor = next((c for c in courts if c.get("indoor") and (not sport or sport in (c.get("sports") or []))), None)
    outdoor = next((c for c in courts if c.get("outdoor") and (not sport or sport in (c.get("sports") or []))), None)
    if sport == "badminton":
        return {"decision": "play_indoor", "venue": (indoor or {}).get("name"),
                "reason": "Badminton is an indoor game: wind moves the shuttle, so book a hall."}
    if not weather.get("available"):
        return {"decision": "check_forecast", "venue": (indoor or outdoor or {}).get("name"),
                "reason": "No forecast right now; pick an indoor court to be safe."}
    rain, wind = weather.get("max_rain_probability_pct") or 0, weather.get("max_wind_kmh") or 0
    if rain >= 50 or wind >= 30:
        why = f"{rain}% chance of rain" if rain >= 50 else f"{wind:.0f} km/h wind"
        return {"decision": "play_indoor" if indoor else "postpone", "venue": (indoor or {}).get("name"),
                "reason": f"{why} in the next few hours, so " + ("move indoors." if indoor else "postpone the outdoor session.")}
    return {"decision": "play_outdoor", "venue": (outdoor or indoor or {}).get("name"),
            "reason": f"Dry enough ({rain}% rain) and calm ({wind:.0f} km/h): good to play outside."}


TOOL_IMPLEMENTATIONS: Dict[str, Callable[..., Dict[str, Any]]] = {
    name: getattr(TheaToolbox, name) for name in (
        "get_full_athlete_status", "set_sport_and_goals", "set_athlete_level_and_generate_plan",
        "update_lesson_progress", "assign_custom_drill", "update_training_schedule",
        "find_nearby_courts_and_weather", "draft_partner_or_coach_message", "manage_gear_reorder_list",
        "set_skill_focus",
    )
}
# Older tool names still accepted from clients/models that learned them.
TOOL_ALIASES = {"find_nearby_courts": "find_nearby_courts_and_weather"}

ALL_SKILL_IDS = sorted({s.id for sp in sports_config.SPORTS_CATALOG.values() for s in sp.skills})

TOOL_DECLARATIONS: List[Dict[str, Any]] = [
    {"name": "get_full_athlete_status",
     "description": "Read the athlete's full state: profile, plan progress, active lesson, schedule, assigned drills, "
                    "gear list, recent live sets and uploads (reps, scores, pro match) and heart-rate trend. Call it "
                    "before answering questions about how they're doing.",
     "parameters_json_schema": {"type": "object", "properties": {}}},
    {"name": "set_sport_and_goals",
     "description": "Set or switch the athlete's sport, skill focus, motivation (why they train) and intensity. "
                    "Switching sport or skill focus rebuilds the lesson plan.",
     "parameters_json_schema": {"type": "object", "properties": {
         "sport": {"type": "string", "enum": list(sports_config.SPORTS_CATALOG)},
         "skill_focus": {"type": "string", "enum": ALL_SKILL_IDS},
         "motivation_why": {"type": "string", "description": "The athlete's reason for training, in their words"},
         "intensity": {"type": "string", "enum": list(db_mongo.INTENSITIES)},
     }, "required": ["sport"]}},
    {"name": "set_athlete_level_and_generate_plan",
     "description": "Set the athlete's level and (re)generate their curriculum of lesson nodes for the current sport. "
                    "Omit curriculum_nodes to use the catalog progression for that level.",
     "parameters_json_schema": {"type": "object", "properties": {
         "level": {"type": "string", "enum": list(db_mongo.LEVELS)},
         "curriculum_nodes": {"type": "array", "maxItems": MAX_CURRICULUM_NODES, "items": {
             "type": "object", "properties": {
                 "title": {"type": "string"},
                 "tips": {"type": "array", "items": {"type": "string"}},
             }, "required": ["title"]}},
     }, "required": ["level"]}},
    {"name": "update_lesson_progress",
     "description": "Mark a curriculum lesson node locked, active or completed. Completing one unlocks the next.",
     "parameters_json_schema": {"type": "object", "properties": {
         "node_id": {"type": "string"},
         "status": {"type": "string", "enum": list(db_mongo.NODE_STATUSES)},
     }, "required": ["node_id", "status"]}},
    {"name": "assign_custom_drill",
     "description": "Assign a drill to the athlete's Home screen and the head of their Live mode queue. stroke_type "
                    "sets which stroke Live mode counts; sequence makes a combo (e.g. clear then lunge).",
     "parameters_json_schema": {"type": "object", "properties": {
         "title": {"type": "string"}, "instruction": {"type": "string"},
         "target_reps": {"type": "integer", "minimum": 1, "maximum": 500},
         "focus_cue": {"type": "string"},
         "stroke_type": {"type": "string", "enum": sorted(kinematics_engine.SKILL_TO_STROKE)},
         "sequence": {"type": "array", "items": {"type": "string", "enum": sorted(kinematics_engine.SKILL_TO_STROKE)}},
     }, "required": ["title", "instruction", "target_reps", "focus_cue"]}},
    {"name": "update_training_schedule",
     "description": "Set the weekly training days and reminder time. Convert 'N times a week' into N concrete, "
                    "well-spaced weekday names. To move one day's session (\"move Tuesday to 7pm\"), pass only "
                    "day_times; the other days keep their time.",
     "parameters_json_schema": {"type": "object", "properties": {
         "days": {"type": "array", "items": {"type": "string", "enum": WEEKDAYS},
                  "description": "Full set of training days; omit to keep the current days"},
         "time_utc": {"type": "string", "description": "Default HH:MM 24h UTC for every day; omit to keep it"},
         "day_times": {"type": "array", "description": "Per-day time overrides", "items": {
             "type": "object", "properties": {
                 "day": {"type": "string", "enum": WEEKDAYS},
                 "time_utc": {"type": "string", "description": "HH:MM 24h UTC"},
             }, "required": ["day", "time_utc"]}},
         "duration_min": {"type": "integer", "minimum": 15, "maximum": 240},
     }}},
    {"name": "set_skill_focus",
     "description": "Record what the athlete wants to focus on (e.g. 'backhand net clearance'). Pass skill_id when "
                    "it matches one of their sport's skills so analysis and live cues target it.",
     "parameters_json_schema": {"type": "object", "properties": {
         "focus": {"type": "string", "description": "The focus in the athlete's words"},
         "skill_id": {"type": "string", "enum": sorted({s.id for sp in sports_config.SPORTS_CATALOG.values()
                                                        for s in sp.skills})},
     }, "required": ["focus"]}},
    {"name": "find_nearby_courts_and_weather",
     "description": "Find London courts near a location (MongoDB $nearSphere on facilities) with indoor/outdoor "
                    "options and a play / move indoors / postpone call from the live forecast.",
     "parameters_json_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lng": {"type": "number"},
         "sport": {"type": "string", "enum": list(sports_config.SPORTS_CATALOG)},
     }}},
    {"name": "draft_partner_or_coach_message",
     "description": "Draft a ready-to-send WhatsApp message (hitting partner invite, availability, reschedule, coach "
                    "update or court booking request). It's saved as a draft; Saint sends it only after approval.",
     "parameters_json_schema": {"type": "object", "properties": {
         "purpose": {"type": "string", "enum": sorted(DRAFT_PURPOSES)},
         "partner_name": {"type": "string"}, "proposed_time": {"type": "string"},
         "tone": {"type": "string", "enum": ["friendly", "formal", "brief"]},
     }, "required": ["purpose"]}},
    {"name": "manage_gear_reorder_list",
     "description": "Keep the athlete's gear reorder list: restrings (with tension notes), shuttle tubes, overgrips, "
                    "shoes. Never places an order.",
     "parameters_json_schema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["add", "remove", "mark_ordered", "list"]},
         "item_name": {"type": "string"}, "notes": {"type": "string"},
         "quantity": {"type": "integer", "minimum": 1, "maximum": 50},
     }, "required": ["action"]}},
]


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def heart_rate_stats(user_id: str) -> Optional[Dict[str, Any]]:
    window = db_mongo.get_watch_timeseries_window(user_name=user_id, limit=15)
    samples = [s for s in window.get("samples", []) if s.get("heart_rate_bpm") is not None]
    if not samples:
        return None
    hrs = [float(s["heart_rate_bpm"]) for s in samples]
    latest = samples[0]
    return {"sample_count": len(hrs), "avg_hr_bpm": round(sum(hrs) / len(hrs), 1), "max_hr_bpm": max(hrs),
            "latest_hr_bpm": hrs[0], "latest_fatigue_index": latest.get("fatigue_index"),
            "latest_sampled_at": str(latest.get("timestamp") or latest.get("sampled_at") or ""),
            "source": window.get("aggregation_method")}


THEA_PERSONA = (
    "You are Thea, an AI colleague from Encode Club (thea@saint.work, WhatsApp +44 7985 791437) who runs the "
    "tennis and badminton side of this athlete's life. You handle biomechanics analysis of their clips, finding "
    "London courts (Finsbury Leisure, Islington and nearby), play-or-postpone calls when weather is in question, "
    "hitting-partner message templates, gear reorders and their structured weekly lesson plan. You are warm, "
    "direct and practical: a colleague who has their back, not a chatbot. Every channel (app, live, WhatsApp, "
    "Gemini) shares one memory, so you remember what they told you elsewhere."
)

CHANNEL_STYLE = {
    "app": "Reply in 2-4 short sentences; the app renders plan, schedule and drill widgets for you.",
    "live": "You are speaking in a live voice session mid-practice: 1-2 short spoken sentences, no lists or markdown.",
    "whatsapp": "Reply as a concise WhatsApp message: plain text, at most 3 short lines, no markdown headers.",
    "gemini": "Reply in 2-4 short sentences.",
}


def system_instruction(memory: Dict[str, Any], hr: Optional[Dict[str, Any]], channel: str) -> str:
    profile = {k: v for k, v in memory.items() if k not in ("chat_history", "_id")}
    return (
        f"{THEA_PERSONA}\n"
        "Rules:\n"
        "- Persist every change the athlete asks for by calling tools; never claim a change you did not make with a tool.\n"
        "- Sport, motivation or intensity mentioned -> set_sport_and_goals. Training frequency or days -> "
        "update_training_schedule with concrete weekday names (one day moved -> day_times only). Level stated -> "
        "set_athlete_level_and_generate_plan. A technique to focus on -> set_skill_focus.\n"
        "- Only cite biomechanics from recent_flaws and heart-rate numbers from the stats below; never invent measurements.\n"
        "- No sport or plan in memory yet: greet them warmly as Thea and ask their sport, level and goal. Otherwise "
        "point them to their active lesson (the curriculum node with status active) as the next step.\n"
        "- Use get_full_athlete_status before judging progress. Court + weather questions -> "
        "find_nearby_courts_and_weather. Messages to partners/coaches/venues -> draft_partner_or_coach_message "
        "(a draft only). Kit -> manage_gear_reorder_list. Drills -> assign_custom_drill with stroke_type so Live counts it.\n"
        "- You don't place bookings or orders yourself: drafts go to Saint for the athlete's approval, so never say "
        "a booking or order is done.\n"
        f"- Location unknown for court search: use central London ({DEFAULT_LAT}, {DEFAULT_LNG}).\n"
        f"- {CHANNEL_STYLE[channel]}\n"
        f"Today (UTC): {datetime.now(timezone.utc).strftime('%A %Y-%m-%d')}\n"
        f"Supported sports: {', '.join(sports_config.SPORTS_CATALOG)}\n"
        f"Athlete memory: {profile}\n"
        f"Watch heart-rate stats (last 15 samples): {hr or 'no recent watch data'}"
    )


def make_speak_text(text: str, channel: str) -> str:
    plain = re.sub(r"https?://\S+", "", text)
    plain = re.sub(r"[*_#`>|~\[\]]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    sentences = re.split(r"(?<=[.!?])\s+", plain)
    spoken = " ".join(sentences[: 2 if channel == "live" else 3])
    return spoken[:300].rstrip()


# ---------------------------------------------------------------------------
# Gemini function-calling loop
# ---------------------------------------------------------------------------

_GEMINI_CLIENT: Any = None


def _gemini_generate(contents: List[Any], config: Any) -> Any:
    # Keep one client alive: a temporary genai.Client closes its HTTP session when collected.
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        _GEMINI_CLIENT = llm_config.get_client()
    return _GEMINI_CLIENT.models.generate_content(
        model=llm_config.GEMINI_MODEL, contents=contents, config=config)


def run_gemini(toolbox: TheaToolbox, message: str, channel: str, hr: Optional[Dict[str, Any]]) -> str:
    from google.genai import types

    tools = [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in TOOL_DECLARATIONS])]

    def config(mode: str = "AUTO") -> Any:
        return types.GenerateContentConfig(
            system_instruction=system_instruction(toolbox.memory, hr, channel),
            tools=tools,
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode)),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=llm_config.GEMINI_THINKING_LEVEL),
        )

    contents: List[Any] = []
    for turn in toolbox.memory.get("chat_history") or []:
        contents.append(types.Content(role="user", parts=[types.Part(text=turn.get("user", ""))]))
        contents.append(types.Content(role="model", parts=[types.Part(text=turn.get("coach", ""))]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    for _ in range(MAX_TOOL_ROUNDS):
        response = _gemini_generate(contents, config())
        calls = response.function_calls or []
        if not calls:
            return (response.text or "").strip()
        contents.append(response.candidates[0].content)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=call.name, response=toolbox.run(call.name, dict(call.args or {})))
            for call in calls
        ]))
    return (_gemini_generate(contents, config("NONE")).text or "").strip()


# ---------------------------------------------------------------------------
# Rule-based fallback (no Gemini key or Gemini error): same tools, same memory
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {"once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}


def _clock_to_24h(clock: str) -> Optional[str]:
    m = re.fullmatch(r"([0-9]{1,2})(?::([0-5][0-9]))?\s*(am|pm)?", clock.strip())
    if not m:
        return None
    hour = int(m.group(1))
    if m.group(3):
        hour = hour % 12 + (12 if m.group(3) == "pm" else 0)
    elif hour < 8:
        hour += 12  # "move it to 7" means the evening for training sessions
    return f"{hour:02d}:{m.group(2) or '00'}" if hour < 24 else None


def plan_fallback_calls(message: str, memory: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    text = message.lower()
    calls: List[Tuple[str, Dict[str, Any]]] = []
    sport = next((sid for sid, s in sports_config.SPORTS_CATALOG.items()
                  if re.search(rf"\b({sid}|{s.display_name.lower()})\b", text)), None)
    intensity = ("competitive" if re.search(r"\bcompet|tournament|\bmatch play", text) else
                 "casual" if re.search(r"\bcasual|for fun|relaxed", text) else
                 "regular" if re.search(r"\bregular(ly)?\b", text) else None)
    if sport or intensity:
        calls.append(("set_sport_and_goals", {"sport": sport or memory.get("sport") or "badminton",
                                              **({"intensity": intensity} if intensity else {})}))
    level = next((lvl for lvl in db_mongo.LEVELS if lvl in text), None)
    if level:
        calls.append(("set_athlete_level_and_generate_plan", {"level": level}))
    focus = re.search(r"\bfocus(?:ing)? on (?:my |the )?(.+?)(?:\s+and\s+(?:move|change|shift|train)\b|[,.!?]|$)", text)
    if focus:
        calls.append(("set_skill_focus", {"focus": focus.group(1).strip()}))
    moves = re.findall(rf"\b(?:move|change|shift|push)\s+(?:my\s+)?({'|'.join(d.lower() for d in WEEKDAYS)})s?"
                       r"(?:'s)?\s+(?:session|practice|training)?\s*(?:to|at)\s+([0-9]{1,2}(?::[0-5][0-9])?\s*(?:am|pm)?)", text)
    if moves:
        day_times = [{"day": day.title(), "time_utc": _clock_to_24h(clock)} for day, clock in moves]
        calls.append(("update_training_schedule", {"day_times": [d for d in day_times if d["time_utc"]]}))
    freq = re.search(r"\b(\d|once|twice|one|two|three|four|five|six|seven)\s*(?:x|times?)?\s*(?:a|per|each)\s*week", text)
    named_days = [] if moves else [d for d in WEEKDAYS if re.search(rf"\b{d.lower()}s?\b", text)]
    if freq or named_days:
        n = freq and (int(freq.group(1)) if freq.group(1).isdigit() else _NUMBER_WORDS[freq.group(1)])
        clock = re.search(r"\b(?:at\s*)?([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b|\b([01]\d|2[0-3]):([0-5]\d)\b", text)
        args: Dict[str, Any] = {"days": named_days or DAY_SPREADS[max(1, min(7, n))]}
        if clock:
            if clock.group(3):
                hour = int(clock.group(1)) % 12 + (12 if clock.group(3) == "pm" else 0)
                args["time_utc"] = f"{hour:02d}:{clock.group(2) or '00'}"
            else:
                args["time_utc"] = f"{clock.group(4)}:{clock.group(5)}"
        calls.append(("update_training_schedule", args))
    if re.search(r"\bcourts?\b|\bnear(by)?\b|where (can|should) i (play|train)|\bweather\b|\brain\b", text):
        calls.append(("find_nearby_courts_and_weather", {"lat": DEFAULT_LAT, "lng": DEFAULT_LNG}))
    if re.search(r"\b(how am i doing|how did|my progress|status|last (live )?set|my stats)\b", text):
        calls.append(("get_full_athlete_status", {}))
    draft = re.search(r"\b(draft|write|message|text)\b.*\b(partner|coach|reschedul|book)", text)
    if draft:
        purpose = ("coach_update" if "coach" in text else "reschedule" if "reschedul" in text
                   else "court_booking" if "book" in text else "hitting_partner")
        name = re.search(r"\b(?:to|for) ([A-Z][a-z]+)\b", message)
        calls.append(("draft_partner_or_coach_message", {"purpose": purpose, **({"partner_name": name.group(1)} if name else {})}))
    gear = re.search(r"\b(?:add|reorder|order|need|buy)\b.*?\b(restring|strings?|overgrips?|grips?|shuttles?|shuttlecocks?|"
                     r"tubes? of shuttles|balls|shoes|racket)\b", text)
    if gear:
        calls.append(("manage_gear_reorder_list", {"action": "add", "item_name": gear.group(1)}))
    elif re.search(r"\bgear( list)?\b", text):
        calls.append(("manage_gear_reorder_list", {"action": "list"}))
    return calls


def fallback_reply(toolbox: TheaToolbox) -> str:
    m = toolbox.memory
    parts = []
    if "set_sport_and_goals" in toolbox.actions:
        parts.append(f"You're set for {m.get('sport')}" + (f" at a {m['intensity']} intensity" if m.get("intensity") else "") + ".")
    if m.get("curriculum_nodes") and "path" in toolbox.widgets:
        active = next((n for n in m["curriculum_nodes"] if n["status"] == "active"), m["curriculum_nodes"][0])
        parts.append(f"Your {len(m['curriculum_nodes'])}-step plan starts with {active['title']}.")
    if "set_skill_focus" in toolbox.actions:
        parts.append(f"Focus noted: {m.get('focus_note')}.")
    if "schedule" in toolbox.widgets:
        s = m["reminder_schedule"]
        moved = "".join(f", {d} at {t}" for d, t in (s.get("day_times") or {}).items())
        parts.append(f"I'll train you {', '.join(s['days_of_week'])} at {s['time_utc']} UTC{moved}.")
    if "courts" in toolbox.widgets and toolbox.widgets["courts"]["courts"]:
        court = toolbox.widgets["courts"]["courts"][0]
        parts.append(f"Closest court: {court['name']} ({court['distance_km']} km).")
        call = toolbox.widgets["courts"].get("play_call") or {}
        if call.get("reason"):
            parts.append(call["reason"])
    if "draft_partner_or_coach_message" in toolbox.actions:
        draft = (m.get("message_drafts") or [{}])[-1]
        parts.append(f"Here's a draft for you to approve: \"{draft.get('text')}\"")
    if "manage_gear_reorder_list" in toolbox.actions:
        needed = [g["item"] for g in m.get("gear_list") or [] if g.get("status") == "needed"]
        parts.append(f"Gear list: {', '.join(needed) or 'nothing outstanding'}.")
    if "get_full_athlete_status" in toolbox.actions and not parts:
        nodes = m.get("curriculum_nodes") or []
        done = sum(n.get("status") == "completed" for n in nodes)
        active = next((n for n in nodes if n.get("status") == "active"), None)
        latest = (recent_sessions(toolbox.user_id, 1) or [None])[0]
        parts.append(f"You've completed {done} of {len(nodes)} lessons" +
                     (f" and you're on {active['title']}." if active else "."))
        if latest:
            parts.append(f"Last {latest['source']} session scored {latest['overall_score']}" +
                         (f" with {latest['counted_reps']}/{latest['reps']} reps counted." if latest['reps'] else "."))
    if parts:
        return " ".join(parts)
    active = next((n for n in m.get("curriculum_nodes") or [] if n.get("status") == "active"), None)
    if active:
        return f"Hi, it's Thea. Your next lesson is {active['title']}. Want to record a few reps so I can check them?"
    return ("Hi, I'm Thea, your Encode Club coach for tennis and badminton. Tell me your sport, your level and "
            "how often you'd like to train, and I'll build your plan.")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def _identity(request: Request) -> Dict[str, Any]:
    return principal(request)


def resolve_athlete(req: ConverseRequest, identity: Dict[str, Any]) -> str:
    user_id = (req.user_id or "").strip() or None
    if not user_id and req.phone_number:
        found = db_mongo.find_athlete_by_phone(req.phone_number)
        user_id = found["user_id"] if found else None
    user_id = user_id or identity["user_id"]
    if identity.get("role") != "admin" and identity["user_id"] != user_id:
        raise HTTPException(403, "This athlete belongs to another player")
    return user_id


@router.post("/converse", response_model=ConverseResponse)
def converse(req: ConverseRequest, identity: Dict[str, Any] = Depends(_identity)) -> ConverseResponse:
    started = time.monotonic()
    user_id = resolve_athlete(req, identity)  # 403 for another player's athlete stays an error
    try:
        return _converse_turn(req, user_id, started)
    except Exception:
        logger.exception("Coach Thea turn failed for %s", user_id)
        reply = "Sorry, something went wrong on my side. Give me a moment and ask me again."
        return ConverseResponse(
            reply_text=reply, speak_text=reply, tool_actions_taken=[], athlete_memory={}, active_widgets=[],
            llm_source="error", llm_model="none", latency_ms=int((time.monotonic() - started) * 1000),
            audio_cue_text=reply, dynamic_widgets=[],
        )


def _converse_turn(req: ConverseRequest, user_id: str, started: float) -> ConverseResponse:
    toolbox = TheaToolbox(user_id)
    if req.phone_number and toolbox.memory.get("phone_number") != req.phone_number:
        toolbox._save({"phone_number": req.phone_number})
    hr = heart_rate_stats(user_id)

    llm_source, reply = "gemini", ""
    if llm_config.GEMINI_API_KEY:
        try:
            reply = run_gemini(toolbox, req.message, req.channel, hr)
            llm_config.update_ai_status(True, latency_ms=int((time.monotonic() - started) * 1000))
        except Exception as exc:
            logger.warning("Coach Thea Gemini call failed, using rule-based fallback: %s", exc)
            llm_config.update_ai_status(False, error=type(exc).__name__)
            llm_source = "fallback"
    else:
        llm_source = "fallback"
    if llm_source == "fallback":
        for name, args in plan_fallback_calls(req.message, toolbox.memory):
            toolbox.run(name, args)
    if not reply:
        reply = fallback_reply(toolbox)

    db_mongo.append_chat_turn(user_id, {"user": req.message, "coach": reply, "channel": req.channel,
                                        "session_id": req.session_id, "tools": toolbox.actions,
                                        "at": datetime.now(timezone.utc).isoformat()})
    memory = db_mongo.get_athlete_memory(user_id)
    widgets = list(toolbox.widgets.values())
    speak = make_speak_text(reply, req.channel)
    return ConverseResponse(
        reply_text=reply, speak_text=speak, tool_actions_taken=toolbox.actions, athlete_memory=memory,
        active_widgets=widgets, llm_source=llm_source,
        llm_model=llm_config.GEMINI_MODEL if llm_source == "gemini" else "rule_based_fallback",
        latency_ms=int((time.monotonic() - started) * 1000), audio_cue_text=speak, dynamic_widgets=widgets,
    )
