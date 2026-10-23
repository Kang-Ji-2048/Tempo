"""
db_mongo.py - MongoDB Atlas Vector Search & Session Persistence (Taha)
Connects via MONGODB_URI to the `badminton_coach` database (`strokes` and `players` collections),
seeds pro reference strokes (Viktor Axelsen & Lee Zii Jia) with `is_pro_reference: True` and 6D `pose_vector`
plus a London training partner document in `players`, and implements `find_closest_pro_pose(user_pose_vector)`
using MongoDB Atlas `$vectorSearch` (index: `pose_vector_index`, path: `pose_vector`) with a Python
cosine-similarity fallback if the Atlas index isn't built yet.
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
        "reference_id": "pro_viktor_axelsen_smash",
        "player_name": "Viktor Axelsen",
        "country": "DEN",
        "stroke_type": "Overhead Jump Smash",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 175.0,
        "right_shoulder_abduction_deg": 168.0,
        "trunk_arch_deg": 172.0,
        "right_knee_flexion_deg": 164.0,
        "left_arm_balance_deg": 145.0,
        "contact_height_norm": 0.94,
        "pose_vector": [
            round(175.0 / 180.0, 4),
            round(168.0 / 180.0, 4),
            round(172.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(145.0 / 180.0, 4),
            0.94,
        ],
        "biomechanical_notes": (
            "Steepest overhead contact point on tour; near-full elbow extension (175.0 deg) "
            "with explosive core bow-and-arrow trunk arch and high non-racket arm counter-balance."
        ),
    },
    {
        "reference_id": "pro_lee_zii_jia_smash",
        "player_name": "Lee Zii Jia",
        "country": "MAS",
        "stroke_type": "Backhand & Forehand Whip Smash",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 171.0,
        "right_shoulder_abduction_deg": 164.0,
        "trunk_arch_deg": 169.0,
        "right_knee_flexion_deg": 158.0,
        "left_arm_balance_deg": 140.0,
        "contact_height_norm": 0.91,
        "pose_vector": [
            round(171.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(169.0 / 180.0, 4),
            round(158.0 / 180.0, 4),
            round(140.0 / 180.0, 4),
            0.91,
        ],
        "biomechanical_notes": (
            "Whip-like kinetic chain transfer with 171.0 deg elbow extension at shuttle impact, "
            "generating extreme shuttle velocity through rapid forearm pronation."
        ),
    },
]

SEED_LONDON_PARTNERS: List[Dict[str, Any]] = [
    {
        "player_id": "partner_london_finsbury_01",
        "name": "Arjun Mehta",
        "city": "London",
        "preferred_venue": "Finsbury Leisure Centre (EC1V)",
        "skill_level": "Advanced Club / County",
        "focus_area": "Overhead Rear-Court Clear & Jump Smash Consistency",
        "availability": "Tonight 20:00 - 22:00 BST",
        "target_pose_vector": [0.94, 0.90, 0.93, 0.88, 0.78, 0.89],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_ethos_02",
        "name": "Chloe Tan",
        "city": "London",
        "preferred_venue": "Ethos Sports Centre - Imperial College (SW7)",
        "skill_level": "Intermediate-Advanced",
        "focus_area": "High-Contact Overhead Biomechanics & Footwork Recovery",
        "availability": "Tomorrow 18:30 - 20:00 BST",
        "target_pose_vector": [0.92, 0.88, 0.91, 0.86, 0.76, 0.87],
        "is_training_partner": True,
    },
]

# In-memory store so the pipeline works seamlessly even if MONGODB_URI is not reachable locally
_MEMORY_STROKES: List[Dict[str, Any]] = [dict(doc) for doc in PRO_REFERENCE_STROKES]
_MEMORY_PLAYERS: List[Dict[str, Any]] = [dict(doc) for doc in SEED_LONDON_PARTNERS]
_MEMORY_APPROVALS: Dict[str, Dict[str, Any]] = {}

_CLIENT: Optional[MongoClient] = None


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


def seed_reference_data() -> Dict[str, Any]:
    """
    Seed Viktor Axelsen (`right_elbow_contact_deg: 175.0`) and Lee Zii Jia (`171.0`)
    into `badminton_coach.strokes` with `is_pro_reference: True` and 6D `pose_vector`,
    plus London training partner documents in `badminton_coach.players`.
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
    Match `user_pose_vector` against pro badminton reference strokes using MongoDB Atlas
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
                        "numCandidates": 10,
                        "limit": 2,
                        "filter": {"is_pro_reference": True},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "reference_id": 1,
                        "player_name": 1,
                        "country": 1,
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
    Find a recommended badminton training partner in `players` collection (defaults to London).
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
