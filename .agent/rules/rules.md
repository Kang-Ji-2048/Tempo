---
trigger: always_on
---

Project: "Tempo", an Android AI sports coach app. I own ONLY ingestion
(video + biometrics) and feedback (cues, overlays, SDUI). Not marketplace/social.

Stack: Kotlin, Jetpack Compose (Material 3), single Activity, Navigation Compose,
MVVM (one ViewModel per screen, StateFlow), Hilt, Retrofit + OkHttp +
kotlinx.serialization, CameraX, MediaPipe Pose Landmarker (33 landmarks),
Media3 (ExoPlayer, Transformer), WorkManager, Health Connect client, FCM.
Target device: Pixel 10 Pro (Android 16). minSdk 26, targetSdk latest.

Backend: FastAPI at BASE_URL (configurable in BuildConfig, default
http://10.0.0.X:8000). Contracts:
- POST /api/v1/sessions/ingest (multipart: "metadata" JSON string + "video" file) -> 202 {session_id}
- GET /api/v1/sessions/{session_id} -> SessionRecord (status PENDING|ANALYZING|COMPLETED|FAILED,
  gemini_feedback, active_widgets)
- WS /api/v1/live/stream
- POST/GET /api/v1/cadence/schedule
SDUI: server sends JSON widgets with a "widget_type" discriminator.
Widgets: PathProgressWidget, DrillCardWidget, ConceptQuizWidget,
CheckInScheduleWidget, QuestionWidget, ChoiceWidget, CapturePromptWidget.

Rules: no business logic in composables; every network call returns a sealed
Result; unknown widget types must never crash; provide a MockApi so every
screen works offline; keep files small and named by feature.