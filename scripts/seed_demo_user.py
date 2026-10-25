#!/usr/bin/env python3
"""Seed demo user demo@tempo.app into MongoDB / local user registry."""
import os
import sys
from pathlib import Path
from uuid import uuid4

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import bcrypt
import db_mongo
import user_auth


def seed():
    email = "demo@tempo.app"
    password = os.environ.get("DEMO_PASSWORD", "TempoDemo2026!")
    display_name = "Tempo Demo Athlete"

    print(f"Seeding demo user: {email}...")

    # Check if user already exists
    existing = user_auth._get_user_by_email(email)
    salt = bcrypt.gensalt()
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    if existing:
        user_id = existing["user_id"]
        record = {
            **existing,
            "display_name": display_name,
            "password_hash": pw_hash,
            "sport": "badminton",
            "skill": "overhead_clear",
            "level": "intermediate",
        }
        print(f"User {email} already exists (ID: {user_id}). Updating password...")
    else:
        user_id = str(uuid4())
        record = {
            "user_id": user_id,
            "email": email,
            "display_name": display_name,
            "password_hash": pw_hash,
            "created_at": user_auth._now(),
            "sport": "badminton",
            "skill": "overhead_clear",
            "level": "intermediate",
            "goal": "overhead_power",
            "playstyle": "aggressive",
            "injuries": [],
            "reference_player": "Viktor Axelsen",
        }
        print(f"Creating new user {email} (ID: {user_id})...")

    user_auth._save_user(record)
    print(f"SUCCESS: Seeded {email} (user_id: {user_id}). Password: {password}")


if __name__ == "__main__":
    seed()
