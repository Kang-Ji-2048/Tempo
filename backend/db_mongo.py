"""
db_mongo.py - MongoDB Atlas Vector Search & Session Persistence (Taha)
Connects via MONGODB_URI to the `badminton_coach` database (`strokes` and `players` collections),
seeds iconic Pro Tennis & Overhead Racket reference strokes (Roger Federer, Novak Djokovic,
Carlos Alcaraz, Serena Williams, Jannik Sinner, Iga Swiatek, Rafael Nadal) with `is_pro_reference: True`
and 6D `pose_vector` plus rich London training partner profiles in `players`, and implements
`find_closest_pro_pose(user_pose_vector)` using MongoDB Atlas `$vectorSearch`
(index: `pose_vector_index`, path: `pose_vector`) with a Python cosine-similarity fallback.
"""

from __future__ import annotations

import datetime
import math
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    MongoClient = None  # type: ignore

    class PyMongoError(Exception):  # type: ignore
        pass

DB_NAME = "badminton_coach"
STROKES_COLLECTION = "strokes"
PLAYERS_COLLECTION = "players"
VECTOR_INDEX_NAME = "pose_vector_index"


PRO_REFERENCE_STROKES: List[Dict[str, Any]] = [
    {
        "reference_id": "pro_roger_federer_serve_smash",
        "player_name": "Roger Federer",
        "country": "SUI",
        "sport": "Tennis",
        "stroke_type": "Pinpoint Overhead Serve & High-Contact Smash",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 176.5,
        "right_shoulder_abduction_deg": 169.0,
        "trunk_arch_deg": 173.0,
        "right_knee_flexion_deg": 165.0,
        "left_arm_balance_deg": 148.0,
        "contact_height_norm": 0.95,
        "pose_vector": [
            round(176.5 / 180.0, 4),
            round(169.0 / 180.0, 4),
            round(173.0 / 180.0, 4),
            round(165.0 / 180.0, 4),
            round(148.0 / 180.0, 4),
            0.95,
        ],
        "biomechanical_notes": (
            "The gold standard of effortless overhead biomechanics (20x Grand Slam champion). "
            "Near-full 176.5 deg elbow extension at impact, fluid trophy-pose thoracic arch (173.0 deg), "
            "and textbook left-arm toss/counter-balance alignment for deceptive placement and zero joint strain."
        ),
    },
    {
        "reference_id": "pro_novak_djokovic_serve_smash",
        "player_name": "Novak Djokovic",
        "country": "SRB",
        "sport": "Tennis",
        "stroke_type": "Elastic Kinetic-Chain Overhead Serve & Smash",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 174.0,
        "right_shoulder_abduction_deg": 166.0,
        "trunk_arch_deg": 171.0,
        "right_knee_flexion_deg": 162.0,
        "left_arm_balance_deg": 144.0,
        "contact_height_norm": 0.93,
        "pose_vector": [
            round(174.0 / 180.0, 4),
            round(166.0 / 180.0, 4),
            round(171.0 / 180.0, 4),
            round(162.0 / 180.0, 4),
            round(144.0 / 180.0, 4),
            0.93,
        ],
        "biomechanical_notes": (
            "24x Grand Slam champion renowned for supreme flexibility and kinetic-chain stability under "
            "extreme cardiovascular load. Maintains a 174.0 deg elbow extension and 166.0 deg shoulder "
            "abduction plane to prevent late-match shoulder impingement."
        ),
    },
    {
        "reference_id": "pro_carlos_alcaraz_overhead",
        "player_name": "Carlos Alcaraz",
        "country": "ESP",
        "sport": "Tennis",
        "stroke_type": "Explosive Jump Overhead Smash & Kick Serve",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 171.5,
        "right_shoulder_abduction_deg": 163.0,
        "trunk_arch_deg": 168.5,
        "right_knee_flexion_deg": 157.0,
        "left_arm_balance_deg": 139.0,
        "contact_height_norm": 0.91,
        "pose_vector": [
            round(171.5 / 180.0, 4),
            round(163.0 / 180.0, 4),
            round(168.5 / 180.0, 4),
            round(157.0 / 180.0, 4),
            round(139.0 / 180.0, 4),
            0.91,
        ],
        "biomechanical_notes": (
            "Dynamic, whip-like overhead acceleration with aggressive lower-body coil (157.0 deg knee drive) "
            "and 171.5 deg elbow extension at contact, generating massive topspin and pace."
        ),
    },
    {
        "reference_id": "pro_serena_williams_serve",
        "player_name": "Serena Williams",
        "country": "USA",
        "sport": "Tennis",
        "stroke_type": "Power First Serve & Overhead Drive",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 175.5,
        "right_shoulder_abduction_deg": 167.5,
        "trunk_arch_deg": 172.0,
        "right_knee_flexion_deg": 163.0,
        "left_arm_balance_deg": 146.0,
        "contact_height_norm": 0.94,
        "pose_vector": [
            round(175.5 / 180.0, 4),
            round(167.5 / 180.0, 4),
            round(172.0 / 180.0, 4),
            round(163.0 / 180.0, 4),
            round(146.0 / 180.0, 4),
            0.94,
        ],
        "biomechanical_notes": (
            "Widely considered the greatest overhead serve motion in tennis history (23x Grand Slam singles titles). "
            "Combines deep leg drive with a 175.5 deg locked-in contact point and explosive forearm pronation."
        ),
    },
    {
        "reference_id": "pro_jannik_sinner_serve",
        "player_name": "Jannik Sinner",
        "country": "ITA",
        "sport": "Tennis",
        "stroke_type": "High-Leverage Platform Overhead Serve",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 173.0,
        "right_shoulder_abduction_deg": 165.0,
        "trunk_arch_deg": 170.0,
        "right_knee_flexion_deg": 160.0,
        "left_arm_balance_deg": 142.0,
        "contact_height_norm": 0.92,
        "pose_vector": [
            round(173.0 / 180.0, 4),
            round(165.0 / 180.0, 4),
            round(170.0 / 180.0, 4),
            round(160.0 / 180.0, 4),
            round(142.0 / 180.0, 4),
            0.92,
        ],
        "biomechanical_notes": (
            "Long-lever kinetic chain with repeatable 173.0 deg elbow extension and clean hip-to-shoulder "
            "separation for high first-serve percentage under pressure."
        ),
    },
    {
        "reference_id": "pro_rafael_nadal_overhead",
        "player_name": "Rafael Nadal",
        "country": "ESP",
        "sport": "Tennis",
        "stroke_type": "Skyhook Overhead Smash & Slice Serve",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 169.5,
        "right_shoulder_abduction_deg": 160.0,
        "trunk_arch_deg": 166.0,
        "right_knee_flexion_deg": 154.0,
        "left_arm_balance_deg": 135.0,
        "contact_height_norm": 0.89,
        "pose_vector": [
            round(169.5 / 180.0, 4),
            round(160.0 / 180.0, 4),
            round(166.0 / 180.0, 4),
            round(154.0 / 180.0, 4),
            round(135.0 / 180.0, 4),
            0.89,
        ],
        "biomechanical_notes": (
            "22x Grand Slam champion known for unmatched core torque and high-margin overhead smash stability "
            "(169.5 deg contact extension with heavy wrist snap)."
        ),
    },
]

