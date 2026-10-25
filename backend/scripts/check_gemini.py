#!/usr/bin/env python3
"""
backend/scripts/check_gemini.py - Diagnostic for Gemini 4 Argon connectivity and billing status.
Runs:
1. Key and model diagnostic
2. Model availability check (client.models.list())
3. Minimal text generation call
4. Structured-output call with BiomechanicalReport response_schema and MEASURED DATA
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import dotenv
dotenv.load_dotenv(backend_dir / ".env", override=False)

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError

from llm_config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_THINKING_LEVEL,
    mask_key,
    update_ai_status,
)


def diagnose_error(exc: Exception) -> str:
    msg = str(exc)
    exc_name = exc.__class__.__name__

    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "too_many_requests" in msg:
        if "spending cap" in msg.lower() or "tier-spend-caps" in msg.lower():
            return "Monthly spending cap exceeded on this billing account. Visit https://ai.studio/billing to raise tier spend caps."
        return "Quota exceeded (HTTP 429). The Gemini API rate limit or project quota was reached."
    elif "403" in msg or "PERMISSION_DENIED" in msg:
        if "free tier" in msg.lower() or "not available" in msg.lower():
            return "Gemini 4 Argon is not available on free-tier keys. Upgrade project billing in Google AI Studio."
        return "Permission denied (HTTP 403). Check project access and API key permissions."
    elif "404" in msg or "NOT_FOUND" in msg:
        return f"Model '{GEMINI_MODEL}' not found for this API key. Verify model availability or permissions."
    elif "401" in msg or "UNAUTHENTICATED" in msg:
        return "Invalid or unauthenticated API key. Check GEMINI_API_KEY in backend/.env."
    return f"{exc_name}: {msg}"


def run_diagnostics() -> int:
    print("=" * 60)
    print("TEMPO GEMINI 4 ARGON DIAGNOSTIC")
    print("=" * 60)

    # 1. Print masked key and target model
    print(f"[1/4] Key & Model Config:")
    print(f"      API Key: {mask_key(GEMINI_API_KEY)}")
    print(f"      Target Model: {GEMINI_MODEL}")
    print(f"      Thinking Level: {GEMINI_THINKING_LEVEL}")

    if not GEMINI_API_KEY:
        print("      FAILED: GEMINI_API_KEY is missing from environment/backend/.env")
        update_ai_status(False, error="GEMINI_API_KEY missing")
        return 1

    client = genai.Client(api_key=GEMINI_API_KEY)

    # 2. List available models
    print("\n[2/4] Checking Model Availability via client.models.list()...")
    argon_found = False
    try:
        models = list(client.models.list())
        model_names = [m.name for m in models]
        argon_found = any(GEMINI_MODEL in name for name in model_names)
        print(f"      OK: Successfully queried {len(models)} models.")
        print(f"      Model '{GEMINI_MODEL}' in catalog: {'YES' if argon_found else 'NO'}")
        if not argon_found:
            matching = [n for n in model_names if "argon" in n.lower() or "gemini-4" in n.lower()]
            print(f"      Alternative candidates: {matching}")
    except Exception as e:
        diagnosis = diagnose_error(e)
        print(f"      FAILED: {e.__class__.__name__} - {e}")
        print(f"      Diagnosis: {diagnosis}")
        update_ai_status(False, error=str(e))
        return 2

    # 3. Minimal text call
    print("\n[3/4] Performing minimal text generation call...")
    text_ok = False
    start_t = time.perf_counter()
    try:
        # Use types.GenerateContentConfig with thinking_level
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL)
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Say 'Tempo ready' in exactly two words.",
            config=config,
        )
        latency = int((time.perf_counter() - start_t) * 1000)
        output_text = (response.text or "").strip()
        print(f"      OK ({latency} ms): Received response: '{output_text}'")
        text_ok = True
    except Exception as e:
        latency = int((time.perf_counter() - start_t) * 1000)
        diagnosis = diagnose_error(e)
        print(f"      FAILED ({latency} ms): {e.__class__.__name__}: {e}")
        print(f"      Diagnosis: {diagnosis}")
        update_ai_status(False, error=str(e), latency_ms=latency)
        # Note: Do not return immediately, test structured call to record full diagnostics

    # 4. Structured-output call with BiomechanicalReport schema
    print("\n[4/4] Performing structured-output call with BiomechanicalReport schema...")
    report_schema = {
        "type": "OBJECT",
        "properties": {
            "overall_score": {"type": "INTEGER"},
            "verification_status": {"type": "STRING", "enum": ["PASS", "FAIL"]},
            "primary_flaw": {"type": "STRING"},
            "biomechanical_diagnosis": {"type": "STRING"},
            "live_drill_prescription": {"type": "STRING"},
            "concise_audio_cue": {"type": "STRING"},
        },
        "required": [
            "overall_score",
            "verification_status",
            "primary_flaw",
            "biomechanical_diagnosis",
            "live_drill_prescription",
            "concise_audio_cue",
        ],
    }

    test_prompt = (
        "MEASURED DATA:\n"
        "Athlete: user_1 | Sport: Badminton | Stroke: Overhead Clear\n"
        "Measured angles: right_elbow_contact_deg = 158.4 deg (threshold = 165.0 deg)\n"
        "Shoulder abduction: 142.0 deg | Trunk arch: 161.5 deg\n"
        "Heart rate: 168 bpm\n"
        "Task: Generate a diagnostic biomechanical report strictly following the schema."
    )

    structured_ok = False
    start_t = time.perf_counter()
    try:
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=GEMINI_THINKING_LEVEL),
            response_mime_type="application/json",
            response_schema=report_schema,
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=test_prompt,
            config=config,
        )
        latency = int((time.perf_counter() - start_t) * 1000)
        raw_text = response.text or "{}"
        parsed = json.loads(raw_text)
        print(f"      OK ({latency} ms): Structured JSON successfully generated:")
        print(f"         overall_score: {parsed.get('overall_score')}")
        print(f"         verification_status: {parsed.get('verification_status')}")
        print(f"         primary_flaw: {parsed.get('primary_flaw')}")
        print(f"         audio_cue: {parsed.get('concise_audio_cue')}")
        structured_ok = True
        update_ai_status(True, latency_ms=latency)
    except Exception as e:
        latency = int((time.perf_counter() - start_t) * 1000)
        diagnosis = diagnose_error(e)
        print(f"      FAILED ({latency} ms): {e.__class__.__name__}: {e}")
        print(f"      Diagnosis: {diagnosis}")
        update_ai_status(False, error=str(e), latency_ms=latency)

    print("\n" + "=" * 60)
    if text_ok and structured_ok:
        print("SUMMARY: ALL GEMINI 4 ARGON CHECKS PASSED.")
        print("=" * 60)
        return 0
    else:
        print("SUMMARY: GEMINI 4 ARGON DIAGNOSTIC FAILED.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(run_diagnostics())
