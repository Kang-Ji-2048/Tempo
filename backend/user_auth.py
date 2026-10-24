"""User authentication, registration, rate limiting, and profile management."""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

try:
    from . import auth, db_mongo
except ImportError:
    import auth
    import db_mongo

logger = logging.getLogger("tempo.auth")

router = APIRouter(prefix="/api/v1", tags=["auth"])

# In-memory users and rate limit tracking fallback
_USERS_MEMORY: Dict[str, Dict[str, Any]] = {}
_FAILED_LOGINS: Dict[str, List[float]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    clean_email = email.strip().lower()
    db = db_mongo.get_db()
    if db is not None:
        try:
            doc = db["users"].find_one({"email": clean_email}, {"_id": 0})
            if doc:
                return doc
        except Exception:
            pass
    return _USERS_MEMORY.get(clean_email)


def _save_user(user: Dict[str, Any]) -> None:
    clean_email = user["email"].strip().lower()
    _USERS_MEMORY[clean_email] = user
    db = db_mongo.get_db()
    if db is not None:
        try:
            db["users"].replace_one({"email": clean_email}, {"_id": user["user_id"], **user}, upsert=True)
        except Exception:
            logger.warning("Could not persist user to MongoDB; saved in volatile memory fallback", exc_info=True)


def _check_rate_limit(email: str) -> None:
    now = time.time()
    window = 600.0  # 10 minutes
    attempts = [t for t in _FAILED_LOGINS.get(email, []) if now - t < window]
    _FAILED_LOGINS[email] = attempts
    if len(attempts) >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please wait 10 minutes before retrying."
        )


def _record_failed_attempt(email: str) -> None:
    now = time.time()
    attempts = _FAILED_LOGINS.setdefault(email, [])
    attempts.append(now)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, description="Password must be at least 8 characters")
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    user_id: str
    access_token: str
    display_name: str


class ProfilePayload(BaseModel):
    sport: str
    skill: Optional[str] = None
    level: str = "intermediate"
    goal: Optional[str] = "overhead_power"
    playstyle: Optional[str] = "aggressive"
    injuries: List[str] = Field(default_factory=list)
    reference_player: Optional[str] = None


@router.post("/auth/register", status_code=201, response_model=AuthResponse)
def register_user(req: RegisterRequest) -> AuthResponse:
    clean_email = req.email.strip().lower()
    if _get_user_by_email(clean_email):
        raise HTTPException(status_code=409, detail="Email is already registered")

    salt = bcrypt.gensalt()
    pw_hash = bcrypt.hashpw(req.password.encode("utf-8"), salt).decode("utf-8")

    user_id = str(uuid4())
    user_record = {
        "user_id": user_id,
        "email": clean_email,
        "display_name": req.display_name.strip(),
        "password_hash": pw_hash,
        "created_at": _now(),
        "sport": None,
        "skill": None,
        "level": None,
    }
    _save_user(user_record)

    token = auth.issue_token(user_id=user_id, role="player")
    return AuthResponse(
        user_id=user_id,
        access_token=token,
        display_name=user_record["display_name"]
    )


@router.post("/auth/login", response_model=AuthResponse)
def login_user(req: LoginRequest) -> AuthResponse:
    clean_email = req.email.strip().lower()
    _check_rate_limit(clean_email)

    user = _get_user_by_email(clean_email)
    if not user:
        _record_failed_attempt(clean_email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(req.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        _record_failed_attempt(clean_email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Clear failed attempts on successful login
    _FAILED_LOGINS.pop(clean_email, None)

    token = auth.issue_token(user_id=user["user_id"], role="player")
    return AuthResponse(
        user_id=user["user_id"],
        access_token=token,
        display_name=user.get("display_name", "Athlete")
    )


@router.get("/auth/me")
def get_current_user_profile(request: Request) -> Dict[str, Any]:
    identity = auth.principal(request)
    user_id = identity["user_id"]

    # Search user in DB or memory
    db = db_mongo.get_db()
    user_doc = None
    if db is not None:
        try:
            user_doc = db["users"].find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
        except Exception:
            pass

    if not user_doc:
        if user_id in _USERS_MEMORY:
            user_doc = {k: v for k, v in _USERS_MEMORY[user_id].items() if k != "password_hash"}
        else:
            for u in _USERS_MEMORY.values():
                if u.get("user_id") == user_id:
                    user_doc = {k: v for k, v in u.items() if k != "password_hash"}
                    break

    if not user_doc:
        # Fallback for legacy user_1 or dev tokens
        return {
            "user_id": user_id,
            "email": f"{user_id}@tempo.local",
            "display_name": user_id.replace("_", " ").title(),
            "sport": "badminton",
            "level": "intermediate",
        }

    return user_doc


@router.post("/auth/logout")
def logout_user(request: Request) -> Dict[str, str]:
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("tempo_session", "")
    if token:
        auth.revoke_token(token)
    return {"status": "logged_out"}


@router.get("/profile")
def get_profile(request: Request) -> Dict[str, Any]:
    return get_current_user_profile(request)


@router.post("/profile")
def update_profile(req: ProfilePayload, request: Request) -> Dict[str, Any]:
    identity = auth.principal(request)
    user_id = identity["user_id"]

    db = db_mongo.get_db()
    update_data = {
        "sport": req.sport,
        "skill": req.skill,
        "level": req.level,
        "goal": req.goal,
        "playstyle": req.playstyle,
        "injuries": req.injuries,
        "reference_player": req.reference_player,
        "updated_at": _now(),
    }

    if db is not None:
        try:
            db["users"].update_one({"user_id": user_id}, {"$set": update_data})
        except Exception:
            pass

    # Update in-memory
    if user_id in _USERS_MEMORY:
        _USERS_MEMORY[user_id].update(update_data)
    else:
        found = False
        for u in _USERS_MEMORY.values():
            if u.get("user_id") == user_id:
                u.update(update_data)
                found = True
                break
        if not found:
            _USERS_MEMORY[user_id] = {"user_id": user_id, **update_data}

    return {"status": "profile_updated", "user_id": user_id, **update_data}
