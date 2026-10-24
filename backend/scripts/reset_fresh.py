#!/usr/bin/env python3
"""Hard-reset sports_coach_db to a fresh-signup state.

Clears all user-owned collections, then seeds only reference data:
pro archetype strokes, the drills catalog (Atlas Search) and London court
facilities (2dsphere). No user is seeded.
Idempotent: safe to run repeatedly.

Uses MONGODB_URI (env or backend/.env), defaulting to mongodb://127.0.0.1:27017.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import db_mongo  # noqa: E402  (also loads backend/.env)
from pymongo import GEOSPHERE, MongoClient  # noqa: E402

CLEARED_COLLECTIONS = [
    "users",
    "profiles",
    "android_sessions",
    "user_schedules",
    "strokes",
    "conversation_history",
    "athlete_memory",
    "saint_notifications",
]


def main() -> int:
    uri = os.environ.get("MONGODB_URI", "").strip() or "mongodb://127.0.0.1:27017"
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
    except Exception as exc:
        print(f"ERROR: cannot reach MongoDB ({type(exc).__name__}). Set MONGODB_URI or start mongod.")
        return 1

    db = client[db_mongo.DB_NAME]
    for name in CLEARED_COLLECTIONS:
        result = db[name].delete_many({})
        print(f"cleared {name}: {result.deleted_count} docs")

    strokes = db[db_mongo.STROKES_COLLECTION]
    for ref in db_mongo.PRO_REFERENCE_STROKES:
        strokes.replace_one({"reference_id": ref["reference_id"]}, {**ref, "is_pro": True}, upsert=True)
    print(f"seeded strokes: {len(db_mongo.PRO_REFERENCE_STROKES)} pro references "
          f"({', '.join(r['player_name'] for r in db_mongo.PRO_REFERENCE_STROKES)})")

    print(f"pose vector index: {db_mongo.ensure_pose_vector_index(db)['action']} (filters: is_pro_reference, sport)")

    drill_count = db_mongo.seed_drills_catalog(db)
    print(f"seeded drills_catalog: {drill_count} drills; search index "
          f"{db_mongo.ensure_drills_search_index(db)['action']}")

    facilities = db[db_mongo.FACILITIES_COLLECTION]
    facilities.create_index([("location_geojson", GEOSPHERE)], name="location_2dsphere_idx")
    for fac in db_mongo.SEED_LONDON_FACILITIES:
        facilities.replace_one({"facility_id": fac["facility_id"]}, {**fac, "city": "London"}, upsert=True)
    print(f"seeded facilities: {len(db_mongo.SEED_LONDON_FACILITIES)} London courts (2dsphere indexed)")

    print(f"reset complete: {db_mongo.DB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
