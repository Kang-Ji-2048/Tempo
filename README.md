# Tempo

Tempo is an Android racket-sports coaching project with video ingestion,
biomechanical analysis, wearable telemetry, and coaching feedback.

- `android/`: Jetpack Compose Android app.
- `app/`: Versioned session-ingestion, feedback, live, and cadence APIs.
- `backend/`: Pose extraction, Apple Watch ETL, MongoDB analytics, and dashboards.
- `watch_receiver/`: Protected HTTPS heart-rate receiver and laptop forwarding utility.

See [the watch receiver guide](watch_receiver/README.md) for the current Apple Health
connection and its temporary-storage limits.

[Deploy the watch receiver on Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2FKang-Ji-2048%2FTempo%2Ftree%2Fmain)

The Blueprint deploys only `watch_receiver/` from `main`, creates one Free web
service, generates separate read/write keys, and disables automatic redeploys.
No credentials or health readings are committed.

## Shared analysis backend

The Android session API and Watch/pose pipeline now use one FastAPI application.
From the repository root:

```powershell
python -m pip install -r requirements.txt
python backend/setup_pose_model.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`uvicorn main:app` from backend/ remains supported. Use one worker. See
[Android integration](backend/ANDROID_INTEGRATION.md) for the session ID contract,
Watch player IDs, failure handling, backend consolidation and remaining limits.
Android mock/API URL settings are unchanged; real-device testing needs a reachable
full backend and a configured local Android SDK. Render's existing service hosts
the Watch receiver only.

## Demo slides

The browser presentation is in [demo/index.html](demo/index.html). It includes eight slides, keyboard navigation, fullscreen mode and presenter notes. See [hosting instructions](demo/README.md) to mount it at /demo/ on the Vercel website. The website source has not yet been identified, so this does not publish the deck.
