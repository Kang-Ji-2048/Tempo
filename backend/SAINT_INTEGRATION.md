# Saint command and approval prototype

Tempo stack: Kotlin / Jetpack Compose, Hilt, Retrofit, Room and WorkManager on Android; FastAPI / Pydantic and MongoDB Atlas (`sports_coach_db`) on the backend. The existing Gemini vision pipeline remains separate.

## What works

Android Home → **Plan with Saint**, or completed Debrief → **Plan next session with Saint**.

1. Open **Home area & preferences**. Save an area, preferred time, sport and level.
2. Enter `Book me an indoor court Saturday morning`.
3. Review the exact date, time, venue mode, sport, area and duration in the proposal.
4. Approve the mock action or decline it.
5. Check the action status after any network interruption. Retry uses the same signed proposal/key.

Saint uses the existing backend address and encrypted Tempo player credential. Its repository deliberately uses the canonical authenticated backend even when `USE_MOCK_API` is enabled for stroke-analysis fixtures. It does not embed API keys or a WhatsApp number. A test-only MockSaintRepository is available for isolated UI work.

## Contract

- `POST /command` with `{ "user": "user_1", "text": "book a court Saturday morning" }` returns a clarifying question or signed proposal. This endpoint does not write preferences, actions or bookings, and does not call venue search/book.
- `GET/PUT /api/v1/saint/preferences/{user}` reads/saves the small preference store.
- `POST /api/v1/saint/actions/decision` with `{ "proposal": <exact returned object>, "approved": true|false }` records a decision and executes approved actions.
- `GET /api/v1/saint/actions/{idempotency_key}` recovers the action status.

All routes use the same Tempo bearer authentication and player ownership checks. Admins retain the existing explicit cross-player access policy.

The Saint assistant gets its own `saint` credential (`python backend/manage_access.py issue --user <player> --role saint --token-file <private path>`). It acts for that one player and only reaches `/command` and `/api/v1/saint/*`; any other route returns 403. When it posts a decision, the action log records `approved_via: saint_relay`, meaning Saint relayed the player's chat reply and Tempo did not see the approval itself. App approvals record `approved_via: player`. A one-time approval link for the player is the planned step before any real payment.

`backend/saint_commands.py::Action` is the source of truth for type, params, summary, requires_approval, idempotency key, owner and expiry. `backend/contracts/saint_action.schema.json` is generated from it. Kotlin wire DTOs preserve the params object; Android never executes or reinterprets venue instructions.

Proposals are HMAC signed, expire after 15 minutes and require approval. The executor rejects modified/expired payloads and admits each key once through Mongo's unique `_id` (or an atomic process lock in the mock fallback). The adapter interface exposes `search()` and `book()`. Only MockVenueAdapter is installed. No real bookings, messages or payments can occur.

Action states: `processing`, `declined`, `executed_mock`, `needs_review`. A provider exception produces `needs_review`; re-submission returns the existing result and never automatically calls the provider again. An ambiguous write failure fails closed. Action logs use `saint_action_log`; preferences use `saint_preferences`, both in the canonical database. No database connection means explicitly labelled volatile `in_memory_demo` storage, suitable only for this mock.

## Run

Use the existing authenticated server configuration:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The `backend/main.py` entrypoint also mounts the command router. Install `backend/requirements.txt`, including tzdata for Europe/London calendar handling on Windows. Set `TEMPO_ACTION_SIGNING_KEY` to a private random value of at least 32 characters for stable signatures across restarts/workers; keep it server-side in your environment. If unset, a temporary process key is used and a restart invalidates outstanding proposals. Do not use that mode for production.

## Validation and limits

`backend/test_saint_commands.py` includes the 20 phrasing regression cases plus approval, expiry, tampering, ownership, no-write planning, provider failure and concurrent duplicate approval checks. The backend suite passed 114 tests. Run:

```powershell
$env:PYTHONPATH='backend'
python -m unittest discover -s backend -p 'test_*.py'
```

The Android Gradle build was attempted but the JDK could not validate the Gradle distribution's TLS certificate; compilation and physical-phone behavior remain unverified. The existing local SDK setup also needs checking on the build machine.

This is the architecture described in the supplied Saint notes, not a connection to saint.agent's hosted service. No verified Saint service API/SDK contract was supplied. The planner is a conservative deterministic prototype, not a model call. It supports one future day/time, badminton or tennis, indoor/outdoor, and 30/60/90 minutes. Morning/afternoon/evening resolve to 09:00/14:00/18:00, shown in the approval summary. Ambiguous or unsupported constraints return questions; the next command should restate the complete request. Prices and availability are not real. The level preference is stored but does not change venue availability.

Before live rollout: integrate the actual Saint/model interface behind a validated planner, add real venue adapters and provider idempotency/reconciliation, exercise Mongo durability and multiworker races, verify phone behavior, then enable live actions only after checking provider terms and payment/booking constraints. The old `/pipeline/approve-saint-action` webhook path is retained for compatibility and is not called by this new screen. It still needs its own receiver contract verification.


## Integration with updated main

The newer main branch's login/register screens, shared Thea home feed and omnichannel adapters are retained. Plan with Saint remains a separate mock court-action workflow, using the same player identity and authenticated Retrofit client. Debug builds accept tempo.baseUrl (Gradle property or local.properties) before BASE_URL; without either, the newer main default remains http://127.0.0.1:8000/ for adb reverse. For an emulator, set tempo.baseUrl=http://10.0.2.2:8000/ locally. Machine-specific local.properties is not tracked. The merged Saint and startup checks passed 18 tests.
