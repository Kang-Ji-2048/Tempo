from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import server


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.write = 'write-' + 'a' * 40
        self.read = 'read-' + 'b' * 40
        self.keys = patch.multiple(server, WRITE_KEY=self.write, READ_KEY=self.read, _latest=None)
        self.keys.start()
        self.addCleanup(self.keys.stop)
        self.client = TestClient(server.app)

    def test_ready(self):
        self.assertEqual(self.client.get('/health').json(), {'status': 'ready'})

    def test_unconfigured_is_fail_closed(self):
        with patch.object(server, 'READ_KEY', self.write):
            for response in (self.client.get('/health'), self.client.get('/reading'), self.client.post('/watch', json={})):
                self.assertEqual(response.status_code, 503)

    def test_no_readings_initially(self):
        self.assertIsNone(self.client.get('/reading', headers={'Authorization': 'Bearer ' + self.read}).json()['reading'])

    def test_write_and_read_roundtrip(self):
        response = self.client.post('/watch', json={'heart_rate_bpm': 140, 'access_key': self.write})
        self.assertEqual(response.status_code, 200)
        latest = self.client.get('/reading', headers={'Authorization': 'Bearer ' + self.read}).json()['reading']
        self.assertEqual(latest['heart_rate_bpm'], 140)
        self.assertEqual(latest['source'], 'user_submitted')
        self.assertEqual(latest['reading_id'], response.json()['reading_id'])

    def test_write_key_cannot_read(self):
        self.assertEqual(self.client.get('/reading', headers={'Authorization': 'Bearer ' + self.write}).status_code, 401)

    def test_read_key_cannot_write(self):
        self.assertEqual(self.client.post('/watch', json={'heart_rate_bpm': 140, 'access_key': self.read}).status_code, 401)

    def test_authentication_required(self):
        self.assertEqual(self.client.get('/reading').status_code, 401)
        self.assertEqual(self.client.post('/watch', json={'heart_rate_bpm': 140}).status_code, 401)

    def test_unicode_key_is_rejected(self):
        self.assertEqual(self.client.post('/watch', json={'heart_rate_bpm': 140, 'access_key': '\u2603'}).status_code, 401)

    def test_invalid_readings_rejected(self):
        for hr in (-1, 251, 'nan', 'infinity', '120 bpm'):
            self.assertEqual(self.client.post('/watch', json={'heart_rate_bpm': hr, 'access_key': self.write}).status_code, 422)

    def test_large_request_rejected(self):
        self.assertEqual(self.client.post('/watch', content='x' * 4097).status_code, 413)

    def test_malformed_json_rejected(self):
        for content in ('{broken', '[]', 'null'):
            self.assertEqual(self.client.post('/watch', content=content).status_code, 400)

    def test_only_latest_reading_is_exposed(self):
        for hr in (120, 140):
            self.client.post('/watch', json={'heart_rate_bpm': hr, 'access_key': self.write})
        reading = self.client.get('/reading', headers={'Authorization': 'Bearer ' + self.read}).json()['reading']
        self.assertEqual(reading['heart_rate_bpm'], 140)

    def test_expired_reading_not_returned(self):
        server._latest = {'received_at': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), 'heart_rate_bpm': 140}
        self.assertIsNone(self.client.get('/reading', headers={'Authorization': 'Bearer ' + self.read}).json()['reading'])

    def test_page_contains_no_keys_and_has_no_store_headers(self):
        response = self.client.get('/')
        self.assertNotIn(self.write, response.text)
        self.assertNotIn(self.read, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
