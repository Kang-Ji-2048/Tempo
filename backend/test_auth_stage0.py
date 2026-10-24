"""Stage 0 Verification Tests:
Verifies public /health access, 401 on protected routes without bearer token,
and 200 on protected routes with a valid player token.
"""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

import main
import db_mongo
import android_api
from test_auth_helpers import auth_headers


class Stage0AuthHealthTests(unittest.TestCase):

    def setUp(self):
        self.environment = patch.dict(os.environ, {'TEMPO_AUTH_TOKENS': '{}'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.database = patch.object(db_mongo, 'get_db', return_value=None)
        self.database.start()
        self.addCleanup(self.database.stop)
        android_api._MEMORY.clear()

        self.user1_headers = auth_headers('user_1', 'player')
        self.user1_client = TestClient(main.app, headers=self.user1_headers)
        self.anonymous_client = TestClient(main.app)

    def test_health_endpoint_is_open_without_auth(self):
        """GET /health must work without any authentication."""
        response = self.anonymous_client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ready')
        self.assertEqual(data.get('service'), 'tempo')

    def test_protected_route_returns_401_without_token(self):
        """Protected routes must return 401 Unauthorized with WWW-Authenticate header when token is missing."""
        for path in [
            '/api/v1/cadence/schedule/user_1',
            '/api/v1/sessions/sess_sample_01',
            '/pipeline/watch-timeseries/user_1',
            '/dashboard'
        ]:
            response = self.anonymous_client.get(path)
            self.assertEqual(response.status_code, 401, f"Path {path} should require authentication")
            self.assertEqual(response.headers.get('WWW-Authenticate'), 'Bearer')

    def test_protected_route_returns_200_with_valid_token(self):
        """Protected routes must succeed (HTTP 200) when presented with a valid bearer token for user_1."""
        # 1. Schedule endpoint for user_1
        response = self.user1_client.get('/api/v1/cadence/schedule/user_1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user_id'], 'user_1')

        # 2. Ingested session retrieval for user_1
        android_api._put('android_sessions', 'user1-test-session', {
            'session_id': 'user1-test-session',
            'user_id': 'user_1',
            'status': 'COMPLETED'
        })
        session_resp = self.user1_client.get('/api/v1/sessions/user1-test-session')
        self.assertEqual(session_resp.status_code, 200)
        self.assertEqual(session_resp.json()['user_id'], 'user_1')
