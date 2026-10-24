# Tempo architecture verification — 24 October 2026

This pass verifies local behavior with external services disabled. Passing tests do not establish that Atlas, a Gemini deployment, HealthKit, or a booking service is connected.

## Corrections

- Player-specific latest telemetry and rolling windows no longer fall back to another player's data. Pairing resolves the player before querying their window.
- Pairing codes use 32 bits of cryptographic randomness instead of 100 possible suffixes. Ingestion validates existence and expiration, including MongoDB lookup after restart.
- Approval requires an explicit session and decision, loads that saved proposal, checks the supplied player name, and atomically claims a pending action. Unknown sessions, overrides, and duplicate attempts cannot dispatch.
- Staging does not call the external webhook. Webhook acceptance means dispatched awaiting confirmation; missing or failed webhooks never report a confirmed booking.
- Memory analytics calculate saved sessions. Atlas retains its `$facet` / `$bucket` pipeline. Both compare zone averages only when both zones exist and avoid claiming causation.
- Synthetic pose and OpenCV heuristic results require `TEMPO_DEMO_MODE=true`. Production requests without a reliable pose return 422. Missing telemetry cannot silently substitute a heart rate; estimated secondary values are listed in `estimated_fields`.
- Telemetry parsers reject malformed and nonfinite measurements and do not read client-supplied local file paths. JSON/XML sample exports pass.
- Pairing URLs preserve HTTPS using `TEMPO_PUBLIC_BASE_URL` when provided. The Android Retrofit base URL gets its required trailing slash.
- Gemini uses configurable `GEMINI_MODEL`, documented `generation_config` and JSON response format, and bounded request time. The analysis response exposes its actual coaching model or deterministic fallback.
- Heavy pose, model and approved-webhook calls run outside the async event loop. SSE queues are bounded. Health reports degraded storage and identifies process-local SSE.
- Automatic demo history and telemetry seeding is disabled outside demo mode. Reference cleanup is opt-in.

## Validation

From the backend directory:

```powershell
python -m unittest discover -s . -p test_architecture.py -v
```

46 offline regression tests pass after the Pose Landmarker migration (26 architecture tests and 20 pose/model-setup tests). Tests cover the HTTP views, demo pipeline, isolation queries for memory and mocked Atlas, pairing expiry and URLs, parsing, rolling averages, analytics, SDK call shape, saved proposals, concurrent claims, rejection, and duplicate approval prevention. They deliberately disable external credentials.

## Remaining integration work

1. **Pose extraction — migrated:** MediaPipe 1.1.1 Tasks Pose Landmarker now runs in VIDEO mode with the official Full model. Angles use estimated world coordinates; contact height uses image coordinates. The model is installed and the real model detects a person in a reference fixture. Synthetic line clips and a sideways-arm reference are rejected. The wrist must be above the head and shoulder, with visible/present joints and nondegenerate geometry. Actual overhead footage is still needed for sports accuracy validation. Highest reach is a contact-frame proxy, not detected impact; left-handed and multi-player analysis are unsupported. See `models/README.md` for setup and constraints.
2. **Apple Watch:** the companion is a manual simulator and export uploader. Its slider and timer do not access HealthKit sensors. Real streaming needs an iPhone/watch app or explicitly configured Shortcut. Sampling frequency is determined by the sender, not guaranteed at 1 Hz. Secondary values and fatigue scores remain estimates.
3. **Atlas:** no live cluster/index checks were performed in this pass. Verify the six-dimensional cosine vector index, reference metadata, time-series and geospatial indexes, persistence, and behavior during connection failure. In-memory fallback is volatile. Reference vectors and partner records are authored demo data.
4. **Gemini:** verify `GEMINI_MODEL` against an actual accessible model deployment. The existing `gemini-4-argon` identifier is retained as a configurable project default, not certified as available. Test real model output and failure observability with the account intended for this project.
5. **Saint:** validate the receiver contract and authentication, then exercise a staging environment. The receiver must honor the session idempotency key. Timeouts leave delivery ambiguous; automatic retry is deliberately avoided. Add callback reconciliation for confirmed bookings and operator recovery for stuck processing states.
6. **Identity and event isolation:** player names supplied in requests are not authenticated identities. Add authentication and ownership enforcement to all routes before external exposure. SSE currently broadcasts to every connected client in one process and has no replay, shared broker, or MongoDB Change Streams consumer. Use one local worker during development; implement authorized subscriptions and shared delivery for deployment.
7. **Operational hardening:** add bounded uploads and ZIP expansion, session retention, freshness checks for cached telemetry, consistent database failure handling, model response validation, structured logging, and production CORS configuration. Some synchronous database calls still execute in async routes.
8. **Demo history:** older versions may already have seeded fabricated user history or telemetry in Atlas. This pass does not delete existing records. Inspect and migrate that data deliberately before treating analytics as real observations.

## Local startup

For a manual demo with synthetic pose data:

```powershell
$env:TEMPO_DEMO_MODE = 'true'
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

For reliable-input mode omit that environment variable or set it to `false`. Run `python setup_pose_model.py` once before analyzing real videos. Use a clear single-player, full-body right-handed overhead clip; low-confidence or non-overhead clips return 422, while an unavailable inference engine returns 503. Set `TEMPO_PUBLIC_BASE_URL` to the externally reachable HTTPS origin when testing a tunnel. Do not expose the current unauthenticated API publicly.

Gemini request reference: https://ai.google.dev/api/interactions-api

## Pose migration verification

The combined 46-test suite passes with external credentials disabled. Real-model inference detected one person in Google's reference pose image and calculated finite world-coordinate angles. Both supplied 24-frame synthetic line videos and a five-frame static sideways-arm reference were processed by the real Tasks model and rejected by the HTTP pipeline with 422. These checks verify integration and failure handling, not stroke-angle accuracy. No real overhead sports clip has yet been validated.

Official API reference: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
