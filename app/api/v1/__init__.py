"""Legacy router exports, loaded only when explicitly requested.

Importing onboarding must not load the older Motor-backed service stack.
"""
from importlib import import_module

__all__ = ["sessions_router", "live_router", "cadence_router"]


def __getattr__(name):
    modules = {
        "sessions_router": "sessions",
        "live_router": "live",
        "cadence_router": "cadence",
    }
    if name not in modules:
        raise AttributeError(name)
    return import_module(f"{__name__}.{modules[name]}").router
