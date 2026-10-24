"""Onboarding assessment and shared-memory home feed.

`POST /api/v1/onboarding/next` is a stateless step machine (the client echoes accumulated
`answers`) that writes each answer into `athlete_memory`:

    sport -> level_q1 -> level_q2 -> goal -> intensity -> schedule -> complete

The two ConceptQuizWidget answers score the athlete's level, and the final step asks
Gemini 4 Argon for a 5-node curriculum (catalog fallback without Gemini).
`GET /api/v1/coach/memory` renders the home screen from the same document.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

if __package__ == "backend.api.v1":
    from ... import coach_converse, db_mongo, llm_config, sports_config
else:
    import coach_converse, db_mongo, llm_config, sports_config

logger = logging.getLogger("tempo.onboarding")

router = APIRouter(prefix="/api/v1", tags=["onboarding"])

PLAN_NODE_COUNT = 5
STEP_PROGRESS = {"sport": 0.1, "level_q1": 0.2, "level_q2": 0.35, "goal": 0.5,
                 "intensity": 0.65, "schedule": 0.8, "complete": 1.0}

GOALS = {
    "fitness": ("Fitness", "Get fitter and healthier through the game", "💪"),
    "social_match_play": ("Social Match Play", "Hold your own in friendly games and club nights", "🤝"),
    "tournament_mastery": ("Tournament Mastery", "Compete and win in tournaments", "🏆"),
    "technique_refinement": ("Technique Refinement", "Polish your strokes with measured feedback", "🎯"),
}
INTENSITY_OPTIONS = {
    "casual_2x": ("casual", 2, "2x / week", "Relaxed pace to build the habit"),
    "regular_3x": ("regular", 3, "3x / week", "Steady progress with recovery days"),
    "competitive_5x": ("competitive", 5, "5x / week", "High volume for fast improvement"),
}
TIME_SLOTS = [("07:00", "Morning"), ("12:30", "Lunch"), ("18:00", "Evening"), ("20:00", "Late evening")]
ARCHETYPES = {"badminton": "Viktor Axelsen", "tennis": "Roger Federer"}

# Two diagnostic questions per sport; the athlete's score (0-2) maps to their level.
LEVEL_QUIZZES: Dict[str, List[Dict[str, Any]]] = {
    "badminton": [
        {"question": "On an overhead clear, where should your racket arm be at contact?",
         "options": ["Bent at 90 deg in front of your chest", "Fully extended, high above your hitting shoulder",
                     "Low beside your hip", "Behind your head with the elbow bent"],
         "correct_index": 1,
         "explanation": "Contact at full extension above the shoulder gives the highest, deepest clear."},
        {"question": "You've just hit a clear from the rear court. What's your next move?",
         "options": ["Watch where the shuttle lands", "Recover towards base and split-step as your opponent hits",
                     "Stay on the back line", "Sprint straight to the net"],
         "correct_index": 1,
         "explanation": "Recovering to base and split-stepping on your opponent's hit covers the whole court."},
    ],
    "tennis": [
        {"question": "Where is the ideal forehand contact point?",
         "options": ["Beside your back hip", "Out in front of your lead hip, with space from your body",
                     "Directly above your head", "Tight to your chest with a bent elbow"],
         "correct_index": 1,
         "explanation": "Contact in front with space lets the kinetic chain transfer into the ball."},
        {"question": "What does a split-step do for you?",
         "options": ["Adds topspin to your next shot", "Loads your legs so you react the moment your opponent strikes",
                     "Slows the rally down", "It only matters when serving"],
         "correct_index": 1,
         "explanation": "Landing the split-step as your opponent strikes lets you push off in any direction."},
    ],
}
GENERIC_QUIZ = [
    {"question": "Where does most of your racket-head speed come from?",
     "options": ["Your wrist alone", "The ground-up chain: legs, hips, trunk, then arm",
                 "Gripping the handle tighter", "Your shoulder alone"],
     "correct_index": 1,
     "explanation": "Speed builds from the ground up; the arm finishes what the legs and trunk start."},
    LEVEL_QUIZZES["tennis"][1],
]
FALLBACK_PAD_NODES = [
    ("Split-Step & Recovery Footwork", "Land your split-step as your opponent strikes, then push off"),
    ("Consistency Rally Challenge", "Keep 20 shots in play at 70% pace before adding power"),
    ("Match Play Application", "Use the stroke under pressure in a points-based game"),
]


class OnboardingStepRequest(BaseModel):
    step_id: str = Field(default="", max_length=64)
    answer: str = Field(default="", max_length=2000)
    answers: Dict[str, str] = Field(default_factory=dict)


class UserProfileResponse(BaseModel):
    user_id: str
    sport: str
    level: str
    goal: str
    playstyle: str
    injuries: str = "none"
    target_archetype: str
    calibration_completed: bool = True


class OnboardingStepResponse(BaseModel):
    step_id: str
    progress: float
    coach_message: str
    widget: Optional[Dict[str, Any]] = None
    is_completed: bool = False
    user_profile: Optional[UserProfileResponse] = None
    athlete_memory: Dict[str, Any] = Field(default_factory=dict)
    llm_source: Optional[str] = None


def quizzes_for(sport: Optional[str]) -> List[Dict[str, Any]]:
    return LEVEL_QUIZZES.get(sport or "", GENERIC_QUIZ)


def quiz_widget(sport: str, index: int, answered_index: Optional[int] = None) -> Dict[str, Any]:
    quiz = quizzes_for(sport)[index]
    return {"widget_type": "ConceptQuizWidget", "id": f"level_q{index + 1}", **quiz,
            **({"answered_index": answered_index} if answered_index is not None else {})}


def score_level(sport: str, answers: Dict[str, str]) -> str:
    correct = 0
    for i, quiz in enumerate(quizzes_for(sport)):
        raw = answers.get(f"level_q{i + 1}", "")
        if raw.strip().lstrip("-").isdigit() and int(raw) == quiz["correct_index"]:
            correct += 1
    return db_mongo.LEVELS[correct]


def sport_choice_widget() -> Dict[str, Any]:
    return {"widget_type": "ChoiceWidget", "id": "sport", "title": "Select Your Sport",
            "subtitle": "Your plan, pro benchmarks and drills adapt to this sport.",
            "options": [{"id": s.id, "label": s.display_name,
                         "description": None if s.analysis_ready else "Coaching only (no video analysis yet)"}
                        for s in sports_config.SPORTS_CATALOG.values()]}


def goal_widget() -> Dict[str, Any]:
    return {"widget_type": "ChoiceWidget", "id": "goal", "title": "Why are you learning?",
            "options": [{"id": k, "label": v[0], "description": v[1], "emoji": v[2]} for k, v in GOALS.items()]}


def intensity_widget() -> Dict[str, Any]:
    return {"widget_type": "ChoiceWidget", "id": "intensity", "title": "How often do you want to train?",
            "options": [{"id": k, "label": v[2], "description": v[3]} for k, v in INTENSITY_OPTIONS.items()]}


def schedule_step_widget(sessions_per_week: int) -> Dict[str, Any]:
    days = coach_converse.DAY_SPREADS[sessions_per_week]
    return {"widget_type": "CheckInScheduleWidget", "id": "schedule", "title": "Pick your training days",
            "subtitle": f"{sessions_per_week}x per week. Thea will nudge you before each session.",
            "days_of_week": days, "target_time_utc": coach_converse.DEFAULT_TIME_UTC, "priming_lead_minutes": 30,
            "preferred_channel": "whatsapp",
            "slots": [{"slot_id": t, "day_label": label, "time_label": f"{t} UTC",
                       "recommended": t == coach_converse.DEFAULT_TIME_UTC} for t, label in TIME_SLOTS],
            "selected_slot_id": coach_converse.DEFAULT_TIME_UTC}


def parse_schedule_answer(answer: str, sessions_per_week: int) -> Dict[str, Any]:
    """Accept the schedule card's JSON, a picked slot time ("18:00"), or anything else for the defaults."""
    args: Dict[str, Any] = {"days": coach_converse.DAY_SPREADS[sessions_per_week]}
    text = (answer or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = {}
        if data.get("days_of_week"):
            args["days"] = data["days_of_week"]
        if data.get("target_time_utc"):
            args["time_utc"] = data["target_time_utc"]
        if data.get("preferred_channel"):
            args["preferred_channel"] = data["preferred_channel"]
    elif re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
        args["time_utc"] = text
    return args


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

def _catalog_drills(sport: str) -> Dict[str, Dict[str, Any]]:
    return {d["drill_id"]: d for d in db_mongo.build_drills_catalog() if d["sport"] == sport}


def _plan_prompt(memory: Dict[str, Any], drills: Dict[str, Dict[str, Any]]) -> str:
    sport = sports_config.get_sport(memory["sport"])
    skills = ", ".join(s.name for s in sport.skills)
    drill_lines = "\n".join(f"- {d['drill_id']}: {d['title']} ({d['skill_name']})" for d in drills.values())
    return (
        f"You are Coach Thea. Design a {PLAN_NODE_COUNT}-lesson progression for a {memory['level']} "
        f"{sport.display_name} player.\n"
        f"Motivation: {GOALS.get(memory.get('motivation_why') or '', ('general improvement',))[0]}. "
        f"Intensity: {memory.get('intensity')}. Primary skill: {memory.get('skill_focus')}. Sport skills: {skills}.\n"
        "Order lessons from foundation to application; each title is short and concrete, each lesson has "
        "2-3 coaching tips a player can act on in one session.\n"
        + (f"Attach a catalog drill_id where one fits:\n{drill_lines}\n" if drill_lines else "")
        + "Also write coach_message: one or two warm sentences introducing the plan to this athlete, who has "
        "just signed up and finished onboarding."
    )


def generate_plan_with_gemini(memory: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ask Gemini 4 Argon for a structured plan; returns None without a key or on any error."""
    if not llm_config.GEMINI_API_KEY:
        return None
    from google.genai import types

    drills = _catalog_drills(memory["sport"])
    node_schema: Dict[str, Any] = {"type": "object", "properties": {
        "title": {"type": "string"},
        "tips": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
    }, "required": ["title", "tips"]}
    if drills:
        node_schema["properties"]["drill_id"] = {"type": "string", "enum": list(drills)}
    schema = {"type": "object", "properties": {
        "nodes": {"type": "array", "items": node_schema, "minItems": PLAN_NODE_COUNT, "maxItems": PLAN_NODE_COUNT},
        "coach_message": {"type": "string"},
    }, "required": ["nodes", "coach_message"]}
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level=llm_config.GEMINI_THINKING_LEVEL),
    )
    try:
        response = coach_converse._gemini_generate([_plan_prompt(memory, drills)], config)
        data = json.loads(response.text)
        nodes = []
        for node in data["nodes"][:PLAN_NODE_COUNT]:
            drill = drills.get(node.get("drill_id") or "")
            nodes.append({"title": node["title"], "tips": node.get("tips") or [],
                          "drill_spec": {k: drill[k] for k in ("drill_id", "title", "instruction", "target_reps",
                                                                "focus_cue")} if drill else None})
        if len(nodes) < PLAN_NODE_COUNT:
            raise ValueError(f"Gemini returned {len(nodes)} nodes")
        return {"nodes": nodes, "coach_message": str(data.get("coach_message") or "").strip()}
    except Exception as exc:
        logger.warning("Argon plan generation failed, using catalog plan: %s", exc)
        return None


def build_onboarding_plan(memory: Dict[str, Any]) -> Dict[str, Any]:
    generated = generate_plan_with_gemini(memory)
    if generated:
        nodes = coach_converse.build_curriculum(memory["sport"], memory["level"], memory.get("skill_focus"),
                                                generated["nodes"])
        return {"nodes": nodes[:PLAN_NODE_COUNT], "coach_message": generated["coach_message"], "source": "gemini"}
    nodes = coach_converse.build_curriculum(memory["sport"], memory["level"], memory.get("skill_focus"))
    nodes = nodes[:PLAN_NODE_COUNT]
    sport = sports_config.get_sport(memory["sport"])
    for title, tip in FALLBACK_PAD_NODES[: PLAN_NODE_COUNT - len(nodes)]:
        nodes.append({"id": f"{memory['sport']}_{len(nodes) + 1:02d}_{coach_converse._slug(title)}",
                      "title": title, "status": "locked", "tips": [tip], "drill_spec": None,
                      "youtube_url": db_mongo.youtube_search_url(sport.display_name, title, memory["level"])})
    return {"nodes": nodes, "coach_message": "", "source": "fallback"}


# ---------------------------------------------------------------------------
# Onboarding step machine
# ---------------------------------------------------------------------------

def user_profile(memory: Dict[str, Any]) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=memory["user_id"], sport=memory.get("sport") or "", level=memory.get("level") or "beginner",
        goal=memory.get("motivation_why") or "technique_refinement", playstyle=memory.get("intensity") or "regular",
        target_archetype=ARCHETYPES.get(memory.get("sport") or "", "Pro Benchmark"),
    )


def step(step_id: str, message: str, widget: Optional[Dict[str, Any]], memory: Dict[str, Any],
         **extra: Any) -> OnboardingStepResponse:
    return OnboardingStepResponse(step_id=step_id, progress=STEP_PROGRESS[step_id], coach_message=message,
                                  widget=widget, athlete_memory=memory, **extra)


@router.post("/onboarding/next", response_model=OnboardingStepResponse)
def next_onboarding_step(req: OnboardingStepRequest,
                         identity: Dict[str, Any] = Depends(coach_converse._identity)) -> OnboardingStepResponse:
    user_id = identity["user_id"]
    toolbox = coach_converse.TheaToolbox(user_id)
    memory = toolbox.memory
    answers = dict(req.answers)
    current, answer = (req.step_id or "").strip(), (req.answer or "").strip()
    if current and answer:
        answers[current] = answer

    if current == "sport" and answer:
        sport = sports_config.get_sport(answer)
        if sport is None:
            raise HTTPException(422, f"Unknown sport {answer}")
        focus = next((s.id for s in sport.skills if s.analysis_ready), sport.skills[0].id if sport.skills else None)
        memory = toolbox._save({"sport": sport.id, "skill_focus": focus, "recent_flaws": []})
        current = "sport_saved"
    elif current in ("", "init"):
        current = "sport_saved" if memory.get("sport") else ""

    sport_id = memory.get("sport")
    if not current or not sport_id:
        return step("sport", "Hey, I'm Thea, your Tempo coach. Which sport are we training?",
                    sport_choice_widget(), memory)

    sport_name = sports_config.get_sport(sport_id).display_name
    if current == "sport_saved":
        return step("level_q1", f"{sport_name}, great. Two quick questions so I can pitch your plan at the right level.",
                    quiz_widget(sport_id, 0), memory)
    if current == "level_q1":
        return step("level_q2", "Nice. One more.", quiz_widget(sport_id, 1), memory)
    if current == "level_q2":
        memory = toolbox._save({"level": score_level(sport_id, answers)})
        return step("goal", f"I'll start you at {memory['level']} level. Why are you learning {sport_name}?",
                    goal_widget(), memory)
    if current == "goal":
        if answer not in GOALS:
            raise HTTPException(422, f"Unknown goal {answer}")
        memory = toolbox._save({"motivation_why": answer})
        return step("intensity", "Love it. How often can you train?", intensity_widget(), memory)
    if current == "intensity":
        if answer not in INTENSITY_OPTIONS:
            raise HTTPException(422, f"Unknown intensity {answer}")
        intensity, per_week, _, _ = INTENSITY_OPTIONS[answer]
        memory = toolbox._save({"intensity": intensity})
        return step("schedule", f"{per_week} sessions a week it is. Pick your days and when I should remind you.",
                    schedule_step_widget(per_week), memory)
    if current == "schedule":
        per_week = INTENSITY_OPTIONS.get(answers.get("intensity", ""), ("regular", 3))[1]
        result = toolbox.run("update_training_schedule", parse_schedule_answer(answer, per_week))
        if not result["ok"]:
            raise HTTPException(422, result["error"])
        plan = build_onboarding_plan(toolbox.memory)
        memory = toolbox._save({"curriculum_nodes": plan["nodes"]})
        schedule = memory["reminder_schedule"]
        message = plan["coach_message"] or (
            f"Your {len(plan['nodes'])}-lesson {sport_name} plan is ready, starting with {plan['nodes'][0]['title']}.")
        message += f" I'll check in {', '.join(schedule['days_of_week'])} at {schedule['time_utc']} UTC."
        return step("complete", message, home_path_widget(memory), memory, is_completed=True,
                    user_profile=user_profile(memory), llm_source=plan["source"])
    raise HTTPException(422, f"Unknown onboarding step {req.step_id}")


# ---------------------------------------------------------------------------
# Home feed from shared memory
# ---------------------------------------------------------------------------

def home_path_widget(memory: Dict[str, Any]) -> Dict[str, Any]:
    widget = coach_converse.path_widget(memory)
    sport = sports_config.get_sport(memory.get("sport") or "")
    widget["title"] = f"{sport.display_name if sport else 'Your'} {(memory.get('level') or '').title()} Path".replace("  ", " ")
    return widget


def home_widgets(memory: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = memory.get("curriculum_nodes") or []
    if not nodes:
        return []
    widgets = [home_path_widget(memory)]
    active = next((n for n in nodes if n["status"] == "active"), None)
    drills = []
    if active and active.get("drill_spec"):
        spec = active["drill_spec"]
        drills.append({"id": spec.get("drill_id") or active["id"], "title": spec["title"],
                       "instruction": spec["instruction"], "target_reps": spec["target_reps"],
                       "focus_cue": spec["focus_cue"]})
    for d in reversed(memory.get("assigned_drills") or []):
        drills.append({k: d[k] for k in ("id", "title", "instruction", "target_reps", "focus_cue")})
    widgets += [{"widget_type": "DrillCardWidget", **d} for d in drills[:2]]
    completed = sum(1 for n in nodes if n["status"] == "completed")
    quizzes = quizzes_for(memory.get("sport"))
    widgets.append(quiz_widget(memory.get("sport") or "", completed % len(quizzes)) | {"id": f"home_quiz_{completed}"})
    return widgets


class CoachMemoryResponse(BaseModel):
    athlete_memory: Dict[str, Any]
    header: Dict[str, Any]
    widgets: List[Dict[str, Any]]
    onboarding_complete: bool


@router.get("/coach/memory", response_model=CoachMemoryResponse)
def get_coach_memory(identity: Dict[str, Any] = Depends(coach_converse._identity)) -> CoachMemoryResponse:
    memory = db_mongo.get_athlete_memory(identity["user_id"])
    sport = sports_config.get_sport(memory.get("sport") or "")
    schedule = memory.get("reminder_schedule") or {}
    nodes = memory.get("curriculum_nodes") or []
    header = {
        "sport": memory.get("sport"),
        "sport_display": sport.display_name if sport else None,
        "level": memory.get("level"),
        "intensity": memory.get("intensity"),
        "sessions_per_week": len(schedule.get("days_of_week") or []),
        "cadence_label": (f"{len(schedule['days_of_week'])}x/week · {schedule['time_utc']} UTC"
                          if schedule.get("days_of_week") else None),
        "completed_nodes": sum(1 for n in nodes if n["status"] == "completed"),
        "total_nodes": len(nodes),
    }
    return CoachMemoryResponse(athlete_memory=memory, header=header, widgets=home_widgets(memory),
                               onboarding_complete=bool(nodes and schedule))
