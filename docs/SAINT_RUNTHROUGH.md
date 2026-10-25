# Saint run-through for the demo recording

This shows Saint doing real work for Tempo: Tempo raises an event, Saint picks it up and asks the player on WhatsApp, and Tempo's backend books once after the player says yes. Venues are mocked, so no real booking or payment happens. Say so on camera.

Saint does not expose an inbound URL, so Saint pulls: it calls `GET /api/v1/saint/events/pending/kang`, which returns each event it hasn't seen yet, once. Leave `SAINT_WEBHOOK_URL` unset so events are staged for it. (If a Saint ever does give you an inbound URL, set `SAINT_WEBHOOK_URL` and Tempo pushes signed events instead.)

## 1. Secrets and a public URL

```bash
export TEMPO_ACTION_SIGNING_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export TEMPO_WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
export TEMPO_DEMO_MODE=false   # demo mode swaps in placeholder angles, so Scene B could never PASS
python backend/setup_pose_model.py   # once, so clips are actually measured
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`GEMINI_API_KEY` must be set (in `backend/.env`) for the Argon coach and auditor. Without it you get the labelled deterministic fallback, which is honest but is not Argon.

Saint has to reach the backend, so expose it, for example with `cloudflared tunnel --url http://localhost:8000`. Use the `https://…` URL it prints as `TEMPO_URL` below. Keep both secrets out of chat and out of git.

## 2. Credentials

```bash
python backend/manage_access.py issue --user kang --role player --days 2 --token-file ~/.tempo/kang.token
python backend/manage_access.py issue --user kang --role saint  --days 2 --token-file ~/.tempo/saint.token
```

The Saint token only reaches `/command` and `/api/v1/saint/*`, and only for `kang`. Tokens go into `backend/.tempo-auth.json`, which is ignored when `TEMPO_AUTH_TOKENS` is set, so unset that first.

## 3. Player preferences

```bash
curl -X PUT "$TEMPO_URL/api/v1/saint/preferences/kang" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)" \
  -H "Content-Type: application/json" \
  -d '{"home_area":"Shoreditch","preferred_time":"18:30","sport":"badminton","level":"intermediate"}'
```

## 4. Set up Saint

Give Saint the tools: `GET $TEMPO_URL/api/v1/saint/tools` with header `Authorization: Bearer <saint token>` returns an OpenAPI document of exactly the routes it may call.

Then give Saint this job in plain English:

> You are my badminton practice assistant. Every few minutes, and whenever I say "check Tempo", call `GET /api/v1/saint/events/pending/kang`. For each event, read `summary`.
> If it has a `proposal`, message me on WhatsApp with the proposal's `action.summary` and ask "Book it?".
> Only after I reply yes, call `POST /api/v1/saint/actions/decision` with `{"proposal": <the proposal, unchanged>, "approved": true}`. If I say no, send `"approved": false`.
> If Tempo answers 410 (expired), call `POST /command` with `{"user": "kang", "text": <suggested_command>}` and ask me again.
> For `fix_verified`, tell me the before and after angles.
> Never book, pay or message anyone else without my yes.

## 5. Record it

**Scene A: a court opens up (about 40 seconds).**
1. Show Tempo with no booking yet (the "before").
2. Fire the event:
   ```bash
   curl -X POST "$TEMPO_URL/api/v1/saint/events/mock-slot-opened/kang" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)"
   ```
3. Say "check Tempo" to Saint (or wait for its next check). Saint messages you on WhatsApp: indoor court, Saturday 10:00, book it? Reply "yes".
4. Show the result (the "after"). Use the `idempotency_key` from the proposal:
   ```bash
   curl "$TEMPO_URL/api/v1/saint/actions/<idempotency_key>" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)"
   ```
   It should show `"status": "executed_mock"` and `"approved_via": "saint_relay"`.

