"""
app/services/vector_matcher.py - MongoDB Atlas Vector Search & Cosine Similarity Kinematic Matcher
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

# Canonical reference pose archetypes across badminton and tennis
REFERENCE_POSE_ARCHETYPES: List[Dict[str, Any]] = [
    {
        "reference_id": "pro_viktor_axelsen_overhead",
        "player_name": "Viktor Axelsen",
        "country": "DEN",
        "sport": "badminton",
        "stroke_type": "overhead_clear",
        "is_pro_reference": True,
        "kinematic_vector": [
            round(175.0 / 180.0, 4),
            round(168.0 / 180.0, 4),
            round(172.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(145.0 / 180.0, 4),
            0.94,
        ],
        "biomechanical_notes": (
            "Steepest overhead contact point on tour; near-full elbow extension (175.0°) "
            "with explosive core bow-and-arrow trunk arch and high counterbalance reach."
        ),
    },
    {
        "reference_id": "pro_lee_zii_jia_smash",
        "player_name": "Lee Zii Jia",
        "country": "MAS",
        "sport": "badminton",
        "stroke_type": "jump_smash",
        "is_pro_reference": True,
        "kinematic_vector": [
            round(171.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(169.0 / 180.0, 4),
            round(158.0 / 180.0, 4),
            round(140.0 / 180.0, 4),
            0.91,
        ],
        "biomechanical_notes": (
            "Whip-like kinetic chain transfer generating extreme shuttlecock velocity through "
            "rapid forearm pronation at 171.0° contact extension."
        ),
    },
    {
        "reference_id": "fundamentals_badminton_overhead",
        "player_name": "Fundamentals Baseline",
        "country": "INT",
        "sport": "badminton",
        "stroke_type": "overhead_clear",
        "is_pro_reference": False,
        "kinematic_vector": [
            round(165.0 / 180.0, 4),
            round(155.0 / 180.0, 4),
            round(160.0 / 180.0, 4),
            round(150.0 / 180.0, 4),
            round(130.0 / 180.0, 4),
            0.85,
        ],
        "biomechanical_notes": "Standard textbook high-clear mechanics emphasizing consistent contact reach and balance.",
    },
    {
        "reference_id": "pro_roger_federer_backhand",
        "player_name": "Roger Federer",
        "country": "SUI",
        "sport": "tennis",
        "stroke_type": "one_handed_backhand",
        "is_pro_reference": True,
        "kinematic_vector": [
            round(172.0 / 180.0, 4),
            round(158.0 / 180.0, 4),
            round(166.0 / 180.0, 4),
            round(148.0 / 180.0, 4),
            round(135.0 / 180.0, 4),
            0.89,
        ],
        "biomechanical_notes": (
            "Iconic one-handed backhand with deep shoulder coil, firm wrist stability, "
            "and explosive kinetic drive through the core."
        ),
    },
    {
        "reference_id": "fundamentals_tennis_backhand",
        "player_name": "Fundamentals Baseline",
        "country": "INT",
        "sport": "tennis",
        "stroke_type": "one_handed_backhand",
        "is_pro_reference": False,
        "kinematic_vector": [
            round(162.0 / 180.0, 4),
            round(145.0 / 180.0, 4),
            round(155.0 / 180.0, 4),
            round(140.0 / 180.0, 4),
            round(120.0 / 180.0, 4),
            0.82,
        ],
        "biomechanical_notes": (
            "Textbook compact backhand prioritizing balance, early preparation, and "
            "clean forward kinetic extension."
        ),
    },
]


def compute_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine similarity between two numeric vectors with safe division guards
    against zero-norm vectors.
    """
    if not v1 or not v2:
        return 0.0

    dim = min(len(v1), len(v2))
    sub1 = v1[:dim]
    sub2 = v2[:dim]

    dot = sum(a * b for a, b in zip(sub1, sub2))
    norm1 = math.sqrt(sum(a * a for a in sub1))
    norm2 = math.sqrt(sum(b * b for b in sub2))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return max(0.0, min(1.0, dot / (norm1 * norm2)))


