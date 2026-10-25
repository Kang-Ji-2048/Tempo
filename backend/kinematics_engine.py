"""Multi-stroke kinematic engine shared by uploaded video (etl_pose) and the live stream (android_api).

Input: per-frame MediaPipe Pose landmarks (33 x [x, y, z, visibility], normalized image coordinates),
optionally with metric world landmarks. Output: phase-segmented `CompletedRep`s with stroke
classification, archetype checks, a 0-100 quality score and the single biggest deviation, plus
session-level drift / heart-rate / combo-sequence analysis.

Design notes (honest limits):
- Monocular pose; racket and shuttle/ball are not tracked. "Impact" is the peak-wrist-speed frame
  (overhead strokes: the highest wrist frame within that window), i.e. a contact *proxy*.
- Heights and speeds are body-relative (divided by shoulder-to-ankle length) so framing distance
  doesn't change thresholds. Forehand/backhand side detection assumes a front/back-ish camera view.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# MediaPipe Pose landmark indices.
NOSE = 0
L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 23, 24, 25, 26, 27, 28
SIDES = {"right": (R_SHOULDER, R_ELBOW, R_WRIST, R_HIP, R_KNEE, R_ANKLE),
         "left": (L_SHOULDER, L_ELBOW, L_WRIST, L_HIP, L_KNEE, L_ANKLE)}
CORE = (NOSE, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)
MIN_VISIBILITY = 0.5

PHASES = ("READY", "PREPARATION", "LOADING", "IMPACT", "FOLLOW_THROUGH")

# Skill ids used by the app/catalog -> engine archetypes.
SKILL_TO_STROKE = {
    "overhead_clear": "overhead_clear", "jump_smash": "jump_smash", "net_lunge_defense": "net_lunge_defense",
    "forehand": "forehand_topspin", "forehand_topspin": "forehand_topspin",
    "one_hand_backhand": "one_handed_backhand", "one_handed_backhand": "one_handed_backhand",
    "two_hand_backhand": "two_handed_backhand", "two_handed_backhand": "two_handed_backhand",
    "first_serve": "first_serve", "serve": "first_serve",
}
STROKES_BY_SPORT = {
    "badminton": ("overhead_clear", "jump_smash", "net_lunge_defense"),
    "tennis": ("forehand_topspin", "one_handed_backhand", "two_handed_backhand", "first_serve"),
}
STROKE_LABELS = {
    "overhead_clear": "overhead clear", "jump_smash": "jump smash", "net_lunge_defense": "net lunge",
    "forehand_topspin": "topspin forehand", "one_handed_backhand": "one-handed backhand",
    "two_handed_backhand": "two-handed backhand", "first_serve": "first serve", "drive": "drive",
    "unclassified": "swing",
}
OVERHEAD_STROKES = {"overhead_clear", "jump_smash", "first_serve"}
FOOTWORK_STROKES = {"net_lunge_defense"}


def stroke_for_skill(skill: Optional[str]) -> Optional[str]:
    return SKILL_TO_STROKE.get((skill or "").strip().lower())


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _angle(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    v1 = [a[i] - b[i] for i in range(len(a))]
    v2 = [c[i] - b[i] for i in range(len(c))]
    n1, n2 = math.sqrt(sum(x * x for x in v1)), math.sqrt(sum(x * x for x in v2))
    if n1 == 0 or n2 == 0:
        return 180.0
    cos = max(-1.0, min(1.0, sum(v1[i] * v2[i] for i in range(len(v1))) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _line_angle_deg(p: Sequence[float], q: Sequence[float]) -> float:
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))


def _wrap(deg: float) -> float:
    deg = (deg + 180.0) % 360.0 - 180.0
    return abs(deg)


@dataclass
class FrameFeatures:
    """Per-frame measurements for one athlete, for the given hitting side."""
    t_ms: int
    side: str
    elbow_deg: float            # hitting-arm elbow
    shoulder_deg: float         # hip-shoulder-elbow (abduction) on hitting side
    lead_knee_deg: float        # most-flexed knee this frame
    back_knee_deg: float        # knee on the hitting side (back leg for most strokes)
    trunk_lean_deg: float       # shoulder-mid -> hip-mid vs vertical; 0 = upright
    coil_deg: float             # shoulder line vs hip line, top-down (x, z) when depth exists
    reach_ratio: float          # hitting wrist height over ankles / nose height over ankles (>1 above head)
    hip_ratio: float            # hip height over ankles / shoulder height over ankles (lower = deeper)
    contact_height_norm: float  # 1 - wrist.y (image space; kept for the 6D vector contract)
    wrist_xy: Tuple[float, float]           # hitting wrist, aspect-corrected, body-height units
    off_wrist_xy: Tuple[float, float]
    hip_mid_xy: Tuple[float, float]
    shoulder_mid_x: float
    hitting_shoulder_x: float
    body_h: float               # shoulder-to-ankle length in aspect-corrected image units
    forearm_deg: float          # direction of elbow->wrist in the image plane
    off_arm_vertical_deg: float # tossing arm (non-hitting shoulder->wrist) angle from vertical
    wrist_above_head: bool
    racket_drop: bool           # hitting wrist below hip plane
    balance: float              # 0-1, hip centre over base of support + upright trunk
    visible: bool = True


def frame_features(landmarks: Sequence[Sequence[float]], t_ms: int, side: str = "right",
                   aspect: float = 0.75, world: Optional[Sequence[Sequence[float]]] = None) -> Optional[FrameFeatures]:
    """Compute features for one frame; None when the core body isn't confidently visible."""
    if len(landmarks) < 33:
        return None
    if any(len(landmarks[i]) < 4 or landmarks[i][3] < MIN_VISIBILITY for i in CORE + SIDES[side][:3]):
        return None
    sh, el, wr, hp, kn, an = SIDES[side]
    other = "left" if side == "right" else "right"
    osh, oel, owr, ohp, okn, oan = SIDES[other]

    def p2(i: int) -> Tuple[float, float]:
        return (landmarks[i][0] * aspect, landmarks[i][1])

    def p3(i: int) -> Tuple[float, float, float]:
        src = world if world is not None and len(world) >= 33 else None
        if src is not None:
            return (float(src[i][0]), float(src[i][1]), float(src[i][2]))
        return (landmarks[i][0] * aspect, landmarks[i][1], landmarks[i][2] * aspect)

    elbow = _angle(p3(sh), p3(el), p3(wr))
    shoulder = _angle(p3(hp), p3(sh), p3(el))
    knee_hit = _angle(p3(hp), p3(kn), p3(an))
    knee_off = _angle(p3(ohp), p3(okn), p3(oan))

    sh_mid = ((p2(L_SHOULDER)[0] + p2(R_SHOULDER)[0]) / 2, (p2(L_SHOULDER)[1] + p2(R_SHOULDER)[1]) / 2)
    hip_mid = ((p2(L_HIP)[0] + p2(R_HIP)[0]) / 2, (p2(L_HIP)[1] + p2(R_HIP)[1]) / 2)
    ankle_y = max(p2(L_ANKLE)[1], p2(R_ANKLE)[1])
    body_h = max(1e-6, ankle_y - sh_mid[1])
    trunk_lean = math.degrees(math.atan2(abs(sh_mid[0] - hip_mid[0]), max(1e-6, hip_mid[1] - sh_mid[1])))

    # Top-down coil: compare shoulder and hip lines in (x, depth). Depth: world z, else normalized z.
    def top(i: int) -> Tuple[float, float]:
        q = p3(i)
        return (q[0], q[2])
    coil = _wrap(_line_angle_deg(top(L_SHOULDER), top(R_SHOULDER)) - _line_angle_deg(top(L_HIP), top(R_HIP)))
    coil = min(coil, 180.0 - coil)

    nose_h = ankle_y - p2(NOSE)[1]
    reach = (ankle_y - p2(wr)[1]) / max(1e-6, nose_h)
    hip_ratio = (ankle_y - hip_mid[1]) / body_h
    off_vec = (p2(owr)[0] - p2(osh)[0], p2(owr)[1] - p2(osh)[1])
    off_vertical = math.degrees(math.atan2(abs(off_vec[0]), max(1e-6, -off_vec[1]))) if off_vec[1] < 0 else 90.0 + \
        math.degrees(math.atan2(off_vec[1], max(1e-6, abs(off_vec[0]))))
    feet = sorted([p2(L_ANKLE)[0], p2(R_ANKLE)[0]])
    margin = 0.08 * body_h
    inside = feet[0] - margin <= hip_mid[0] <= feet[1] + margin
    balance = max(0.0, min(1.0, (1.0 if inside else 0.5) - max(0.0, trunk_lean - 20.0) / 60.0))

    scale = 1.0 / body_h
    return FrameFeatures(
        t_ms=int(t_ms), side=side, elbow_deg=elbow, shoulder_deg=shoulder,
        lead_knee_deg=min(knee_hit, knee_off), back_knee_deg=knee_hit, trunk_lean_deg=trunk_lean,
        coil_deg=coil, reach_ratio=reach, hip_ratio=hip_ratio,
        contact_height_norm=round(1.0 - landmarks[wr][1], 4),
        wrist_xy=(p2(wr)[0] * scale, p2(wr)[1] * scale), off_wrist_xy=(p2(owr)[0] * scale, p2(owr)[1] * scale),
        hip_mid_xy=(hip_mid[0] * scale, hip_mid[1] * scale), shoulder_mid_x=sh_mid[0] * scale,
        hitting_shoulder_x=p2(sh)[0] * scale, body_h=body_h,
        forearm_deg=_line_angle_deg(p2(el), p2(wr)), off_arm_vertical_deg=off_vertical,
        wrist_above_head=p2(wr)[1] < p2(NOSE)[1], racket_drop=p2(wr)[1] > hip_mid[1], balance=balance,
    )


