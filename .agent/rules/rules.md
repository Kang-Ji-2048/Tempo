# Project: Tempo AI - Adaptive Multimodal Sports Coach (Encode 2026)
## Role & Ownership
We are developing the **Ingestion & Output/Feedback** engine for Tempo AI.
Other team members are handling court infrastructure, live booking APIs, and client-side design. Our core focus is handling incoming session data (video + biometric telemetry) and transforming it into personalized, kinematic coaching feedback and dynamic lesson widgets.

## Core Tech Stack
- **Backend Framework:** Python 3.11+ / FastAPI with async WebSockets and task queues
- **AI / Multimodal Reasoning:** Gemini Argon via Google GenAI SDK (video kinometrics, biomechanical breakdown, audio cue generation)
- **Database & Retrieval:** MongoDB Atlas (Motor async driver, PyMongo)
  - Atlas Vector Search: matching joint angles / kinematic vectors to pro and textbook baselines
  - Time-Series Collections: wearable telemetry (heart rate, cadence, calories)
- **Agent Orchestrator:** Saint (Thea) for background check-ins and external tool triggers
- **Client Protocol:** Server-Driven UI (SDUI) JSON contract consumed by an Android Jetpack Compose client

## Deliverable Scope (Ingestion & Feedback)
1. **Async Video + Telemetry Ingestion:** Upload endpoints accepting 1080p MP4 clips alongside Health Connect biometric time-series JSON payloads.
2. **Gemini Argon Biomechanical Pipeline:** Prompt chains extracting kinematic chain deviations, fatigue-correlated breakdown, and prescriptive audio cues.
3. **Atlas Vector Matcher:** Cosine similarity comparison between user stroke mechanics and reference pro/fundamental pose libraries.
4. **Server-Driven UI Generator:** Emits structured JSON defining user skill progression trees (`PathNodeWidget`), actionable drills (`DrillCardWidget`), and tactical quizzes (`QuizCardWidget`).
5. **Real-Time Edge Cueing:** WebSocket endpoint for keyframe drops (2-3 fps) + live heart rate to trigger instantaneous micro-audio corrections.
