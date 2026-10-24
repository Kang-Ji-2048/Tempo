# Tempo Developer Runbook

## 1. Running the FastAPI Backend

From repository root:
```bash
# Ensure virtualenv is active and dependencies installed
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Start the server on port 8000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 2. Generating Authentication Tokens

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
