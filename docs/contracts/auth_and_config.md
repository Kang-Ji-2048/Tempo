# Contract: Authentication and Configuration

This document specifies how the Tempo Android client authenticates against the canonical FastAPI backend (`/backend`), how debug builds configure connection settings, and how the unified athlete identity (`user_id`) is managed across all client and backend subsystems.

---

## 1. Authentication Contract

### Header Format
All protected endpoints require HTTP Bearer authentication:
```http
Authorization: Bearer <access_token>
```

### Token Resolution Hierarchy (Client)
The Android client resolves the access token via the following precedence in `NetworkModule.kt` / `PlayerIdentity`:
1. **Dynamic/Persisted Token**: `PlayerIdentity.accessToken` stored securely in encrypted `SharedPreferences` (e.g., entered or refreshed at runtime).
2. **Debug Fallback**: `BuildConfig.TEMPO_DEBUG_TOKEN` sourced from `android/local.properties` (`TEMPO_DEBUG_TOKEN=<token>`).
3. **Unauthenticated / Empty**: `""` if neither is present.

### Server-Side Validation (`backend/auth.py`)
- The backend parses the token from `Authorization: Bearer <token>`.
- Token length must satisfy `32 <= len(token) <= 512`.
- The token is SHA-256 hashed and looked up in the authenticated identity store (`TEMPO_AUTH_TOKENS` environment variable or `.tempo-auth.json`).
- If valid and unexpired, the request state receives `request.state.identity = {"user_id": ..., "role": "player"|"admin"}`.
- If the token is invalid or expired:
  - Returns `401 Unauthorized` with header `WWW-Authenticate: Bearer`.
- If authentication is completely unconfigured on the server:
  - Returns `503 Service Unavailable`.

### Client 401 Handling
- When the OkHttp interceptor receives an HTTP 401 response:
  - It notifies `AuthBannerNotifier.notifyUnauthorized()`.
  - The UI presents a prominent top banner: `"Backend rejected the token, check local.properties"`.
  - The app never crashes or silently discards the failure.

---

## 2. Public vs Protected Routes

| Route | Method | Access | Description |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | **Public** | Returns `{"status": "ready", "service": "tempo"}` without requiring a token. Detailed diagnostics require admin role. |
| `/login` | `GET` | **Public** | Web sign-in portal. |
| `/auth/session` | `POST`/`DELETE` | **Public/Session** | Browser session cookie management. |
| `/api/v1/sessions/*` | Any | **Protected** | Session ingest, status polling, and report retrieval. Must match authenticated player or admin. |
| `/api/v1/cadence/schedule/*` | Any | **Protected** | Cadence scheduling and updates. Must match authenticated player or admin. |
| `/api/v1/onboarding/*` | Any | **Protected** | Adaptive onboarding question progression. |
| `/api/v1/live/*` | Any | **Protected** | Live stream keypoint ingestion and audio cues. |

---

## 3. Unified Identity (`user_id`)

### Canonical ID: `user_1`
To resolve legacy divergence across repositories and backend tables, there is **one single source of truth** for the athlete identity:
- **Default value**: `"user_1"`
- **Android source of truth**: `PlayerIdentity.userId`
- **Configuration**: Sourced from `local.properties` via `TEMPO_USER_ID`, exposed in `BuildConfig.TEMPO_USER_ID`, and persisted in `PlayerIdentity`.
- **Usage**:
  - `OnboardingViewModel`: saves profile under `PlayerIdentity.userId`.
  - `ScheduleViewModel`: queries and persists cadence under `PlayerIdentity.userId`.
  - `UploadWorker`: passes `PlayerIdentity.userId` in the `metadata` JSON to `POST /api/v1/sessions/ingest`.
  - `MockTempoApi`: seeds and returns sessions/schedules for `PlayerIdentity.userId`.
  - `UserProfileRepository` / Room database: saves and queries the active user profile for `PlayerIdentity.userId`.
  - Backend `players` collection, `android_sessions`, and `strokes` collection match `user_1`.

---

## 4. Android Build Configurations

Read from `android/local.properties` (which is git-ignored):
```properties
BASE_URL=http://10.0.2.2:8000/
TEMPO_DEBUG_TOKEN=<your-token-from-manage_access.py>
TEMPO_USER_ID=user_1
THEA_NUMBER=4477985791437
USE_MOCK_API=false
```

### Build Types:
- `debug`: `BASE_URL` from `local.properties` (default `http://10.0.2.2:8000/`), `USE_MOCK_API=false` (default), cleartext traffic permitted via `network_security_config.xml`.
- `demoOffline`: `BASE_URL=http://10.0.2.2:8000/`, `USE_MOCK_API=true`, inherits debug signing.
- `release`: `BASE_URL=https://api.tempo.app/`, `USE_MOCK_API=false`, cleartext traffic strictly disallowed.