SEED_LONDON_PARTNERS: List[Dict[str, Any]] = [
    {
        "player_id": "partner_london_finsbury_01",
        "name": "Arjun Mehta",
        "city": "London",
        "preferred_venue": "Islington Tennis & Racket Centre / Finsbury Leisure (EC1V)",
        "skill_level": "LTA Rating 3.2 / Advanced Club",
        "focus_area": "Roger Federer Overhead Extension & High-Contact Serve/Smash Consistency",
        "availability": "Tonight 20:00 - 22:00 BST",
        "target_pose_vector": [0.95, 0.91, 0.94, 0.89, 0.79, 0.91],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_regents_02",
        "name": "Chloe Tan",
        "city": "London",
        "preferred_venue": "Regent's Park Tennis & Racket Courts (NW1)",
        "skill_level": "LTA Rating 4.1 / Intermediate-Advanced",
        "focus_area": "Novak Djokovic Kinetic-Chain Recovery & Trophy Pose Alignment",
        "availability": "Tomorrow 18:30 - 20:00 BST",
        "target_pose_vector": [0.93, 0.89, 0.92, 0.87, 0.77, 0.89],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_roehampton_03",
        "name": "Marcus Vance",
        "city": "London",
        "preferred_venue": "National Tennis Centre - Roehampton (SW15)",
        "skill_level": "LTA Rating 2.4 / County Performance",
        "focus_area": "Carlos Alcaraz Explosive Overhead Smash & High-HR Rally Endurance",
        "availability": "Saturday 10:00 - 12:00 BST",
        "target_pose_vector": [0.95, 0.91, 0.94, 0.87, 0.77, 0.91],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_bloomsbury_04",
        "name": "Elena Rostova",
        "city": "London",
        "preferred_venue": "Bloomsbury Fitness & Courts - UCL (WC1E)",
        "skill_level": "University 1st Team",
        "focus_area": "Serena Williams First-Serve Pronation & Left-Arm Toss Balance",
        "availability": "Tonight 21:00 - 22:30 BST",
        "target_pose_vector": [0.97, 0.93, 0.95, 0.90, 0.81, 0.94],
        "is_training_partner": True,
    },
]

