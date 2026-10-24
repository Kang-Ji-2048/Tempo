"""
app/services/gemini_analyzer.py - Async Gemini 4 Argon Biomechanical Analysis Engine
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.core.config import Settings, get_settings
from app.models.feedback import BiomechanicalReport, KineticPhase

logger = logging.getLogger(__name__)

SYSTEM_COACH_INSTRUCTION = """You are an elite, Olympic-caliber biomechanics coach specializing in racket and court sports (badminton, tennis, squash).
Your coaching persona is direct, constructive, biomechanically rigorous, and empathetic.

Your mission:
1. Analyze the athlete's practice video clip alongside their synchronized wearable biometric telemetry (heart rate, cadence, active calories).
2. Deconstruct the stroke into four sequential kinetic phases:
   - Preparation (unit turn, footwork positioning)
   - Loading (trophy pose, trunk coiling, racket drop)
   - Impact (peak elbow/shoulder extension, contact height, pronation)
   - Follow-Through (deceleration, recovery balance)
3. Correlate physiological fatigue (e.g. sustained heart rate spikes >165 BPM or cadence drops) with observable kinematic deviations in the video (e.g. late racket drop, collapsed elbow angle, decreased shoulder abduction).
4. Identify the root-cause mechanical flaw (not just symptoms) and deliver a punchy earbud audio cue (max 12 words) alongside a warm 30-45s spoken debrief script.
5. Return strictly valid structured data matching the BiomechanicalReport schema.
"""


class GeminiAnalyzer:
    """
    Async multimodal biomechanical analysis engine powered by Gemini 4 Argon.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        mock_mode: Optional[bool] = None,
        client: Optional[genai.Client] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name or settings.GEMINI_MODEL
        self.mock_mode = mock_mode if mock_mode is not None else (settings.GEMINI_MOCK_MODE or not bool(self.api_key))
        self.client = client or (genai.Client(api_key=self.api_key) if self.api_key else None)

    async def analyze_session(
        self,
        video_path: Optional[str] = None,
        video_url: Optional[str] = None,
        telemetry: Optional[List[Dict[str, Any]]] = None,
        sport: str = "badminton",
        stroke_type: str = "overhead_clear",
        target_archetype: Optional[str] = None,
    ) -> BiomechanicalReport:
        """
        Executes end-to-end multimodal biomechanical evaluation.
        Uses asynchronous file upload, state polling, and structured Gemini generation.
        Falls back to deterministic mock evaluation if mock_mode is enabled or API key is absent.
        """
        archetype = target_archetype or ("Viktor Axelsen" if sport.lower() == "badminton" else "Fundamentals Baseline")
        telemetry_points = telemetry or []

        if self.mock_mode or not self.client:
            logger.info("Running GeminiAnalyzer in deterministic mock mode for %s (%s)", sport, stroke_type)
            return self._build_deterministic_report(
                sport=sport,
                stroke_type=stroke_type,
                target_archetype=archetype,
                telemetry=telemetry_points,
            )

        try:
            # 1. Asynchronously upload video file and poll until ACTIVE
            uploaded_file_part = None
            if video_path and os.path.exists(video_path):
                uploaded_file_part = await self._upload_and_poll_video(video_path)

            # 2. Build analysis prompt incorporating biometrics & sports metadata
            prompt = self._build_analysis_prompt(
                sport=sport,
                stroke_type=stroke_type,
                target_archetype=archetype,
                telemetry=telemetry_points,
                video_url=video_url,
            )

            # 3. Assemble multimodal contents
            contents: List[Any] = []
            if uploaded_file_part is not None:
                contents.append(uploaded_file_part)
            contents.append(prompt)

            # 4. Configure native Pydantic structured output
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BiomechanicalReport,
                system_instruction=SYSTEM_COACH_INSTRUCTION,
            )

            logger.info("Calling Gemini 4 Argon (%s) with async client...", self.model_name)
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # 5. Extract structured output from response.parsed (with text fallback)
            if hasattr(response, "parsed") and response.parsed is not None:
                if isinstance(response.parsed, BiomechanicalReport):
                    return response.parsed
                if isinstance(response.parsed, dict):
                    return BiomechanicalReport.model_validate(response.parsed)

            if response.text:
                return BiomechanicalReport.model_validate_json(response.text)

            raise RuntimeError("Gemini model returned empty response without parsed payload or text.")

        except Exception as exc:
            logger.warning("Gemini API call failed or encountered error: %s. Using fallback report.", exc)
            if self.mock_mode or not self.api_key:
                return self._build_deterministic_report(
                    sport=sport,
                    stroke_type=stroke_type,
                    target_archetype=archetype,
                    telemetry=telemetry_points,
                )
            raise

    async def _upload_and_poll_video(self, video_path: str, timeout_sec: float = 30.0, backoff_sec: float = 2.0) -> Any:
        """
        Asynchronously uploads the video file and polls until its processing state is ACTIVE.
        """
        logger.info("Asynchronously uploading video %s to Gemini File API...", video_path)
        file_obj = await self.client.aio.files.upload(
            file=video_path,
            mime_type="video/mp4",
        )
        logger.info("Uploaded video as %s. Polling for ACTIVE state...", file_obj.name)

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_sec:
            file_status = await self.client.aio.files.get(name=file_obj.name)
            raw_state = getattr(file_status, "state", None)
            state_str = str(getattr(raw_state, "name", raw_state)).upper()

            if "ACTIVE" in state_str:
                logger.info("Video %s reached ACTIVE state in %.1fs", file_obj.name, time.monotonic() - start_time)
                return file_status
            elif "FAILED" in state_str:
                raise RuntimeError(f"Gemini video processing failed with state: {state_str}")

            logger.debug("Video state is %s, sleeping %.1fs...", state_str, backoff_sec)
            await asyncio.sleep(backoff_sec)

        logger.warning("Video polling timed out after %ds; proceeding with original file handle", timeout_sec)
        return file_obj

    def _build_analysis_prompt(
        self,
        sport: str,
        stroke_type: str,
        target_archetype: str,
        telemetry: List[Dict[str, Any]],
        video_url: Optional[str] = None,
    ) -> str:
        """Formats the input prompt correlating video context and wearable biometrics."""
        hr_values = [p.get("heart_rate") for p in telemetry if p.get("heart_rate")]
        avg_hr = round(sum(hr_values) / len(hr_values), 1) if hr_values else "N/A"
        max_hr = max(hr_values) if hr_values else "N/A"
        sample_count = len(telemetry)

        telemetry_snippet = (
            f"Wearable Biometric Stream (Android Health Connect):\n"
            f"- Samples: {sample_count} data points\n"
            f"- Average Heart Rate: {avg_hr} BPM\n"
            f"- Peak Heart Rate: {max_hr} BPM\n"
            f"- Telemetry Samples (first 5): {telemetry[:5]}\n"
        )

        return (
            f"Sport: {sport}\n"
            f"Stroke Type: {stroke_type}\n"
            f"Target Archetype: {target_archetype}\n"
            f"{f'Remote Video URL: {video_url}' if video_url else ''}\n\n"
            f"{telemetry_snippet}\n"
            f"Analyze the kinetic chain of this stroke. Compare joint angles (especially elbow extension, "
            f"shoulder abduction, and trunk inclination) to {target_archetype}. Correlate any breakdown "
            f"with the recorded heart rate data and output a strictly typed BiomechanicalReport."
        )

    def _build_deterministic_report(
        self,
        sport: str,
        stroke_type: str,
        target_archetype: str,
        telemetry: List[Dict[str, Any]],
    ) -> BiomechanicalReport:
        """
        High-precision deterministic biomechanical report used in mock mode, tests,
        and when external API credentials are not active.
        """
        hr_values = [p.get("heart_rate", 160) for p in telemetry if isinstance(p.get("heart_rate"), (int, float))]
        avg_hr = round(sum(hr_values) / len(hr_values), 1) if hr_values else 165.0
        max_hr = max(hr_values) if hr_values else 172.0

        is_elevated_load = max_hr > 165.0

        if sport.lower() == "badminton":
            matched_archetype = target_archetype or "Viktor Axelsen"
            overall_score = 78 if is_elevated_load else 85
            primary_flaw = (
                "Right elbow angle dropped to 158.4° at shuttle impact (below target threshold of 175.0°), "
                "caused by premature forearm pronation before full shoulder extension."
            )
            fatigue_desc = (
                f"As heart rate climbed to {max_hr:.0f} BPM (average {avg_hr:.0f} BPM), late preparation "
                f"shortened the trunk arch from 172° to 161°, compressing the contact reach by ~12cm."
            )
            audio_cue = "Accelerate forearm pronation at peak reach, not before."
            voice_script = (
                f"Great work out there! Your court coverage was explosive today. However, as your heart rate "
                f"surpassed {max_hr:.0f} BPM, your right elbow dropped to 158 degrees at impact rather than staying "
                f"fully extended like {matched_archetype}. Focus on driving your hips earlier so your arm reaches peak "
                f"extension at contact. Let's do the 30-second rapid pronation drill to lock it in!"
            )
            phases = [
                KineticPhase(
                    phase_name="Preparation",
                    timestamp_ms=300,
                    joint_angles={"trunk_arch_deg": 168.0, "left_arm_balance_deg": 142.0},
                    form_accuracy_score=92,
                    observation="Stable base with strong non-racket arm elevation for tracking shuttle height.",
                ),
                KineticPhase(
                    phase_name="Loading",
                    timestamp_ms=850,
                    joint_angles={"trunk_arch_deg": 161.5, "right_elbow_flexion_deg": 95.0},
                    form_accuracy_score=80,
                    observation="Slightly restricted thoracic arch during loading phase under fatigue.",
                ),
                KineticPhase(
                    phase_name="Impact",
                    timestamp_ms=1320,
                    joint_angles={"right_elbow_contact_deg": 158.4, "shoulder_abduction_deg": 142.0},
                    form_accuracy_score=74,
                    observation="Elbow flexion at contact (158.4°) lacked full extension compared to Axelsen profile (175°).",
                ),
                KineticPhase(
                    phase_name="Follow-Through",
                    timestamp_ms=1750,
                    joint_angles={"deceleration_pronation_deg": 140.0, "recovery_balance_score": 85.0},
                    form_accuracy_score=88,
                    observation="Smooth kinetic dissipation across the torso with quick split-step recovery.",
                ),
            ]
        else:
            # Tennis or general court sport baseline
            matched_archetype = target_archetype or "Fundamentals Baseline"
            overall_score = 81
            primary_flaw = "Hip uncoiling initiated after racket drop rather than leading the forward kinetic chain."
            fatigue_desc = f"At {avg_hr:.0f} BPM, recovery step cadence slowed, leading to rushed preparation."
            audio_cue = "Drive hips before racket release on forward swing."
            voice_script = (
                "Solid practice set! Your contact point was clean out in front. Under sustained cardiovascular load, "
                "your hip rotation lagged slightly behind the arm swing. Initiate the turn from your rear hip first "
                "to maximize ground force transfer. Try the kinetic coil drill next!"
            )
            phases = [
                KineticPhase(
                    phase_name="Preparation",
                    timestamp_ms=400,
                    joint_angles={"unit_turn_deg": 88.0, "knee_flexion_deg": 145.0},
                    form_accuracy_score=90,
                    observation="Clean unit turn with shoulders perpendicular to baseline.",
                ),
                KineticPhase(
                    phase_name="Loading",
                    timestamp_ms=900,
                    joint_angles={"hip_coil_deg": 42.0, "racket_lag_deg": 78.0},
                    form_accuracy_score=82,
                    observation="Racket drop initiated on time, but hip coil could be deeper.",
                ),
                KineticPhase(
                    phase_name="Impact",
                    timestamp_ms=1400,
                    joint_angles={"elbow_extension_deg": 165.0, "contact_height_norm": 0.88},
                    form_accuracy_score=80,
                    observation="Firm wrist at ball contact with good horizontal spacing.",
                ),
                KineticPhase(
                    phase_name="Follow-Through",
                    timestamp_ms=1850,
                    joint_angles={"shoulder_rotation_deg": 110.0},
                    form_accuracy_score=86,
                    observation="Complete shoulder wrap-around over the opposite shoulder.",
                ),
            ]

        return BiomechanicalReport(
            overall_score=overall_score,
            matched_archetype=matched_archetype,
            primary_flaw=primary_flaw,
            fatigue_correlation=fatigue_desc,
            kinetic_phases=phases,
            concise_audio_cue=audio_cue,
            coach_voice_note_script=voice_script,
        )


# Singleton instance helper
_gemini_analyzer: Optional[GeminiAnalyzer] = None


def get_gemini_analyzer() -> GeminiAnalyzer:
    """Provides the active GeminiAnalyzer instance."""
    global _gemini_analyzer
    if _gemini_analyzer is None:
        _gemini_analyzer = GeminiAnalyzer()
    return _gemini_analyzer


def set_gemini_analyzer(analyzer: GeminiAnalyzer) -> None:
    """Overrides the active GeminiAnalyzer instance (for testing/mocking)."""
    global _gemini_analyzer
    _gemini_analyzer = analyzer
