"""Synthetic but geometric MediaPipe-style pose sequences for kinematic tests.

Each stroke is a list of keyframes (joint positions in normalized image coords, aspect 1.0) that are
linearly interpolated at the requested frame rate. Arms are placed by exact elbow angles so measured
angles are known; shoulder depth (z) creates torso coil.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
BASE: Dict[str, Tuple[float, float, float]] = {
    "nose": (0.50, 0.20, 0.0), "l_sh": (0.45, 0.30, 0.0), "r_sh": (0.55, 0.30, 0.0),
    "l_el": (0.42, 0.42, 0.0), "r_el": (0.58, 0.42, 0.0), "l_wr": (0.41, 0.52, 0.0), "r_wr": (0.60, 0.52, 0.0),
    "l_hip": (0.47, 0.55, 0.0), "r_hip": (0.53, 0.55, 0.0), "l_kn": (0.47, 0.72, 0.0), "r_kn": (0.53, 0.72, 0.0),
    "l_an": (0.47, 0.90, 0.0), "r_an": (0.53, 0.90, 0.0),
}
INDEX = {"nose": 0, "l_sh": 11, "r_sh": 12, "l_el": 13, "r_el": 14, "l_wr": 15, "r_wr": 16,
         "l_hip": 23, "r_hip": 24, "l_kn": 25, "r_kn": 26, "l_an": 27, "r_an": 28}


def arm(shoulder: Tuple[float, float, float], upper_dir_deg: float, elbow_deg: float,
        upper: float = 0.13, fore: float = 0.13, bend_sign: float = 1.0):
    """Elbow + wrist for an upper arm pointing `upper_dir_deg` (0 = +x, -90 = up) with an exact elbow angle."""
    a = math.radians(upper_dir_deg)
    el = (shoulder[0] + upper * math.cos(a), shoulder[1] + upper * math.sin(a), shoulder[2])
    b = a + bend_sign * math.radians(180.0 - elbow_deg)
    wr = (el[0] + fore * math.cos(b), el[1] + fore * math.sin(b), shoulder[2])
    return el, wr


def leg(hip: Tuple[float, float, float], knee_deg: float, thigh: float = 0.17, shin: float = 0.18,
        lean_deg: float = 0.0):
    a = math.radians(90.0 + lean_deg)
    kn = (hip[0] + thigh * math.cos(a), hip[1] + thigh * math.sin(a), hip[2])
    b = a - math.radians(180.0 - knee_deg)
    an = (kn[0] + shin * math.cos(b), kn[1] + shin * math.sin(b), hip[2])
    return kn, an


def pose(**joints) -> Dict[str, Tuple[float, float, float]]:
    out = dict(BASE)
    out.update(joints)
    return out


def landmarks(p: Dict[str, Tuple[float, float, float]], visibility: float = 0.99) -> List[List[float]]:
    lm = [[p["nose"][0], p["nose"][1], 0.0, visibility] for _ in range(33)]
    for name, idx in INDEX.items():
        x, y, z = p[name]
        lm[idx] = [x, y, z, visibility]
    return lm


def interpolate(keys: Sequence[Tuple[float, Dict[str, Tuple[float, float, float]]]], fps: float = 15.0,
                start_ms: int = 0) -> List[Tuple[int, List[List[float]]]]:
    """keys: [(duration_s_to_reach_this_pose, pose), ...]; the first entry's duration is a hold."""
    frames: List[Tuple[int, List[List[float]]]] = []
    t = 0.0
    prev = keys[0][1]
    for duration, target in keys:
        steps = max(1, int(round(duration * fps)))
        for s in range(1, steps + 1):
            k = s / steps
            mix = {n: tuple(prev[n][i] + (target[n][i] - prev[n][i]) * k for i in range(3)) for n in target}
            t += 1.0 / fps
            frames.append((start_ms + int(round(t * 1000)), landmarks(mix)))
        prev = target
    return frames


def _coiled(p, depth: float):
    """Turn the shoulders: push one shoulder forward in depth to create a top-down coil angle."""
    l, r = p["l_sh"], p["r_sh"]
    p["l_sh"], p["r_sh"] = (l[0], l[1], depth), (r[0], r[1], -depth)
    return p