def detect_side(frames: Sequence[Sequence[Sequence[float]]], aspect: float = 0.75) -> str:
    """Hitting side = the wrist that travels further across the clip/window (handles left-handers)."""
    travel = {"right": 0.0, "left": 0.0}
    prev: Dict[str, Tuple[float, float]] = {}
    for lm in frames:
        if len(lm) < 33:
            continue
        for side, idx in (("right", R_WRIST), ("left", L_WRIST)):
            if lm[idx][3] < MIN_VISIBILITY:
                prev.pop(side, None)
                continue
            point = (lm[idx][0] * aspect, lm[idx][1])
            if side in prev:
                travel[side] += math.dist(point, prev[side])
            prev[side] = point
    return "left" if travel["left"] > travel["right"] * 1.15 else "right"


# ---------------------------------------------------------------------------
# Rep state machine
# ---------------------------------------------------------------------------

@dataclass
class PhaseKeyframe:
    phase: str
    t_ms: int
    angles: Dict[str, float]


@dataclass
class CompletedRep:
    rep_index: int
    started_ms: int
    impact_ms: int
    ended_ms: int
    side: str
    detected_stroke: str
    phase_angles: Dict[str, float]
    keyframes: List[PhaseKeyframe]
    pose_vector_6d: List[float]
    metrics: Dict[str, float]
    quality_score: int = 0
    primary_deviation: Optional[str] = None
    checks: List[Dict[str, Any]] = field(default_factory=list)
    target_stroke: Optional[str] = None
    stroke_matches_target: bool = True
    rep_counted: bool = False
    heart_rate: Optional[float] = None
    pro_match: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["keyframes"] = [asdict(k) for k in self.keyframes]
        return out


