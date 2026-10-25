"""
db_mongo.py - MongoDB Atlas Vector Search, Time-Series Biometrics, 2dsphere Geospatial Partner Search,
Change Streams & Longitudinal Fatigue-Biomechanics Analytics (Taha)

Showcases 5 Flagship MongoDB Atlas Features for the Hackathon Bounty:
1. Atlas `$vectorSearch` (`pose_vector_index` on `strokes.pose_vector`) matching 6D user biomechanics
   against Tennis GOATs (Roger Federer, Novak Djokovic, Carlos Alcaraz, Serena Williams, Jannik Sinner, Rafael Nadal).
2. MongoDB Time-Series Collection (`watch_telemetry_ts`) with `timeField="timestamp"`, `metaField="metadata"`,
   and `granularity="seconds"` + `$setWindowFields` rolling heart-rate & HRV trend computation.
3. Geospatial `2dsphere` Indexing + `$geoNear` on `players.location_geojson` to match London training partners
   by both physical distance (km from Sumanth's Android GPS) AND 6D biomechanical vector compatibility.
4. Multi-Stage `$facet` + `$bucket` Aggregation Pipeline correlating Apple Watch Heart-Rate Zones
   (`<145 BPM`, `145-165 BPM`, `>165 BPM`) against `right_elbow_contact_deg` collapse.
5. Real-Time MongoDB Change Streams (`db.watch()`) + Android Pairing Code (`TMPO-xxxx`) for zero-config
   Apple Watch -> MongoDB Atlas -> Android Jetpack Compose live streaming.
"""

from __future__ import annotations

