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
    "saint_deliveries",
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

    print(f"users indexes: {db_mongo.ensure_user_indexes(db)}")

    strokes = db[db_mongo.STROKES_COLLECTION]
    for ref in db_mongo.PRO_REFERENCE_STROKES:
        strokes.replace_one({"reference_id": ref["reference_id"]}, {**ref, "is_pro": True}, upsert=True)
    print(f"seeded strokes: {len(db_mongo.PRO_REFERENCE_STROKES)} pro references "
          f"({', '.join(r['player_name'] for r in db_mongo.PRO_REFERENCE_STROKES)})")

    print(f"pose vector index: {db_mongo.ensure_pose_vector_index(db)['action']} (filters: is_pro_reference, sport)")

    dropped = db_mongo.drop_legacy_search_indexes(db)
    print(f"legacy search indexes dropped: {', '.join(dropped) or 'none present'}")
    drill_count = db_mongo.seed_drills_catalog(db)
    action = db_mongo.ensure_drills_search_index(db)["action"]
    status = db_mongo.wait_for_search_index(db, db_mongo.DRILLS_COLLECTION, db_mongo.DRILLS_SEARCH_INDEX_NAME)
    print(f"seeded drills_catalog: {drill_count} drills; search index {action} -> {status}")

    print(f"seeded facilities: {db_mongo.seed_facilities(db)} London courts (2dsphere indexed)")

    print(f"reset complete: {db_mongo.DB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
