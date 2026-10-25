"""Local operator tool. Tokens are written to a private file, never printed."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import secrets

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['issue', 'revoke'])
parser.add_argument('--user', required=True)
parser.add_argument('--role', choices=['player', 'admin', 'saint'], default='player')
parser.add_argument('--days', type=int, default=30)
parser.add_argument('--token-file', type=Path, required=True)
parser.add_argument('--store', type=Path, default=Path(__file__).with_name('.tempo-auth.json'))
args = parser.parse_args()
if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}', args.user) or not 1 <= args.days <= 90:
    parser.error('Use a lowercase player ID containing letters, digits, underscores or hyphens, and a lifetime between 1 and 90 days')
table = json.loads(args.store.read_text()) if args.store.exists() else {}
if args.action == 'issue':
    if args.token_file.exists():
        parser.error('Token output already exists; choose a new file')
    token = secrets.token_urlsafe(48)
    table[hashlib.sha256(token.encode()).hexdigest()] = {
        'user_id': args.user, 'role': args.role,
        'expires_at': (datetime.now(timezone.utc) + timedelta(days=args.days)).isoformat()}
    args.token_file.parent.mkdir(parents=True, exist_ok=True)
    with open(args.token_file, 'x', encoding='utf-8') as target:
        target.write(token)
    os.chmod(args.token_file, 0o600)
else:
    token = args.token_file.read_text().strip()
    record = table.get(hashlib.sha256(token.encode()).hexdigest())
    if not record or record['user_id'] != args.user:
        parser.error('Credential does not belong to that player')
    record['disabled'] = True
temporary = args.store.with_suffix('.tmp')
temporary.write_text(json.dumps(table, indent=2), encoding='utf-8')
os.chmod(temporary, 0o600)
temporary.replace(args.store)
print('Credential ' + ('issued to the chosen private file.' if args.action == 'issue' else 'revoked.'))
