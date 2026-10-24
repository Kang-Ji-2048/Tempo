import json
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import main
import auth
import android_api
import db_mongo
from test_auth_helpers import auth_headers

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'TEMPO_AUTH_TOKENS': '{}'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.database = patch.object(db_mongo, 'get_db', return_value=None)
        self.database.start()
        self.addCleanup(self.database.stop)
        android_api._MEMORY.clear()
        self.alice_headers = auth_headers('alice', 'player')
        self.bob_headers = auth_headers('bob', 'player')
        self.alice = TestClient(main.app, headers=self.alice_headers)
        self.bob = TestClient(main.app, headers=self.bob_headers)
        self.anonymous = TestClient(main.app)

    def test_sample_timestamp_is_required_and_preserved(self):
        from datetime import datetime, timezone, timedelta
        base = {'user_name': 'alice', 'heart_rate_bpm': 140}
        self.assertEqual(self.alice.post('/pipeline/etl-apple-watch', json=base).status_code, 422)
        for value in ((datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat(),
                      (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(), '2026-10-24T12:00:00'):
            self.assertEqual(self.alice.post('/pipeline/etl-apple-watch', json={**base, 'sampled_at': value}).status_code, 422)
        timestamp = datetime.now(timezone.utc).isoformat()
        response = self.alice.post('/pipeline/etl-apple-watch', json={**base, 'sampled_at': timestamp})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['apple_watch_biometrics']['sampled_at'], timestamp)

    def test_private_routes_require_authentication(self):
        for path in ('/dashboard', '/architecture', '/openapi.json', '/pipeline/latest-apple-watch',
                     '/api/v1/sessions/unknown', '/api/v1/cadence/schedule/alice'):
            self.assertEqual(self.anonymous.get(path).status_code, 401, path)

    def test_public_health_has_no_database_or_model_details(self):
        self.assertEqual(self.anonymous.get('/health').json(), {'status': 'ready', 'service': 'tempo'})

    def test_unconfigured_authentication_fails_closed(self):
        with patch.dict(os.environ, {'TEMPO_AUTH_TOKENS': '{}'}):
            self.assertEqual(self.alice.get('/dashboard').status_code, 503)

    def test_cross_player_watch_reads_are_denied(self):
        for path in ('/pipeline/latest-apple-watch?user_name=bob', '/pipeline/watch-timeseries/bob', '/pipeline/analytics/bob'):
            self.assertEqual(self.alice.get(path).status_code, 403)
        self.assertEqual(self.alice.get('/pipeline/watch-timeseries/alice').status_code, 200)

    def test_cross_player_session_and_schedule_are_denied(self):
        android_api._put('android_sessions', 'bob-session', {'session_id': 'bob-session', 'user_id': 'bob'})
        self.assertEqual(self.alice.get('/api/v1/sessions/bob-session').status_code, 403)
        self.assertEqual(self.alice.get('/api/v1/cadence/schedule/bob').status_code, 403)
        self.assertEqual(self.alice.post('/api/v1/cadence/schedule', json={'user_id': 'bob'}).status_code, 403)

    def test_cross_player_upload_is_denied(self):
        r = self.alice.post('/api/v1/sessions/ingest', data={'metadata': json.dumps({
            'user_id': 'bob', 'sport': 'badminton', 'stroke_type': 'overhead_clear'})},
            files={'video': ('clip.mp4', b'clip', 'video/mp4')})
        self.assertEqual(r.status_code, 403)

    def test_pairing_code_does_not_grant_another_players_write_access(self):
        code = db_mongo.create_watch_pairing_session('bob')['pairing_code']
        r = self.alice.post('/pipeline/etl-apple-watch', json={'pairing_code': code, 'heart_rate_bpm': 140})
        self.assertEqual(r.status_code, 403)

    def test_pair_creation_and_approval_cannot_impersonate_another_player(self):
        self.assertEqual(self.alice.post('/pipeline/pair-watch', json={'user_name': 'bob'}).status_code, 403)
        self.assertEqual(self.alice.post('/pipeline/approve-saint-action', json={
            'session_id': 'bob-session', 'user_name': 'bob', 'approved': True}).status_code, 403)

    def test_cookie_login_and_csrf(self):
        token = self.alice_headers['Authorization'][7:]
        self.assertEqual(self.anonymous.post('/auth/session', json={'token': token}).status_code, 403)
        r = self.anonymous.post('/auth/session', json={'token': token}, headers={'Origin': 'http://testserver'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('HttpOnly', r.headers['set-cookie'])
        self.assertEqual(self.anonymous.get('/dashboard').status_code, 200)
        self.assertEqual(self.anonymous.post('/pipeline/pair-watch', json={'user_name': 'alice'},
            headers={'Origin': 'https://attacker.example'}).status_code, 403)

    def test_live_events_are_filtered_by_verified_identity(self):
        identity = {'user_id': 'alice', 'role': 'player'}
        self.assertTrue(auth.event_visible(identity, {'data': {'user_name': 'alice'}}))
        self.assertFalse(auth.event_visible(identity, {'data': {'user_name': 'bob'}}))
        self.assertFalse(auth.event_visible(identity, {'data': {}}))

    def test_websocket_requires_a_credential(self):
        with self.assertRaises(WebSocketDisconnect) as error:
            with self.anonymous.websocket_connect('/api/v1/live/stream'):
                pass
        self.assertEqual(error.exception.code, 4401)

    def test_case_alias_credentials_cannot_share_a_lowercased_watch_bucket(self):
        headers = auth_headers('ALICE', 'player')
        self.assertEqual(TestClient(main.app, headers=headers).get('/pipeline/latest-apple-watch').status_code, 503)

    def test_revoked_and_expired_tokens_are_denied(self):
        table = json.loads(os.environ['TEMPO_AUTH_TOKENS'])
        for record in table.values(): record['expires_at'] = '2000-01-01T00:00:00+00:00'
        with patch.dict(os.environ, {'TEMPO_AUTH_TOKENS': json.dumps(table)}):
            self.assertEqual(self.alice.get('/dashboard').status_code, 401)
        for record in table.values():
            record['expires_at'] = '2099-01-01T00:00:00+00:00'
            record['disabled'] = True
        with patch.dict(os.environ, {'TEMPO_AUTH_TOKENS': json.dumps(table)}):
            self.assertEqual(self.alice.get('/dashboard').status_code, 401)
