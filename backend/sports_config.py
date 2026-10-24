"""Single source of truth for sports, skills, biomechanical rubrics, and drills."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DrillDefinition(BaseModel):
    id: str
    title: str
    instruction: str
    focus_cue: str
    target_reps: int = 10


class FaultDefinition(BaseModel):
    id: str
    name: str
    description: str
    cue_id: str
    drill_ids: List[str]


class SkillDefinition(BaseModel):
    id: str
    name: str
    analysis_ready: bool = True
    phases: List[str] = Field(default_factory=lambda: ["Preparation", "Loading", "Impact", "Follow-Through"])
    metrics: List[str] = Field(default_factory=lambda: ["right_elbow_contact_deg", "right_shoulder_abduction_deg", "trunk_arch_deg"])
    threshold_pass_deg: float = 165.0
    rubric_by_level: Dict[str, Dict[str, float]] = Field(default_factory=lambda: {
        "beginner": {"elbow_target_deg": 160.0, "shoulder_abduction_target_deg": 135.0},
        "intermediate": {"elbow_target_deg": 165.0, "shoulder_abduction_target_deg": 142.0},
        "advanced": {"elbow_target_deg": 172.0, "shoulder_abduction_target_deg": 148.0},
    })
    common_faults: List[FaultDefinition] = Field(default_factory=list)
    drills: List[DrillDefinition] = Field(default_factory=list)


class SportDefinition(BaseModel):
    id: str
    display_name: str
    icon_key: str
    analysis_ready: bool = True
    skills: List[SkillDefinition] = Field(default_factory=list)


# Authoring the sports catalog
SPORTS_CATALOG: Dict[str, SportDefinition] = {
    "badminton": SportDefinition(
        id="badminton",
        display_name="Badminton",
        icon_key="badminton_shuttle",
        analysis_ready=True,
        skills=[
            SkillDefinition(
                id="overhead_clear",
                name="Overhead Clear",
                analysis_ready=True,
                phases=["Preparation", "Loading", "Impact", "Follow-Through"],
                metrics=["right_elbow_contact_deg", "right_shoulder_abduction_deg", "trunk_arch_deg", "right_knee_flexion_deg"],
                threshold_pass_deg=165.0,
                common_faults=[
                    FaultDefinition(
                        id="dropped_elbow",
                        name="Dropped Elbow at Contact",
                        description="Elbow collapses below 165° leading to flat, push-like trajectory.",
                        cue_id="cue_elbow_high",
                        drill_ids=["drill_shadow_reach", "drill_high_toss_hold"]
                    ),
                    FaultDefinition(
                        id="insufficient_trunk_arch",
                        name="Insufficient Thoracic Coil",
                        description="Trunk arch angle < 155° preventing full kinetic energy transfer.",
                        cue_id="cue_coil_chest",
                        drill_ids=["drill_banded_rotation"]
                    )
                ],
                drills=[
                    DrillDefinition(
                        id="drill_shadow_reach",
                        title="Trophy Pose to High Reach",
                        instruction="Perform 3 sets of 10 slow-motion shadow overhead swings extending the racket elbow to full extension above your right ear.",
                        focus_cue="Brush the ceiling with full reach",
                        target_reps=10
                    ),
                    DrillDefinition(
                        id="drill_high_toss_hold",
                        title="High Shuttle Contact Freeze",
                        instruction="Have a feeder toss high clears. Hit and freeze at impact for 1 second verifying straight arm alignment.",
                        focus_cue="Lock reach at the highest apex",
                        target_reps=8
                    ),
                    DrillDefinition(
                        id="drill_banded_rotation",
                        title="Resistance Band Coil & Pronate",
                        instruction="Anchor resistance band at waist height; coil torso 45 degrees and accelerate elbow extension through pronation.",
                        focus_cue="Explode through torso rotation",
                        target_reps=12
                    )
                ]
            ),
            SkillDefinition(
                id="jump_smash",
                name="Jump Smash",
                analysis_ready=False,
                phases=["Approach", "Takeoff", "Peak Apex Impact", "Landing"],
                metrics=["vertical_jump_height", "right_elbow_contact_deg"],
                threshold_pass_deg=170.0
            )
        ]
    ),
    "tennis": SportDefinition(
        id="tennis",
        display_name="Tennis",
        icon_key="tennis_ball",
        analysis_ready=True,
        skills=[
            SkillDefinition(
                id="forehand",
                name="Modern Forehand",
                analysis_ready=True,
                phases=["Unit Turn", "Lag Phase", "Impact Zone", "Windshield Wiper"],
                metrics=["right_elbow_contact_deg", "trunk_arch_deg", "contact_height_norm"],
                threshold_pass_deg=155.0,
                common_faults=[
                    FaultDefinition(
                        id="jammed_contact",
                        name="Jammed Contact Point",
                        description="Hitting too close to the body with excessive elbow flexion (< 140°).",
                        cue_id="cue_space_arm",
                        drill_ids=["drill_drop_feed_extension"]
                    )
                ],
                drills=[
                    DrillDefinition(
                        id="drill_drop_feed_extension",
                        title="Self-Drop Extension Drill",
                        instruction="Drop ball 2 feet in front; step forward and drive through contact with relaxed elbow extension.",
                        focus_cue="Extend through the hitting zone",
                        target_reps=10
                    )
                ]
            ),
            SkillDefinition(
                id="one_hand_backhand",
                name="One-Handed Backhand",
                analysis_ready=True,
                phases=["Unit Turn", "Drop & Slot", "Forward Drive", "High Finish"],
                metrics=["right_elbow_contact_deg", "right_shoulder_abduction_deg"],
                threshold_pass_deg=170.0,
                common_faults=[
                    FaultDefinition(
                        id="bent_elbow_contact",
                        name="Bent Arm at Backhand Impact",
                        description="Collapsing elbow (< 165°) losing structural stability.",
                        cue_id="cue_firm_wrist_straight_arm",
                        drill_ids=["drill_backhand_wall_freeze"]
                    )
                ],
                drills=[
                    DrillDefinition(
                        id="drill_backhand_wall_freeze",
                        title="Impact Point Wall Press",
                        instruction="Place racket against a wall at ideal contact height, holding straight-arm posture for 5 seconds.",
                        focus_cue="Firm wrist, straight elbow lock",
                        target_reps=6
                    )
                ]
            )
        ]
    ),
    "padel": SportDefinition(
        id="padel",
        display_name="Padel",
        icon_key="padel_racket",
        analysis_ready=False,
        skills=[
            SkillDefinition(id="bandeja", name="Bandeja", analysis_ready=False),
            SkillDefinition(id="vibora", name="Vibora", analysis_ready=False)
        ]
    ),
    "pickleball": SportDefinition(
        id="pickleball",
        display_name="Pickleball",
        icon_key="pickleball_paddle",
        analysis_ready=False,
        skills=[
            SkillDefinition(id="kitchen_dink", name="Kitchen Line Dink", analysis_ready=False),
            SkillDefinition(id="third_shot_drop", name="Third Shot Drop", analysis_ready=False)
        ]
    ),
    "squash": SportDefinition(
        id="squash",
        display_name="Squash",
        icon_key="squash_ball",
        analysis_ready=False,
        skills=[
            SkillDefinition(id="straight_drive", name="Rail / Straight Drive", analysis_ready=False)
        ]
    ),
    "table_tennis": SportDefinition(
        id="table_tennis",
        display_name="Table Tennis",
        icon_key="table_tennis_paddle",
        analysis_ready=False,
        skills=[
            SkillDefinition(id="forehand_loop", name="Forehand Topspin Loop", analysis_ready=False)
        ]
    ),
    "golf": SportDefinition(
        id="golf",
        display_name="Golf",
        icon_key="golf_tee",
        analysis_ready=False,
        skills=[
            SkillDefinition(id="driver_swing", name="Driver Full Swing", analysis_ready=False)
        ]
    )
}


def get_all_sports() -> List[Dict[str, Any]]:
    """Returns list of sports formatted for mobile selection grid."""
    return [
        {
            "id": s.id,
            "display_name": s.display_name,
            "icon_key": s.icon_key,
            "analysis_ready": s.analysis_ready,
            "skills": [
                {
                    "id": k.id,
                    "name": k.name,
                    "analysis_ready": k.analysis_ready,
                }
                for k in s.skills
            ]
        }
        for s in SPORTS_CATALOG.values()
    ]


def get_sport(sport_id: str) -> Optional[SportDefinition]:
    return SPORTS_CATALOG.get((sport_id or "").strip().lower())


def get_skill(sport_id: str, skill_id: str) -> Optional[SkillDefinition]:
    sport = get_sport(sport_id)
    if not sport:
        return None
    for skill in sport.skills:
        if skill.id.lower() == (skill_id or "").strip().lower():
            return skill
    # Default to first skill if matching
    if sport.skills:
        return sport.skills[0]
    return None


def is_skill_analysis_ready(sport_id: str, skill_id: str) -> bool:
    sport = get_sport(sport_id)
    if not sport or not sport.analysis_ready:
        return False
    for skill in sport.skills:
        if skill.id.lower() == (skill_id or "").strip().lower():
            return skill.analysis_ready
    return False

