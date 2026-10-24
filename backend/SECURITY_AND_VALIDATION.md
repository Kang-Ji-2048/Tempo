# Tempo: timestamps, real-video checks and access control

Implemented locally on 24 October 2026. Nothing from this pass has been pushed or deployed. The Android LAN URL and mock-mode selection are unchanged.

Sumanth built the Android recording, upload, analysis and visual-correction features. This work connects and secures those features. The missing SDK on this laptop prevents a local Android build; it does not mean his Android implementation is missing.

## 4. Actual Health sample timestamps

The HTTPS receiver now requires `sampled_at` alongside `heart_rate_bpm` and `access_key`. It must describe when Apple Health measured the sample, not when the Shortcut runs. The receiver and backend reject missing, timezone-free, future or older-than-five-minute timestamps. A 30-second future clock allowance accommodates small device clock differences.

The forwarding CLI and local setup GUI preserve `sampled_at`. The ETL parser, latest player record and MongoDB time-series retain it. The time-series `timestamp` uses sensor time, with `received_at` retained separately. Analysis rejects stale cached samples even if they were recently received. The dashboard displays sample time and receipt time separately.

Update the iPhone Shortcut before deploying the receiver change:

1. Find Heart Rate Health Samples, latest first, limit one.
2. Get the Value from that sample for the numeric `heart_rate_bpm` field.
3. Get the Start Date from **the same sample**.
4. Format that date as ISO 8601, including the timezone.
5. Add a **Text JSON body field** named `sampled_at` containing the formatted date. Keep `access_key` in the JSON body as before.

Do not use Current Date as the sample date. The receiver remains a Shortcut bridge; these timestamps do not create continuous Watch streaming or prove synchronization with the video.

## 5. Real analysis checks

Source: [Diemo Ruhnow's overhead-clear demonstration](https://www.youtube.com/watch?v=5tG-krOy1ro).

The public video was downloaded locally with TLS certificate verification enabled, using Windows trusted root certificates. It has not been added to the repository or republished.

- The original two-player clip was rejected with `multiple_players_detected`.
- A seven-second crop was also rejected. No detection gate was weakened to force a successful result.
- A documented three-second crop, **19–22 seconds, x=500–854 of the 854×480 video, full vertical extent**, produced 25 usable overhead frames, a six-value pose vector and an estimated right-elbow angle of **163.64°**. Synthetic pose fallback was disabled.
- An authenticated HTTP integration check then exercised pairing, timestamped Watch ingestion, Android upload, session polling, measured feedback and identical-upload reuse. The biometric value in that check was an explicitly synthetic local fixture; external database writes, Gemini and external dispatch were disabled.
- The machine-readable result is in `Tempo-real-video-integration.json` beside this guide.

This verifies integration and input rejection, not scientific accuracy. The video has no ground-truth 3D joint annotations. Highest reach remains a contact proxy, and the 165° screen remains a project heuristic. Professional reference profiles are labelled illustrative/unvalidated; Android does not present them as a verified matched archetype.

Google documents the configured [Gemini 4 Argon model](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon/) and [Interactions API](https://ai.google.dev/api/interactions-api). A minimal synthetic live-model probe reached Google but returned `RateLimitError`. No private readings or sports video were sent during that probe. Live coaching therefore remains unverified until the account's quota/billing/access issue is resolved.

Provider errors, missing keys, invalid JSON and schema failures now have explicit statuses. Structured output is validated before it can be labelled live. Human approval and the measured threshold cannot be overridden by model output. Android distinguishes demo responses and rule-based fallback feedback.

Set `TEMPO_REQUIRE_LIVE_MODEL=true` on the backend when a missing live model should fail the session with 503 rather than return labelled rule-based feedback.

Reproducible commands from `C:\Users\Admin\Tempo\Tempo`:

```powershell
python backend/validate_runtime.py --probe-model --output runtime-check.json
python backend/validate_runtime.py --video PATH_TO_A_SINGLE_PLAYER_CLIP.mp4 --output video-check.json
```

## 6. Authentication and ownership

Protected API routes now require expiring, revocable bearer credentials. Only credential hashes are stored server-side. Unconfigured authentication fails closed; public health returns a minimal response. Player IDs are bound to the credential, rather than trusted because the caller supplied them.

Ownership checks cover Android uploads/results, schedule reads/writes, Watch pairing/ingestion, telemetry/history, analysis and approvals. Possessing another player's pairing code does not authorize writing their data. SSE events are player-filtered, and SSE/WebSocket credentials are rechecked during use. Separate operator credentials allow administrative access.

The browser dashboard supports `/login` and an HttpOnly, SameSite session cookie, with same-origin checks for cookie-authenticated writes. Dashboard table values use DOM text nodes rather than inserting stored values as HTML. Production HTTPS sets Secure cookies. The requested HTTP LAN address remains available for development; it does not encrypt credentials or health data in transit.

Android sends Authorization headers automatically, stores its token with Android Keystore AES-GCM encryption, redacts Authorization from logs, avoids request-body logging and disables app backup. Clip review contains a masked token-entry field. These Android changes still need SDK/device verification.

### Local setup

Two 30-day local credentials have been provisioned without printing their values:

- Player `user_1`: `C:\Users\Admin\Documents\Codex\2026-10-24\lelts\work\tempo-player.token`.
- Operator `local_operator`: `C:\Users\Admin\Documents\Codex\2026-10-24\lelts\work\tempo-operator.token`.

Keep these files private. Paste the player token into the Android clip-review Access token field and keep its Player ID as `user_1`. Use the operator token only for operator tools or the dashboard login. Do not paste tokens into chat, URLs, source code or the APK configuration.

The backend's default hashed registry is `C:\Users\Admin\Tempo\Tempo\backend\.tempo-auth.json`; Git ignores it. A hosted backend must receive its own registry through the `TEMPO_AUTH_FILE` path or `TEMPO_AUTH_TOKENS` server configuration. Do not deploy a registry containing public test credentials.

For the local forwarding process:

```powershell
$env:TEMPO_API_TOKEN_FILE = 'C:\Users\Admin\Documents\Codex\2026-10-24\lelts\work\tempo-player.token'
$env:TEMPO_PLAYER_ID = 'user_1'
```

The updated setup GUI reads those variables. The forwarding CLI also supports `TEMPO_API_TOKEN_FILE` and requires `--user-id user_1`. Its Render read key remains a separate credential. Existing running processes need restarting with the new configuration.

Issue another player's credential using a lowercase identifier:

```powershell
python backend/manage_access.py issue --user alice --token-file PATH_TO_PRIVATE_FILE.token
python backend/manage_access.py revoke --user alice --token-file PATH_TO_PRIVATE_FILE.token
```

The tool never prints tokens. Issuing an additional token does not revoke existing tokens; revoke them explicitly. The registry is reread for requests, so revocation does not require a backend restart.

## Verification and remaining rollout

- **95** canonical backend tests passed.
- **15** HTTPS receiver tests passed.
- **26** imported service component tests passed.
- Authenticated real-video integration passed, with synthetic local-only biometrics and external services disabled.
- Git whitespace checks passed.
- Android compilation/device execution remains unverified because this laptop has no configured SDK.
- Live Gemini verification is blocked by the account's rate limit.
- Ground-truth sports accuracy and reference calibration remain outstanding.
- Render still runs the previous receiver revision. Deploy the new receiver and update the Shortcut together. The full backend and relay also need restarting with credentials.
- The full backend remains a single-worker application with process-local background jobs; durable hosted job recovery is separate work.

These changes do not establish production readiness or remove the need for a real Android/Watch device test.