def _snapshot(f: FrameFeatures) -> Dict[str, float]:
    return {"elbow_deg": round(f.elbow_deg, 1), "shoulder_deg": round(f.shoulder_deg, 1),
            "lead_knee_deg": round(f.lead_knee_deg, 1), "back_knee_deg": round(f.back_knee_deg, 1),
            "trunk_lean_deg": round(f.trunk_lean_deg, 1), "coil_deg": round(f.coil_deg, 1),
            "reach_ratio": round(f.reach_ratio, 3), "hip_ratio": round(f.hip_ratio, 3)}


class RepTracker:
    """READY -> PREPARATION -> LOADING -> IMPACT -> FOLLOW_THROUGH -> CompletedRep.

    Stroke mode is driven by hitting-wrist speed (body heights / s); footwork mode (lunges) by hip
    travel and lead-knee depth. `feed()` returns a CompletedRep when one finishes, else None, and
    `phase_changed` tells callers when to emit a phase update.
    """

    # Body-heights per second. Tuned on real clips: a relaxed ready stance stays under ~0.5.
    IDLE_SPEED, PREP_SPEED, IMPACT_SPEED = 0.6, 1.0, 2.2
    LUNGE_START_SPEED, LUNGE_KNEE_DEG = 0.35, 150.0
    MAX_WINDUP_MS, MAX_FOLLOW_MS, SETTLE_MS = 2500, 1200, 200

    def __init__(self, target_stroke: Optional[str] = None, sport: Optional[str] = None, side: str = "right") -> None:
        self.target_stroke = target_stroke
        self.sport = sport
        self.side = side
        self.mode = "footwork" if target_stroke in FOOTWORK_STROKES else "stroke"
        self.phase = "READY"
        self.phase_changed = False
        self.transitions: List[str] = []  # every phase entered during the last feed(), in order
        self.reps: List[CompletedRep] = []
        self._prev: Optional[FrameFeatures] = None
        self._frames: List[FrameFeatures] = []
        self._phase_since = 0
        self._peak_speed = 0.0
        self._slow_since: Optional[int] = None
        self._baseline_hip: Optional[Tuple[float, float]] = None
        self._baseline_hip_y: Optional[float] = None
        self._ready_buffer: List[Tuple[FrameFeatures, float]] = []  # recent (frame, speed) while READY
        self._prep_peak = 0.0
        self._armed = True  # footwork: a new lunge may start only after standing still again
        self.last_speed = 0.0

    def reset_target(self, target_stroke: Optional[str], sport: Optional[str] = None) -> None:
        self.target_stroke = target_stroke
        self.sport = sport or self.sport
        self.mode = "footwork" if target_stroke in FOOTWORK_STROKES else "stroke"
        self._to("READY", self._prev.t_ms if self._prev else 0)
        self._frames = []

    def _to(self, phase: str, t_ms: int) -> None:
        if phase != self.phase:
            self.transitions.append(phase)
            self.phase_changed = True
        self.phase = phase
        self._phase_since = t_ms

    def feed(self, f: Optional[FrameFeatures], heart_rate: Optional[float] = None) -> Optional[CompletedRep]:
        self.phase_changed = False
        self.transitions = []
        if f is None:
            return None
        prev = self._prev
        self._prev = f
        if prev is None or f.t_ms <= prev.t_ms:
            self._baseline_hip = f.hip_mid_xy
            self._baseline_hip_y = f.hip_mid_xy[1]
            return None
        dt = (f.t_ms - prev.t_ms) / 1000.0
        # Wrist speed relative to the hips: walking or lunging the whole body is not a swing.
        speed = math.dist(_rel(f), _rel(prev)) / dt
        hip_speed = math.dist(f.hip_mid_xy, prev.hip_mid_xy) / dt
        self.last_speed = speed
        standing_still = f.lead_knee_deg > 160 and hip_speed < self.LUNGE_START_SPEED * 0.5 and speed < self.IDLE_SPEED
        if standing_still:
            self._armed = True
        if self.phase == "READY" and (self._baseline_hip is None or standing_still):
            # Track the resting stance (only while upright and still) as the reference for lunge travel,
            # recovery and jump height.
            self._baseline_hip = f.hip_mid_xy
            self._baseline_hip_y = f.hip_mid_xy[1] if self._baseline_hip_y is None else \
                0.8 * self._baseline_hip_y + 0.2 * f.hip_mid_xy[1]
        return self._feed_footwork(f, hip_speed, heart_rate) if self.mode == "footwork" \
            else self._feed_stroke(f, speed, heart_rate)

    def _feed_stroke(self, f: FrameFeatures, speed: float, hr: Optional[float]) -> Optional[CompletedRep]:
        t = f.t_ms
        if self.phase == "READY":
            self._ready_buffer = (self._ready_buffer + [(f, speed)])[-30:]
            if speed >= self.IMPACT_SPEED:
                # A relaxed take-back can stay under PREP_SPEED: the swing itself starts the rep, and the
                # buffered frames since the athlete last stood still become its preparation history.
                self._frames = self._since_still()
                self._prep_peak = speed
                self._to("PREPARATION", t)
                self._to("LOADING", t)
                self._peak_speed = speed
                self._to("IMPACT", t)
            elif speed >= self.PREP_SPEED or f.wrist_above_head or (f.racket_drop and speed > self.IDLE_SPEED):
                self._frames = self._since_still()
                self._prep_peak = speed
                self._peak_speed = 0.0
                self._to("PREPARATION", t)
            return None
        self._frames.append(f)
        if self.phase in ("PREPARATION", "LOADING"):
            if speed >= self.IMPACT_SPEED:
                if self.phase == "PREPARATION":
                    self._to("LOADING", t)
                self._peak_speed = speed
                self._to("IMPACT", t)
                return None
            if t - self._phase_since > self.MAX_WINDUP_MS:
                self._to("READY", t)  # abandoned wind-up, no rep
                self._ready_buffer = []
                return None
            if self.phase == "PREPARATION":
                self._prep_peak = max(self._prep_peak, speed)
                # Take-back turning point (wrist decelerates), racket drop, knee load or trophy position.
                if speed < self._prep_peak * 0.75 or f.racket_drop or f.back_knee_deg < 155 or f.wrist_above_head:
                    self._to("LOADING", t)
            return None
        if self.phase == "IMPACT":
            if speed > self._peak_speed:
                self._peak_speed = speed
            elif speed < self._peak_speed * 0.5:
                self._to("FOLLOW_THROUGH", t)
                self._slow_since = None
            return None
        # FOLLOW_THROUGH
        if speed < self.IDLE_SPEED:
            self._slow_since = self._slow_since or t
        else:
            self._slow_since = None
        if (self._slow_since and t - self._slow_since >= self.SETTLE_MS) or t - self._phase_since > self.MAX_FOLLOW_MS:
            rep = self._complete(hr)
            self._to("READY", t)
            self._ready_buffer = []
            return rep
        return None

    def _since_still(self) -> List[FrameFeatures]:
        """Buffered READY frames after the athlete's last still moment (the start of the take-back)."""
        buf = self._ready_buffer
        start = max((i for i, (_, sp) in enumerate(buf) if sp < self.IDLE_SPEED * 0.5), default=0)
        return [fr for fr, _ in buf[start:]]

    def _feed_footwork(self, f: FrameFeatures, hip_speed: float, hr: Optional[float]) -> Optional[CompletedRep]:
        t = f.t_ms
        if self.phase == "READY":
            if not self._armed:
                return None
            if hip_speed >= self.LUNGE_START_SPEED or f.lead_knee_deg < self.LUNGE_KNEE_DEG:
                self._frames = [f]
                self._to("PREPARATION", t)
            return None
        self._frames.append(f)
        deepest = min(self._frames, key=lambda x: x.lead_knee_deg)
        if self.phase == "PREPARATION":
            if f.lead_knee_deg < self.LUNGE_KNEE_DEG:
                self._to("LOADING", t)
            elif t - self._phase_since > self.MAX_WINDUP_MS:
                self._to("READY", t)
            return None
        if self.phase == "LOADING":
            if f.lead_knee_deg > deepest.lead_knee_deg + 8:  # rising out of the lunge: deepest point passed
                self._to("IMPACT", deepest.t_ms)
                self._to("FOLLOW_THROUGH", t)
            return None
        # FOLLOW_THROUGH: push back to base
        base = self._baseline_hip or f.hip_mid_xy
        if math.dist(f.hip_mid_xy, base) < 0.12 and f.lead_knee_deg > self.LUNGE_KNEE_DEG or \
                t - self._phase_since > 2 * self.MAX_FOLLOW_MS:
            rep = self._complete(hr, recovery_ms=t - deepest.t_ms)
            self._to("READY", t)
            self._armed = False
            return rep
        return None

    MIN_LUNGE_TRAVEL_BH = 0.08

    def _complete(self, hr: Optional[float], recovery_ms: Optional[int] = None) -> Optional[CompletedRep]:
        frames = self._frames
        if len(frames) < 4:
            return None
        if self.mode == "footwork":
            base = self._baseline_hip or frames[0].hip_mid_xy
            travel = max(math.dist(f.hip_mid_xy, base) for f in frames)
            if travel < self.MIN_LUNGE_TRAVEL_BH:
                return None  # a knee bend in place (e.g. loading for a clear), not a lunge
        rep = build_rep(frames, len(self.reps) + 1, self.side, self.sport, self.target_stroke,
                        self.mode, self._baseline_hip_y, recovery_ms, hr)
        if rep is not None:
            self.reps.append(rep)
        return rep


