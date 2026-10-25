# Saint run-through for the demo recording

This shows Saint doing real work for Tempo, in the player's own accounts. Tempo emails the player each event. A proposal comes with a one-time approval link. Saint sees the email in the inbox, asks the player on WhatsApp, and adds the session to their calendar once they approve. The player's tap on the link is the only thing that books, and Tempo books once. Venues are mocked, so no real booking or payment happens. Say so on camera.

Saint does not hold a Tempo credential, call Tempo or expose an inbound URL, so Tempo never talks to Saint directly: email is the hand-off, and the link keeps the yes with the player. (If a Saint ever gives you an inbound URL or takes a token, `SAINT_WEBHOOK_URL` and the `saint` role still work; see `backend/SAINT_INTEGRATION.md`.)

Before relying on this, ask Saint to confirm it can read your inbox and add calendar events.

## 1. Secrets, email and a public URL

Start a tunnel first, because the approval link needs the public URL: `cloudflared tunnel --url http://localhost:8000`. Use the `https://…` URL it prints as `TEMPO_URL`.

```bash
export TEMPO_ACTION_SIGNING_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export TEMPO_PUBLIC_URL="$TEMPO_URL"           # the approval links point here
export TEMPO_EMAIL_TO="<the inbox Saint works in>"
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER="<sending Gmail address>" SMTP_PASSWORD="<a Gmail app password>"
export TEMPO_DEMO_MODE=false   # demo mode swaps in placeholder angles, so Scene B could never PASS
python backend/setup_pose_model.py   # once, so clips are actually measured
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

A Gmail app password needs 2-step verification on the sending account (Google Account, Security, App passwords). Sending from a second account to your own inbox makes the email easy to spot. `GEMINI_API_KEY` must be set (in `backend/.env`) for the Argon coach and auditor. Without it you get the labelled deterministic fallback, which is honest but is not Argon. Keep every secret out of chat and out of git.

## 2. Your credential

```bash
python backend/manage_access.py issue --user kang --role player --days 2 --token-file ~/.tempo/kang.token
```

Tokens go into `backend/.tempo-auth.json`, which is ignored when `TEMPO_AUTH_TOKENS` is set, so unset that first. Saint gets no token.

## 3. Player preferences

```bash
curl -X PUT "$TEMPO_URL/api/v1/saint/preferences/kang" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)" \
  -H "Content-Type: application/json" \
  -d '{"home_area":"Shoreditch","preferred_time":"18:30","sport":"badminton","level":"intermediate"}'
