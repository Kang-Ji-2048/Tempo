"""
app/services/sdui_generator.py - Adaptive Server-Driven UI (SDUI) Generator
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.models.feedback import BiomechanicalReport
from app.models.sdui import (
    ConceptQuizWidget,
    DrillCardWidget,
    PathNode,
    PathProgressWidget,
    SDUIPayload,
)

logger = logging.getLogger(__name__)


class SDUIGenerator:
    """
    Translates biomechanical analysis reports and user progress into dynamic,
    adaptive Server-Driven UI (SDUI) payloads for the Android Jetpack Compose client.
    """

    @classmethod
    def generate_payload(
        cls,
        report: BiomechanicalReport,
        user_id: str,
        sport: str = "badminton",
        stroke_type: str = "overhead_clear",
        streak_days: int = 5,
    ) -> SDUIPayload:
        """
        Synthesizes a complete SDUIPayload with PathProgressWidget, DrillCardWidget,
        and ConceptQuizWidget tailored to the athlete's primary mechanical flaw.
        """
        logger.info("Generating SDUI payload for user %s (score=%d, sport=%s)", user_id, report.overall_score, sport)

        # 1. Generate skill mastery progression tree
        path_widget = cls._build_path_progress_widget(
            score=report.overall_score,
            streak=streak_days,
            sport=sport,
            stroke_type=stroke_type,
        )

        # 2. Select remedial drill tailored to primary flaw
        drill_widget = cls._select_remedial_drill(
            report=report,
            sport=sport,
            stroke_type=stroke_type,
        )

        # 3. Generate interactive tactical concept quiz
        quiz_widget = cls._build_concept_quiz(
            report=report,
            sport=sport,
        )

        # 4. Formulate top card coaching banner summary
        score_descriptor = "Mastery" if report.overall_score >= 85 else ("Solid Technique" if report.overall_score >= 75 else "Form Breakdown")
        coach_summary = (
            f"{score_descriptor} ({report.overall_score}/100) vs {report.matched_archetype}. "
            f"Focus: {report.concise_audio_cue}"
        )

        widgets: List[Dict[str, Any]] = [
            path_widget.model_dump(),
            drill_widget.model_dump(),
            quiz_widget.model_dump(),
        ]

        return SDUIPayload(
            screen="post_session_analysis",
            coach_summary=coach_summary,
            widgets=widgets,
        )

    @classmethod
    def _build_path_progress_widget(
        cls,
        score: int,
        streak: int,
        sport: str,
        stroke_type: str,
    ) -> PathProgressWidget:
        """Constructs the progression path node state."""
        passed = score >= 75

        nodes = [
            PathNode(
                node_id="node_prep_01",
                title="Unit Turn & Setup",
                status="COMPLETED",
                xp_reward=50,
            ).model_dump(),
            PathNode(
                node_id="node_impact_02",
                title="Peak Reach & Impact Extension",
                status="COMPLETED" if passed else "ACTIVE",
                xp_reward=75,
            ).model_dump(),
            PathNode(
                node_id="node_pronation_03",
                title="Forearm Pronation Speed",
                status="ACTIVE" if passed else "LOCKED",
                xp_reward=100,
            ).model_dump(),
            PathNode(
                node_id="node_mastery_04",
                title="High-Tempo Jump Smash",
                status="LOCKED",
                xp_reward=150,
            ).model_dump(),
        ]

        active_id = "node_pronation_03" if passed else "node_impact_02"

        return PathProgressWidget(
            widget_type="PathProgressWidget",
            current_streak=streak,
            active_node_id=active_id,
            nodes=nodes,
        )

    @classmethod
    def _select_remedial_drill(
        cls,
        report: BiomechanicalReport,
        sport: str,
        stroke_type: str,
    ) -> DrillCardWidget:
        """Dynamically prescribes a focused remedial drill based on root-cause flaw."""
        flaw_lower = report.primary_flaw.lower()

        if "elbow" in flaw_lower or "pronation" in flaw_lower:
            return DrillCardWidget(
                widget_type="DrillCardWidget",
                id="drill_pronation_wall_30s",
                title="30s Rapid Pronation Drill",
                instruction=(
                    "Stand 1 meter from a wall with your racket raised. Rapidly rotate your forearm inward "
                    "hitting the shuttlecock against the wall target at full extension. Do not allow your elbow to drop below shoulder level."
                ),
                target_reps=15,
                focus_cue="Full elbow extension at contact before the forearm snaps inward.",
            )
        elif "hip" in flaw_lower or "coil" in flaw_lower or "rotation" in flaw_lower:
            return DrillCardWidget(
                widget_type="DrillCardWidget",
                id="drill_hip_drive_coil_20reps",
                title="Explosive Hip Uncoiling Drill",
                instruction=(
                    "Start in trophy pose with rear hip loaded. Drive rear hip forward 15 degrees before "
                    "allowing racket arm to drop into acceleration. Focus on the kinetic lag."
                ),
                target_reps=20,
                focus_cue="Hips lead the shoulders; arm follows like a whip.",
            )
        elif "fatigue" in flaw_lower or "drop" in flaw_lower:
            return DrillCardWidget(
                widget_type="DrillCardWidget",
                id="drill_high_tempo_shadow_4x10",
                title="Cardio-Kinetic Shadow Series",
                instruction=(
                    "Perform 4 sets of 10 rapid rear-court jump-and-reach shadow strokes. Keep heart rate "
                    "monitored on your watch and maintain identical contact height on reps 8, 9, and 10."
                ),
                target_reps=10,
                focus_cue="Lock in reach when breathing gets heavy.",
            )
        else:
            return DrillCardWidget(
                widget_type="DrillCardWidget",
                id="drill_kinetic_sync_baseline",
                title="Kinetic Chain Synchronization",
                instruction=(
                    "Execute 3 sets of 12 smooth shadow repetitions focusing on seamless power transfer from "
                    "legs through the core into full arm reach."
                ),
                target_reps=12,
                focus_cue="Smooth acceleration over raw muscle tension.",
            )

    @classmethod
    def _build_concept_quiz(
        cls,
        report: BiomechanicalReport,
        sport: str,
    ) -> ConceptQuizWidget:
        """Builds an interactive concept quiz reinforcing the target biomechanical principle."""
        flaw_lower = report.primary_flaw.lower()

        if "elbow" in flaw_lower or "pronation" in flaw_lower:
            return ConceptQuizWidget(
                widget_type="ConceptQuizWidget",
                question="Why does hitting the shuttle with full elbow extension generate steeper downward smash angle?",
                options=[
                    "It raises the geometrical contact vertex above net height, maximizing downward angular trajectory.",
                    "It bends the racket shaft backward to store elastic tension.",
                    "It reduces the player's cardiovascular heart rate.",
                    "It delays the opponent's split-step reaction by 200 milliseconds.",
                ],
                correct_index=0,
                explanation=(
                    "Every 5cm of contact height elevation steepens the smash vector by approximately 3.8 degrees, "
                    "preventing the shuttle from floating within the opponent's drive zone."
                ),
            )
        else:
            return ConceptQuizWidget(
                widget_type="ConceptQuizWidget",
                question="What is the primary role of the non-racket arm during the overhead stroke preparation?",
                options=[
                    "To generate aerodynamic lift for jump height.",
                    "To counterbalance thoracic rotation and calibrate spatial distance to the projectile.",
                    "To signal shot selection to doubles partner.",
                    "To damp racket string vibrations upon contact.",
                ],
                correct_index=1,
                explanation=(
                    "The non-racket arm tracks the shuttle's descent and serves as an essential rotational counter-weight, "
                    "preventing premature torso opening."
                ),
            )