class MultiTracker:
    """Runs a stroke tracker and/or a footwork tracker side by side for combo drills (e.g. clear + lunge).

    Single-stroke drills use one tracker. Completed reps are renumbered in time order.
    """

    def __init__(self, sequence: Optional[List[str]], sport: Optional[str], side: str = "right") -> None:
        self.sequence = [s for s in (sequence or []) if s]
        self.sport = sport
        kinds = {("footwork" if s in FOOTWORK_STROKES else "stroke") for s in self.sequence} or {"stroke"}
        target_for = {k: next((s for s in self.sequence if (s in FOOTWORK_STROKES) == (k == "footwork")), None)
                      for k in kinds}
        single = len(set(self.sequence)) == 1
        self.trackers = {k: RepTracker(target_for[k] if single else None, sport, side) for k in kinds}
        if "footwork" in self.trackers:
            self.trackers["footwork"].mode = "footwork"
        self.reps: List[CompletedRep] = []

    @property
    def phase(self) -> str:
        active = [t.phase for t in self.trackers.values() if t.phase != "READY"]
        return active[0] if active else "READY"

    @property
    def transitions(self) -> List[str]:
        return [p for t in self.trackers.values() for p in t.transitions]

    @property
    def last_speed(self) -> float:
        return max(t.last_speed for t in self.trackers.values())

    def expected_next(self) -> Optional[str]:
        return self.sequence[len(self.reps) % len(self.sequence)] if self.sequence else None

    def feed(self, f: Optional[FrameFeatures], heart_rate: Optional[float] = None) -> List[CompletedRep]:
        done = []
        for tracker in self.trackers.values():
            expected = self.expected_next()
            rep = tracker.feed(f, heart_rate)
            if rep is None:
                continue
            if len(self.sequence) > 1:
                # Grade a combo rep against the stroke the sequence expects at this position.
                rep.target_stroke = expected
                grade_rep(rep)
            rep.rep_index = len(self.reps) + 1
            self.reps.append(rep)
            done.append(rep)
        return done


