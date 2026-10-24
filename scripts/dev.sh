#!/usr/bin/env bash
set -e

# scripts/dev.sh - Start Tempo backend reachable from physical phones on LAN
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo "TEMPO BACKEND DEV SERVER RUNNER"
echo "============================================================"

# 1. Load backend/.env if present
if [ -f "$ROOT_DIR/backend/.env" ]; then
    echo "Loading environment from backend/.env..."
    set -o allexport
    source "$ROOT_DIR/backend/.env"
    set +o allexport
fi

# 2. Print machine's LAN IPv4 addresses
echo ""
echo "--- LAN IPv4 Addresses on this machine ---"
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    ipconfig getifaddr en0 2>/dev/null && echo "  Wi-Fi (en0): $(ipconfig getifaddr en0)"
    ipconfig getifaddr en1 2>/dev/null && echo "  Ethernet/Wi-Fi (en1): $(ipconfig getifaddr en1)"
    ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print "  LAN IP: " $2}'
else
    # Linux
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | sed 's/^/  LAN IP: /'
fi

echo ""
echo "For physical Android devices on the same Wi-Fi:"
echo "  Option A: Set BASE_URL=http://<YOUR_LAN_IP>:8000/ in android/local.properties and rebuild"
echo "  Option B (Recommended for USB): Run 'adb reverse tcp:8000 tcp:8000' and use http://localhost:8000/"
echo "Note (macOS): If connections fail, check System Settings -> Network -> Firewall and allow incoming connections."
echo "============================================================"
echo ""

# 3. Run uvicorn on 0.0.0.0:8000
cd "$ROOT_DIR"
exec uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