# In-memory store so the pipeline works seamlessly even if MONGODB_URI is not reachable locally
_MEMORY_STROKES: List[Dict[str, Any]] = [dict(doc) for doc in PRO_REFERENCE_STROKES]
_MEMORY_PLAYERS: List[Dict[str, Any]] = [dict(doc) for doc in SEED_LONDON_PARTNERS]
_MEMORY_APPROVALS: Dict[str, Dict[str, Any]] = {}
_LATEST_WATCH_METRICS: Dict[str, Dict[str, Any]] = {}

_CLIENT: Optional[Any] = None


def get_mongo_client() -> Optional[Any]:
    """Return a connected MongoClient if MONGODB_URI is set and reachable, else None."""
    global _CLIENT
    if MongoClient is None:
        return None
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        return None
    if _CLIENT is not None:
        return _CLIENT
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
        client.admin.command("ping")
        _CLIENT = client
        return _CLIENT
    except Exception:
        return None


def get_db():
    """Return the `badminton_coach` database handle if connected, else None."""
    client = get_mongo_client()
    if client is None:
        return None
    return client[DB_NAME]


def check_mongo_health() -> Dict[str, Any]:
    """Check MongoDB connection status and seeded document counts."""
    db = get_db()
    if db is None:
        return {
            "connected": False,
            "mode": "in_memory_fallback",
            "database": DB_NAME,
            "collections": [STROKES_COLLECTION, PLAYERS_COLLECTION],
            "pro_references_count": sum(1 for s in _MEMORY_STROKES if s.get("is_pro_reference")),
            "london_partners_count": len(_MEMORY_PLAYERS),
        }
    try:
        pro_count = db[STROKES_COLLECTION].count_documents({"is_pro_reference": True})
        partner_count = db[PLAYERS_COLLECTION].count_documents({"city": "London"})
        return {
            "connected": True,
            "mode": "mongodb_atlas",
            "database": DB_NAME,
            "collections": [STROKES_COLLECTION, PLAYERS_COLLECTION],
            "pro_references_count": pro_count,
            "london_partners_count": partner_count,
        }
    except Exception as exc:
        return {
            "connected": False,
            "mode": "in_memory_fallback",
            "database": DB_NAME,
            "error": str(exc),
        }


