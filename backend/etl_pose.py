"""
etl_pose.py - Video & Apple Watch ETL Pipeline (Kong)
Scans uploaded videos using OpenCV + MediaPipe Tasks Pose Landmarker,
identifies peak overhead shuttle contact frame (minimum y coordinate of RIGHT_WRIST),
computes 5 key 3D joint angles + normalized contact height, outputs raw angles and a
6D normalized pose_vector, and parses Apple Watch workout JSON/XML biometrics.
"""

from __future__ import annotations

import json
import math
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

from pathlib import Path
from threading import Lock
import importlib.util
import logging

try:
    if __package__:
        from . import kinematics_engine as kin
    else:
        import kinematics_engine as kin
except ImportError:  # pragma: no cover - script execution from backend/
    import kinematics_engine as kin

logger = logging.getLogger(__name__)
mp = None
_MP_LOCK = Lock()
REQUIRED_LANDMARKS = (0, 11, 12, 13, 14, 16, 23, 24, 26, 28)
# Same body check for a left-handed player (hitting arm and leg on the left).
REQUIRED_LANDMARKS_LEFT = (0, 11, 12, 13, 15, 23, 24, 25, 27)
# Hitting side: shoulder, elbow, wrist, hip, knee, ankle, then the non-hitting shoulder and hip.
SIDE_JOINTS = {"right": (12, 14, 16, 24, 26, 28, 11, 23), "left": (11, 13, 15, 23, 25, 27, 12, 24)}
MODEL_FILENAME = "pose_landmarker_full.task"


