"""Compatibility entry point: Android sessions and Watch share one backend.

Run ``python -m uvicorn app.main:app`` from the repository root.
Legacy service modules remain importable for component tests, not mounted here.
"""
from backend.main import app


def create_application():
    """Return the canonical application; no second database or analysis dispatcher."""
    return app