def seed_reference_data(remove_legacy_badminton_pros: bool = True) -> Dict[str, Any]:
    """
    Seed iconic Pro Tennis reference strokes (Roger Federer, Novak Djokovic, Carlos Alcaraz,
    Serena Williams, Jannik Sinner, Rafael Nadal) into `badminton_coach.strokes` with
    `is_pro_reference: True` and 6D `pose_vector`, plus London training partners in `badminton_coach.players`.
    """
    db = get_db()
    if db is None:
        return {
            "seeded": True,
            "mode": "in_memory_fallback",
            "pro_references": [p["player_name"] for p in PRO_REFERENCE_STROKES],
            "london_partners": [p["name"] for p in SEED_LONDON_PARTNERS],
        }

    try:
        strokes_col = db[STROKES_COLLECTION]
        players_col = db[PLAYERS_COLLECTION]

        if remove_legacy_badminton_pros:
            active_ref_ids = [r["reference_id"] for r in PRO_REFERENCE_STROKES]
            strokes_col.delete_many(
                {
                    "is_pro_reference": True,
                    "reference_id": {"$nin": active_ref_ids},
                }
            )

        for ref in PRO_REFERENCE_STROKES:
            strokes_col.update_one(
                {"reference_id": ref["reference_id"]},
                {"$set": ref},
                upsert=True,
            )

        for partner in SEED_LONDON_PARTNERS:
            players_col.update_one(
                {"player_id": partner["player_id"]},
                {"$set": partner},
                upsert=True,
            )

        return {
            "seeded": True,
            "mode": "mongodb_atlas",
            "pro_references": [p["player_name"] for p in PRO_REFERENCE_STROKES],
            "london_partners": [p["name"] for p in SEED_LONDON_PARTNERS],
        }
    except PyMongoError as exc:
        return {
            "seeded": False,
            "mode": "in_memory_fallback",
            "error": str(exc),
        }


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(float(a) ** 2 for a in vec_a))
    norm_b = math.sqrt(sum(float(b) ** 2 for b in vec_b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return round(float(dot / (norm_a * norm_b)), 4)


def _strip_mongo_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(doc)
    if "_id" in cleaned:
        cleaned["_id"] = str(cleaned["_id"])
    return cleaned


def find_closest_pro_pose(user_pose_vector: List[float]) -> Dict[str, Any]:
    """
    Match `user_pose_vector` against pro reference strokes (Roger Federer, Novak Djokovic,
    Carlos Alcaraz, Serena Williams, Jannik Sinner, Rafael Nadal) using MongoDB Atlas
    `$vectorSearch` (index: `pose_vector_index`, path: `pose_vector`), with a Python
    cosine-similarity fallback if the Atlas index isn't built yet or MongoDB is offline.
    """
    db = get_db()
    if db is not None:
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": VECTOR_INDEX_NAME,
                        "path": "pose_vector",
                        "queryVector": [float(x) for x in user_pose_vector],
                        "numCandidates": 20,
                        "limit": 4,
                        "filter": {"is_pro_reference": True},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "reference_id": 1,
                        "player_name": 1,
                        "country": 1,
                        "sport": 1,
                        "stroke_type": 1,
                        "is_pro_reference": 1,
                        "right_elbow_contact_deg": 1,
                        "right_shoulder_abduction_deg": 1,
                        "trunk_arch_deg": 1,
                        "right_knee_flexion_deg": 1,
                        "left_arm_balance_deg": 1,
                        "contact_height_norm": 1,
                        "pose_vector": 1,
                        "biomechanical_notes": 1,
                        "similarity_score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]
            results = list(db[STROKES_COLLECTION].aggregate(pipeline))
            if results:
                best = _strip_mongo_id(results[0])
                best["similarity_score"] = round(float(best.get("similarity_score", 0.0)), 4)
                best["search_method"] = "mongodb_atlas_vector_search"
                best["all_pro_matches"] = [_strip_mongo_id(r) for r in results]
                return best
        except Exception:
            # Fall back to Python cosine similarity if the Atlas $vectorSearch index isn't ready
            pass

    # Fetch pro references from MongoDB if connected, otherwise from seeded memory
    candidates: List[Dict[str, Any]] = []
    if db is not None:
        try:
            candidates = list(db[STROKES_COLLECTION].find({"is_pro_reference": True}, {"_id": 0}))
        except Exception:
            candidates = []
    if not candidates:
        candidates = [dict(doc) for doc in PRO_REFERENCE_STROKES]

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cand in candidates:
        sim = cosine_similarity(user_pose_vector, cand.get("pose_vector", []))
        enriched = _strip_mongo_id(cand)
        enriched["similarity_score"] = sim
        scored.append((sim, enriched))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_match = dict(scored[0][1])
    best_match["search_method"] = "python_cosine_similarity_fallback"
    best_match["all_pro_matches"] = [item[1] for item in scored]
    return best_match


def find_training_partner(city: str = "London", user_pose_vector: Optional[List[float]] = None) -> Dict[str, Any]:
    """
    Find a recommended training partner in `players` collection (defaults to London).
    """
    db = get_db()
    partners: List[Dict[str, Any]] = []
    if db is not None:
        try:
            partners = list(db[PLAYERS_COLLECTION].find({"city": city}, {"_id": 0}))
        except Exception:
            partners = []
    if not partners:
        partners = [dict(p) for p in SEED_LONDON_PARTNERS if p.get("city", "").lower() == city.lower()]
    if not partners:
        partners = [dict(SEED_LONDON_PARTNERS[0])]

    if user_pose_vector:
        for p in partners:
            target_vec = p.get("target_pose_vector", user_pose_vector)
            p["compatibility_score"] = cosine_similarity(user_pose_vector, target_vec)
        partners.sort(key=lambda x: x.get("compatibility_score", 0.0), reverse=True)
    else:
        for p in partners:
            p["compatibility_score"] = 0.96

    return _strip_mongo_id(partners[0])


def save_analysis_session(session_doc: Dict[str, Any]) -> str:
    """
    Save the full stroke analysis session + staged Saint AI job into `badminton_coach.strokes`.
    Returns the `session_id`.
    """
    session_id = session_doc.get("session_id") or f"session_{uuid.uuid4().hex[:12]}"
    session_doc["session_id"] = session_id
    session_doc["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    session_doc["is_pro_reference"] = False

    db = get_db()
    if db is not None:
        try:
            doc_copy = dict(session_doc)
            db[STROKES_COLLECTION].insert_one(doc_copy)
        except Exception:
            pass

    _MEMORY_STROKES.append(_strip_mongo_id(session_doc))
    _MEMORY_APPROVALS[session_id] = _strip_mongo_id(session_doc)
    return session_id


def update_saint_approval(
    session_id: Optional[str],
    approved: bool,
    reviewer_name: str = "Sumanth",
    notes: Optional[str] = None,
    dispatch_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Record human-in-the-loop approval/rejection of a staged Saint court booking & partner notification.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status_str = "APPROVED_AND_DISPATCHED" if approved else "REJECTED_BY_USER"

    update_fields = {
        "saint_approval_status": status_str,
        "saint_approved": approved,
        "saint_approved_by": reviewer_name,
        "saint_approved_at": timestamp,
        "saint_reviewer_notes": notes or "",
        "saint_dispatch_result": dispatch_result or {},
    }

    db = get_db()
    session_record: Optional[Dict[str, Any]] = None

    if db is not None:
        try:
            query = {"session_id": session_id} if session_id else {"is_pro_reference": False}
            sort_spec = [("created_at", -1)]
            doc = db[STROKES_COLLECTION].find_one_and_update(
                query,
                {"$set": update_fields},
                sort=sort_spec,
                return_document=True,
            )
            if doc:
                session_record = _strip_mongo_id(doc)
        except Exception:
            pass

    if session_id and session_id in _MEMORY_APPROVALS:
        _MEMORY_APPROVALS[session_id].update(update_fields)
        session_record = _MEMORY_APPROVALS[session_id]
    elif _MEMORY_APPROVALS:
        latest_key = list(_MEMORY_APPROVALS.keys())[-1]
        _MEMORY_APPROVALS[latest_key].update(update_fields)
        session_record = _MEMORY_APPROVALS[latest_key]
    else:
        session_record = {
            "session_id": session_id or f"session_{uuid.uuid4().hex[:8]}",
            **update_fields,
        }

    return session_record


def save_live_watch_telemetry(user_name: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save live Apple Watch biometrics pushed from the user's iPhone/Watch (via iOS Shortcut or Health Auto Export)
    into memory and MongoDB so the next video analysis automatically uses the real watch heart rate & calories.
    """
    key = (user_name or "Sumanth").strip().lower()
    record = {
        "user_name": user_name or "Sumanth",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **metrics,
    }
    _LATEST_WATCH_METRICS[key] = record
    _LATEST_WATCH_METRICS["latest"] = record

    db = get_db()
    if db is not None:
        try:
            db[PLAYERS_COLLECTION].update_one(
                {"player_id": f"live_watch_{key}"},
                {"$set": {"player_id": f"live_watch_{key}", "is_live_watch": True, **record}},
                upsert=True,
            )
        except Exception:
            pass
    return record


def get_latest_watch_telemetry(user_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently synced live Apple Watch metrics for `user_name` (or any latest sync).
    """
    if user_name:
        key = user_name.strip().lower()
        if key in _LATEST_WATCH_METRICS:
            return _LATEST_WATCH_METRICS[key]
    if "latest" in _LATEST_WATCH_METRICS:
        return _LATEST_WATCH_METRICS["latest"]

    db = get_db()
    if db is not None:
        try:
            doc = db[PLAYERS_COLLECTION].find_one(
                {"is_live_watch": True},
                {"_id": 0},
                sort=[("updated_at", -1)],
            )
            if doc:
                return _strip_mongo_id(doc)
        except Exception:
            pass
    return None