# ---------------------------------------------------------------------------
# Rep construction, classification and grading
# ---------------------------------------------------------------------------

def _rel(f: FrameFeatures) -> Tuple[float, float]:
    return (f.wrist_xy[0] - f.hip_mid_xy[0], f.wrist_xy[1] - f.hip_mid_xy[1])


def _speed_series(frames: List[FrameFeatures]) -> List[float]:
    out = [0.0]
    for a, b in zip(frames, frames[1:]):
        dt = max(1e-3, (b.t_ms - a.t_ms) / 1000.0)
        out.append(math.dist(_rel(a), _rel(b)) / dt)
    return out


def _pronation_proxy(frames: List[FrameFeatures], i: int) -> float:
    """Peak forearm rotation rate (deg/s) in the image plane around impact; a pronation-snap proxy."""
    best = 0.0
    for a, b in zip(frames[max(0, i - 3):i + 3], frames[max(0, i - 3) + 1:i + 4]):
        dt = max(1e-3, (b.t_ms - a.t_ms) / 1000.0)
        best = max(best, _wrap(b.forearm_deg - a.forearm_deg) / dt)
    return best


def build_rep(frames: List[FrameFeatures], index: int, side: str, sport: Optional[str],
              target: Optional[str], mode: str = "stroke", baseline_hip_y: Optional[float] = None,
              recovery_ms: Optional[int] = None, hr: Optional[float] = None) -> Optional[CompletedRep]:
    speeds = _speed_series(frames)
    if mode == "footwork":
        i_imp = min(range(len(frames)), key=lambda i: frames[i].lead_knee_deg)
    else:
        i_imp = max(range(len(frames)), key=lambda i: speeds[i])
        # Overhead contact: the highest wrist in the fast approach up to the speed peak. Frames after the
        # peak are follow-through (a high forehand finish must not read as an overhead contact).
        window = [i for i in range(max(0, i_imp - 2), i_imp + 1) if speeds[i] >= speeds[i_imp] * 0.5]
        if any(frames[i].wrist_above_head for i in window):
            i_imp = max(window, key=lambda i: frames[i].reach_ratio)
    pre, post = frames[:i_imp + 1], frames[i_imp:]
    imp = frames[i_imp]
    prep_f = max(pre, key=lambda f: f.coil_deg)
    load_f = min(pre, key=lambda f: f.back_knee_deg if mode == "stroke" else f.lead_knee_deg)
    follow_f = post[min(len(post) - 1, max(1, len(post) // 2))]
    baseline = baseline_hip_y if baseline_hip_y is not None else frames[0].hip_mid_xy[1]
    jump = max(0.0, baseline - min(f.hip_mid_xy[1] for f in frames))
    follow_high = any(f.wrist_xy[1] < f.hip_mid_xy[1] - 0.55 for f in post)  # wrist finishes above shoulder line
    metrics = {
        "peak_wrist_speed_bh_s": round(speeds[i_imp] if mode == "stroke" else max(speeds), 2),
        "pronation_proxy_deg_s": round(_pronation_proxy(frames, i_imp), 1),
        "jump_height_bh": round(jump, 3),
        "attack_angle_deg": round(math.degrees(math.atan2(imp.hip_mid_xy[1] - 0.55 - imp.wrist_xy[1],
                                                          max(1e-6, abs(imp.wrist_xy[0] - imp.hitting_shoulder_x)))), 1),
        "contact_space_bh": round(abs(imp.wrist_xy[0] - imp.hip_mid_xy[0]), 3),
        "racket_drop": float(any(f.racket_drop for f in pre)),
        "follow_through_high": float(follow_high),
        "two_hands_at_contact": float(math.dist(imp.wrist_xy, imp.off_wrist_xy) < 0.15),
        "toss_arm_vertical_deg": round(min(f.off_arm_vertical_deg for f in pre), 1),
        "min_trunk_lean_back_deg": round(max(f.trunk_lean_deg for f in post), 1),
        "lunge_depth_knee_deg": round(min(f.lead_knee_deg for f in frames), 1),
        "lowest_hip_ratio": round(min(f.hip_ratio for f in frames), 3),
        "recovery_ms": float(recovery_ms) if recovery_ms is not None else float(frames[-1].t_ms - imp.t_ms),
        "cross_body": float((imp.wrist_xy[0] - imp.shoulder_mid_x) * (imp.hitting_shoulder_x - imp.shoulder_mid_x) < 0),
    }
    phase_angles = {
        "prep_coil_deg": round(prep_f.coil_deg, 1),
        "loading_knee_deg": round(load_f.back_knee_deg if mode == "stroke" else load_f.lead_knee_deg, 1),
        "impact_elbow_deg": round(imp.elbow_deg, 1),
        "impact_shoulder_deg": round(imp.shoulder_deg, 1),
        "impact_trunk_deg": round(imp.trunk_lean_deg, 1),
        "contact_height_norm": round(imp.contact_height_norm, 3),
        "reach_ratio": round(imp.reach_ratio, 3),
        "follow_through_trunk_deg": round(follow_f.trunk_lean_deg, 1),
        "balance_score": round(sum(f.balance for f in post) / len(post), 2),
    }
    detected = classify_stroke(sport, imp, metrics, mode)
    vector = [round(imp.elbow_deg / 180.0, 4), round(imp.shoulder_deg / 180.0, 4),
              round((180.0 - imp.trunk_lean_deg) / 180.0, 4), round(load_f.back_knee_deg / 180.0, 4),
              round(phase_angles["balance_score"], 4), round(max(0.0, min(1.0, imp.contact_height_norm)), 4)]
    keyframes = [PhaseKeyframe("Preparation", prep_f.t_ms, _snapshot(prep_f)),
                 PhaseKeyframe("Loading", load_f.t_ms, _snapshot(load_f)),
                 PhaseKeyframe("Impact", imp.t_ms, _snapshot(imp)),
                 PhaseKeyframe("Follow-Through", follow_f.t_ms, _snapshot(follow_f))]
    rep = CompletedRep(rep_index=index, started_ms=frames[0].t_ms, impact_ms=imp.t_ms, ended_ms=frames[-1].t_ms,
                       side=side, detected_stroke=detected, phase_angles=phase_angles, keyframes=keyframes,
                       pose_vector_6d=vector, metrics=metrics, target_stroke=target, heart_rate=hr)
    grade_rep(rep)
    return rep


def classify_stroke(sport: Optional[str], imp: FrameFeatures, m: Dict[str, float], mode: str) -> str:
    if mode == "footwork" or (m["lunge_depth_knee_deg"] < 135 and m["lowest_hip_ratio"] < 0.5
                              and not imp.wrist_above_head):
        return "net_lunge_defense"
    if imp.wrist_above_head or imp.reach_ratio > 1.0:
        if sport == "tennis":
            return "first_serve"
        return "jump_smash" if m["jump_height_bh"] >= 0.05 else "overhead_clear"
    if sport == "badminton":
        return "drive"
    if m["two_hands_at_contact"]:
        return "two_handed_backhand"
    return "one_handed_backhand" if m["cross_body"] else "forehand_topspin"


@dataclass
class Check:
    key: str
    label: str
    value: float
    ok: bool
    weight: float
    gap: float  # how far outside the target, in the metric's own unit
    message: str


def _range_check(key: str, label: str, value: float, lo: Optional[float], hi: Optional[float], weight: float,
                 unit: str, scale: float, fix: str) -> Check:
    gap = (lo - value) if lo is not None and value < lo else (value - hi) if hi is not None and value > hi else 0.0
    target = f"{lo:g}-{hi:g}" if lo is not None and hi is not None else (f"{lo:g}+" if lo is not None else f"under {hi:g}")
    msg = f"{label}: {value:.0f}{unit} (target {target}{unit}). {fix}" if unit == "°" else \
        f"{label}: {value:.2f}{unit} (target {target}{unit}). {fix}"
    return Check(key, label, value, gap <= 0, weight, gap / scale, msg)


def _flag_check(key: str, label: str, ok: bool, weight: float, message: str) -> Check:
    return Check(key, label, 1.0 if ok else 0.0, ok, weight, 0.0 if ok else 1.0, message)


def archetype_checks(stroke: str, a: Dict[str, float], m: Dict[str, float],
                     elbow_target: Optional[float] = None) -> List[Check]:
    if stroke == "overhead_clear":
        return [
            _range_check("impact_elbow_deg", "Elbow at contact", a["impact_elbow_deg"], elbow_target or 165, None, 0.4,
                         "°", 15, "Reach up and hit at full extension."),
            _range_check("reach_ratio", "Contact height", a["reach_ratio"], 1.05, None, 0.25, "x head height", 0.15,
                         "Take the shuttle higher, above your hitting shoulder."),
            _range_check("prep_coil_deg", "Torso coil", a["prep_coil_deg"], 20, None, 0.2, "°", 20,
                         "Turn your shoulders side-on before you swing."),
            _range_check("balance_score", "Balance", a["balance_score"], 0.7, None, 0.15, "", 0.3,
                         "Land the scissor-kick under your hips."),
        ]
    if stroke == "jump_smash":
        return [
            _range_check("jump_height_bh", "Jump height", m["jump_height_bh"], 0.05, None, 0.25, " body heights", 0.05,
                         "Drive up off both legs before you hit."),
            _range_check("attack_angle_deg", "Attack angle", m["attack_angle_deg"], 55, None, 0.25, "°", 20,
                         "Hit further in front so the shuttle goes steeply down."),
            _range_check("pronation_proxy_deg_s", "Forearm snap", m["pronation_proxy_deg_s"], 400, None, 0.25, "°/s", 300,
                         "Snap the forearm through contact."),
            _range_check("follow_through_trunk_deg", "Forward fold", a["follow_through_trunk_deg"], 15, None, 0.25, "°", 15,
                         "Fold forward through the shot to finish the kinetic chain."),
        ]
    if stroke == "net_lunge_defense":
        return [
            _range_check("loading_knee_deg", "Lead knee", a["loading_knee_deg"], 100, 135, 0.3, "°", 25,
                         "Lunge to a 100-135° lead knee."),
            _range_check("lowest_hip_ratio", "Hip height", m["lowest_hip_ratio"], None, 0.55, 0.2, "", 0.15,
                         "Sink your hips to lower your centre of gravity."),
            _range_check("impact_trunk_deg", "Trunk lean", a["impact_trunk_deg"], None, 25, 0.3, "°", 20,
                         "Keep your chest up instead of collapsing head-down."),
            _range_check("recovery_ms", "Recovery", m["recovery_ms"] / 1000.0, None, 1.2, 0.2, "s", 0.8,
                         "Push back to base faster off the lead leg."),
        ]
    if stroke == "forehand_topspin":
        return [
            _range_check("prep_coil_deg", "Unit turn", a["prep_coil_deg"], 30, None, 0.25, "°", 25,
                         "Turn shoulders past your hips early in the take-back."),
            _flag_check("racket_drop", "Low-to-high path", bool(m["racket_drop"]), 0.2,
                        "No racket drop: let the hitting hand fall below your hip before swinging up."),
            _range_check("contact_space_bh", "Contact space", m["contact_space_bh"], 0.25, None, 0.25, " body heights",
                         0.15, "Make contact further in front of your lead hip."),
            _flag_check("follow_through_high", "High finish", bool(m["follow_through_high"]), 0.15,
                        "Finish over your shoulder with a windshield-wiper follow-through."),
            _range_check("impact_elbow_deg", "Elbow at contact", a["impact_elbow_deg"], elbow_target or 140, None, 0.15,
                         "°", 20, "Give the arm space instead of jamming the elbow."),
        ]
    if stroke in ("one_handed_backhand", "two_handed_backhand"):
        one = stroke == "one_handed_backhand"
        return [
            _range_check("impact_elbow_deg", "Elbow at contact", a["impact_elbow_deg"],
                         (elbow_target or 165) if one else 140, None, 0.35, "°", 20,
                         "Firm, straight hitting arm at contact." if one else "Keep both arms long through contact."),
            _range_check("prep_coil_deg", "Shoulder coil", a["prep_coil_deg"], 30, None, 0.25, "°", 25,
                         "Turn your back shoulder to the net on the take-back."),
            _range_check("trunk_lean_deg", "Balanced finish", m["min_trunk_lean_back_deg"], None, 20, 0.2, "°", 20,
                         "Stay tall at the finish instead of falling backwards."),
            _range_check("balance_score", "Balance", a["balance_score"], 0.7, None, 0.2, "", 0.3,
                         "Set your feet before you swing."),
        ]
    if stroke == "first_serve":
        return [
            _range_check("loading_knee_deg", "Trophy knee bend", a["loading_knee_deg"], None, 160, 0.2, "°", 20,
                         "Bend your knees in the trophy pose to load the legs."),
            _range_check("toss_arm_vertical_deg", "Tossing arm", m["toss_arm_vertical_deg"], None, 25, 0.2, "°", 25,
                         "Point the tossing arm straight up at the ball."),
            _range_check("reach_ratio", "Reach at contact", a["reach_ratio"], 1.15, None, 0.25, "x head height", 0.15,
                         "Reach up and hit at full height."),
            _range_check("impact_elbow_deg", "Elbow at contact", a["impact_elbow_deg"], elbow_target or 165, None, 0.2,
                         "°", 15, "Extend fully at contact."),
            _range_check("pronation_proxy_deg_s", "Pronation snap", m["pronation_proxy_deg_s"], 400, None, 0.15, "°/s",
                         300, "Snap the forearm over through contact."),
        ]
    return [_range_check("balance_score", "Balance", a["balance_score"], 0.7, None, 1.0, "", 0.3, "Stay balanced.")]


def grade_rep(rep: CompletedRep, elbow_target: Optional[float] = None, min_counted_quality: int = 60) -> CompletedRep:
    """Score the rep against the *target* stroke's archetype (or what was detected if there's no target)."""
    stroke = rep.target_stroke or rep.detected_stroke
    checks = archetype_checks(stroke, rep.phase_angles, rep.metrics, elbow_target)
    penalty = sum(c.weight * min(1.0, c.gap) for c in checks)
    rep.quality_score = int(round(max(0.0, min(100.0, 100.0 * (1.0 - penalty)))))
    worst = max((c for c in checks if not c.ok), key=lambda c: c.weight * min(1.0, c.gap), default=None)
    rep.stroke_matches_target = rep.target_stroke is None or rep.detected_stroke == rep.target_stroke or (
        rep.detected_stroke in OVERHEAD_STROKES and rep.target_stroke in OVERHEAD_STROKES and rep.target_stroke != "first_serve")
    rep.primary_deviation = worst.message if worst else None
    if not rep.stroke_matches_target:
        rep.primary_deviation = (f"That looked like a {STROKE_LABELS.get(rep.detected_stroke, rep.detected_stroke)}, "
                                 f"not a {STROKE_LABELS.get(stroke, stroke)}.")
    rep.checks = [asdict(c) for c in checks]
    rep.rep_counted = rep.stroke_matches_target and rep.quality_score >= min_counted_quality
    return rep


# ---------------------------------------------------------------------------
# Session analysis: drift, heart-rate correlation, combo sequence
# ---------------------------------------------------------------------------

FATIGUE_HR_BPM = 165.0


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def session_analysis(reps: List[CompletedRep], sequence: Optional[List[str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"reps": len(reps), "counted_reps": sum(r.rep_counted for r in reps),
                           "mean_quality": round(_avg([r.quality_score for r in reps]), 1) if reps else None,
                           "drift": None, "fatigue_correlated": False, "sequence_compliance": None}
    if len(reps) >= 6:
        first, last = reps[:3], reps[-3:]
        def mean(rs: List[CompletedRep], key: str) -> float:
            return _avg([r.phase_angles[key] for r in rs])
        height_drop = (mean(first, "reach_ratio") - mean(last, "reach_ratio")) / max(1e-6, mean(first, "reach_ratio"))
        knee_loss = mean(last, "loading_knee_deg") - mean(first, "loading_knee_deg")  # bigger angle = less bend
        elbow_drop = mean(first, "impact_elbow_deg") - mean(last, "impact_elbow_deg")
        quality_drop = _avg([r.quality_score for r in first]) - _avg([r.quality_score for r in last])
        signals = []
        if height_drop >= 0.05:
            signals.append(f"contact height has dropped {height_drop * 100:.0f}%")
        if knee_loss >= 8:
            signals.append(f"knee bend decreased by {knee_loss:.0f}°")
        if elbow_drop >= 6:
            signals.append(f"elbow extension dropped {elbow_drop:.0f}°")
        drifting = bool(signals) or quality_drop >= 10
        advice = ("your legs are getting tired, so bend lower instead of reaching with your arm"
                  if knee_loss >= 8 else "take a short break and reset your form")
        out["drift"] = {
            "detected": drifting, "contact_height_drop_pct": round(height_drop * 100, 1),
            "knee_bend_loss_deg": round(knee_loss, 1), "elbow_drop_deg": round(elbow_drop, 1),
            "quality_drop": round(quality_drop, 1),
            "message": (f"Your {' and '.join(signals) or 'rep quality has dropped'} over the last {len(last)} reps: "
                        f"{advice}.") if drifting else None,
        }
        hot = [r.heart_rate for r in last if r.heart_rate is not None]
        out["fatigue_correlated"] = bool(drifting and hot and _avg(hot) > FATIGUE_HR_BPM)
    if sequence:
        expected = [sequence[i % len(sequence)] for i in range(len(reps))]
        hits = sum(r.detected_stroke == e or (e in OVERHEAD_STROKES and r.detected_stroke in OVERHEAD_STROKES
                                              and e != "first_serve") for r, e in zip(reps, expected))
        out["sequence_compliance"] = {"sequence": sequence, "matched": hits,
                                      "ratio": round(hits / len(reps), 2) if reps else None,
                                      "next_expected": sequence[len(reps) % len(sequence)]}
    return out


def analyse_frames(frames: List[Tuple[int, Sequence[Sequence[float]], Optional[Sequence[Sequence[float]]]]],
                   sport: Optional[str], target_stroke: Optional[str], aspect: float = 0.75) -> Dict[str, Any]:
    """Run the tracker over a recorded clip: [(t_ms, image_landmarks, world_landmarks|None), ...]."""
    side = detect_side([f[1] for f in frames], aspect)
    tracker = RepTracker(target_stroke=target_stroke, sport=sport, side=side)
    for t_ms, image, world in frames:
        tracker.feed(frame_features(image, t_ms, side, aspect, world))
    # A clip often ends mid-follow-through; close the last rep if it reached impact.
    if tracker.phase in ("IMPACT", "FOLLOW_THROUGH"):
        tracker._complete(None)
    return {"side": side, "reps": tracker.reps, "session": session_analysis(tracker.reps)}