def pose_model_path() -> Path:
    configured = os.environ.get("TEMPO_POSE_MODEL_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).parent / "models" / MODEL_FILENAME


def get_pose_runtime_status() -> Dict[str, Any]:
    """Cheap configuration check; successful inference is verified separately."""
    model_present = pose_model_path().is_file()
    installed = importlib.util.find_spec("mediapipe") is not None
    return {"engine": "mediapipe_tasks_pose_landmarker", "model_present": model_present,
            "mediapipe_installed": installed, "opencv_available": cv2 is not None,
            "configured": model_present and installed and cv2 is not None,
            "coordinate_space": "estimated_world_meters", "handedness": "right",
            "contact_selection": "highest_visible_overhead_wrist_proxy"}


def _ensure_mediapipe_loaded() -> bool:
    global mp
    with _MP_LOCK:
        if mp is not None:
            return True
        try:
            import mediapipe as _mp
            if not hasattr(_mp.tasks.vision, "PoseLandmarker"):
                return False
            mp = _mp
            return True
        except (ImportError, AttributeError, OSError):
            logger.exception("MediaPipe Tasks could not be loaded")
            return False


# Clean fallback biometrics & pose when no full body is detected in a test clip or synthetic video
FALLBACK_RAW_ANGLES: Dict[str, float] = {
    "right_elbow_contact_deg": 158.4,
    "right_shoulder_abduction_deg": 142.0,
    "trunk_arch_deg": 161.5,
    "right_knee_flexion_deg": 152.0,
    "left_arm_balance_deg": 118.0,
    "contact_height_norm": 0.78,
}


def compute_angle_3d(
    a: Union[Tuple[float, float, float], List[float], np.ndarray],
    b: Union[Tuple[float, float, float], List[float], np.ndarray],
    c: Union[Tuple[float, float, float], List[float], np.ndarray],
) -> float:
    """
    Compute the 3D interior angle (in degrees, [0, 180]) at vertex `b` formed by rays `ba` and `bc`.
    """
    va = np.array(a, dtype=np.float64) - np.array(b, dtype=np.float64)
    vc = np.array(c, dtype=np.float64) - np.array(b, dtype=np.float64)

    norm_a = np.linalg.norm(va)
    norm_c = np.linalg.norm(vc)
    if not np.isfinite(va).all() or not np.isfinite(vc).all() or norm_a < 1e-8 or norm_c < 1e-8:
        raise ValueError("Joint coordinates must be finite and form nonzero segments")

    cos_theta = float(np.dot(va, vc) / (norm_a * norm_c))
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return round(float(math.degrees(math.acos(cos_theta))), 2)


def build_pose_vector(raw_angles: Dict[str, float]) -> List[float]:
    """
    Convert the 5 key joint angles + contact_height_norm into a 6D normalized pose_vector:
    [elbow/180, shoulder/180, trunk/180, knee/180, left_arm/180, height]
    """
    elbow = float(raw_angles.get("right_elbow_contact_deg", FALLBACK_RAW_ANGLES["right_elbow_contact_deg"]))
    shoulder = float(raw_angles.get("right_shoulder_abduction_deg", FALLBACK_RAW_ANGLES["right_shoulder_abduction_deg"]))
    trunk = float(raw_angles.get("trunk_arch_deg", FALLBACK_RAW_ANGLES["trunk_arch_deg"]))
    knee = float(raw_angles.get("right_knee_flexion_deg", FALLBACK_RAW_ANGLES["right_knee_flexion_deg"]))
    left_arm = float(raw_angles.get("left_arm_balance_deg", FALLBACK_RAW_ANGLES["left_arm_balance_deg"]))
    height = float(raw_angles.get("contact_height_norm", FALLBACK_RAW_ANGLES["contact_height_norm"]))

    height_clamped = max(0.0, min(1.0, height))
    return [
        round(elbow / 180.0, 4),
        round(shoulder / 180.0, 4),
        round(trunk / 180.0, 4),
        round(knee / 180.0, 4),
        round(left_arm / 180.0, 4),
        round(height_clamped, 4),
    ]


def _extract_landmark_3d(landmarks: Any, idx: int) -> Tuple[float, float, float]:
    lm = landmarks[idx]
    return (float(lm.x), float(lm.y), float(lm.z))


def _pose_unavailable(status: str, frames_scanned: int = 0) -> Dict[str, Any]:
    # Retain the demo contract; the HTTP layer refuses these values outside demo mode.
    raw = dict(FALLBACK_RAW_ANGLES)
    return {"status": status, "used_fallback": True, "overhead_contact_detected": False, "frames_scanned": frames_scanned,
            "peak_contact_frame": None, "raw_angles": raw, **raw,
            "pose_vector": build_pose_vector(raw), "coordinate_space": "synthetic_demo",
            "contact_selection": "unavailable", "valid_pose_frames": 0}


def _angles_from_landmarks(world: Any, image: Any, side: str = "right") -> Dict[str, float]:
    """Contract angles for the hitting side. Keys keep their historical `right_*` names (hitting arm)."""
    sh, el, wr, hp, kn, an, osh, ohp = SIDE_JOINTS[side]

    def angle(a, b, c):
        return compute_angle_3d(*(_extract_landmark_3d(world, i) for i in (a, b, c)))
    return {"right_elbow_contact_deg": angle(sh, el, wr),
            "right_shoulder_abduction_deg": angle(hp, sh, el),
            "trunk_arch_deg": angle(sh, hp, kn),
            "right_knee_flexion_deg": angle(hp, kn, an),
            "left_arm_balance_deg": angle(ohp, osh, 13 if side == "right" else 14),  # non-hitting arm
            # Height remains an image-space feature for the existing vector contract.
            "contact_height_norm": round(1.0 - float(image[wr].y), 4)}


def _reliable_full_body_pose(image: Any, world: Any, side: str = "right") -> bool:
    """Every required landmark is confident, finite and inside the frame (any stroke, not only overhead)."""
    if len(image) < 33 or len(world) < 33:
        return False
    for idx in (REQUIRED_LANDMARKS if side == "right" else REQUIRED_LANDMARKS_LEFT):
        landmark = image[idx]
        confidence = (getattr(landmark, "visibility", None), getattr(landmark, "presence", None))
        if any(value is None or not math.isfinite(value) or value < 0.5 for value in confidence):
            return False
        if not all(math.isfinite(v) for v in _extract_landmark_3d(image, idx) + _extract_landmark_3d(world, idx)):
            return False
        if not (0 <= landmark.x <= 1 and 0 <= landmark.y <= 1):
            return False
    return True


def _is_overhead(image: Any, side: str = "right") -> bool:
    sh, _, wr = SIDE_JOINTS[side][:3]
    return image[wr].y < min(image[0].y, image[sh].y) - 0.02


def _reliable_overhead_pose(image: Any, world: Any, side: str = "right") -> bool:
    return _reliable_full_body_pose(image, world, side) and _is_overhead(image, side)


def _landmark_rows(image: Any, world: Any) -> Tuple[List[List[float]], List[List[float]]]:
    img = [[float(p.x), float(p.y), float(getattr(p, "z", 0.0) or 0.0), float(getattr(p, "visibility", 0.0) or 0.0)]
           for p in image]
    wld = [[float(p.x), float(p.y), float(p.z)] for p in world]
    return img, wld


def extract_pose_from_video(video_path: str, sport: Optional[str] = None,
                            target_stroke: Optional[str] = None) -> Dict[str, Any]:
    """Use Tasks VIDEO mode and world landmarks to measure a single player (either hand).

    Best first: (1) the RepTracker segments complete reps (Preparation -> Loading -> Impact ->
    Follow-Through) and the best rep's impact frame gives the angles, for any stroke; (2) without a
    complete rep, the highest reliable overhead wrist frame; (3) otherwise the fastest full-body wrist
    frame. Frames with a second person are skipped unless they dominate. No racket, ball/shuttle or
    actual impact is detected: "impact" is a contact proxy.
    """
    if not video_path or not os.path.isfile(video_path):
        return _pose_unavailable("fallback_no_video")
    if cv2 is None:
        return _pose_unavailable("opencv_unavailable")
    if not pose_model_path().is_file():
        return _pose_unavailable("pose_model_missing")
    if not _ensure_mediapipe_loaded():
        return _pose_unavailable("mediapipe_tasks_unavailable")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return _pose_unavailable("fallback_unreadable_video")
    frames_scanned = 0
    ambiguous_frames = 0
    aspect = 0.75
    single: List[Tuple[int, int, Any, Any]] = []  # (frame_idx, timestamp_ms, image landmarks, world landmarks)
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    fps_estimated = not math.isfinite(fps) or fps <= 0
    if fps_estimated:
        fps = 30.0
    last_timestamp = -1
    try:
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(pose_model_path())),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=2, min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5, min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_idx = frames_scanned
                frames_scanned += 1
                if frame_idx == 0 and getattr(frame, "shape", None) is not None and frame.shape[0]:
                    aspect = frame.shape[1] / frame.shape[0]
                # Prefer decoder presentation time, retaining strict increase for duplicate timestamps.
                presentation_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                estimated_ms = round(frame_idx * 1000.0 / fps)
                timestamp = max(last_timestamp + 1, round(presentation_ms) if math.isfinite(presentation_ms) and presentation_ms >= 0 else estimated_ms)
                if presentation_ms == 0 and frame_idx > 0:
                    timestamp = max(timestamp, estimated_ms)
                last_timestamp = timestamp
                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(image, timestamp)
                if len(result.pose_landmarks) > 1:
                    ambiguous_frames += 1
                    continue
                if len(result.pose_landmarks) != 1 or len(result.pose_world_landmarks) != 1:
                    continue
                single.append((frame_idx, timestamp, result.pose_landmarks[0], result.pose_world_landmarks[0]))
    except (ValueError, RuntimeError, OSError):
        logger.exception("Pose Landmarker inference failed")
        return _pose_unavailable("pose_inference_failed", frames_scanned)
    finally:
        cap.release()

    rows = [(idx, ts) + _landmark_rows(img, wld) for idx, ts, img, wld in single]
    side = kin.detect_side([r[2] for r in rows], aspect)
    visibility_ids = REQUIRED_LANDMARKS if side == "right" else REQUIRED_LANDMARKS_LEFT
    full_body = [(idx, ts, img, wld) for idx, ts, img, wld in single if _reliable_full_body_pose(img, wld, side)]
    warnings = ["Monocular 3D pose estimate; actual racket impact is not detected.",
                f"{side.title()}-handed single-player analysis (hitting side detected from wrist travel)."]
    # No identity tracking: frames with a second person were skipped. Refuse only if they dominate.
    if ambiguous_frames:
        if ambiguous_frames >= len(full_body):
            return _pose_unavailable("multiple_players_detected", frames_scanned)
        warnings.append(f"Skipped {ambiguous_frames} frames with more than one person in view.")

    by_ts = {ts: (idx, img, wld) for idx, ts, img, wld in single}
    analysis = kin.analyse_frames([(ts, img_rows, wld_rows) for _, ts, img_rows, wld_rows in rows],
                                  sport, target_stroke, aspect)
    reps: List[Any] = analysis["reps"]
    rep_payload: Optional[Dict[str, Any]] = None
    if reps:
        best_rep = max(reps, key=lambda r: (r.stroke_matches_target, r.quality_score))
        peak_idx, normalized, world = by_ts[best_rep.impact_ms]
        timestamp = best_rep.impact_ms
        raw = _angles_from_landmarks(world, normalized, side)
        overhead = best_rep.detected_stroke in kin.OVERHEAD_STROKES
        status, selection = "detected", "rep_tracker_impact"
        visibility = min(normalized[i].visibility for i in visibility_ids)
        valid = len(full_body)
        rep_payload = {
            "reps": [r.to_dict() for r in reps], "rep_count": len(reps), "best_rep_index": best_rep.rep_index,
            "detected_stroke": best_rep.detected_stroke, "target_stroke": target_stroke,
            "quality_score": best_rep.quality_score, "primary_deviation": best_rep.primary_deviation,
            "session_analysis": analysis["session"],
            "kinetic_phases": [{"phase_name": k.phase, "timestamp_ms": k.t_ms, "joint_angles": k.angles,
                                "frame_index": by_ts[k.t_ms][0] if k.t_ms in by_ts else None}
                               for k in best_rep.keyframes],
        }
    else:
        overhead_frames = [(idx, ts, img, wld) for idx, ts, img, wld in full_body if _is_overhead(img, side)]
        wrist = SIDE_JOINTS[side][2]
        if overhead_frames:
            peak_idx, timestamp, normalized, world = min(overhead_frames, key=lambda f: f[2][wrist].y)
            status, selection, overhead = "detected", "highest_visible_overhead_wrist_proxy", True
            valid = len(overhead_frames)
        elif full_body:
            fastest, best_speed = full_body[0], -1.0
            for prev, cur in zip(full_body, full_body[1:]):
                if cur[1] > prev[1] and cur[0] == prev[0] + 1:
                    speed = math.dist((cur[2][wrist].x, cur[2][wrist].y), (prev[2][wrist].x, prev[2][wrist].y)) / (
                        (cur[1] - prev[1]) / 1000.0)
                    if speed > best_speed:
                        fastest, best_speed = cur, speed
            peak_idx, timestamp, normalized, world = fastest
            status, selection, overhead = "detected_no_overhead_contact", f"fastest_{side}_wrist_full_body_frame", False
            warnings.append("No overhead contact was visible; angles are from the fastest full-body swing frame.")
            valid = len(full_body)
        else:
            return _pose_unavailable("fallback_no_reliable_pose", frames_scanned)
        try:
            raw = _angles_from_landmarks(world, normalized, side)
        except ValueError:
            return _pose_unavailable("fallback_no_reliable_pose", frames_scanned)
        visibility = min(normalized[i].visibility for i in visibility_ids)
    return {"status": status, "used_fallback": False, "overhead_contact_detected": overhead,
            "handedness": side, "frames_scanned": frames_scanned, "valid_pose_frames": valid,
            "peak_contact_frame": peak_idx, "peak_contact_timestamp_ms": timestamp,
            "raw_angles": raw, **raw, "pose_vector": build_pose_vector(raw),
            "engine": "mediapipe_tasks_pose_landmarker", "coordinate_space": "estimated_world_meters",
            "contact_selection": selection,
            "min_landmark_visibility": round(visibility, 4), "fps_estimated": fps_estimated,
            "rep_analysis": rep_payload,
            "warnings": warnings}