class VectorMatcher:
    """
    Service for querying and matching kinematic vectors against pro/fundamental archetypes.
    """

    @classmethod
    async def seed_reference_archetypes(cls, db: Optional[AsyncIOMotorDatabase] = None) -> int:
        """
        Seeds canonical reference pose archetypes into sports_coach_db.pose_archetypes.
        """
        target_db = db if db is not None else get_database()
        settings = get_settings()
        collection = target_db[settings.POSE_ARCHETYPES_COLLECTION]

        count = 0
        for archetype in REFERENCE_POSE_ARCHETYPES:
            doc = dict(archetype)
            doc["_id"] = doc["reference_id"]
            # Upsert document by reference_id
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": doc},
                upsert=True,
            )
            count += 1

        logger.info("Seeded/verified %d reference pose archetypes in MongoDB Atlas", count)
        return count

    @classmethod
    async def find_closest_archetype(
        cls,
        kinematic_vector: List[float],
        sport: str = "badminton",
        stroke_type: str = "overhead_clear",
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Dict[str, Any]:
        """
        Finds the closest matching archetype vector using MongoDB Atlas $vectorSearch,
        falling back to in-memory cosine similarity computation.
        """
        target_db = db if db is not None else get_database()
        settings = get_settings()
        collection = target_db[settings.POSE_ARCHETYPES_COLLECTION]

        # 1. Attempt MongoDB Atlas $vectorSearch aggregation pipeline
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "pose_vector_index",
                        "path": "kinematic_vector",
                        "queryVector": kinematic_vector,
                        "numCandidates": 20,
                        "limit": 3,
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
                        "kinematic_vector": 1,
                        "biomechanical_notes": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]

            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=3)
            # Accept Atlas $vectorSearch results only when an actual positive score was produced
            if results and results[0].get("score") is not None and float(results[0].get("score", 0.0)) > 0.0:
                top_match = results[0]
                logger.info(
                    "Atlas $vectorSearch matched: %s (score=%.4f)",
                    top_match.get("player_name"),
                    top_match.get("score", 0.0),
                )
                return {
                    "matched_player": top_match.get("player_name", "Viktor Axelsen"),
                    "reference_id": top_match.get("reference_id"),
                    "similarity_score": round(float(top_match.get("score", 0.95)), 4),
                    "search_method": "atlas_vector_search",
                    "biomechanical_notes": top_match.get("biomechanical_notes", ""),
                    "kinematic_vector": top_match.get("kinematic_vector", []),
                }
        except Exception as exc:
            logger.debug("Atlas $vectorSearch unavailable (%s). Falling back to cosine similarity.", exc)

        # 2. Pure-Python Cosine Similarity Fallback
        # Query candidates from collection or fallback to in-memory seeds
        candidates: List[Dict[str, Any]] = []
        try:
            db_cursor = collection.find({})
            candidates = await db_cursor.to_list(length=50)
        except Exception:
            pass

        if not candidates:
            candidates = REFERENCE_POSE_ARCHETYPES

        # Filter by sport if possible
        sport_candidates = [c for c in candidates if c.get("sport", "").lower() == sport.lower()]
        target_candidates = sport_candidates if sport_candidates else candidates

        best_match: Optional[Dict[str, Any]] = None
        best_similarity = -1.0

        for candidate in target_candidates:
            cand_vector = candidate.get("kinematic_vector") or candidate.get("pose_vector") or []
            similarity = compute_cosine_similarity(kinematic_vector, cand_vector)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate

        if not best_match:
            best_match = REFERENCE_POSE_ARCHETYPES[0]
            best_similarity = 0.92

        logger.info(
            "Cosine fallback matched %s (similarity=%.4f, sport=%s)",
            best_match.get("player_name"),
            best_similarity,
            sport,
        )

        return {
            "matched_player": best_match.get("player_name", "Viktor Axelsen"),
            "reference_id": best_match.get("reference_id", "pro_viktor_axelsen_overhead"),
            "similarity_score": round(best_similarity, 4),
            "search_method": "cosine_similarity_fallback",
            "biomechanical_notes": best_match.get("biomechanical_notes", ""),
            "kinematic_vector": best_match.get("kinematic_vector", []),
        }