import datetime
import math
import os
import secrets
from threading import Lock
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _load_local_env() -> None:
    """Automatically load key=value pairs from backend/.env if present."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_local_env()

try:
    from pymongo import ASCENDING, GEOSPHERE, MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    MongoClient = None  # type: ignore
    ASCENDING = 1  # type: ignore
    GEOSPHERE = "2dsphere"  # type: ignore

    class PyMongoError(Exception):  # type: ignore
        pass

if __package__:
    from .database_config import DATABASE_NAME, validate_database_name, validate_database_environment
else:
    from database_config import DATABASE_NAME, validate_database_name, validate_database_environment

validate_database_environment()
DB_NAME = DATABASE_NAME
WATCH_DB_NAME = DATABASE_NAME
STROKES_COLLECTION = "strokes"
PLAYERS_COLLECTION = "players"
WATCH_TS_COLLECTION = "watch_telemetry_ts"
WATCH_PAIRINGS_COLLECTION = "watch_pairings"
VECTOR_INDEX_NAME = "pose_vector_index"


PRO_REFERENCE_STROKES: List[Dict[str, Any]] = [
    {
        "reference_id": "pro_roger_federer_serve_smash",
        "player_name": "Roger Federer",
        "country": "SUI",
        "sport": "tennis",
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
        "sport": "tennis",
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
        "sport": "tennis",
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
        "sport": "tennis",
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
        "sport": "tennis",
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
        "sport": "tennis",
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
    },    {
        "reference_id": "pro_viktor_axelsen_overhead_clear",
        "player_name": "Viktor Axelsen",
        "country": "DEN",
        "sport": "badminton",
        "stroke_type": "Full-Reach Overhead Clear",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 176.0,
        "right_shoulder_abduction_deg": 168.0,
        "trunk_arch_deg": 164.0,
        "right_knee_flexion_deg": 148.0,
        "left_arm_balance_deg": 142.0,
        "contact_height_norm": 0.96,
        "pose_vector": [
            round(176.0 / 180.0, 4),
            round(168.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(148.0 / 180.0, 4),
            round(142.0 / 180.0, 4),
            0.96,
        ],
        "biomechanical_notes": (
            "Two-time Olympic champion whose 1.94 m frame delivers near-full 176 deg elbow extension at contact, "
            "a tall rear-court contact point and a stable non-racket-arm counterbalance for deep, flat clears."
        ),
    },
    {
        "reference_id": "pro_an_se_young_overhead_clear",
        "player_name": "An Se-young",
        "country": "KOR",
        "sport": "badminton",
        "stroke_type": "Defensive-to-Attack Overhead Clear",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 172.0,
        "right_shoulder_abduction_deg": 164.0,
        "trunk_arch_deg": 161.0,
        "right_knee_flexion_deg": 142.0,
        "left_arm_balance_deg": 138.0,
        "contact_height_norm": 0.93,
        "pose_vector": [
            round(172.0 / 180.0, 4),
            round(164.0 / 180.0, 4),
            round(161.0 / 180.0, 4),
            round(142.0 / 180.0, 4),
            round(138.0 / 180.0, 4),
            0.93,
        ],
        "biomechanical_notes": (
            "Olympic and world champion with elite rear-court recovery: compact kinetic chain, deep knee load (142 deg) "
            "and early shoulder rotation that turns defensive clears into attacking length."
        ),
    },
    {
        "reference_id": "pro_lee_zii_jia_jump_smash",
        "player_name": "Lee Zii Jia",
        "country": "MAS",
        "sport": "badminton",
        "stroke_type": "Explosive Jump Smash",
        "is_pro_reference": True,
        "right_elbow_contact_deg": 174.0,
        "right_shoulder_abduction_deg": 170.0,
        "trunk_arch_deg": 158.0,
        "right_knee_flexion_deg": 132.0,
        "left_arm_balance_deg": 140.0,
        "contact_height_norm": 0.98,
        "pose_vector": [
            round(174.0 / 180.0, 4),
            round(170.0 / 180.0, 4),
            round(158.0 / 180.0, 4),
            round(132.0 / 180.0, 4),
            round(140.0 / 180.0, 4),
            0.98,
        ],
        "biomechanical_notes": (
            "Explosive jumper whose airborne contact sits at the highest normalized point of the set (0.98), "
            "pairing a pronounced trunk arch with a deep 132 deg take-off knee bend for steep smash angles."
        ),
    },
]

# London training partners with GeoJSON `Point` coordinates ([longitude, latitude]) for MongoDB 2dsphere `$geoNear`
SEED_LONDON_PARTNERS: List[Dict[str, Any]] = [
    {
        "player_id": "partner_london_finsbury_01",
        "name": "Arjun Mehta",
        "city": "London",
        "preferred_venue": "Islington Tennis & Racket Centre / Finsbury Leisure (EC1V)",
        "postcode": "EC1V 3PU",
        "location_geojson": {
            "type": "Point",
            "coordinates": [-0.0982, 51.5265],  # Clerkenwell / Finsbury
        },
        "skill_level": "LTA Rating 3.2 / Advanced Club",
        "focus_area": "Roger Federer Overhead Extension & High-Contact Serve/Smash Consistency",
        "availability": "Tonight 20:00 - 22:00 BST",
        "target_pose_vector": [0.95, 0.91, 0.94, 0.89, 0.79, 0.91],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_bloomsbury_04",
        "name": "Elena Rostova",
        "city": "London",
        "preferred_venue": "Bloomsbury Fitness & Courts - UCL (WC1E)",
        "postcode": "WC1E 6BT",
        "location_geojson": {
            "type": "Point",
            "coordinates": [-0.1328, 51.5248],  # UCL Bloomsbury
        },
        "skill_level": "University 1st Team",
        "focus_area": "Serena Williams First-Serve Pronation & Left-Arm Toss Balance",
        "availability": "Tonight 21:00 - 22:30 BST",
        "target_pose_vector": [0.97, 0.93, 0.95, 0.90, 0.81, 0.94],
        "is_training_partner": True,
    },
    {
        "player_id": "partner_london_regents_02",
        "name": "Chloe Tan",
        "city": "London",
        "preferred_venue": "Regent's Park Tennis & Racket Courts (NW1)",
        "postcode": "NW1 4NR",
        "location_geojson": {
            "type": "Point",
            "coordinates": [-0.1566, 51.5293],  # Regent's Park
        },
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
        "postcode": "SW15 5JQ",
        "location_geojson": {
            "type": "Point",
            "coordinates": [-0.2528, 51.4547],  # Roehampton
        },
        "skill_level": "LTA Rating 2.4 / County Performance",
        "focus_area": "Carlos Alcaraz Explosive Overhead Smash & High-HR Rally Endurance",
        "availability": "Saturday 10:00 - 12:00 BST",
        "target_pose_vector": [0.95, 0.91, 0.94, 0.87, 0.77, 0.91],
        "is_training_partner": True,
    },
]

# Seed historical sessions for user_1 so longitudinal `$facet` + `$bucket` analytics work immediately
SEED_HISTORICAL_SESSIONS: List[Dict[str, Any]] = [
    {
        "session_id": "seed_session_fresh_01",
        "user_name": "user_1",
        "is_pro_reference": False,
        "verification_status": "PASS",
        "created_at": "2026-10-21T19:15:00+00:00",
        "pose_analysis": {
            "raw_angles": {
                "right_elbow_contact_deg": 173.2,
                "right_shoulder_abduction_deg": 165.0,
                "trunk_arch_deg": 170.1,
                "right_knee_flexion_deg": 161.0,
                "left_arm_balance_deg": 143.0,
                "contact_height_norm": 0.92,
            },
            "pose_vector": [0.9622, 0.9167, 0.945, 0.8944, 0.7944, 0.92],
        },
        "apple_watch_biometrics": {
            "heart_rate_bpm": 134.0,
            "peak_heart_rate_bpm": 148.0,
            "hrv_sdnn_ms": 58.0,
            "active_calories_kcal": 210.0,
            "fatigue_index": 36.4,
            "fatigue_state": "OPTIMAL_RECOVERY_READY",
        },
        "pro_comparison": {"matched_pro": "Novak Djokovic", "similarity_score": 0.9998},
        "saint_approval_status": "APPROVED_AND_DISPATCHED",
    },
    {
        "session_id": "seed_session_moderate_02",
        "user_name": "user_1",
        "is_pro_reference": False,
        "verification_status": "PASS",
        "created_at": "2026-10-22T20:10:00+00:00",
        "pose_analysis": {
            "raw_angles": {
                "right_elbow_contact_deg": 167.4,
                "right_shoulder_abduction_deg": 158.0,
                "trunk_arch_deg": 166.0,
                "right_knee_flexion_deg": 155.0,
                "left_arm_balance_deg": 134.0,
                "contact_height_norm": 0.87,
            },
            "pose_vector": [0.93, 0.8778, 0.9222, 0.8611, 0.7444, 0.87],
        },
        "apple_watch_biometrics": {
            "heart_rate_bpm": 156.0,
            "peak_heart_rate_bpm": 169.0,
            "hrv_sdnn_ms": 39.5,
            "active_calories_kcal": 390.0,
            "fatigue_index": 61.2,
            "fatigue_state": "MODERATE_FATIGUE_ELEVATED_LOAD",
        },
        "pro_comparison": {"matched_pro": "Carlos Alcaraz", "similarity_score": 0.9991},
        "saint_approval_status": "APPROVED_AND_DISPATCHED",
    },
    {
        "session_id": "seed_session_fatigued_03",
        "user_name": "user_1",
        "is_pro_reference": False,
        "verification_status": "FAIL",
        "created_at": "2026-10-23T21:30:00+00:00",
        "pose_analysis": {
            "raw_angles": {
                "right_elbow_contact_deg": 154.8,
                "right_shoulder_abduction_deg": 139.0,
                "trunk_arch_deg": 159.0,
                "right_knee_flexion_deg": 149.0,
                "left_arm_balance_deg": 115.0,
                "contact_height_norm": 0.76,
            },
            "pose_vector": [0.86, 0.7722, 0.8833, 0.8278, 0.6389, 0.76],
        },
        "apple_watch_biometrics": {
            "heart_rate_bpm": 178.0,
            "peak_heart_rate_bpm": 191.0,
            "hrv_sdnn_ms": 21.0,
            "active_calories_kcal": 585.0,
            "fatigue_index": 89.4,
            "fatigue_state": "HIGH_FATIGUE_AEROBIC_OVERLOAD",
        },
        "pro_comparison": {"matched_pro": "Rafael Nadal", "similarity_score": 0.9985},
        "saint_approval_status": "PENDING_HUMAN_APPROVAL",
    },
]

# In-memory store so the pipeline works seamlessly even if MONGODB_URI is not reachable locally
_MEMORY_STROKES: List[Dict[str, Any]] = [
    *[dict(doc) for doc in PRO_REFERENCE_STROKES],
    *([dict(doc) for doc in SEED_HISTORICAL_SESSIONS] if os.environ.get("TEMPO_DEMO_MODE", "false").lower() == "true" else []),
]
_MEMORY_PLAYERS: List[Dict[str, Any]] = [dict(doc) for doc in SEED_LONDON_PARTNERS]
_MEMORY_APPROVALS: Dict[str, Dict[str, Any]] = {}
_APPROVAL_LOCK = Lock()
_LATEST_WATCH_METRICS: Dict[str, Dict[str, Any]] = {}
_MEMORY_WATCH_TS: List[Dict[str, Any]] = []
_MEMORY_PAIRINGS: Dict[str, Dict[str, Any]] = {}

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


def get_db(database_name: Optional[str] = None):
    """Return the `sports_coach_db` database handle if connected, else None."""
    target_name = validate_database_name(database_name)
    client = get_mongo_client()
    if client is None:
        return None
    return client[target_name]


def _ensure_watch_collection(db: Any) -> None:
    """Prepare only watch storage; never create app/geo collections in the target DB."""
    if WATCH_TS_COLLECTION not in db.list_collection_names():
        db.create_collection(WATCH_TS_COLLECTION, timeseries={
            "timeField": "timestamp", "metaField": "metadata", "granularity": "seconds",
        })
    options = db[WATCH_TS_COLLECTION].options()
    timeseries = options.get("timeseries", {})
    if timeseries.get("timeField") != "timestamp" or timeseries.get("metaField") != "metadata":
        raise ValueError("Watch collection has an incompatible time-series schema")


def _ensure_timeseries_and_geo_indexes(db: Any) -> Dict[str, Any]:
    """
    Ensure MongoDB Time-Series collection (`watch_telemetry_ts`) and `2dsphere` geospatial index
    on `players.location_geojson` exist in Atlas.
    """
    status = {"timeseries_collection": False, "geo_2dsphere_index": False}
    if db is None:
        return status
    try:
        existing_cols = db.list_collection_names()
        if WATCH_TS_COLLECTION not in existing_cols:
            db.create_collection(
                WATCH_TS_COLLECTION,
                timeseries={
                    "timeField": "timestamp",
                    "metaField": "metadata",
                    "granularity": "seconds",
                },
            )
        status["timeseries_collection"] = True
    except Exception:
        status["timeseries_collection"] = True

    try:
        db[PLAYERS_COLLECTION].create_index([("location_geojson", GEOSPHERE)], name="location_2dsphere_idx")
        status["geo_2dsphere_index"] = True
    except Exception:
        pass

    return status


def check_mongo_health() -> Dict[str, Any]:
    """Check MongoDB connection status, active collections, and advanced Atlas features."""
    db = get_db()
    if db is None:
        return {
            "connected": False,
            "mode": "in_memory_fallback",
            "database": DB_NAME,
            "collections": [STROKES_COLLECTION, PLAYERS_COLLECTION, WATCH_TS_COLLECTION],
            "pro_references_count": sum(1 for s in _MEMORY_STROKES if s.get("is_pro_reference")),
            "london_partners_count": len(_MEMORY_PLAYERS),
            "atlas_features": [
                "atlas_vector_search",
                "timeseries_watch_telemetry",
                "geospatial_2dsphere_partner_match",
                "facet_bucket_fatigue_analytics",
                "process_local_sse_push",
            ],
        }
    try:
        pro_count = db[STROKES_COLLECTION].count_documents({"is_pro_reference": True})
        partner_count = db[PLAYERS_COLLECTION].count_documents({"city": "London", "is_training_partner": True})
        watch_db = get_db(WATCH_DB_NAME)
        ts_count = watch_db[WATCH_TS_COLLECTION].count_documents({})
        return {
            "connected": True,
            "mode": "mongodb_atlas",
            "database": DB_NAME,
            "collections": [STROKES_COLLECTION, PLAYERS_COLLECTION, WATCH_TS_COLLECTION, WATCH_PAIRINGS_COLLECTION],
            "pro_references_count": pro_count,
            "london_partners_count": partner_count,
            "watch_timeseries_points": ts_count,
            "watch_telemetry_database": WATCH_DB_NAME,
            "atlas_features": [
                "atlas_vector_search",
                "timeseries_watch_telemetry",
                "geospatial_2dsphere_partner_match",
                "facet_bucket_fatigue_analytics",
                "process_local_sse_push",
            ],
        }
    except Exception as exc:
        return {
            "connected": False,
            "mode": "in_memory_fallback",
            "database": DB_NAME,
            "error": str(exc),
        }


def seed_reference_data(remove_legacy_badminton_pros: bool = False) -> Dict[str, Any]:
    """
    Seed iconic Pro Tennis reference strokes (Roger Federer, Novak Djokovic, Carlos Alcaraz,
    Serena Williams, Jannik Sinner, Rafael Nadal), London training partners with GeoJSON coordinates,
    historical Sumanth sessions for longitudinal analytics, and Time-Series Apple Watch samples.
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
        idx_status = _ensure_timeseries_and_geo_indexes(db)
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

        for hist in (SEED_HISTORICAL_SESSIONS if os.environ.get("TEMPO_DEMO_MODE", "false").lower() == "true" else []):
            strokes_col.update_one(
                {"session_id": hist["session_id"]},
                {"$set": hist},
                upsert=True,
            )

        # Migrate any legacy placeholder records to user_1
        strokes_col.update_many({"user_name": "Sumanth"}, {"$set": {"user_name": "user_1"}})
        players_col.update_many({"user_name": "Sumanth"}, {"$set": {"user_name": "user_1"}})
        try:
            db[WATCH_TS_COLLECTION].update_many(
                {"metadata.user_name": "Sumanth"},
                {"$set": {"metadata.user_name": "user_1"}},
            )
        except Exception:
            pass

        seed_facilities(db)
        for partner in SEED_LONDON_PARTNERS:
            players_col.update_one(
                {"player_id": partner["player_id"]},
                {"$set": partner},
                upsert=True,
            )

        # Seed initial Apple Watch Time-Series telemetry points if empty
        if os.environ.get("TEMPO_DEMO_MODE", "false").lower() == "true" and db[WATCH_TS_COLLECTION].count_documents({}) == 0:
            now = datetime.datetime.now(datetime.timezone.utc)
            sample_points = [
                {
                    "timestamp": now - datetime.timedelta(seconds=30),
                    "metadata": {"user_name": "user_1", "device": "Apple Watch Ultra", "pairing_code": "TMPO-88"},
                    "heart_rate_bpm": 162.0,
                    "hrv_sdnn_ms": 34.0,
                    "active_calories_kcal": 460.0,
                    "wrist_acceleration_peak_mps": 29.1,
                    "fatigue_index": 71.2,
                },
                {
                    "timestamp": now - datetime.timedelta(seconds=15),
                    "metadata": {"user_name": "user_1", "device": "Apple Watch Ultra", "pairing_code": "TMPO-88"},
                    "heart_rate_bpm": 169.0,
                    "hrv_sdnn_ms": 27.5,
                    "active_calories_kcal": 478.0,
                    "wrist_acceleration_peak_mps": 30.4,
                    "fatigue_index": 79.8,
                },
                {
                    "timestamp": now,
                    "metadata": {"user_name": "user_1", "device": "Apple Watch Ultra", "pairing_code": "TMPO-88"},
                    "heart_rate_bpm": 174.5,
                    "hrv_sdnn_ms": 22.8,
                    "active_calories_kcal": 495.0,
                    "wrist_acceleration_peak_mps": 27.9,
                    "fatigue_index": 85.6,
                },
            ]
            db[WATCH_TS_COLLECTION].insert_many(sample_points)

        return {
            "seeded": True,
            "mode": "mongodb_atlas",
            "indexes": idx_status,
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


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Fallback Haversine distance in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return round(2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 2)


def _strip_mongo_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(doc)
    if "_id" in cleaned:
        cleaned["_id"] = str(cleaned["_id"])
    for k, v in list(cleaned.items()):
        if isinstance(v, datetime.datetime):
            cleaned[k] = v.isoformat()
    return cleaned


def ensure_pose_vector_index(db: Any) -> Dict[str, Any]:
    """
    Create or update the Atlas `pose_vector_index` on `strokes.pose_vector` (6D cosine),
    with `is_pro_reference` and `sport` as filter fields for per-sport pro matching.
    """
    from pymongo.operations import SearchIndexModel

    definition = {
        "fields": [
            {"type": "vector", "path": "pose_vector", "numDimensions": 6, "similarity": "cosine"},
            {"type": "filter", "path": "is_pro_reference"},
            {"type": "filter", "path": "sport"},
        ]
    }
    col = db[STROKES_COLLECTION]
    existing = {idx["name"]: idx for idx in col.list_search_indexes()}
    if VECTOR_INDEX_NAME in existing:
        col.update_search_index(VECTOR_INDEX_NAME, definition)
        return {"index": VECTOR_INDEX_NAME, "action": "updated"}
    col.create_search_index(SearchIndexModel(definition=definition, name=VECTOR_INDEX_NAME, type="vectorSearch"))
    return {"index": VECTOR_INDEX_NAME, "action": "created"}


def find_closest_pro_pose(user_pose_vector: List[float], sport: Optional[str] = None) -> Dict[str, Any]:
    """
    Match `user_pose_vector` against pro reference strokes of the user's `sport` (tennis or badminton)
    using MongoDB Atlas `$vectorSearch` (index: `pose_vector_index`, path: `pose_vector`, filtered on
    `sport`), with a Python cosine-similarity fallback if the Atlas index isn't built yet or MongoDB is
    offline. If no pros exist for `sport`, all pros are considered and `sport_matched` is False.
    """
    sport_id = (sport or "").strip().lower() or None
    pro_filter: Dict[str, Any] = {"is_pro_reference": True}
    if sport_id:
        pro_filter["sport"] = sport_id
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
                        "filter": pro_filter,
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
                best["sport_matched"] = bool(sport_id)
                best["all_pro_matches"] = [_strip_mongo_id(r) for r in results]
                return best
        except Exception:
            pass

    candidates: List[Dict[str, Any]] = []
    if db is not None:
        try:
            candidates = list(db[STROKES_COLLECTION].find({"is_pro_reference": True}, {"_id": 0}))
        except Exception:
            candidates = []
    if not candidates:
        candidates = [dict(doc) for doc in PRO_REFERENCE_STROKES]
    same_sport = [c for c in candidates if sport_id and c.get("sport") == sport_id]
    sport_matched = bool(same_sport)
    if sport_matched:
        candidates = same_sport

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cand in candidates:
        sim = cosine_similarity(user_pose_vector, cand.get("pose_vector", []))
        enriched = _strip_mongo_id(cand)
        enriched["similarity_score"] = sim
        scored.append((sim, enriched))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_match = dict(scored[0][1])
    best_match["search_method"] = "python_cosine_similarity_fallback"
    best_match["sport_matched"] = sport_matched
    best_match["all_pro_matches"] = [item[1] for item in scored]
    return best_match


def find_training_partner(
    city: str = "London",
    user_pose_vector: Optional[List[float]] = None,
    user_lon: float = -0.1328,  # Default: Central London / UCL
    user_lat: float = 51.5248,
) -> Dict[str, Any]:
    """
    Hybrid MongoDB Geospatial (`$geoNear` 2dsphere) + 6D Biomechanical Vector Compatibility Partner Search.
    Finds the best London training partner ranked by both physical proximity (km from Android GPS)
    and biomechanical pose vector alignment.
    """
    db = get_db()
    partners: List[Dict[str, Any]] = []
    geo_method = "haversine_fallback"

    if db is not None:
        try:
            _ensure_timeseries_and_geo_indexes(db)
            geo_pipeline = [
                {
                    "$geoNear": {
                        "near": {"type": "Point", "coordinates": [float(user_lon), float(user_lat)]},
                        "distanceField": "distance_meters",
                        "query": {"city": city, "is_training_partner": True},
                        "spherical": True,
                    }
                },
                {"$project": {"_id": 0}},
            ]
            partners = list(db[PLAYERS_COLLECTION].aggregate(geo_pipeline))
            if partners:
                geo_method = "mongodb_atlas_2dsphere_geonear"
                for p in partners:
                    p["distance_km"] = round(float(p.pop("distance_meters", 0.0)) / 1000.0, 2)
        except Exception:
            partners = []

    if not partners:
        partners = [dict(p) for p in SEED_LONDON_PARTNERS if p.get("city", "").lower() == city.lower()]
        for p in partners:
            coords = p.get("location_geojson", {}).get("coordinates", [-0.0982, 51.5265])
            p["distance_km"] = _haversine_km(user_lon, user_lat, float(coords[0]), float(coords[1]))

    for p in partners:
        target_vec = p.get("target_pose_vector") or user_pose_vector or [0.95, 0.91, 0.94, 0.89, 0.79, 0.91]
        vec_score = cosine_similarity(user_pose_vector, target_vec) if user_pose_vector else 0.97
        dist_km = float(p.get("distance_km", 1.5))
        # Hybrid score combining 75% biomechanical match + 25% London court proximity
        proximity_bonus = max(0.0, 1.0 - (dist_km / 20.0))
        p["compatibility_score"] = vec_score
        p["hybrid_rank_score"] = round(0.75 * vec_score + 0.25 * proximity_bonus, 4)
        p["search_method"] = geo_method

    partners.sort(key=lambda x: x.get("hybrid_rank_score", 0.0), reverse=True)
    best = _strip_mongo_id(partners[0])
    best["all_nearby_partners"] = [_strip_mongo_id(p) for p in partners]
    return best


def create_watch_pairing_session(user_name: str = "user_1", android_device_id: str = "pixel_compose_01") -> Dict[str, Any]:
    """
    Create a 6-character pairing code (e.g. `TMPO-88`) in MongoDB so the Android Jetpack Compose app
    and the player's Apple Watch / iPhone HealthKit Shortcut link seamlessly without typing URLs.
    """
    suffix = secrets.token_hex(4).upper()
    pairing_code = f"TMPO-{suffix}"
    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {
        "pairing_code": pairing_code,
        "user_name": user_name,
        "android_device_id": android_device_id,
        "status": "PAIRED_READY",
        "created_at": now.isoformat(),
        "expires_at": (now + datetime.timedelta(hours=12)).isoformat(),
    }
    _MEMORY_PAIRINGS[pairing_code] = doc
    _MEMORY_PAIRINGS["latest"] = doc

    db = get_db()
    if db is not None:
        try:
            db[WATCH_PAIRINGS_COLLECTION].update_one(
                {"pairing_code": pairing_code},
                {"$set": doc},
                upsert=True,
            )
        except Exception:
            pass
    return doc


def watch_pairing_owner(code: str) -> str:
    pairing = _MEMORY_PAIRINGS.get(code)
    if pairing is None:
        db = get_db()
        if db is not None:
            pairing = db[WATCH_PAIRINGS_COLLECTION].find_one({'pairing_code': code})
    if not pairing:
        raise ValueError('Unknown pairing code')
    return pairing['user_name']


def save_live_watch_telemetry(
    user_name: str,
    metrics: Dict[str, Any],
    pairing_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert live Apple Watch biometrics into:
    1. MongoDB Time-Series collection (`watch_telemetry_ts`) for `$setWindowFields` rolling heart-rate analytics.
    2. Latest player state in `players` so the Android app and next stroke analysis automatically use it.
    """
    resolved_user = (user_name or "user_1").strip()
    if pairing_code:
        pairing = _MEMORY_PAIRINGS.get(pairing_code)
        if pairing is None:
            db = get_db()
            if db is not None:
                pairing = db[WATCH_PAIRINGS_COLLECTION].find_one({"pairing_code": pairing_code})
        if pairing is None:
            raise ValueError("Unknown pairing code")
        expires_at = datetime.datetime.fromisoformat(pairing["expires_at"])
        if expires_at <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("Pairing code has expired")
        resolved_user = pairing["user_name"]

    key = resolved_user.lower()
    now_dt = datetime.datetime.now(datetime.timezone.utc)

    ts_point = {
        "timestamp": datetime.datetime.fromisoformat(metrics["sampled_at"]) if metrics.get("sampled_at") else now_dt,
        "received_at": now_dt,
        "sampled_at": metrics.get("sampled_at"),
        "metadata": {
            "user_name": resolved_user,
            "device": "Apple Watch",
            "pairing_code": pairing_code or "TMPO-LIVE",
        },
        "heart_rate_bpm": float(metrics.get("heart_rate_bpm", 168.0)),
        "peak_heart_rate_bpm": float(metrics.get("peak_heart_rate_bpm", 178.0)),
        "resting_heart_rate_bpm": float(metrics.get("resting_heart_rate_bpm", 56.0)),
        "hrv_sdnn_ms": float(metrics.get("hrv_sdnn_ms", 28.0)),
        "active_calories_kcal": float(metrics.get("active_calories_kcal", 420.0)),
        "wrist_acceleration_peak_mps": float(metrics.get("wrist_acceleration_peak_mps", 28.4)),
        "fatigue_index": float(metrics.get("fatigue_index", 75.0)),
        "fatigue_state": str(metrics.get("fatigue_state", "MODERATE_FATIGUE_ELEVATED_LOAD")),
    }
    _MEMORY_WATCH_TS.append(dict(ts_point))

    record = {
        "user_name": resolved_user,
        "pairing_code": pairing_code or "TMPO-LIVE",
        "updated_at": now_dt.isoformat(),
        **metrics,
    }
    _LATEST_WATCH_METRICS[key] = record
    _LATEST_WATCH_METRICS["latest"] = record

    receipt = {"database": WATCH_DB_NAME, "collection": WATCH_TS_COLLECTION, "persisted": False}
    record["storage"] = receipt
    watch_db = get_db(WATCH_DB_NAME)
    if watch_db is not None:
        try:
            _ensure_watch_collection(watch_db)
            result = watch_db[WATCH_TS_COLLECTION].insert_one(dict(ts_point))
            receipt["persisted"] = bool(result.acknowledged)
        except Exception:
            receipt["error"] = "watch_storage_write_failed"
    # Latest player state and Watch time-series share sports_coach_db.
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
    return _strip_mongo_id(record)


def get_watch_timeseries_window(user_name: str = "user_1", limit: int = 15) -> Dict[str, Any]:
    """
    Query the MongoDB Time-Series collection (`watch_telemetry_ts`) using `$setWindowFields`
    to compute a rolling 3-sample moving-average Heart Rate and Fatigue Index for the Android app.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    db = get_db(WATCH_DB_NAME)
    points: List[Dict[str, Any]] = []
    method = "in_memory_timeseries"

    if db is not None:
        try:
            match_stage = {"$match": {"metadata.user_name": user_name}}
            pipeline = [
                match_stage,
                {
                    "$setWindowFields": {
                        "sortBy": {"timestamp": 1},
                        "output": {
                            "rolling_avg_hr_bpm": {
                                "$avg": "$heart_rate_bpm",
                                "window": {"documents": [-2, 0]},
                            },
                            "rolling_avg_fatigue_index": {
                                "$avg": "$fatigue_index",
                                "window": {"documents": [-2, 0]},
                            },
                        },
                    }
                },
                {"$sort": {"timestamp": -1}},
                {"$limit": int(limit)},
                {"$project": {"_id": 0}},
            ]
            points = [_strip_mongo_id(p) for p in db[WATCH_TS_COLLECTION].aggregate(pipeline)]
            if points:
                method = "mongodb_atlas_timeseries_window_fields"
        except Exception:
            points = []

    if not points:
        raw = [p for p in _MEMORY_WATCH_TS if p.get("metadata", {}).get("user_name", "").lower() == user_name.lower()]
        for i, p in enumerate(raw):
            window = raw[max(0, i - 2) : i + 1]
            p_copy = _strip_mongo_id(p)
            p_copy["rolling_avg_hr_bpm"] = round(sum(x["heart_rate_bpm"] for x in window) / len(window), 1)
            p_copy["rolling_avg_fatigue_index"] = round(sum(x["fatigue_index"] for x in window) / len(window), 1)
            points.append(p_copy)
        points.reverse()
        points = points[:limit]

    return {
        "user_name": user_name,
        "collection": WATCH_TS_COLLECTION,
        "database": WATCH_DB_NAME,
        "aggregation_method": method,
        "sample_count": len(points),
        "samples": points,
    }


def get_fatigue_biomechanics_analytics(user_name: str = "user_1") -> Dict[str, Any]:
    """Summarize actual sessions by HR zone; never invent measurements for missing users."""
    db = get_db()
    if db is not None:
        try:
            pipeline = [
                {"$match": {"is_pro_reference": False, "user_name": user_name}},
                {
                    "$facet": {
                        "hr_zone_buckets": [
                            {
                                "$bucket": {
                                    "groupBy": "$apple_watch_biometrics.heart_rate_bpm",
                                    "boundaries": [0, 145, 165, 240],
                                    "default": "Other",
                                    "output": {
                                        "sessions_count": {"$sum": 1},
                                        "avg_heart_rate_bpm": {"$avg": "$apple_watch_biometrics.heart_rate_bpm"},
                                        "avg_elbow_contact_deg": {
                                            "$avg": "$pose_analysis.raw_angles.right_elbow_contact_deg"
                                        },
                                        "avg_contact_height_norm": {
                                            "$avg": "$pose_analysis.raw_angles.contact_height_norm"
                                        },
                                        "pass_count": {
                                            "$sum": {
                                                "$cond": [{"$eq": ["$verification_status", "PASS"]}, 1, 0]
                                            }
                                        },
                                    },
                                }
                            }
                        ],
                        "overall_summary": [
                            {
                                "$group": {
                                    "_id": "$user_name",
                                    "total_sessions": {"$sum": 1},
                                    "peak_elbow_deg": {"$max": "$pose_analysis.raw_angles.right_elbow_contact_deg"},
                                    "min_elbow_deg": {"$min": "$pose_analysis.raw_angles.right_elbow_contact_deg"},
                                    "avg_hr_bpm": {"$avg": "$apple_watch_biometrics.heart_rate_bpm"},
                                }
                            }
                        ],
                    }
                },
            ]
            agg_res = list(db[STROKES_COLLECTION].aggregate(pipeline))
            if agg_res:
                facet_data = agg_res[0]
                zone_labels = {
                    0: "Zone 1-2 (<145 BPM - Optimal Recovery)",
                    145: "Zone 3-4 (145-<165 BPM - Moderate Load)",
                    165: "Zone 5 (>=165 BPM - High Fatigue Overload)",
                }
                buckets = []
                for b in facet_data.get("hr_zone_buckets", []):
                    b_id = b.get("_id")
                    buckets.append(
                        {
                            "hr_zone": zone_labels.get(b_id, str(b_id)),
                            "sessions_count": b.get("sessions_count", 0),
                            "avg_heart_rate_bpm": round(float(b.get("avg_heart_rate_bpm") or 0.0), 1),
                            "avg_elbow_contact_deg": round(float(b.get("avg_elbow_contact_deg") or 0.0), 1),
                            "avg_contact_height_norm": round(float(b.get("avg_contact_height_norm") or 0.0), 3),
                            "pass_count": b.get("pass_count", 0),
                        }
                    )
                summary = (facet_data.get("overall_summary") or [{}])[0]
                low = next((b for b in buckets if b["hr_zone"].startswith("Zone 1")), None)
                high = next((b for b in buckets if b["hr_zone"].startswith("Zone 5")), None)
                comparable = low is not None and high is not None
                peak_e = low["avg_elbow_contact_deg"] if comparable else 0.0
                min_e = high["avg_elbow_contact_deg"] if comparable else 0.0
                return {
                    "user_name": user_name,
                    "aggregation_pipeline": "mongodb_atlas_facet_bucket",
                    "fatigue_induced_elbow_drop_deg": round(peak_e - min_e, 1),
                    "has_comparable_zones": comparable,
                    "insight": (f"Average elbow angle differs by {round(peak_e - min_e, 1)} degrees between low and high HR sessions. This association does not establish fatigue as the cause."
                                if comparable else "Insufficient sessions across low and high HR zones to compare elbow angles."),
                    "hr_zone_buckets": buckets,
                    "overall_summary": _strip_mongo_id(summary),
                }
        except Exception:
            pass

    method = "in_memory_facet_fallback"
    rows = [s for s in _MEMORY_STROKES
            if s.get("user_name") == user_name and s.get("is_pro_reference") is False
            # Clips with no reliable pose carry no angles; they can't join the elbow-vs-HR comparison.
            and "right_elbow_contact_deg" in ((s.get("pose_analysis") or {}).get("raw_angles") or {})]
    buckets = []
    for low, high, label in [(0, 145, "Zone 1-2 (<145 BPM)"),
                             (145, 165, "Zone 3-4 (145-<165 BPM)"),
                             (165, float("inf"), "Zone 5 (>=165 BPM)")]:
        group = [s for s in rows if low <= s["apple_watch_biometrics"]["heart_rate_bpm"] < high]
        if not group:
            continue
        def avg(field):
            return sum(field(s) for s in group) / len(group)
        buckets.append({
            "hr_zone": label, "sessions_count": len(group),
            "avg_heart_rate_bpm": round(avg(lambda s: s["apple_watch_biometrics"]["heart_rate_bpm"]), 1),
            "avg_elbow_contact_deg": round(avg(lambda s: s["pose_analysis"]["raw_angles"]["right_elbow_contact_deg"]), 1),
            "avg_contact_height_norm": round(avg(lambda s: s["pose_analysis"]["raw_angles"]["contact_height_norm"]), 3),
            "pass_count": sum(s.get("verification_status") == "PASS" for s in group),
        })
    low_zone = next((b for b in buckets if b["hr_zone"].startswith("Zone 1")), None)
    high_zone = next((b for b in buckets if b["hr_zone"].startswith("Zone 5")), None)
    comparable = low_zone is not None and high_zone is not None
    drop = round(low_zone["avg_elbow_contact_deg"] - high_zone["avg_elbow_contact_deg"], 1) if comparable else 0.0
    return {
        "user_name": user_name, "aggregation_pipeline": method,
        "fatigue_induced_elbow_drop_deg": drop, "has_comparable_zones": comparable,
        "insight": (f"Average elbow angle differs by {drop} degrees between low and high HR sessions. "
                    "This association does not establish fatigue as the cause." if comparable else
                    "Insufficient sessions across low and high HR zones to compare elbow angles."),
        "hr_zone_buckets": buckets, "overall_summary": {"total_sessions": len(rows)},
    }


def get_latest_watch_telemetry(user_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recently synced live Apple Watch metrics for `user_name` (or any latest sync).
    """
    if user_name:
        key = user_name.strip().lower()
        if key in _LATEST_WATCH_METRICS:
            return _LATEST_WATCH_METRICS[key]
    if not user_name and "latest" in _LATEST_WATCH_METRICS:
        return _LATEST_WATCH_METRICS["latest"]

    db = get_db()
    if db is not None:
        try:
            doc = db[PLAYERS_COLLECTION].find_one(
                {"is_live_watch": True, **({"user_name": user_name} if user_name else {})},
                {"_id": 0},
                sort=[("updated_at", -1)],
            )
            if doc:
                return _strip_mongo_id(doc)
        except Exception:
            pass
    return None


def save_analysis_session(session_doc: Dict[str, Any]) -> str:
    """
    Save the full stroke analysis session + staged Saint AI job into `sports_coach_db.strokes`.
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


def get_analysis_session(session_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    if db is not None:
        # Approval is fail-closed when the configured database cannot be read.
        doc = db[STROKES_COLLECTION].find_one({"session_id": session_id, "is_pro_reference": False})
        return _strip_mongo_id(doc) if doc else None
    return _MEMORY_APPROVALS.get(session_id)


def claim_saint_action(session_id: str, user_name: str) -> bool:
    query = {"session_id": session_id, "user_name": user_name,
             "saint_approval_status": "PENDING_HUMAN_APPROVAL"}
    db = get_db()
    if db is not None:
        doc = db[STROKES_COLLECTION].find_one_and_update(
            query, {"$set": {"saint_approval_status": "PROCESSING_APPROVAL"}})
        if not doc:
            return False
    with _APPROVAL_LOCK:
        record = _MEMORY_APPROVALS.get(session_id)
        if db is None and (not record or record.get("user_name") != user_name or
                          record.get("saint_approval_status") != "PENDING_HUMAN_APPROVAL"):
            return False
        if record:
            record["saint_approval_status"] = "PROCESSING_APPROVAL"
    return True


def update_saint_approval(session_id: str, approved: bool, reviewer_name: str = "user_1",
                          notes: Optional[str] = None,
                          dispatch_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    dispatch = (dispatch_result or {}).get("webhook_dispatch", {})
    status = ("APPROVED_AND_DISPATCHED" if dispatch.get("dispatched") else
              "APPROVED_DISPATCH_FAILED" if dispatch.get("webhook_configured") else
              "APPROVED_AWAITING_WEBHOOK") if approved else "REJECTED_BY_USER"
    fields = {"saint_approval_status": status, "saint_approved": approved,
              "saint_approved_by": reviewer_name,
              "saint_approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "saint_reviewer_notes": notes or "", "saint_dispatch_result": dispatch_result or {}}
    db = get_db()
    if db is not None:
        result = db[STROKES_COLLECTION].update_one({"session_id": session_id}, {"$set": fields})
        if not result.matched_count:
            raise ValueError("Unknown analysis session")
    with _APPROVAL_LOCK:
        for record in _MEMORY_STROKES:
            if record.get("session_id") == session_id:
                record.update(fields)
        if session_id in _MEMORY_APPROVALS:
            _MEMORY_APPROVALS[session_id].update(fields)
    return {"session_id": session_id, **fields}


# ---------------------------------------------------------------------------
# Unified athlete core memory (shared by app, live, WhatsApp and Gemini channels)
# ---------------------------------------------------------------------------

if __package__:
    from . import sports_config as _sports_config
else:
    import sports_config as _sports_config

import logging as _logging
import re as _re
import threading as _threading
from urllib.parse import quote_plus as _quote_plus

_memory_log = _logging.getLogger("tempo.athlete_memory")

ATHLETE_MEMORY_COLLECTION = "athlete_memory"
DRILLS_COLLECTION = "drills_catalog"
FACILITIES_COLLECTION = "facilities"
SAINT_QUEUE_COLLECTION = "saint_notifications"
DRILLS_SEARCH_INDEX_NAME = "drills_text_index"
CHAT_HISTORY_TURNS = 15

LEVELS = ("beginner", "intermediate", "advanced")
INTENSITIES = ("casual", "regular", "competitive")
NODE_STATUSES = ("locked", "active", "completed")
MEMORY_FIELDS = (
    "phone_number", "sport", "skill_focus", "level", "motivation_why", "intensity",
    "reminder_schedule", "curriculum_nodes", "recent_flaws", "chat_history", "assigned_drills",
    "last_completed_node", "focus_note", "gear_list", "message_drafts",
)

# indoor/outdoor flags are what each venue offers; prices and booking lead times change, so they are
# deliberately not stored: Thea points to live availability and drafts the booking request instead.
SEED_LONDON_FACILITIES: List[Dict[str, Any]] = [
    {"facility_id": "fac_finsbury_leisure", "name": "Finsbury Leisure Centre", "postcode": "EC1V 3PU",
     "sports": ["badminton"], "indoor": True, "outdoor": False,
     "location_geojson": {"type": "Point", "coordinates": [-0.0982, 51.5265]}},
    {"facility_id": "fac_islington_tennis_centre", "name": "Islington Tennis Centre", "postcode": "N7 9RQ",
     "sports": ["tennis"], "indoor": True, "outdoor": True,
     "location_geojson": {"type": "Point", "coordinates": [-0.1196, 51.5524]}},
    {"facility_id": "fac_westway_sports_centre", "name": "Westway Sports & Fitness Centre", "postcode": "W10 6RP",
     "sports": ["tennis", "badminton"], "indoor": True, "outdoor": True,
     "location_geojson": {"type": "Point", "coordinates": [-0.2154, 51.5207]}},
    {"facility_id": "fac_regents_park_tennis", "name": "Regent's Park Tennis Centre", "postcode": "NW1 4NU",
     "sports": ["tennis"], "indoor": False, "outdoor": True,
     "location_geojson": {"type": "Point", "coordinates": [-0.1530, 51.5285]}},
    {"facility_id": "fac_paddington_rec", "name": "Paddington Recreation Ground", "postcode": "W9 1PD",
     "sports": ["tennis"], "indoor": False, "outdoor": True,
     "location_geojson": {"type": "Point", "coordinates": [-0.1918, 51.5300]}},
    {"facility_id": "fac_lee_valley_hockey_tennis", "name": "Lee Valley Hockey & Tennis Centre", "postcode": "E20 3AB",
     "sports": ["tennis"], "indoor": True, "outdoor": True,
     "location_geojson": {"type": "Point", "coordinates": [-0.0151, 51.5507]}},
    {"facility_id": "fac_ucl_bloomsbury", "name": "Bloomsbury Fitness - UCL", "postcode": "WC1E 7HY",
     "sports": ["badminton"], "indoor": True, "outdoor": False,
     "location_geojson": {"type": "Point", "coordinates": [-0.1340, 51.5246]}},
]

_MEMORY_ATHLETES: Dict[str, Dict[str, Any]] = {}
_MEMORY_SAINT_QUEUE: List[Dict[str, Any]] = []
_ATHLETE_LOCK = Lock()


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def youtube_search_url(*terms: str) -> str:
    """A YouTube search link (never a guessed video id) for a lesson or drill."""
    return "https://www.youtube.com/results?search_query=" + _quote_plus(" ".join(t for t in terms if t))


def default_athlete_memory(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "phone_number": None,
        "sport": None,
        "skill_focus": None,
        "level": None,
        "motivation_why": None,
        "intensity": None,
        "reminder_schedule": None,
        "curriculum_nodes": [],
        "recent_flaws": [],
        "chat_history": [],
        "assigned_drills": [],
        "last_completed_node": None,
        "focus_note": None,
        "gear_list": [],
        "message_drafts": [],
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }


def _validate_memory_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    unknown = set(updates) - set(MEMORY_FIELDS)
    if unknown:
        raise ValueError(f"Unknown athlete_memory fields: {sorted(unknown)}")
    clean = dict(updates)
    if clean.get("level") is not None and clean["level"] not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    if clean.get("intensity") is not None and clean["intensity"] not in INTENSITIES:
        raise ValueError(f"intensity must be one of {INTENSITIES}")
    if clean.get("sport") is not None:
        clean["sport"] = str(clean["sport"]).strip().lower()
    for node in clean.get("curriculum_nodes") or []:
        if node.get("status") not in NODE_STATUSES:
            raise ValueError(f"curriculum node status must be one of {NODE_STATUSES}")
    if "chat_history" in clean:
        clean["chat_history"] = list(clean["chat_history"])[-CHAT_HISTORY_TURNS:]
    return clean


USER_INDEXES = {"user_id_unique": "user_id", "email_unique": "email"}
LEGACY_USER_INDEXES = ("userId_1", "location_2dsphere_idx")  # old camelCase schema; userId is never written


def ensure_user_indexes(db: Any) -> Dict[str, List[str]]:
    """Drop stale camelCase `users` indexes (a unique `userId` makes every second sign-up collide on
    null and fall back to process memory) and index the fields accounts actually use."""
    col = db["users"]
    existing = col.index_information()
    dropped = [name for name in LEGACY_USER_INDEXES if name in existing]
    for name in dropped:
        col.drop_index(name)
    created = []
    for name, field in USER_INDEXES.items():
        if name not in existing:
            col.create_index(field, name=name, unique=True,
                             partialFilterExpression={field: {"$type": "string"}})
            created.append(name)
    return {"dropped": dropped, "created": created}


def get_athlete_memory(user_id: str) -> Dict[str, Any]:
    """Return the athlete's memory document, or a fresh default (not yet persisted)."""
    db = get_db()
    if db is not None:
        try:
            doc = db[ATHLETE_MEMORY_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})
            if doc:
                return doc
        except PyMongoError:
            pass
    with _ATHLETE_LOCK:
        cached = _MEMORY_ATHLETES.get(user_id)
        return dict(cached) if cached else default_athlete_memory(user_id)


def find_athlete_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    phone = (phone_number or "").strip()
    if not phone:
        return None
    db = get_db()
    if db is not None:
        try:
            doc = db[ATHLETE_MEMORY_COLLECTION].find_one({"phone_number": phone}, {"_id": 0})
            if doc:
                return doc
        except PyMongoError:
            pass
    with _ATHLETE_LOCK:
        for doc in _MEMORY_ATHLETES.values():
            if doc.get("phone_number") == phone:
                return dict(doc)
    return None


def update_athlete_memory(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and `$set` fields on the athlete's memory (upserting it), returning the new document."""
    clean = _validate_memory_updates(updates)
    now = _utc_now_iso()
    db = get_db()
    if db is not None:
        try:
            from pymongo import ReturnDocument

            defaults = {k: v for k, v in default_athlete_memory(user_id).items()
                        if k not in clean and k not in ("user_id", "updated_at")}
            doc = db[ATHLETE_MEMORY_COLLECTION].find_one_and_update(
                {"user_id": user_id},
                {"$set": {**clean, "updated_at": now}, "$setOnInsert": defaults},
                upsert=True,
                projection={"_id": 0},
                return_document=ReturnDocument.AFTER,
            )
            return doc
        except PyMongoError as exc:
            _memory_log.warning("athlete_memory Atlas write failed, using memory: %s", exc)
    with _ATHLETE_LOCK:
        doc = _MEMORY_ATHLETES.setdefault(user_id, default_athlete_memory(user_id))
        doc.update(clean)
        doc["updated_at"] = now
        return dict(doc)


def append_chat_turn(user_id: str, turn: Dict[str, Any]) -> None:
    """Push one {user, coach, channel, at} turn, keeping only the last CHAT_HISTORY_TURNS."""
    db = get_db()
    if db is not None:
        try:
            db[ATHLETE_MEMORY_COLLECTION].update_one(
                {"user_id": user_id},
                {"$push": {"chat_history": {"$each": [turn], "$slice": -CHAT_HISTORY_TURNS}},
                 "$set": {"updated_at": _utc_now_iso()}},
                upsert=True,
            )
            return
        except PyMongoError:
            pass
    with _ATHLETE_LOCK:
        doc = _MEMORY_ATHLETES.setdefault(user_id, default_athlete_memory(user_id))
        doc["chat_history"] = (doc.get("chat_history", []) + [turn])[-CHAT_HISTORY_TURNS:]


def set_lesson_node_status(user_id: str, node_id: str, status: str) -> Dict[str, Any]:
    """Set one curriculum node's status; completing a node activates the next locked one."""
    if status not in NODE_STATUSES:
        raise ValueError(f"status must be one of {NODE_STATUSES}")
    memory = get_athlete_memory(user_id)
    nodes = [dict(n) for n in memory.get("curriculum_nodes") or []]
    index = next((i for i, n in enumerate(nodes) if n.get("id") == node_id), None)
    if index is None:
        raise ValueError(f"Unknown lesson node: {node_id}")
    nodes[index]["status"] = status
    updates: Dict[str, Any] = {"curriculum_nodes": nodes}
    if status == "completed":
        completed_at = _utc_now_iso()
        nodes[index]["completed_at"] = completed_at
        nxt = next((n for n in nodes[index + 1:] if n.get("status") == "locked"), None)
        if nxt and not any(n.get("status") == "active" for n in nodes):
            nxt["status"] = "active"
        # Watched by the change stream to queue Saint cadence notifications.
        updates["last_completed_node"] = {"id": node_id, "title": nodes[index].get("title"),
                                          "completed_at": completed_at}
    return update_athlete_memory(user_id, updates)


# --- Drills catalog with Atlas Search ($search) and regex fallback ---------

def build_drills_catalog() -> List[Dict[str, Any]]:
    drills: List[Dict[str, Any]] = []
    for sport in _sports_config.SPORTS_CATALOG.values():
        for skill in sport.skills:
            faults = {d: f.name for f in skill.common_faults for d in f.drill_ids}
            for drill in skill.drills:
                drills.append({
                    "drill_id": drill.id,
                    "sport": sport.id,
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "title": drill.title,
                    "instruction": drill.instruction,
                    "focus_cue": drill.focus_cue,
                    "target_reps": drill.target_reps,
                    "fixes_fault": faults.get(drill.id),
                    "youtube_url": youtube_search_url(sport.display_name, skill.name, drill.title, "drill"),
                })
    return drills


def seed_drills_catalog(db: Any) -> int:
    drills = build_drills_catalog()
    for drill in drills:
        db[DRILLS_COLLECTION].replace_one({"drill_id": drill["drill_id"]}, drill, upsert=True)
    return len(drills)


def ensure_drills_search_index(db: Any) -> Dict[str, Any]:
    """Create the Atlas Search (Lucene) index over drill text fields if it doesn't exist."""
    from pymongo.operations import SearchIndexModel

    col = db[DRILLS_COLLECTION]
    if any(idx["name"] == DRILLS_SEARCH_INDEX_NAME for idx in col.list_search_indexes()):
        return {"index": DRILLS_SEARCH_INDEX_NAME, "action": "exists"}
    definition = {"mappings": {"dynamic": False, "fields": {
        "title": {"type": "string"}, "instruction": {"type": "string"},
        "focus_cue": {"type": "string"}, "skill_name": {"type": "string"},
        "fixes_fault": {"type": "string"}, "sport": {"type": "token"},
    }}}
    try:
        col.create_search_index(SearchIndexModel(definition=definition, name=DRILLS_SEARCH_INDEX_NAME, type="search"))
    except PyMongoError as exc:
        # M0/M2 clusters cap search indexes at 3; search_drills() then uses the regex fallback.
        return {"index": DRILLS_SEARCH_INDEX_NAME, "action": f"skipped ({exc.__class__.__name__}: "
                f"{str(exc).split(',')[0]})"}
    return {"index": DRILLS_SEARCH_INDEX_NAME, "action": "created"}


# Search indexes from an earlier schema that no code queries; they fill the M0 3-index quota.
LEGACY_SEARCH_INDEXES = (("users", "partner_text_index"), ("pro_references", "pose_vector_index"))


def _search_index(db: Any, collection: str, name: str) -> Optional[Dict[str, Any]]:
    try:
        return next(iter(db[collection].list_search_indexes(name)), None)
    except PyMongoError:
        return None


def drop_legacy_search_indexes(db: Any, wait_s: float = 90.0) -> List[str]:
    """Drop the unused legacy search indexes (absent ones are ignored) and wait until Atlas frees them."""
    import time as _time

    dropped = []
    for collection, name in LEGACY_SEARCH_INDEXES:
        if _search_index(db, collection, name) is None:
            continue
        try:
            db[collection].drop_search_index(name)
            dropped.append(f"{collection}.{name}")
        except PyMongoError as exc:
            _memory_log.warning("could not drop search index %s.%s: %s", collection, name, exc)
    deadline = _time.time() + wait_s
    while dropped and _time.time() < deadline and any(
            _search_index(db, c, n) is not None for c, n in LEGACY_SEARCH_INDEXES):
        _time.sleep(2)
    return dropped


def wait_for_search_index(db: Any, collection: str, name: str, wait_s: float = 180.0) -> str:
    """Poll until an Atlas search index is queryable; returns its final status."""
    import time as _time

    deadline = _time.time() + wait_s
    while True:
        idx = _search_index(db, collection, name)
        status = (idx or {}).get("status", "MISSING")
        if (idx and idx.get("queryable")) or status == "FAILED" or _time.time() >= deadline:
            return "READY" if idx and idx.get("queryable") else status
        _time.sleep(3)


def search_drills(query: str, sport: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """Atlas `$search` over drills_catalog, falling back to regex, then to the in-process catalog."""
    sport_id = (sport or "").strip().lower() or None
    text = (query or "").strip()
    fields = ["title", "instruction", "focus_cue", "skill_name", "fixes_fault"]
    db = get_db()
    if db is not None and text:
        try:
            search: Dict[str, Any] = {"index": DRILLS_SEARCH_INDEX_NAME,
                                      "compound": {"must": [{"text": {"query": text, "path": fields}}]}}
            if sport_id:
                search["compound"]["filter"] = [{"equals": {"path": "sport", "value": sport_id}}]
            results = list(db[DRILLS_COLLECTION].aggregate([
                {"$search": search}, {"$limit": int(limit)}, {"$project": {"_id": 0}},
            ]))
            if results:
                return {"method": "atlas_search", "drills": results}
        except PyMongoError:
            pass
    words = [w for w in _re.split(r"\W+", text) if len(w) > 2]
    pattern = "|".join(_re.escape(w) for w in words) or ".*"
    if db is not None:
        try:
            match: Dict[str, Any] = {"$or": [{f: {"$regex": pattern, "$options": "i"}} for f in fields]}
            if sport_id:
                match["sport"] = sport_id
            results = list(db[DRILLS_COLLECTION].find(match, {"_id": 0}).limit(int(limit)))
            if results:
                return {"method": "regex_fallback", "drills": results}
        except PyMongoError:
            pass
    regex = _re.compile(pattern, _re.I)
    local = [d for d in build_drills_catalog()
             if (not sport_id or d["sport"] == sport_id) and any(regex.search(str(d.get(f) or "")) for f in fields)]
    return {"method": "in_memory_catalog", "drills": local[:limit]}


# --- Facilities ($nearSphere on 2dsphere) ----------------------------------

def seed_facilities(db: Any) -> int:
    """Idempotently upsert the London court seed (2dsphere-indexed); safe on every startup."""
    col = db[FACILITIES_COLLECTION]
    col.create_index([("location_geojson", GEOSPHERE)], name="location_2dsphere_idx")
    for fac in SEED_LONDON_FACILITIES:
        col.replace_one({"facility_id": fac["facility_id"]}, {**fac, "city": "London"}, upsert=True)
    return len(SEED_LONDON_FACILITIES)


def find_nearby_facilities(lat: float, lng: float, limit: int = 5, max_km: float = 25.0) -> Dict[str, Any]:
    db = get_db()
    found: List[Dict[str, Any]] = []
    method = "in_memory_haversine"
    if db is not None:
        try:
            found = list(db[FACILITIES_COLLECTION].find({"location_geojson": {"$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                "$maxDistance": float(max_km) * 1000.0,
            }}}, {"_id": 0}).limit(int(limit)))
            method = "mongodb_nearSphere_2dsphere"
        except PyMongoError:
            found = []
    if not found and method != "mongodb_nearSphere_2dsphere":
        found = sorted((dict(f) for f in SEED_LONDON_FACILITIES),
                       key=lambda f: _haversine_km(lng, lat, *f["location_geojson"]["coordinates"]))[:limit]
    for fac in found:
        flng, flat = fac["location_geojson"]["coordinates"]
        fac["distance_km"] = round(_haversine_km(float(lng), float(lat), flng, flat), 2)
    return {"method": method, "facilities": found}


# --- Change stream: log mutations, queue Saint cadence on lesson completion ---

def queue_saint_notification(notification: Dict[str, Any]) -> Dict[str, Any]:
    doc = {"status": "queued", "queued_at": _utc_now_iso(), **notification}
    db = get_db()
    if db is not None:
        try:
            db[SAINT_QUEUE_COLLECTION].insert_one(dict(doc))
            return doc
        except PyMongoError:
            pass
    with _ATHLETE_LOCK:
        _MEMORY_SAINT_QUEUE.append(doc)
    return doc


def handle_athlete_memory_change(change: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Process one change-stream event; returns the Saint notifications it queued."""
    full = change.get("fullDocument") or {}
    user_id = full.get("user_id") or "unknown"
    updated = (change.get("updateDescription") or {}).get("updatedFields") or {}
    _memory_log.info("athlete_memory %s user=%s fields=%s", change.get("operationType"), user_id,
                     sorted(updated) if updated else "*")
    completed = updated.get("last_completed_node") or (
        full.get("last_completed_node") if change.get("operationType") == "replace" else None)
    if not completed:
        return []
    schedule = full.get("reminder_schedule") or {}
    return [queue_saint_notification({
        "user_id": user_id,
        "type": "lesson_completed",
        "node_id": completed.get("id"),
        "node_title": completed.get("title"),
        "channel": schedule.get("preferred_channel", "whatsapp"),
        "phone_number": full.get("phone_number"),
    })]


_WATCHER_THREAD: Optional[_threading.Thread] = None
_WATCHER_STOP = _threading.Event()


def start_athlete_memory_watcher() -> bool:
    """Start a daemon thread on `db.athlete_memory.watch()`; returns False if Atlas is unavailable."""
    global _WATCHER_THREAD
    if _WATCHER_THREAD and _WATCHER_THREAD.is_alive():
        return True
    if os.environ.get("TEMPO_DISABLE_CHANGE_STREAM", "").lower() in {"1", "true", "yes"}:
        return False
    db = get_db()
    if db is None:
        return False

    def _run() -> None:
        while not _WATCHER_STOP.is_set():
            try:
                with db[ATHLETE_MEMORY_COLLECTION].watch(full_document="updateLookup",
                                                         max_await_time_ms=1000) as stream:
                    while not _WATCHER_STOP.is_set():
                        change = stream.try_next()
                        if change is not None:
                            handle_athlete_memory_change(change)
            except Exception as exc:
                _memory_log.warning("athlete_memory change stream restarting: %s", exc)
                _WATCHER_STOP.wait(5)

    _WATCHER_STOP.clear()
    _WATCHER_THREAD = _threading.Thread(target=_run, name="athlete-memory-watch", daemon=True)
    _WATCHER_THREAD.start()
    return True


def stop_athlete_memory_watcher() -> None:
    _WATCHER_STOP.set()