def _derive_fatigue_state(
    heart_rate_bpm: float,
    active_calories_kcal: float,
    explicit_state: Optional[str] = None,
    hrv_sdnn_ms: Optional[float] = None,
) -> str:
    if explicit_state and str(explicit_state).strip():
        return str(explicit_state).strip().upper()
    if (
        heart_rate_bpm >= 172.0
        or active_calories_kcal >= 600.0
        or (hrv_sdnn_ms is not None and hrv_sdnn_ms < 28.0)
    ):
        return "HIGH_FATIGUE_AEROBIC_OVERLOAD"
    if (
        heart_rate_bpm >= 150.0
        or active_calories_kcal >= 350.0
        or (hrv_sdnn_ms is not None and hrv_sdnn_ms < 45.0)
    ):
        return "MODERATE_FATIGUE_ELEVATED_LOAD"
    return "OPTIMAL_RECOVERY_READY"


def _compute_fatigue_index(
    heart_rate_bpm: float,
    active_calories_kcal: float,
    hrv_sdnn_ms: Optional[float] = None,
) -> float:
    """
    Compute a normalized [0.0 - 100.0] cardiovascular fatigue score from Apple Watch biometrics.
    """
    hr_norm = max(0.0, min(1.0, (heart_rate_bpm - 90.0) / 105.0))
    cal_norm = max(0.0, min(1.0, active_calories_kcal / 800.0))
    if hrv_sdnn_ms is not None and hrv_sdnn_ms > 0:
        hrv_norm = max(0.0, min(1.0, (80.0 - hrv_sdnn_ms) / 65.0))
        score = (0.55 * hr_norm + 0.25 * cal_norm + 0.20 * hrv_norm) * 100.0
    else:
        score = (0.65 * hr_norm + 0.35 * cal_norm) * 100.0
    return round(float(score), 1)


