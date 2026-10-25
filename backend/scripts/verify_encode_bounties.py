#!/usr/bin/env python3
"""Encode London 2026: verify every claimed sponsor feature against the live stack.

Drives a throwaway athlete through the real backend (HTTP) and queries MongoDB Atlas directly, then
prints an ASCII scorecard. PASS = proven live; WARN = works but not on the named feature or not fully
configured (the detail says why and how to fix); FAIL = broken. Exit code is 1 if anything FAILs.

    uv run python backend/scripts/verify_encode_bounties.py            # needs the server on :8000
    uv run python backend/scripts/verify_encode_bounties.py --skip-video --keep-user
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import db_mongo, llm_config  # noqa: E402  (loads backend/.env)

FIXTURE = ROOT / "tests" / "fixtures" / "sample_clip.mp4"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def ascii_text(text: str) -> str:
    """Scorecard-safe: drop emoji/markdown that would break the fixed-width box."""
    clean = re.sub(r"\*+", "", text.encode("ascii", "ignore").decode())
    clean = re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", "", clean)  # _italics_, keep snake_case
    return " ".join(clean.split())


def message_body(formatted: str) -> str:
    """Saint messages are 'HEADER\n\nbody\n\nCTA'; quote the body."""
    parts = [p for p in formatted.split("\n\n") if p.strip()]
    return parts[1] if len(parts) > 1 else formatted


@dataclass
class Result:
    group: str
    name: str
    status: str  # PASS | WARN | FAIL | SKIP
    detail: str
    seconds: float


class Verifier:
    def __init__(self, base_url: str, skip_video: bool) -> None:
        self.base = base_url.rstrip("/")
        self.skip_video = skip_video
        self.results: List[Result] = []
        self.db = db_mongo.get_db()
        self.user_id: Optional[str] = None
        self.headers: Dict[str, str] = {}
        self.phone = "+44" + str(uuid.uuid4().int)[:10]
        self.session: Dict[str, Any] = {}

    # -- harness ---------------------------------------------------------------------------------
    def check(self, group: str, name: str, fn: Callable[[], tuple]) -> None:
        started = time.monotonic()
        try:
            status, detail = fn()
        except AssertionError as exc:
            status, detail = "FAIL", str(exc) or "assertion failed"
        except Exception as exc:  # report, keep going
            status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
            if os.environ.get("VERIFY_DEBUG"):
                traceback.print_exc()
        self.results.append(Result(group, name, status, ascii_text(detail), time.monotonic() - started))
        print(f"  [{status}] {group} :: {name}", flush=True)

    def post(self, path: str, timeout: float = 120, **kwargs: Any) -> Dict[str, Any]:
        res = requests.post(self.base + path, headers=self.headers, timeout=timeout, **kwargs)
        assert res.status_code in (200, 201, 202), f"POST {path} -> HTTP {res.status_code}: {res.text[:160]}"
        return res.json()

    def get(self, path: str) -> Dict[str, Any]:
        res = requests.get(self.base + path, headers=self.headers, timeout=30)
        assert res.status_code == 200, f"GET {path} -> HTTP {res.status_code}: {res.text[:160]}"
        return res.json()

    def memory(self) -> Dict[str, Any]:
        return self.db[db_mongo.ATHLETE_MEMORY_COLLECTION].find_one({"user_id": self.user_id}, {"_id": 0}) or {}

    # -- preflight ---------------------------------------------------------------------------------
    def preflight(self) -> bool:
        assert self.db is not None, "MongoDB Atlas is unreachable: set MONGODB_URI in backend/.env"
        try:
            requests.get(self.base + "/health", timeout=5).raise_for_status()
        except Exception as exc:
            sys.exit(f"Backend not reachable at {self.base} ({exc}). Start it with ./scripts/dev.sh")
        email = f"encode_verify_{int(time.time())}@tempo.app"
        reg = requests.post(self.base + "/api/v1/auth/register", timeout=15,
                            json={"email": email, "password": "EncodeVerify2026!", "display_name": "Encode Judge"})
        assert reg.status_code == 201, f"register failed: {reg.text[:160]}"
        self.user_id = reg.json()["user_id"]
        self.headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        stored = self.db["users"].count_documents({"user_id": self.user_id})
        print(f"Athlete {self.user_id} ({email}); account persisted to Atlas: {bool(stored)}")
        return True

    # -- Gemini 4 Argon ----------------------------------------------------------------------------
    def argon_tool_calling(self) -> tuple:
        body = self.post("/api/v1/coach/converse", json={
            "message": "I play badminton, I'm intermediate and I want to train 3 times a week at 6pm",
            "channel": "app"})
        tools = body["tool_actions_taken"]
        mem = self.memory()
        assert body["llm_source"] == "gemini", f"converse fell back to rules ({body['llm_model']}); check GEMINI_API_KEY"
        assert {"set_sport_and_goals", "update_training_schedule"} <= set(tools), f"tools called: {tools}"
        assert mem.get("sport") == "badminton" and mem.get("reminder_schedule"), "athlete_memory not mutated"
        return "PASS", (f"{body['llm_model']} called {', '.join(tools)}; athlete_memory now sport={mem['sport']}, "
                        f"level={mem.get('level')}, days={','.join(d[:3] for d in mem['reminder_schedule']['days_of_week'])}")

    def argon_multimodal(self) -> tuple:
        if self.skip_video:
            return "SKIP", "--skip-video"
        assert FIXTURE.exists(), f"missing {FIXTURE}"
        mem = self.memory()
        active = next((n for n in mem.get("curriculum_nodes") or [] if n["status"] == "active"), None)
        meta = {"user_id": self.user_id, "sport": "badminton", "stroke_type": "overhead_clear", "telemetry": [],
                **({"node_id": active["id"]} if active else {})}
        with open(FIXTURE, "rb") as clip:
            accepted = self.post("/api/v1/sessions/ingest", data={"metadata": json.dumps(meta)},
                                 files={"video": ("sample_clip.mp4", clip, "video/mp4")})
        deadline = time.time() + 180
        record: Dict[str, Any] = {}
        while time.time() < deadline:
            record = self.get(f"/api/v1/sessions/{accepted['session_id']}")
            if record["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(2)
        assert record.get("status") == "COMPLETED", f"session {record.get('status')}: {record.get('error_message')}"
        self.session = record
        pose = (record.get("gemini_feedback") or {}).get("pose_analysis") or {}
        card = (record.get("gemini_feedback") or {}).get("pro_comparison_card") or {}
        assert not pose.get("used_fallback", True), "pose extraction fell back to synthetic angles"
        elbow = next((a for a in card.get("angles", []) if a["metric"] == "right_elbow_contact_deg"), {})
        detail = (f"{record.get('llm_model')} | video_used={record.get('video_used')} | pose {pose.get('engine')} "
                  f"{pose.get('valid_pose_frames')} frames | elbow {elbow.get('athlete_deg')} vs "
                  f"{card.get('matched_pro')} {elbow.get('pro_deg')} | score {record.get('overall_score')} -> "
                  f"{(record.get('adaptation') or {}).get('action')}")
        if record.get("llm_source") != "gemini":
            return "FAIL", f"analysis used {record.get('llm_model')} ({record.get('llm_error')})"
        if not record.get("video_used"):
            return "WARN", "Gemini analysed pose only (video upload skipped; GEMINI_SEND_VIDEO?) | " + detail
        return "PASS", detail

    # -- MongoDB Atlas -----------------------------------------------------------------------------
    def mongo_document_memory(self) -> tuple:
        mem = self.memory()
        nodes = mem.get("curriculum_nodes") or []
        shapes = sorted({"drill" if n.get("drill_spec") else "concept" for n in nodes} |
                        ({"remedial"} if any(n.get("remedial_quiz") for n in nodes) else set()))
        channels = [t.get("channel") for t in mem.get("chat_history") or []]
        assert nodes and channels, "athlete_memory lacks curriculum or chat state"
        return "PASS", (f"1 document: {len(nodes)} lesson nodes (shapes: {', '.join(shapes)}), "
                        f"{len(channels)} chat turns via {sorted(set(channels))}, "
                        f"{len(mem.get('recent_flaws') or [])} measured flaws, schedule + focus in place")

    def mongo_vector_search(self) -> tuple:
        idx = next(iter(self.db[db_mongo.STROKES_COLLECTION].list_search_indexes(db_mongo.VECTOR_INDEX_NAME)), None)
        assert idx and idx.get("queryable"), f"{db_mongo.VECTOR_INDEX_NAME} missing or not queryable"
        vector = self.session.get("kinematic_vector") or [0.95, 0.91, 0.92, 0.85, 0.8, 0.93]
        hits = list(self.db[db_mongo.STROKES_COLLECTION].aggregate([
            {"$vectorSearch": {"index": db_mongo.VECTOR_INDEX_NAME, "path": "pose_vector", "queryVector": vector,
                               "numCandidates": 20, "limit": 3,
                               "filter": {"is_pro_reference": True, "sport": "badminton"}}},
            {"$project": {"_id": 0, "player_name": 1, "sport": 1, "score": {"$meta": "vectorSearchScore"}}}]))
        assert hits and all(h["sport"] == "badminton" for h in hits), f"unexpected hits: {hits}"
        fields = [f["path"] + ":" + f["type"] for f in idx["latestDefinition"]["fields"]]
        return "PASS", (f"$vectorSearch on 6D pose_vector ({', '.join(fields)}) -> "
                        + ", ".join(f"{h['player_name']} {h['score']:.4f}" for h in hits))

    def mongo_time_series(self) -> tuple:
        opts = self.db[db_mongo.WATCH_TS_COLLECTION].options().get("timeseries")
        assert opts and opts.get("timeField") == "timestamp", "watch_telemetry_ts is not a time-series collection"
        now = datetime.now(timezone.utc)
        for i, hr in enumerate([142, 151, 158, 166, 171, 175]):
            db_mongo.save_live_watch_telemetry(self.user_id, {
                "sampled_at": (now - timedelta(seconds=10 * (6 - i))).isoformat(), "heart_rate_bpm": hr,
                "fatigue_index": 50 + 6 * i})
        window = db_mongo.get_watch_timeseries_window(user_name=self.user_id, limit=6)
        assert window["aggregation_method"] == "mongodb_atlas_timeseries_window_fields", window["aggregation_method"]
        latest = window["samples"][0]
        return "PASS", (f"{window['sample_count']} samples in time-series ({opts['granularity']}, meta={opts['metaField']}); "
                        f"$setWindowFields rolling HR {latest['rolling_avg_hr_bpm']:.1f} bpm, "
                        f"fatigue {latest['rolling_avg_fatigue_index']:.1f}")

    def mongo_geospatial(self) -> tuple:
        indexes = self.db[db_mongo.FACILITIES_COLLECTION].index_information()
        assert any(v.get("key") == [("location_geojson", "2dsphere")] for v in indexes.values()), "no 2dsphere index"
        found = db_mongo.find_nearby_facilities(51.5248, -0.1328, limit=3)
        assert found["method"] == "mongodb_nearSphere_2dsphere" and found["facilities"], found["method"]
        return "PASS", "$nearSphere from UCL -> " + ", ".join(
            f"{f['name']} {f['distance_km']}km" for f in found["facilities"])

    def mongo_atlas_search(self) -> tuple:
        result = db_mongo.search_drills("elbow extension at contact", sport="badminton", limit=3)
        titles = ", ".join(d["title"] for d in result["drills"]) or "no hits"
        if result["method"] == "atlas_search":
            return "PASS", f"$search ({db_mongo.DRILLS_SEARCH_INDEX_NAME}) -> {titles}"
        others = []
        for col in self.db.list_collection_names():
            try:
                others += [f"{col}.{i['name']}" for i in self.db[col].list_search_indexes()]
            except Exception:
                pass
        return "WARN", (f"{db_mongo.DRILLS_SEARCH_INDEX_NAME} not created: cluster is at its 3 search-index limit "
                        f"({', '.join(others)}). Served by {result['method']} -> {titles}. Fix: delete an unused index "
                        "in Atlas, then rerun backend/scripts/reset_fresh.py")

    def mongo_change_stream(self) -> tuple:
        col = self.db[db_mongo.ATHLETE_MEMORY_COLLECTION]
        received: List[Dict[str, Any]] = []
        ready = threading.Event()

        def watch() -> None:
            with col.watch([{"$match": {"fullDocument.user_id": self.user_id}}], full_document="updateLookup",
                           max_await_time_ms=500) as stream:
                ready.set()
                end = time.time() + 15
                while time.time() < end and not received:
                    change = stream.try_next()
                    if change and "last_completed_node" in (change.get("updateDescription") or {}).get("updatedFields", {}):
                        received.append(change)

        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        ready.wait(10)
        time.sleep(0.5)
        mem = self.memory()
        node = next((n for n in mem.get("curriculum_nodes") or [] if n["status"] == "active"), None)
        assert node, "no active lesson to complete"
        db_mongo.set_lesson_node_status(self.user_id, node["id"], "completed")
        thread.join(16)
        assert received, "db.athlete_memory.watch() saw no event within 15s"
        queue = self.db[db_mongo.SAINT_QUEUE_COLLECTION]
        deadline, server_queued = time.time() + 10, None
        while time.time() < deadline and not server_queued:
            server_queued = queue.find_one({"user_id": self.user_id, "type": "lesson_completed", "node_id": node["id"]})
            time.sleep(0.5)
        if not server_queued:
            return "WARN", ("change stream delivered the update, but the server's watcher didn't queue a Saint "
                            "notification (is TEMPO_DISABLE_CHANGE_STREAM set?)")
        return "PASS", (f"db.athlete_memory.watch() -> {received[0]['operationType']} on {node['id']}; server watcher "
                        f"queued Saint '{server_queued['type']}' via {server_queued.get('channel')}")

    # -- Saint agent runtime -----------------------------------------------------------------------
    def _next_session(self) -> datetime:
        schedule = self.memory()["reminder_schedule"]
        now = datetime.now(timezone.utc)
        for i in range(1, 9):
            day = now + timedelta(days=i)
            if day.strftime("%A") in schedule["days_of_week"]:
                hhmm = (schedule.get("day_times") or {}).get(day.strftime("%A")) or schedule["time_utc"]
                h, m = map(int, hhmm.split(":"))
                return day.replace(hour=h, minute=m, second=0, microsecond=0)
        raise AssertionError("no scheduled training day")

    def saint_cadence(self) -> tuple:
        session = self._next_session()
        result = self.post("/api/v1/cadence/trigger", json={"now": (session - timedelta(hours=5)).isoformat(),
                                                           "dispatch": False})["results"][0]
        assert result["kind"] in ("next_session", "missed_drill"), result
        logged = self.db[db_mongo.SAINT_QUEUE_COLLECTION].count_documents({"user_id": self.user_id,
                                                                          "type": f"cadence_{result['kind']}"})
        mirror = self.db["user_schedules"].find_one({"_id": self.user_id}) or {}
        assert logged and mirror.get("days_of_week"), "cadence not logged or schedule not mirrored"
        return "PASS", (f"{result['event_type']}/{result['kind']} from athlete_memory schedule "
                        f"({', '.join(d[:3] for d in mirror['days_of_week'])} {mirror.get('target_time_utc')} UTC); "
                        f"logged to saint_notifications: \"{message_body(result['message'])[:110]}\"")

    def saint_priming(self) -> tuple:
        session = self._next_session()
        result = self.post("/api/v1/cadence/trigger", json={"now": (session - timedelta(minutes=15)).isoformat(),
                                                           "dispatch": True})["results"][0]
        assert result["event_type"] == "PRE_SESSION_PRIMING", f"got {result['event_type']}/{result['kind']}"
        text = message_body(result["message"])
        dispatch = result["dispatch"]
        detail = f"15 min before {session:%a %H:%M} UTC: \"{text[:160]}\" | dispatch {dispatch['status']}"
        if not dispatch["dispatched"]:
            return "WARN", detail + " (set SAINT_WEBHOOK_URL so Saint delivers it to WhatsApp)"
        receipt = self.db["saint_deliveries"].find_one({"user_id": self.user_id, "event_type": "PRE_SESSION_PRIMING"})
        assert receipt, "dispatched, but no delivery receipt recorded"
        assert receipt.get("to") and receipt["to"] == self.phone_for_receipts(), f"receipt addressed to {receipt.get('to')}"
        url = os.environ.get("SAINT_WEBHOOK_URL", "")
        where = ("loopback receipt endpoint; point SAINT_WEBHOOK_URL at the Saint agent for real WhatsApp sends"
                 if "127.0.0.1" in url or "localhost" in url else url)
        return "PASS", detail + f" -> receipt {receipt['receipt_id'][:8]} to {receipt['to']} ({where})"

    def phone_for_receipts(self) -> Optional[str]:
        return self.memory().get("phone_number")

    def saint_whatsapp(self) -> tuple:
        self.post("/api/v1/coach/whatsapp/link", json={"phone_number": self.phone})
        body = self.post("/api/v1/webhooks/whatsapp", json={
            "from_number": f"whatsapp:{self.phone}", "body": "What should I focus on this week?"})
        assert body.get("linked") and body["user_id"] == self.user_id and body["channel"] == "whatsapp", body
        last = (self.memory().get("chat_history") or [{}])[-1]
        assert last.get("channel") == "whatsapp", "WhatsApp turn not stored in shared memory"
        return "PASS", (f"inbound from {self.phone} resolved to athlete, routed to {body['llm_model']} "
                        f"(whatsapp channel), reply queued to {body['outbound']['to']}: "
                        f"\"{body['reply_text'][:110]}\"")

    # -- cleanup + report --------------------------------------------------------------------------
    def cleanup(self) -> None:
        if not self.user_id:
            return
        for col, key in ((db_mongo.ATHLETE_MEMORY_COLLECTION, "user_id"), (db_mongo.SAINT_QUEUE_COLLECTION, "user_id"),
                         ("users", "user_id"), ("android_sessions", "user_id"), ("user_schedules", "_id"),
                         ("saint_deliveries", "user_id"),
                         (db_mongo.WATCH_TS_COLLECTION, "metadata.user_name")):
            try:
                self.db[col].delete_many({key: self.user_id})
            except Exception:
                pass
        self.db[db_mongo.STROKES_COLLECTION].delete_many({"user_name": self.user_id})


def render(results: List[Result], model: str) -> str:
    width = 100
    line = "+" + "-" * (width - 2) + "+"
    out = [line, "|" + "ENCODE LONDON 2026  ::  TEMPO SPONSOR VERIFICATION".center(width - 2) + "|",
           "|" + f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}  ::  model {model}  ::  db {db_mongo.DB_NAME}".center(width - 2) + "|",
           line]
    group = None
    for r in results:
        if r.group != group:
            group = r.group
            out.append("| " + group.upper().ljust(width - 4) + " |")
            out.append("|" + "." * (width - 2) + "|")
        head = f"[{r.status}] {r.name}"
        out.append("| " + f"{head:<64}{r.seconds:>7.1f}s".ljust(width - 4) + " |")
        for chunk in textwrap.wrap(r.detail, width - 12):
            out.append("|        " + chunk.ljust(width - 10) + " |")
        out.append("|" + " " * (width - 2) + "|")
    counts = {s: sum(r.status == s for r in results) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    out.append(line)
    out.append("| " + "  ".join(f"{k} {v}" for k, v in counts.items()).center(width - 4) + " |")
    out.append(line)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("TEMPO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--skip-video", action="store_true", help="skip the ~45s multimodal clip analysis")
    parser.add_argument("--keep-user", action="store_true", help="leave the verification athlete in Atlas")
    args = parser.parse_args()

    v = Verifier(args.base_url, args.skip_video)
    print(f"Verifying against {v.base} ...")
    v.preflight()
    try:
        g, m, s = "Gemini 4 Argon", "MongoDB Atlas", "Saint agent runtime"
        v.check(g, "(b) Tool-calling agent: POST /api/v1/coach/converse", v.argon_tool_calling)
        v.check(g, "(a) Multimodal video + pose biomechanical analysis", v.argon_multimodal)
        v.check(m, "1. Document core memory (athlete_memory)", v.mongo_document_memory)
        v.check(m, "2. Atlas Vector Search ($vectorSearch, 6D pose)", v.mongo_vector_search)
        v.check(m, "3. Time-Series (watch_telemetry_ts + $setWindowFields)", v.mongo_time_series)
        v.check(m, "4. Geospatial 2dsphere ($nearSphere courts)", v.mongo_geospatial)
        v.check(m, "5a. Atlas Search ($search drills)", v.mongo_atlas_search)
        v.check(m, "5b. Change Streams (db.athlete_memory.watch())", v.mongo_change_stream)
        v.check(s, "Proactive cadence scheduling", v.saint_cadence)
        v.check(s, "WhatsApp omnichannel routing", v.saint_whatsapp)
        v.check(s, "Pre-session mental priming", v.saint_priming)
    finally:
        if not args.keep_user:
            v.cleanup()
    print()
    print(render(v.results, llm_config.GEMINI_MODEL))
    return 1 if any(r.status == "FAIL" for r in v.results) else 0


if __name__ == "__main__":
    sys.exit(main())