def overhead_clear(elbow_at_contact: float = 172.0, knee_load: float = 140.0, coil: float = 0.06,
                   jump: float = 0.0) -> List[Tuple[float, Dict]]:
    ready = pose()
    sh = BASE["r_sh"]
    el, wr = arm(sh, -60, 95)
    prep = _coiled(pose(r_el=el, r_wr=wr), coil)
    kn, an = leg(BASE["r_hip"], knee_load)
    el, wr = arm(sh, -100, 70, bend_sign=-1)
    load = _coiled(pose(r_el=el, r_wr=wr, r_kn=kn, r_an=an), coil)
    lift = (0.0, -jump, 0.0)
    el, wr = arm(sh, -85, elbow_at_contact)
    up = {n: (v[0] + lift[0], v[1] + lift[1], v[2]) for n, v in pose(r_el=el, r_wr=wr).items()}
    el, wr = arm(sh, 110, 160)
    follow = pose(r_el=el, r_wr=(0.44, 0.58, 0.0))
    # The racket hand is fastest into contact; the follow-through decelerates.
    return [(0.6, ready), (0.35, prep), (0.3, load), (0.1, up), (0.4, follow), (0.6, ready)]


def forehand(drop: bool = True, contact_x: float = 0.70, high_finish: bool = True, coil: float = 0.08):
    ready = pose()
    take = _coiled(pose(r_el=(0.70, 0.40, 0.0), r_wr=(0.80, 0.45, 0.0)), coil)
    load = _coiled(pose(r_el=(0.70, 0.48, 0.0), r_wr=(0.78, 0.66 if drop else 0.45, 0.0)), coil)
    hit = pose(r_el=(0.64, 0.40, 0.0), r_wr=(contact_x, 0.47, 0.0))
    finish = pose(r_el=(0.45, 0.26, 0.0), r_wr=(0.36, 0.16 if high_finish else 0.50, 0.0))
    # Contact is the fastest moment of a real groundstroke: short approach, slower finish.
    return [(0.6, ready), (0.4, take), (0.25, load), (0.07, hit), (0.4, finish), (0.6, ready)]


def one_handed_backhand(elbow_at_contact: float = 172.0, coil: float = 0.08):
    ready = pose()
    take = _coiled(pose(r_el=(0.40, 0.40, 0.0), r_wr=(0.30, 0.45, 0.0)), coil)
    load = _coiled(pose(r_el=(0.40, 0.46, 0.0), r_wr=(0.30, 0.58, 0.0)), coil)
    el, wr = arm(BASE["r_sh"], 170, elbow_at_contact)
    hit = pose(r_el=el, r_wr=wr)
    finish = pose(r_el=(0.68, 0.24, 0.0), r_wr=(0.78, 0.15, 0.0))
    return [(0.6, ready), (0.4, take), (0.25, load), (0.07, hit), (0.4, finish), (0.6, ready)]


def lunge(knee_deg: float = 120.0, hip_drop: float = 0.12, lean_deg: float = 10.0, recover_s: float = 0.6):
    ready = pose()
    shift = (0.10, hip_drop)
    deep = {n: (v[0] + shift[0] * (n not in ("l_an", "l_kn")), v[1] + shift[1] * (n not in ("l_an", "r_an", "l_kn")), v[2])
            for n, v in pose().items()}
    kn, an = leg(deep["r_hip"], knee_deg)
    deep["r_kn"], deep["r_an"] = kn, (an[0], 0.90, 0.0)
    lean = math.tan(math.radians(lean_deg)) * (deep["r_hip"][1] - deep["r_sh"][1])
    for n in ("nose", "l_sh", "r_sh", "l_el", "r_el", "l_wr", "r_wr"):
        v = deep[n]
        deep[n] = (v[0] + lean, v[1], v[2])
    step = {n: tuple(ready[n][i] + (deep[n][i] - ready[n][i]) * 0.5 for i in range(3)) for n in ready}
    return [(0.6, ready), (0.3, step), (0.3, deep), (recover_s, ready), (0.6, ready)]


def sequence(*strokes, fps: float = 15.0, gap_s: float = 0.0) -> List[Tuple[int, List[List[float]]]]:
    frames: List[Tuple[int, List[List[float]]]] = []
    t = 0
    for keys in strokes:
        part = interpolate(keys, fps, t)
        frames.extend(part)
        t = part[-1][0] + int(gap_s * 1000)
    return frames


def mirror(frames):
    """Left-handed version: flip x and swap left/right landmark slots."""
    swap = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23, 25: 26, 26: 25, 27: 28, 28: 27}
    out = []
    for t, lm in frames:
        flipped = [[1.0 - p[0], p[1], p[2], p[3]] for p in lm]
        out.append((t, [flipped[swap.get(i, i)] for i in range(33)]))
    return out
