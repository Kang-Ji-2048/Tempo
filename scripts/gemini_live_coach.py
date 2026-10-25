#!/usr/bin/env python3
"""Gemini Live companion for Coach Thea: same as gemini_coach_cli.py, plus a live status view.

    uv run python scripts/gemini_live_coach.py --email you@tempo.app
    uv run python scripts/gemini_live_coach.py --email you@tempo.app \
        --once "How did my last live set on the Pixel go? Unlock my next lesson and give me a 5-rep jump smash drill"

Every message runs on the shared athlete_memory in MongoDB Atlas, so the Pixel's Home screen picks the
change up on its next refresh (it polls the memory version every few seconds). /status prints the same
Tempo context brief Saint and the WhatsApp hand-off use; /memory shows the raw fields.
Voice: run this inside the Gemini app's Live mode or any dictation tool; the companion itself is text.
"""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("gemini_coach_cli.py")), run_name="__main__")
