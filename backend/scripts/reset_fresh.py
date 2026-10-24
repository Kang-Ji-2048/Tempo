#!/usr/bin/env python3
"""Hard-reset sports_coach_db to a fresh-signup state.

Clears all user-owned collections, then seeds only reference data:
pro archetype strokes and London court facilities (2dsphere). No user is seeded.
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
]
FACILITIES_COLLECTION = "facilities"

LONDON_FACILITIES = [
    {"facility_id": "fac_islington_tennis_centre", "name": "Islington Tennis Centre", "postcode": "N7 9RQ",
     "location_geojson": {"type": "Point", "coordinates": [-0.1196, 51.5524]}},
    {"facility_id": "fac_westway_sports_centre", "name": "Westway Sports & Fitness Centre", "postcode": "W10 6RP",
     "location_geojson": {"type": "Point", "coordinates": [-0.2154, 51.5207]}},
    {"facility_id": "fac_regents_park_tennis", "name": "Regent's Park Tennis Centre", "postcode": "NW1 4NU",
     "location_geojson": {"type": "Point", "coordinates": [-0.1530, 51.5285]}},
    {"facility_id": "fac_paddington_rec", "name": "Paddington Recreation Ground", "postcode": "W9 1PD",
     "location_geojson": {"type": "Point", "coordinates": [-0.1918, 51.5300]}},
    {"facility_id": "fac_lee_valley_hockey_tennis", "name": "Lee Valley Hockey & Tennis Centre", "postcode": "E20 3AB",
     "location_geojson": {"type": "Point", "coordinates": [-0.0151, 51.5507]}},
    {"facility_id": "fac_ucl_bloomsbury", "name": "Bloomsbury Fitness - UCL", "postcode": "WC1E 7HY",
     "location_geojson": {"type": "Point", "coordinates": [-0.1340, 51.5246]}},
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

    facilities = db[FACILITIES_COLLECTION]
    facilities.create_index([("location_geojson", GEOSPHERE)], name="location_2dsphere_idx")
    for fac in LONDON_FACILITIES:
        facilities.replace_one({"facility_id": fac["facility_id"]}, {**fac, "city": "London"}, upsert=True)
    print(f"seeded facilities: {len(LONDON_FACILITIES)} London courts (2dsphere indexed)")

    print(f"reset complete: {db_mongo.DB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
