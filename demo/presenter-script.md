# Tempo · three-minute pitch

Title, problem, solution + architecture, Argon, MongoDB, Saint, demo, impact + next steps, then an untimed team/Q&A background.

## 1. Tempo · 0:00–0:10

Tempo helps amateur racket-sport players turn a practice clip into one clear coaching focus and a plan for their next session.

Presenter cue: Introduce Tempo briefly, then move to the player problem.

## 2. Problem · 0:10–0:30

Tempo is for amateur badminton and tennis players. A video shows the stroke, but it does not tell the player what to work on next. Useful advice still needs a drill, another session and a way to check progress. We connect those steps.

Presenter cue: Start here; there is no separate cover. Describe the problem without claiming a market study.

## 3. Solution and architecture · 0:30–0:55

Our solution is one coaching loop, from a practice clip to the next session. Android captures the clip, FastAPI checks pose and sample freshness, and MongoDB keeps the player history. Gemini returns coaching feedback and drill widgets. The player can then review the next practice action.

Presenter cue: Use the diagram for the brief solution explanation. Watch samples arrive through the paired iPhone Shortcut route; Safari does not read Health directly.

## 4. Use of Gemini 4 Argon · 0:55–1:20

Gemini 4 Argon is the coaching layer. Video and pose estimates provide movement evidence; goals and session context help shape the reply. We return one clear focus with a drill the player can use. Model failures and fallback results stay visible rather than appearing as live coaching.

Presenter cue: Live Gemini access must be checked before presenting. Highest reach is a contact proxy, and the 165-degree gate is a project heuristic. Do not claim calibrated movement accuracy.

## 5. Use of MongoDB · 1:20–1:45

MongoDB Atlas connects the history behind that coaching. Shared player memory stores goals, sessions and feedback. Time-series storage preserves the actual Watch sample times. Vector search retrieves similar reference strokes. Those references are illustrative, so we do not present the match as a validated technique score.

Presenter cue: The canonical database is sports_coach_db. Shared player memory and time-series storage are implemented; reference profiles have not been validated against ground truth.

## 6. Use of Saint · 1:45–2:10

Argon finds the flaw; Saint books the fix. When a stroke fails the elbow check, or a court opens up, Tempo sends Saint a signed event with a ready proposal. Saint asks you in chat, and only after your yes does Tempo's backend book it, once, and log that Saint relayed the approval. Venues are mocked today, so no real booking or payment is made.

Presenter cue: The only dedicated Saint slide. Events reach Saint only when SAINT_WEBHOOK_URL is set; say so if the demo uses the staged log instead. The venue adapter is mocked. Do not claim live availability, a booking confirmation or a payment.

## 7. Demo · 2:10–2:40

Here is the demo: capture a short set, open the debrief, then review the next practice action. Approve or decline the proposal. Court execution here is explicitly mocked.

Presenter cue: Allow roughly 15 seconds to show the prepared Android walkthrough or a recording. If unavailable, narrate the steps. Use the same player credential and saved home area; label sample results. The full phone/video/Watch/action flow has not been verified together.

## 8. Impact and next steps · 2:40–3:00

The prototype gives a player one clear focus. We have checked twenty command phrases and extracted twenty-five usable frames from a real clip. Next comes a full phone rehearsal, then a player pilot to measure usefulness, followed by a real venue-provider connection.

Presenter cue: Prototype metrics, not measured player improvement. The earlier 25-frame crop used synthetic local biometrics and has no ground-truth angle annotations. The 20 phrases test the deterministic parser. The timeline is a planned sequence, not committed dates.

## 9. Questions and team · Q&A background

No scripted introduction.

Presenter cue: Leave this slide up for questions. There is no timed team introduction. Credits: Sumanth — Gemini 4 Argon; Taha — MongoDB; Kang — Saint AI; Yue — UX/UI.

VISUAL: Team photo supplied by the user. Keep this untimed slide visible during questions.