```

## 4. Set up Saint

Give Saint this job in plain English:

> You are my badminton practice assistant. Watch my inbox for emails from Tempo (the subject starts with "Tempo:").
> For each one, message me on WhatsApp with a one-line summary.
> If the email has an "Approve or decline" link, ask "Book it?" and send me the link. Never open or tap the link yourself: I decide.
> When I tell you I approved, add the session to my calendar with the drill from the email in the description.
> If the email says a fix was verified, tell me the before and after angles.
> Never book, pay or message anyone else on my behalf.

## 5. Record it

**Scene A: a court opens up (about 40 seconds).**
1. Show your calendar with Saturday free (the "before").
2. Fire the event:
   ```bash
   curl -X POST "$TEMPO_URL/api/v1/saint/events/mock-slot-opened/kang" -H "Authorization: Bearer $(cat ~/.tempo/kang.token)"
   ```
3. The email arrives. Saint messages you on WhatsApp: indoor court, Saturday 10:00, book it? Here's the link.
4. Tap the link. The page shows the proposal with Approve and Decline. Tap Approve, and the page says "Booked (mock)".
5. Tell Saint you approved. Saint adds it to your calendar (the "after").

**Scene B: Argon finds the flaw, Saint follows up (about 60 seconds).**
1. Upload a clip with a bent elbow. Argon returns FAIL, and the analysis includes `argon_audit` (the second Argon agent's check).
2. Tempo emails the drill and a court proposal. Saint asks you, and you approve through the link.
3. Upload a clip with a full reach. Argon returns PASS, Tempo emails "Fix verified" with the before and after angles, and Saint tells you.

### Before you press record

- `GET $TEMPO_URL/health` shows `pose_runtime.configured: true`, and `GET $TEMPO_URL/api/v1/ai/status` shows Gemini live.
- Fire Scene A once as a dry run. Check that the email arrives (`saint_event_log` shows `"email": "sent"`), Saint messages you, and the link opens from your phone.
- Approve within 15 minutes of the email: proposals expire after that, and the page says so.
- Upload both Scene B clips once beforehand and check that the bent-elbow clip FAILs and the full-reach clip PASSes. Doing FAIL then PASS leaves the last verdict as PASS, so the loop starts fresh on camera.
- Clear old Tempo emails and WhatsApp messages from Saint so the screen shows only this run.

## Shot list (about 3 minutes)

Each shot is labelled with the judging criterion it shows. Keep the phone and the laptop both in frame or use a split screen, so viewers see Tempo and Saint at the same time.

| # | Time | Shot | Say | Criterion |
|---|------|------|-----|-----------|
| 1 | 0:00–0:15 | Face to camera, racket in hand | "I know my smash is off, but not why, and I never get round to booking practice." | Real-world use |
| 2 | 0:15–0:45 | Film a bent-elbow clear on the phone and upload. The debrief shows FAIL with the measured elbow angle. | "Gemini 4 Argon measures the elbow at contact, and a second Argon agent audits the diagnosis against the numbers." Point at `argon_audit`. | Before (working proof) |
| 3 | 0:45–1:15 | WhatsApp: Saint's message with the drill, "Indoor court tomorrow 18:30. Book it?" and the link. | "I didn't ask Saint to do anything. It saw Argon's result land in my inbox, and it asks me before anything happens." | Cool factor, human control |
| 4 | 1:15–1:40 | Tap the link, then Approve: "Booked (mock)". Tap the link again: "Already decided". | "Saint never holds a booking credential. Only my tap books, and it books once." | Human control |
| 5 | 1:40–1:55 | Tell Saint "done". The session appears in your calendar with the drill. | "Saint puts it in my calendar, with the drill attached." | Real-world use |
| 6 | 1:55–2:30 | Next session: film a full-reach clear and upload. PASS. WhatsApp: "Fix verified: elbow 152° to 168° (target 165°)." | "Same measurement, a week of drills later, and Saint closes the loop." | After (working proof) |
| 7 | 2:30–2:45 | Scene A: a court opens up; tap Decline. | "When I say no, nothing happens." | Human control |
| 8 | 2:45–3:00 | The slide: "Argon finds the flaw. Saint books the fix." | "Courts are mocked today. Real venue providers come next, behind the same one-time link." | Real-world use |

If time is short, cut shot 7 first. Shots 2, 3, 4 and 6 are the before and after, so keep those. Read the angles off the screen rather than from this script, because the real numbers will differ.

## If Saint can't read the inbox in time

Show the email and tap the link yourself, and say on camera that Saint's step is shown by hand. The booking and the calendar entry still need your tap.

## Submission note (draft)

> We asked Saint to act as a badminton player's practice assistant, working in the player's own inbox, WhatsApp and calendar. Tempo, our coaching backend, emails the player when Gemini 4 Argon fails a stroke, when a court opens up, or when a fix is verified. A proposal comes with a one-time approval link. Saint picks up the email, asks the player on WhatsApp, and adds the session to the calendar once they approve. Saint never holds a Tempo credential: only the player's tap on the link books, once.
> Tools and accounts: the player's email inbox, WhatsApp and calendar, through Saint. Tempo's one-time signed approval link. The venue provider is a mock, so no real bookings or payments were made.
