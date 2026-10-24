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
