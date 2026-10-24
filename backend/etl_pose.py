"""
etl_pose.py - Video & Apple Watch ETL Pipeline (Kong)
Scans uploaded .mp4 badminton stroke videos using OpenCV + MediaPipe Pose,
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

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = hasattr(mp, "solutions") and hasattr(mp.solutions, "pose")
except Exception:
    mp = None
    HAS_MEDIAPIPE = False


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
    if norm_a < 1e-8 or norm_c < 1e-8:
        return 180.0

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


def extract_pose_from_video(video_path: str) -> Dict[str, Any]:
    """
    Scan an uploaded .mp4 badminton stroke video with OpenCV + MediaPipe Pose (`mp.solutions.pose`).
    Identifies the peak overhead shuttle contact frame (minimum `y` coordinate of `RIGHT_WRIST`),
    computes the 5 key 3D joint angles + `contact_height_norm` (`1.0 - wrist_y`), and outputs both
    raw angles and the 6D normalized `pose_vector`.
    Includes a clean fallback if no full body is detected in a test clip.
    """
    if not video_path or not os.path.exists(video_path) or cv2 is None:
        raw_angles = dict(FALLBACK_RAW_ANGLES)
        return {
            "status": "fallback_no_video",
            "used_fallback": True,
            "frames_scanned": 0,
            "peak_contact_frame": 0,
            "raw_angles": raw_angles,
            **raw_angles,
            "pose_vector": build_pose_vector(raw_angles),
        }

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raw_angles = dict(FALLBACK_RAW_ANGLES)
        return {
            "status": "fallback_unreadable_video",
            "used_fallback": True,
            "frames_scanned": 0,
            "peak_contact_frame": 0,
            "raw_angles": raw_angles,
            **raw_angles,
            "pose_vector": build_pose_vector(raw_angles),
        }

    best_wrist_y = float("inf")
    best_frame_idx = -1
    best_landmarks = None
    frames_scanned = 0

    if HAS_MEDIAPIPE:
        mp_pose = mp.solutions.pose
        with mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                frames_scanned += 1
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb_frame)

                if results.pose_landmarks and results.pose_landmarks.landmark:
                    lms = results.pose_landmarks.landmark
                    right_wrist = lms[mp_pose.PoseLandmark.RIGHT_WRIST.value]
                    right_shoulder = lms[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                    right_hip = lms[mp_pose.PoseLandmark.RIGHT_HIP.value]

                    # Require core landmarks to have reasonable visibility
                    if (
                        getattr(right_wrist, "visibility", 1.0) >= 0.35
                        and getattr(right_shoulder, "visibility", 1.0) >= 0.35
                        and getattr(right_hip, "visibility", 1.0) >= 0.35
                    ):
                        wrist_y = float(right_wrist.y)
                        if wrist_y < best_wrist_y:
                            best_wrist_y = wrist_y
                            best_frame_idx = frames_scanned - 1
                            best_landmarks = lms
    else:
        # Still count frames with OpenCV if MediaPipe is unavailable in the runtime
        while True:
            ret, _ = cap.read()
            if not ret:
                break
            frames_scanned += 1

    cap.release()

    if best_landmarks is None or not HAS_MEDIAPIPE:
        raw_angles = dict(FALLBACK_RAW_ANGLES)
        return {
            "status": "fallback_no_full_body_detected",
            "used_fallback": True,
            "frames_scanned": frames_scanned,
            "peak_contact_frame": 0,
            "raw_angles": raw_angles,
            **raw_angles,
            "pose_vector": build_pose_vector(raw_angles),
        }

    PL = mp.solutions.pose.PoseLandmark

    r_shoulder = _extract_landmark_3d(best_landmarks, PL.RIGHT_SHOULDER.value)
    r_elbow = _extract_landmark_3d(best_landmarks, PL.RIGHT_ELBOW.value)
    r_wrist = _extract_landmark_3d(best_landmarks, PL.RIGHT_WRIST.value)
    r_hip = _extract_landmark_3d(best_landmarks, PL.RIGHT_HIP.value)
    r_knee = _extract_landmark_3d(best_landmarks, PL.RIGHT_KNEE.value)
    r_ankle = _extract_landmark_3d(best_landmarks, PL.RIGHT_ANKLE.value)

    l_shoulder = _extract_landmark_3d(best_landmarks, PL.LEFT_SHOULDER.value)
    l_elbow = _extract_landmark_3d(best_landmarks, PL.LEFT_ELBOW.value)
    l_hip = _extract_landmark_3d(best_landmarks, PL.LEFT_HIP.value)

    # 1. Right elbow angle at contact (shoulder - elbow - wrist)
    right_elbow_contact_deg = compute_angle_3d(r_shoulder, r_elbow, r_wrist)
    # 2. Right shoulder abduction angle (hip - shoulder - elbow)
    right_shoulder_abduction_deg = compute_angle_3d(r_hip, r_shoulder, r_elbow)
    # 3. Trunk arch angle (shoulder - hip - knee)
    trunk_arch_deg = compute_angle_3d(r_shoulder, r_hip, r_knee)
    # 4. Right knee flexion angle (hip - knee - ankle)
    right_knee_flexion_deg = compute_angle_3d(r_hip, r_knee, r_ankle)
    # 5. Left arm balance angle (left hip - left shoulder - left elbow)
    left_arm_balance_deg = compute_angle_3d(l_hip, l_shoulder, l_elbow)
    # 6. Normalized contact height (1.0 - wrist_y)
    contact_height_norm = round(max(0.0, min(1.0, 1.0 - float(r_wrist[1]))), 4)

    raw_angles = {
        "right_elbow_contact_deg": right_elbow_contact_deg,
        "right_shoulder_abduction_deg": right_shoulder_abduction_deg,
        "trunk_arch_deg": trunk_arch_deg,
        "right_knee_flexion_deg": right_knee_flexion_deg,
        "left_arm_balance_deg": left_arm_balance_deg,
        "contact_height_norm": contact_height_norm,
    }

    return {
        "status": "detected",
        "used_fallback": False,
        "frames_scanned": frames_scanned,
        "peak_contact_frame": best_frame_idx,
        "raw_angles": raw_angles,
        **raw_angles,
        "pose_vector": build_pose_vector(raw_angles),
    }


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
) -> Dict[str, Any]:
    """
    ETL parser for Apple Watch workout biometrics:
    Supports:
    1. Apple HealthKit `export.xml` or `export.zip` (`<Workout>`, `<WorkoutStatistics>`, `<Record>`)
    2. Live Apple Watch HealthKit / Health Auto Export JSON payloads
    3. Direct form fields (`heart_rate_bpm`, `active_calories_kcal`, `fatigue_state`)
    """
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

    # Check if `payload` is a file path on disk
    if isinstance(payload, str) and os.path.exists(payload) and os.path.isfile(payload):
        with open(payload, "rb") as f:
            payload = f.read()

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
                text = raw_bytes.decode("utf-8", errors="ignore").strip()
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

                    hr = float(
                        data.get(
                            "heart_rate_bpm",
                            data.get("heartRateBpm", data.get("avgHeartRate", hr if hr is not None else 168.0)),
                        )
                    )
                    if "peak_heart_rate_bpm" in data or "maxHeartRate" in data:
                        peak_hr = float(data.get("peak_heart_rate_bpm", data.get("maxHeartRate")))
                    if "resting_heart_rate_bpm" in data or "restingHeartRate" in data:
                        resting_hr = float(data.get("resting_heart_rate_bpm", data.get("restingHeartRate")))
                    if "hrv_sdnn_ms" in data or "heartRateVariabilitySDNN" in data:
                        hrv_sdnn_ms = float(data.get("hrv_sdnn_ms", data.get("heartRateVariabilitySDNN")))
                    cal = float(
                        data.get(
                            "active_calories_kcal",
                            data.get(
                                "activeCaloriesKcal",
                                data.get("activeEnergyBurned", cal if cal is not None else 420.0),
                            ),
                        )
                    )
                    if "workout_duration_min" in data or "durationMinutes" in data:
                        duration_min = float(data.get("workout_duration_min", data.get("durationMinutes")))
                    if "wrist_acceleration_peak_mps" in data:
                        wrist_speed_mps = float(data["wrist_acceleration_peak_mps"])
                    workout_type = str(data.get("workout_activity_type", data.get("workoutActivityType", workout_type)))
                    f_state = data.get("fatigue_state", data.get("fatigueState", f_state))
                except Exception:
                    pass

            elif text.startswith("<"):
                source_format = "apple_healthkit_xml"
                try:
                    root = ET.fromstring(text)
                    hr_samples: List[float] = []
                    resting_samples: List[float] = []
                    hrv_samples: List[float] = []
                    cal_samples: List[float] = []

                    for elem in root.iter():
                        tag = elem.tag.lower()
                        attrib = {k.lower(): v for k, v in elem.attrib.items()}

                        # Direct custom attributes
                        if "heart_rate_bpm" in attrib:
                            hr_samples.append(float(attrib["heart_rate_bpm"]))
                        if "active_calories_kcal" in attrib:
                            cal_samples.append(float(attrib["active_calories_kcal"]))
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
                                    cal_samples.append(float(attrib["totalenergyburned"]))
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
                                cal_samples.append(float(attrib["sum"]))

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
                                    cal_samples.append(num_val)
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
                    if cal_samples:
                        cal = max(cal_samples) if len(cal_samples) == 1 else sum(cal_samples)
                except Exception:
                    pass

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
    }