**Scene B: Argon finds the flaw, Saint follows up (about 60 seconds).**
1. Upload a clip with a bent elbow. Argon returns FAIL, and the analysis includes `argon_audit` (the second Argon agent's check).
2. Saint picks up an `argon_verdict` event with the drill and a court proposal, and asks you.
3. Upload a clip with a full reach. Argon returns PASS, and Saint picks up `fix_verified` with the before and after angles.

### Before you press record

- `GET $TEMPO_URL/health` shows `pose_runtime.configured: true`, and `GET $TEMPO_URL/api/v1/ai/status` shows Gemini live.
- Fire Scene A once as a dry run, and check that Saint's message arrives and `saint_event_log` shows `"status": "pulled"`, not `staged`.
- Upload both Scene B clips once beforehand and check that the bent-elbow clip FAILs and the full-reach clip PASSes. Doing FAIL then PASS leaves the last verdict as PASS, so the loop starts fresh on camera.
- Clear old WhatsApp messages from Saint so the screen shows only this run.

## Shot list (about 3 minutes)

Each shot is labelled with the judging criterion it shows. Keep the phone and the laptop both in frame or use a split screen, so viewers see Tempo and Saint at the same time.

| # | Time | Shot | Say | Criterion |
|---|------|------|-----|-----------|
| 1 | 0:00–0:15 | Face to camera, racket in hand | "I know my smash is off, but not why, and I never get round to booking practice." | Real-world use |
| 2 | 0:15–0:45 | Film a bent-elbow clear on the phone and upload. The debrief shows FAIL with the measured elbow angle. | "Gemini 4 Argon measures the elbow at contact, and a second Argon agent audits the diagnosis against the numbers." Point at `argon_audit`. | Before (working proof) |
| 3 | 0:45–1:15 | WhatsApp: Saint's message with the drill and "Indoor court tomorrow 18:30. Book it?" | "I didn't ask Saint to do anything. It picked up Argon's result from Tempo, and it asks me before acting." | Cool factor, human control |
| 4 | 1:15–1:35 | Reply "yes". Show the action record: `executed_mock`, `approved_via: saint_relay`. Tap yes again to show it doesn't double-book. | "Saint never holds the booking credentials. It relays my yes, and Tempo's backend books once." | Human control |
| 5 | 1:35–1:55 | Scene A: fire the court-opened event and decline it with "no". | "When I say no, nothing happens." | Human control |
| 6 | 1:55–2:30 | Next session: film a full-reach clear and upload. PASS. WhatsApp: "Fix verified: elbow 152° to 168° (target 165°)." | "Same measurement, a week of drills later, and Saint closes the loop." | After (working proof) |
| 7 | 2:30–2:50 | Screen: `/api/v1/saint/tools` and a 403 when the Saint token calls another route. | "Saint's credential reaches only its own routes, for one player." | Human control |
| 8 | 2:50–3:00 | The slide: "Argon finds the flaw. Saint books the fix." | "Courts are mocked today. Real providers and payments come next, behind a one-time approval link." | Real-world use |

If time is short, cut shots 5 and 7 first. Shots 2, 3, 4 and 6 are the before and after, so keep those. Read the angles off the screen rather than from this script, because the real numbers will differ.

## If Saint can't reach Tempo in time

Call the pending endpoint yourself with the saint token and show the events, then the `saint_event_log` collection. Say on camera that this step was done by hand rather than by Saint.

## Submission note (draft)

> We asked Saint to act as a badminton player's practice assistant. Tempo, our coaching backend, raises events when Gemini 4 Argon fails a stroke, when a court opens up, or when a fix is verified, and Saint checks for them through Tempo's API. Saint asks the player on WhatsApp before anything happens. After the player says yes, Saint calls Tempo's decision endpoint, and Tempo books once and logs that Saint relayed the approval.
> Tools and accounts: Saint's WhatsApp, Tempo's REST API (OpenAPI tools at `/api/v1/saint/tools`, with a Saint-only credential scoped to one player), including its pending-events feed. The venue provider is a mock, so no real bookings or payments were made.
