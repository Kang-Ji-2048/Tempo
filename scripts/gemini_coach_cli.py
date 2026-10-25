#!/usr/bin/env python3
"""Chat with Coach Thea over the Gemini adapter, editing the same athlete_memory the app shows.

    uv run python scripts/gemini_coach_cli.py --email you@tempo.app            # prompts for password
    uv run python scripts/gemini_coach_cli.py --token <bearer> --user-id <id>  # admin acting for a user
    uv run python scripts/gemini_coach_cli.py --email you@tempo.app \\
        --once "I want to focus on my backhand net clearance and move my Tuesday session to 7pm"

Each reply prints the tools Thea called and what changed in athlete_memory; pull to refresh
Home on the Pixel to see the same change. Commands: /memory, /quit.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any, Dict, Optional

import requests

WATCHED = ("sport", "level", "intensity", "skill_focus", "focus_note", "reminder_schedule")


def login(base: str, email: str, password: str) -> Dict[str, Any]:
    res = requests.post(f"{base}/api/v1/auth/login", json={"email": email, "password": password}, timeout=15)
    if res.status_code != 200:
        sys.exit(f"Login failed ({res.status_code}): {res.text[:200]}")
    return res.json()


def memory_snapshot(base: str, headers: Dict[str, str]) -> Dict[str, Any]:
    res = requests.get(f"{base}/api/v1/coach/memory", headers=headers, timeout=15)
    res.raise_for_status()
    return res.json()


def describe(value: Any) -> str:
    if isinstance(value, dict) and "days_of_week" in value:
        moved = "".join(f", {d[:3]} {t}" for d, t in (value.get("day_times") or {}).items())
        return f"{', '.join(d[:3] for d in value['days_of_week'])} at {value.get('time_utc')} UTC{moved}"
    return json.dumps(value) if isinstance(value, (dict, list)) else str(value)


def print_changes(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    changed = [k for k in WATCHED if before.get(k) != after.get(k)]
    if not changed:
        print("  (no memory fields changed)")
    for key in changed:
        print(f"  {key}: {describe(before.get(key))} -> {describe(after.get(key))}")


def send(base: str, headers: Dict[str, str], message: str, target: Dict[str, Optional[str]]) -> None:
    before = memory_snapshot(base, headers)["athlete_memory"] if not any(target.values()) else {}
    res = requests.post(f"{base}/api/v1/webhooks/gemini", headers=headers, timeout=120,
                        json={"message": message, **{k: v for k, v in target.items() if v}})
    if res.status_code != 200:
        print(f"! {res.status_code}: {res.text[:300]}")
        return
    body = res.json()
    print(f"\nThea ({body.get('llm_source')}): {body['reply_text']}")
    print(f"  tools: {', '.join(body['tool_actions_taken']) or 'none'}")
    print_changes(before or {}, body["athlete_memory"])
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("TEMPO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", help="sign in as this athlete (prompts for password)")
    parser.add_argument("--password", default=os.environ.get("TEMPO_PASSWORD"))
    parser.add_argument("--token", default=os.environ.get("TEMPO_TOKEN"), help="existing Bearer token")
    parser.add_argument("--user-id", help="act for this athlete (admin token only)")
    parser.add_argument("--target-email", help="act for the athlete with this email (admin token only)")
    parser.add_argument("--once", help="send one message and exit")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    token = args.token
    if not token:
        if not args.email:
            parser.error("pass --email (or --token)")
        session = login(base, args.email, args.password or getpass.getpass("Tempo password: "))
        token = session["access_token"]
        print(f"Signed in as {session.get('display_name') or args.email} ({session['user_id']})")
    headers = {"Authorization": f"Bearer {token}"}
    target = {"user_id": args.user_id, "email": args.target_email}

    if args.once:
        send(base, headers, args.once, target)
        return
    print("Talk to Coach Thea. /memory shows your shared memory, /quit exits.\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return
        if line == "/memory":
            snap = memory_snapshot(base, headers)
            for key in WATCHED:
                print(f"  {key}: {describe(snap['athlete_memory'].get(key))}")
            print(f"  plan: {snap['header'].get('completed_nodes')}/{snap['header'].get('total_nodes')} lessons done\n")
            continue
        send(base, headers, line, target)


if __name__ == "__main__":
    main()
