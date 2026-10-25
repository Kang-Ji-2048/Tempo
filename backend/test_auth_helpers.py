"""Explicit offline-test credentials; never imported by application startup."""
import hashlib
import json
import os

def auth_headers(user_id='test-admin', role='admin'):
    token = 'offline-test-credential-for-' + user_id + '-' + role + '-00000000'
    table = json.loads(os.environ.get('TEMPO_AUTH_TOKENS', '{}'))
    table[hashlib.sha256(token.encode()).hexdigest()] = {
        'user_id': user_id, 'role': role, 'expires_at': '2099-01-01T00:00:00+00:00'}
    os.environ['TEMPO_AUTH_TOKENS'] = json.dumps(table)
    return {'Authorization': 'Bearer ' + token}
