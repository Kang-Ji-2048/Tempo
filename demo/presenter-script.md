# Tempo · three-minute pitch

Eight timed slides, then the team photo stays up for questions. One dedicated Saint slide.

## 1. Tempo · 0:00–0:10

Tempo helps amateur racket-sport players know what to practise next: one clear coaching focus and a drill for their next session.

Presenter cue: Keep the opening short. The audience and problem are on the next slide.

## 2. Problem · 0:10–0:30

Amateur players can film their strokes, but turning that footage into better practice is harder. What should I change? How should I practise it? And when will I play again? Tempo connects those questions into a next step the player can use.

Presenter cue: Frame this as the problem Tempo is addressing; do not imply a completed customer study. Reveal the three horizontal question blocks with three advances. The fourth advance moves to the solution. Builds are included in this slide’s 20 seconds.

## 3. Solution and architecture · 0:30–0:55

Our solution gives the player one clear correction and a drill for the next session. Behind it, Android captures the clip, FastAPI checks the movement and Watch context, MongoDB keeps the history, and Gemini returns the coaching reply. The result comes back to the same player.

Presenter cue: Lead with the player benefit, then point across the diagram once. Highest reach is a contact proxy, Watch context uses actual sample timestamps, and model fallbacks stay labelled.

## 4. Use of Gemini 4 Argon · 0:55–1:20

Gemini 4 Argon is the coaching layer. Video and pose estimates provide movement evidence; goals and session context help shape the reply. We return one clear focus with a drill the player can use. Model failures and fallback results stay visible rather than appearing as live coaching.

Presenter cue: Live Gemini access must be checked before presenting. Highest reach is a contact proxy, and the 165-degree gate is a project heuristic. Do not claim calibrated movement accuracy.

## 5. Use of MongoDB · 1:20–1:45

MongoDB Atlas connects the history behind that coaching. Shared player memory stores goals, sessions and feedback. Time-series storage preserves the actual Watch sample times. Vector search retrieves similar reference strokes. Those references are illustrative, so we do not present the match as a validated technique score.

Presenter cue: The canonical database is sports_coach_db. Shared player memory and time-series storage are implemented; reference profiles have not been validated against ground truth.

## 6. Use of Saint · 1:45–2:10

Argon finds the flaw; Saint books the fix. When a stroke fails the elbow check, or a court opens up, Tempo gives Saint an event with a signed, ready proposal. Saint asks you in chat, and only after your yes does Tempo's backend book it, once, and log that Saint relayed the approval. When a later clip passes, Saint tells you the fix is verified, with the before and after angles. Venues remain mocked, so no real booking or payment is made.

Presenter cue: Saint picks up events by polling Tempo's pending-events route with its own credential; if it hasn't, show the event log instead. A Saint-scoped credential reaches only Saint routes. The backend records Saint-relayed approvals. Technical details for questions: signed proposals expire after 15 minutes and idempotency keys prevent duplicate execution. Keep the mock-venue disclosure and do not claim verified availability, real booking or payment.

## 7. Demo · 2:10–2:40

Here is the demo: capture a short set, open the debrief, then review the next practice action. Approve or decline the proposal. Court execution here is explicitly mocked.

Presenter cue: Allow roughly 15 seconds to show the prepared Android walkthrough or a recording. If unavailable, narrate the steps. Use the same player credential and saved home area; label sample results. The full phone/video/Watch/action flow has not been verified together.

VIDEO: The blank 16:9 area is reserved for a prepared recording. No video is embedded yet.

## 8. Impact and next steps · 2:40–3:00

Our prototype gives a player one clear focus, with twenty command phrases checked and twenty-five usable frames from a real clip. The pilot will measure what matters to players: whether the feedback is useful, whether drills get completed and whether players return. Real venue integration follows that pilot.

Presenter cue: The numbers on the left are prototype signals, not measured customer impact. The 20 phrases test a deterministic parser; the earlier 25-frame crop used synthetic local biometrics and has no ground-truth angle validation. Feedback usefulness, drill completion and return sessions are proposed pilot measures, not observed results. Timeline stages are planned, not dated commitments.

## 9. Questions and team · Q&A background

No scripted introduction.

Presenter cue: Leave this slide up for questions. There is no timed team introduction. Credits: Sumanth — Gemini 4 Argon; Taha — MongoDB; Kang — Saint AI; Yue — UX/UI.

VISUAL: Team photo supplied by the user. Keep this untimed slide visible during questions.
