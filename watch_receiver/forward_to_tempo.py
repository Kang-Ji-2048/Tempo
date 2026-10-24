"""Run after deployment; both network connections originate from this laptop."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True, help='Deployed HTTPS receiver origin')
parser.add_argument('--user-id', required=True, help='Player ID matching the Android profile')
parser.add_argument('--state', default=str(Path(__file__).with_name('.forwarded-state.json')))
args = parser.parse_args()
origin = args.url.rstrip('/')
parts = urlsplit(origin)
if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
    raise SystemExit('Use an HTTPS origin without credentials, query, or fragment')
key = os.environ.get('TEMPO_READ_KEY', '')
if len(key) < 32:
    raise SystemExit('Set TEMPO_READ_KEY before starting the receiver')
api_token_path = os.environ.get('TEMPO_API_TOKEN_FILE')
api_token = Path(api_token_path).read_text().strip() if api_token_path else os.environ.get('TEMPO_API_TOKEN', '')
if len(api_token) < 32:
    raise SystemExit('Configure TEMPO_API_TOKEN_FILE for this player')
state = Path(args.state)
last_id = state.read_text(encoding='utf-8').strip() if state.exists() else ''
pair_request = urllib.request.Request('http://127.0.0.1:8000/pipeline/pair-watch',
    data=json.dumps({'user_name': args.user_id, 'android_device_id': 'hosted_https_relay'}).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_token})
with urllib.request.urlopen(pair_request, timeout=10) as response:
    pairing = json.load(response)['pairing_code']
print('Waiting for real readings. Press Ctrl+C to stop.', flush=True)
while True:
    try:
        request = urllib.request.Request(origin + '/reading', headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=15) as response:
            reading = json.load(response)['reading']
        if reading and reading['reading_id'] != last_id:
            request = urllib.request.Request('http://127.0.0.1:8000/pipeline/etl-apple-watch',
                data=json.dumps({'pairing_code': pairing, 'heart_rate_bpm': reading['heart_rate_bpm'], 'sampled_at': reading['sampled_at']}).encode(),
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + api_token})
            with urllib.request.urlopen(request, timeout=10) as response:
                json.load(response)
            last_id = reading['reading_id']
            state.write_text(last_id, encoding='utf-8')
            print('Forwarded a new reading into Tempo.', flush=True)
    except KeyboardInterrupt:
        break
    except Exception as exc:
        print('Receiver temporarily unavailable: ' + type(exc).__name__, flush=True)
    time.sleep(3)
