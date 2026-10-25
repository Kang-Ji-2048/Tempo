## 1. Running the FastAPI Backend Reachable from Phone

Use the dev runner script from the repo root:
```bash
./scripts/dev.sh
```
`scripts/dev.sh` will:
1. Load `backend/.env` (including `GEMINI_API_KEY`).
2. Print your machine's local LAN IPv4 addresses.
3. Start `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`.

> **Live drill voice (ElevenLabs):** add `ELEVENLABS_API_KEY` to `backend/.env` (optional: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`, default `eleven_flash_v2_5`). The app streams live-drill cues, Thea's live replies and the set summary from `GET /api/v1/tts`; without a key it falls back to on-device TTS. Never commit the key.

> **macOS Firewall Note:** If physical phones cannot connect, open **System Settings -> Network -> Firewall** and ensure incoming connections to Python / uvicorn are allowed, or temporarily disable the firewall during local development.

---

## 2. Connecting a Physical Android Phone (Pixel 10 Pro)

`10.0.2.2` is an Android Emulator-only alias and **never works on physical devices**. You have two options:

### Option A: Reverse Port Forwarding via USB (Recommended & Most Reliable)
With your phone connected via USB and USB Debugging enabled:
```bash
adb reverse tcp:8000 tcp:8000
```
In `android/local.properties`:
```properties
BASE_URL=http://localhost:8000/
```
Then rebuild or run the app. All `localhost:8000` requests on the phone route over USB directly to your laptop's backend!

### Option B: Local Wi-Fi LAN IP
Ensure both your laptop and phone are on the same Wi-Fi network. Find your laptop's LAN IP (printed by `./scripts/dev.sh`, e.g. `192.168.1.142`).
In `android/local.properties`:
```properties
BASE_URL=http://192.168.1.142:8000/
```
Rebuild the debug APK.

---

## 3. Demo User Seeding

To seed the demo user (`demo@tempo.app`):
```bash
uv run python scripts/seed_demo_user.py
```
Default password is `TempoDemo2026!` (or override with `DEMO_PASSWORD` environment variable). In debug builds, you can tap "Use demo account" on the Login screen to autofill these credentials.

---

## 4. Generating Developer Authentication Tokens

The backend authenticates requests via opaque bearer tokens validated through `backend/auth.py` and managed by `backend/manage_access.py`.

### Issuing a Token for `user_1`
To generate a 30-day token for the canonical athlete `user_1`:
```bash
# Issue token to a local, private file
python backend/manage_access.py issue \
  --user user_1 \
  --role player \
  --days 30 \
  --token-file backend/.tempo-player.token
```
This registers the SHA-256 hash in `backend/.tempo-auth.json` and writes the raw token to `backend/.tempo-player.token`.

To read the issued token:
```bash
cat backend/.tempo-player.token
```

### Revoking a Token
```bash
python backend/manage_access.py revoke \
  --user user_1 \
  --token-file backend/.tempo-player.token
```

---

## 3. Configuring Android (`android/local.properties`)

Create or update `android/local.properties` (this file is git-ignored):
```properties
sdk.dir=/Users/sjanjanam/Library/Android/sdk
BASE_URL=http://10.0.2.2:8000/
TEMPO_DEBUG_TOKEN=<paste_token_from_tempo-player.token>
TEMPO_USER_ID=user_1
THEA_NUMBER=4477985791437
USE_MOCK_API=false
```

- When running in the Android Studio Android Emulator, `10.0.2.2` automatically routes to your host machine's `localhost`.
- When running on a physical Pixel phone on the same Wi-Fi, replace `10.0.2.2` with your computer's local Wi-Fi IP (e.g. `http://192.168.1.50:8000/`).

---

## 4. Building and Running Android

```bash
cd android
# Build debug APK
./gradlew assembleDebug

# Run unit tests
./gradlew testDebugUnitTest
```
