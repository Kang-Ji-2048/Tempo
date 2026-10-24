# Tempo Safari demo

A standalone, installable static prototype. No build step. Serve `dist/` over HTTPS or localhost. All asset paths are relative, including the service worker scope.

## Included

- Three-step local onboarding; Today, Review, Plan and You screens.
- Device-only video preview, explicitly separate from the measured example review.
- Saved drill, manual rep counter, completion history, pauseable rest timer and calendar-file export.
- Home Screen manifest, Apple touch icon, safe-area layout and offline app-shell cache.
- Watch integration explanation with no credentials or fabricated live readings.

Profile and practice progress use localStorage. Videos use temporary object URLs and never leave the browser. Google Fonts is optional; system fonts work offline. Reset is available from You. The service worker caches only same-origin GET requests. No backend, HealthKit or AI requests run in this mockup.

## iPhone

Open the hosted URL in Safari, tap Share → Add to Home Screen, enable Open as Web App if shown, then Add. Actual installation, camera selection and offline behavior still require an iPhone smoke test.

## Remaining product integration

1. Connect Watch requests to the correct authenticated endpoint: Android currently requests `/reading` from its main backend; the backend exposes `/pipeline/latest-apple-watch`. The separate receiver uses its own read credential.
2. Replace fixed onboarding player identity with persisted authenticated player/session identity. Mount onboarding consistently in both server entrypoints.
3. Connect real upload → measured review → drill/result flow, including upload/retry errors and missing results. Validate live model quota and actual clip accuracy.
4. Validate Android permissions, Health Connect, audio and notification paths on a physical phone; mock mode remains enabled by default.
5. Wire this browser prototype to authenticated HTTPS APIs only when moving beyond the demo. Safari cannot directly read HealthKit.

## Validation

JavaScript syntax checked with Node. Browser walkthrough verifies onboarding, example review, drill save, 10-rep completion gating and completion confirmation. Do not interpret the example elbow angle as medical advice or a new measurement. The original backend estimate came from 25 usable frames of a separate public badminton clip and has no ground-truth validation.
