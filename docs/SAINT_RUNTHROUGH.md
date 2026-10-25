# Saint run-through for the demo recording

This shows Saint doing real work for Tempo: Tempo pushes an event, Saint asks the player on WhatsApp, and Tempo's backend books once after the player says yes. Venues are mocked, so no real booking or payment happens. Say so on camera.

The steps assume Saint can (a) receive an HTTPS POST and (b) call HTTPS endpoints as tools. If your Saint takes events another way (email, a chat message), swap step 4 for that. The Tempo side doesn't change.

## 1. Secrets and a public URL

```bash
export TEMPO_ACTION_SIGNING_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export TEMPO_WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
export SAINT_WEBHOOK_URL="<the URL Saint gave you for incoming events>"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

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

> You are my badminton practice assistant. Tempo sends you events at your incoming URL. For each event, read `summary`.
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
3. Saint messages you on WhatsApp: indoor court, Saturday 10:00, book it? Reply "yes".
4. Show the result (the "after"). Use the `idempotency_key` from the proposal:
   ```bash
   curl "$TEMPO_URL/api/v1/saint/actions/<idempotency_key>" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)"
   ```
   It should show `"status": "executed_mock"` and `"approved_via": "saint_relay"`.

**Scene B: Argon finds the flaw, Saint follows up (about 60 seconds).**
1. Upload a clip with a bent elbow. Argon returns FAIL, and the analysis includes `argon_audit` (the second Argon agent's check).
2. Saint receives an `argon_verdict` event with the drill and a court proposal, and asks you.
3. Upload a clip with a full reach. Argon returns PASS, and Saint receives `fix_verified` with the before and after angles.

## If Saint can't receive events in time

Point `SAINT_WEBHOOK_URL` at Tempo's own receipt endpoint (`$TEMPO_URL/api/v1/webhooks/saint-delivery-receipt`) and show the `saint_event_log` and `saint_deliveries` collections instead. Say on camera that the Saint delivery is staged.

## Submission note (draft)

> We asked Saint to act as a badminton player's practice assistant. Tempo, our coaching backend, pushes Saint signed events when Gemini 4 Argon fails a stroke, when a court opens up, or when a fix is verified. Saint asks the player on WhatsApp before anything happens. After the player says yes, Saint calls Tempo's decision endpoint, and Tempo books once and logs that Saint relayed the approval.
> Tools and accounts: Saint's WhatsApp, Tempo's REST API (OpenAPI tools at `/api/v1/saint/tools`, with a Saint-only credential scoped to one player), and Tempo's signed event webhook. The venue provider is a mock, so no real bookings or payments were made.
