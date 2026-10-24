# Tempo shared backend and Android integration — 24 October 2026

## One runtime

From the repository root:

```powershell
python -m pip install -r requirements.txt
python backend/setup_pose_model.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The existing `uvicorn main:app` command from `backend/` still works. `app.main`
now aliases `backend.main.app`: both expose the same Android session API, pose
pipeline, Watch pairing, analytics, dashboards and approval endpoints. They share
the PyMongo database configuration in backend/.env. Do not launch both servers.

## How the implementations differed

| Area | Existing measured backend | Imported Android service modules |
| --- | --- | --- |
| Pose | MediaPipe world-coordinate extraction and explicit failure | Gemini video report, with automatic mock report when no key exists |
| Sessions | Canonical stroke records plus Android adapter | Android-first session envelope and processing statuses |
| Database | PyMongo in sports_coach_db | Motor in the same sports_coach_db |
| Telemetry | Watch pairing, latest player state, sports_coach_db.watch_telemetry_ts | Per-upload Health Connect metadata |
| Feedback | Measured pose, coaching model provenance, drills | Four phases, scores, audio text and richer SDUI |
| Operations | Watch analytics and explicit approval controls | Upload storage, separate live and cadence modules |

Production uses the measured backend plus Android envelopes, not two analysis
dispatchers. Imported app/api and app/services remain for component tests and
future porting; they are not mounted by app.main. Tests/conftest.py constructs an
explicit isolated legacy router harness. Its tests do not certify the production
pipeline. The imported signed-video-URL route, persistent video storage, four-phase
Gemini reports, and external cadence delivery have not been ported to the shared
runtime. Current canonical uploads accept video files and delete staging files
after processing; Android retains its own clip for playback.

## Session and upload contract

Android supplies session_id in multipart metadata and uses that ID for Room,
WorkManager, backend records and polling. The server generates an ID only for
clients that omit it. A repeated ID with identical parsed metadata and video bytes
returns the existing status without another analysis. Changed metadata, player or
video with the same ID returns 409. Admission is serialized within one worker;
cross-worker atomic idempotency is not implemented. Use one backend worker.

Worker retries retain the selected upload file, preserve the ID and do not replace
an active upload. Transient network/429/5xx failures retry at most three times;
other errors become UPLOAD_FAILED with a persisted message. The analysis screen
checks WorkManager and Room, stops on failed/cancelled uploads, bounds repeated
network errors and has a 15-minute wait limit. Retry re-enqueues a failed upload
with its original metadata. A failed backend analysis needs a newly recorded
session; Retry only refreshes its status.

## Player and Watch data

Clip review exposes a saved Player ID, initially user_1. This must exactly match
the player selected in the iPhone/forwarding Watch connection. It is an identifier,
not authentication. The worker captures the ID in its work input so changing the
profile later cannot reassign an in-flight session.

No Android health collector is connected yet. Uploads therefore send an empty
telemetry list, allowing the server to fetch only that player's paired Watch
reading. No hard-coded BPM/calorie samples are sent. Missing data fails explicitly;
cached Watch receipts older than five minutes are rejected. received_at is an
ingestion receipt time, not proof that the Health sensor sample itself is recent.
The receiver now requires sampled_at from the actual Health sample Start Date;
that ISO 8601 value is preserved in the relay, ETL, latest state and Atlas time-series.
Missing, naive, future or older-than-five-minute sensor timestamps are rejected.
Sensor timestamps alone do not establish synchronization with the recorded stroke.
Render currently hosts only the HTTPS receiver; the forwarding bridge must run
for these readings to reach the canonical database.

## Feedback and visual correction

DrillCardWidget includes id, title, instruction, target_reps and focus_cue. Ten
target reps is a practice prescription default, not a measured performance result.
An uncalibrated overall score remains absent and displays Unavailable. Four sample
phase timings and diagnoses are not substituted. When MediaPipe has a measured
highest-reach timestamp, the API returns a single explicitly labelled contact-proxy
phase with no invented score. Actual racket impact is not detected.

Visual correction uses only this session's video and detected landmarks; it never
selects the most recent unrelated clip or substitutes a synthetic athlete track.
New measured-only cache names bypass earlier synthetic caches. Up to 120 samples
span the entire clip. Missing video, skeletons and phase data have explicit UI
messages. Reference archetype assets are still authored examples, not validated
professional motion-capture data. SDUI action persistence remains future work.

## Build and test limits

Mock API selection and API base URL are unchanged at the user's request. Set real
mode and a reachable full-backend URL before device integration testing; the Render
Watch receiver URL does not implement the analysis API. The checked-in Android SDK
path points to another developer's Mac. Configure a local SDK before APK assembly.

Backend regressions run with external services disabled:
`python -m unittest discover -s backend -p "test_*.py" -q`.
Install requirements-dev.txt for the historical pytest component suite. Passing
offline tests does not verify Atlas, a live Gemini deployment, Android compilation,
camera behavior or real-device Watch/video synchronization. Authentication and ownership checks are now implemented; reliable hosted jobs,
full-backend deployment and calibrated sports accuracy validation remain required.

Verified in this integration pass: 74 canonical backend unittest regressions and
26 imported-service pytest component tests passed with external services disabled.
Gradle configured the project but :app:testDebugUnitTest stopped at SDK location
not found; Kotlin tests and APK assembly have not run. Added JVM regressions cover
stable mock upload IDs, HTTP error status, player identity, drill decoding and
phase timestamps without fabricated scores. A real phone/video/Watch session has
not been tested in this pass. No changes were pushed or deployed.

All MongoDB record types now share sports_coach_db. Database selectors reject conflicting overrides. Restart existing processes after pulling; historical records in older databases are not moved by this change.