def _extract_xml_bytes_if_zip(raw_bytes: bytes) -> bytes:
    """If the user uploaded an Apple Health `export.zip`, extract `export.xml` from it."""
    if raw_bytes[:4] == b"PK\x03\x04":
        import io

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith("export.xml") or name.lower().endswith(".xml"):
                    return zf.read(name)
    return raw_bytes


def parse_apple_watch_metrics(
    payload: Optional[Union[str, bytes, Dict[str, Any]]] = None,
    heart_rate_bpm: Optional[float] = None,
    active_calories_kcal: Optional[float] = None,
    fatigue_state: Optional[str] = None,
    sampled_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ETL parser for Apple Watch workout biometrics:
    Supports:
    1. Apple HealthKit `export.xml` or `export.zip` (`<Workout>`, `<WorkoutStatistics>`, `<Record>`)
    2. Live Apple Watch HealthKit / Health Auto Export JSON payloads
    3. Direct form fields (`heart_rate_bpm`, `active_calories_kcal`, `fatigue_state`)
    """
    if __package__:
        from .telemetry_time import normalize
    else:
        from telemetry_time import normalize
    sample_time = sampled_at
    if isinstance(payload, dict):
        sample_time = sample_time or payload.get('sampled_at')
    elif isinstance(payload, (str, bytes)):
        try:
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                sample_time = sample_time or decoded.get('sampled_at')
        except (ValueError, UnicodeError):
            pass
    sample_time = normalize(sample_time) if sample_time is not None else None
    hr: Optional[float] = float(heart_rate_bpm) if heart_rate_bpm is not None else None
    peak_hr: Optional[float] = None
    resting_hr: Optional[float] = None
    hrv_sdnn_ms: Optional[float] = None
    cal: Optional[float] = float(active_calories_kcal) if active_calories_kcal is not None else None
    duration_min: Optional[float] = None
    wrist_speed_mps: Optional[float] = None
    workout_type: str = "HKWorkoutActivityTypeTennis"
    source_format: str = "form_fields"
    f_state = fatigue_state

    if isinstance(payload, dict):
        payload = json.dumps(payload, allow_nan=False)
    if payload is not None and not isinstance(payload, (str, bytes)):
        raise ValueError("Expected JSON, XML, or ZIP telemetry")

    if payload is not None:
        if isinstance(payload, dict):
            source_format = "json_dict"
            hr = float(payload.get("heart_rate_bpm", payload.get("heartRateBpm", hr if hr is not None else 168.0)))
            peak_hr = float(payload.get("peak_heart_rate_bpm", payload.get("maxHeartRateBpm", hr)))
            resting_hr = (
                float(payload["resting_heart_rate_bpm"])
                if "resting_heart_rate_bpm" in payload
                else None
            )
            hrv_sdnn_ms = (
                float(payload["hrv_sdnn_ms"])
                if "hrv_sdnn_ms" in payload
                else None
            )
            cal = float(
                payload.get(
                    "active_calories_kcal",
                    payload.get("activeCaloriesKcal", cal if cal is not None else 420.0),
                )
            )
            duration_min = (
                float(payload["workout_duration_min"])
                if "workout_duration_min" in payload
                else None
            )
            wrist_speed_mps = (
                float(payload["wrist_acceleration_peak_mps"])
                if "wrist_acceleration_peak_mps" in payload
                else None
            )
            workout_type = str(payload.get("workout_activity_type", workout_type))
            f_state = payload.get("fatigue_state", f_state)

        elif isinstance(payload, (str, bytes)):
            if isinstance(payload, bytes):
                raw_bytes = _extract_xml_bytes_if_zip(payload)
                text = raw_bytes.decode("utf-8-sig", errors="strict").strip()
            else:
                text = payload.strip()

            if text.startswith("{"):
                source_format = "apple_watch_json"
                try:
                    data = json.loads(text)
                    # Support nested Health Auto Export / HealthKit JSON structures (`data.workouts` or flat)
                    if isinstance(data.get("data"), dict) and isinstance(data["data"].get("workouts"), list) and data["data"]["workouts"]:
                        w = data["data"]["workouts"][-1]
                        data = {**data, **w}

                    measured_hr = data.get('heart_rate_bpm', data.get('heartRateBpm', data.get('avgHeartRate', hr)))
                    hr = float(measured_hr) if measured_hr is not None else None
                    if "peak_heart_rate_bpm" in data or "maxHeartRate" in data:
                        peak_hr = float(data.get("peak_heart_rate_bpm", data.get("maxHeartRate")))
                    if "resting_heart_rate_bpm" in data or "restingHeartRate" in data:
                        resting_hr = float(data.get("resting_heart_rate_bpm", data.get("restingHeartRate")))
                    if "hrv_sdnn_ms" in data or "heartRateVariabilitySDNN" in data:
                        hrv_sdnn_ms = float(data.get("hrv_sdnn_ms", data.get("heartRateVariabilitySDNN")))
                    measured_cal = data.get('active_calories_kcal', data.get('activeCaloriesKcal', data.get('activeEnergyBurned', cal)))
                    cal = float(measured_cal) if measured_cal is not None else None
                    if "workout_duration_min" in data or "durationMinutes" in data:
                        duration_min = float(data.get("workout_duration_min", data.get("durationMinutes")))
                    if "wrist_acceleration_peak_mps" in data:
                        wrist_speed_mps = float(data["wrist_acceleration_peak_mps"])
                    workout_type = str(data.get("workout_activity_type", data.get("workoutActivityType", workout_type)))
                    f_state = data.get("fatigue_state", data.get("fatigueState", f_state))
                except Exception as exc:
                    raise ValueError("Malformed Apple Watch telemetry") from exc

            elif text.startswith("<"):
                source_format = "apple_healthkit_xml"
                try:
                    root = ET.fromstring(text)
                    hr_samples: List[float] = []
                    resting_samples: List[float] = []
                    hrv_samples: List[float] = []
                    workout_cal: Optional[float] = None
                    record_cal_samples: List[float] = []

                    for elem in root.iter():
                        tag = elem.tag.lower()
                        attrib = {k.lower(): v for k, v in elem.attrib.items()}

                        # Direct custom attributes
                        if "heart_rate_bpm" in attrib:
                            hr_samples.append(float(attrib["heart_rate_bpm"]))
                        if "active_calories_kcal" in attrib:
                            workout_cal = float(attrib["active_calories_kcal"])
                        if "fatigue_state" in attrib:
                            f_state = attrib["fatigue_state"]
                        if "hrv_sdnn_ms" in attrib:
                            hrv_samples.append(float(attrib["hrv_sdnn_ms"]))

                        # Standard Apple HealthKit <Workout> element
                        if tag == "workout":
                            if "workoutactivitytype" in attrib:
                                workout_type = elem.attrib.get("workoutActivityType", workout_type)
                            if "duration" in attrib:
                                try:
                                    duration_min = round(float(attrib["duration"]), 1)
                                except ValueError:
                                    pass
                            if "totalenergyburned" in attrib:
                                try:
                                    workout_cal = float(attrib["totalenergyburned"])
                                except ValueError:
                                    pass

                        # Standard Apple HealthKit <WorkoutStatistics> element
                        if tag == "workoutstatistics":
                            stat_type = attrib.get("type", "").lower()
                            if "heartrate" in stat_type:
                                if "average" in attrib:
                                    hr_samples.append(float(attrib["average"]))
                                if "maximum" in attrib:
                                    peak_hr = max(peak_hr or 0.0, float(attrib["maximum"]))
                            elif "activeenergyburned" in stat_type and "sum" in attrib:
                                workout_cal = float(attrib["sum"])

                        # Standard Apple HealthKit <Record> or custom tags
                        rec_type = attrib.get("type", "").lower()
                        val = attrib.get("value") or (elem.text.strip() if elem.text else None)
                        if val:
                            try:
                                num_val = float(val)
                                if "heartratevariabilitysdnn" in rec_type or tag in ("hrv_sdnn_ms", "hrv"):
                                    hrv_samples.append(num_val)
                                elif "restingheartrate" in rec_type or tag == "resting_heart_rate_bpm":
                                    resting_samples.append(num_val)
                                elif "heartrate" in rec_type or tag in ("heart_rate_bpm", "heartrate"):
                                    hr_samples.append(num_val)
                                elif "activeenergyburned" in rec_type or tag in (
                                    "active_calories_kcal",
                                    "activecalories",
                                ):
                                    record_cal_samples.append(num_val)
                            except ValueError:
                                if tag in ("fatigue_state", "fatiguestate"):
                                    f_state = val

                    if hr_samples:
                        hr = sum(hr_samples) / len(hr_samples)
                        peak_hr = max(peak_hr or 0.0, max(hr_samples))
                    if resting_samples:
                        resting_hr = sum(resting_samples) / len(resting_samples)
                    if hrv_samples:
                        hrv_sdnn_ms = sum(hrv_samples) / len(hrv_samples)
                    if workout_cal is not None:
                        cal = workout_cal
                    elif record_cal_samples:
                        cal = sum(record_cal_samples)
                except Exception as exc:
                    raise ValueError("Malformed Apple Watch telemetry") from exc

            else:
                raise ValueError("Expected JSON, XML, or ZIP telemetry")

    for name, value in {"heart_rate_bpm": hr, "peak_heart_rate_bpm": peak_hr,
                        "resting_heart_rate_bpm": resting_hr, "hrv_sdnn_ms": hrv_sdnn_ms,
                        "active_calories_kcal": cal, "workout_duration_min": duration_min,
                        "wrist_acceleration_peak_mps": wrist_speed_mps}.items():
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError(f"{name} must be finite and nonnegative")
    if hr is not None and not 20 <= hr <= 250:
        raise ValueError("heart_rate_bpm must be between 20 and 250")
    if hr is None:
        raise ValueError("A heart rate measurement is required")

    final_hr = round(hr if hr is not None else 168.0, 1)
    final_peak_hr = round(peak_hr if peak_hr is not None else max(final_hr + 8.0, 174.0), 1)
    final_resting_hr = round(resting_hr if resting_hr is not None else 58.0, 1)
    final_hrv = round(hrv_sdnn_ms if hrv_sdnn_ms is not None else (24.5 if final_hr >= 170.0 else 48.0), 1)
    final_cal = round(cal if cal is not None else 420.0, 1)
    final_duration = round(duration_min if duration_min is not None else 45.0, 1)
    final_wrist_speed = round(wrist_speed_mps if wrist_speed_mps is not None else 28.4, 1)

    final_fatigue = _derive_fatigue_state(
        heart_rate_bpm=final_hr,
        active_calories_kcal=final_cal,
        explicit_state=f_state,
        hrv_sdnn_ms=final_hrv,
    )
    fatigue_index = _compute_fatigue_index(
        heart_rate_bpm=final_hr,
        active_calories_kcal=final_cal,
        hrv_sdnn_ms=final_hrv,
    )

    return {
        "sampled_at": sample_time,
        "heart_rate_bpm": final_hr,
        "peak_heart_rate_bpm": final_peak_hr,
        "resting_heart_rate_bpm": final_resting_hr,
        "hrv_sdnn_ms": final_hrv,
        "active_calories_kcal": final_cal,
        "workout_duration_min": final_duration,
        "wrist_acceleration_peak_mps": final_wrist_speed,
        "workout_activity_type": workout_type,
        "fatigue_index": fatigue_index,
        "fatigue_state": final_fatigue,
        "source_format": source_format,
        "estimated_fields": [name for name, value in {
            "peak_heart_rate_bpm": peak_hr, "resting_heart_rate_bpm": resting_hr,
            "hrv_sdnn_ms": hrv_sdnn_ms, "active_calories_kcal": cal,
            "workout_duration_min": duration_min, "wrist_acceleration_peak_mps": wrist_speed_mps,
        }.items() if value is None] + ["fatigue_index"],
    }

