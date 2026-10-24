from test_auth_helpers import auth_headers
"""Offline architecture regressions. No Atlas, model, or booking requests are made."""
import datetime
import os
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from types import SimpleNamespace

# Set before imports so local .env cannot activate external services.
for name in ('MONGODB_URI', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'SAINT_WEBHOOK_URL'):
    os.environ[name] = ''
os.environ['TEMPO_DEMO_MODE'] = 'false'

from fastapi.testclient import TestClient
import db_mongo as db
import agent_argon_saint as agent
import etl_pose
import main


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.database = patch.object(db, 'get_db', return_value=None)
        self.database.start()
        self.addCleanup(self.database.stop)
        db._LATEST_WATCH_METRICS.clear()
        db._MEMORY_WATCH_TS.clear()
        db._MEMORY_PAIRINGS.clear()
        db._MEMORY_APPROVALS.clear()
        db._MEMORY_STROKES[:] = [dict(p) for p in db.PRO_REFERENCE_STROKES]
        self.client = TestClient(main.app, headers=auth_headers())

    def session(self, user='alice'):
        return db.save_analysis_session({
            'user_name': user, 'saint_approval_status': 'PENDING_HUMAN_APPROVAL',
            'saint_agent_job': {'plain_english_instruction': 'Saved instruction',
                                'venue': 'Saved venue', 'proposed_slot': 'Saved slot'},
            'apple_watch_biometrics': {'heart_rate_bpm': 130},
            'pose_analysis': {'raw_angles': {'right_elbow_contact_deg': 170,
                                             'contact_height_norm': .9}},
            'verification_status': 'PASS',
        })

    def test_android_session_uses_only_the_matching_players_watch(self):
        from unittest.mock import AsyncMock
        import android_api
        android_api._MEMORY.clear()
        db.save_live_watch_telemetry('alice', etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=137))
        db.save_live_watch_telemetry('bob', etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=181))
        import json
        with patch.object(main, 'extract_pose_from_video', return_value={
            'used_fallback': False, 'status': 'pose_extracted', 'pose_vector': [.9] * 6,
            'raw_angles': {'right_elbow_contact_deg': 170}, 'frames_scanned': 3, 'peak_contact_frame': 1,
        }):
            response = self.client.post('/api/v1/sessions/ingest', data={'metadata': json.dumps({
                'session_id': 'watch-session', 'user_id': 'alice', 'sport': 'badminton',
                'stroke_type': 'overhead_clear', 'telemetry': []})}, files={'video': ('clip.mp4', b'clip', 'video/mp4')})
        record = self.client.get('/api/v1/sessions/' + response.json()['session_id']).json()
        self.assertEqual(record['status'], 'COMPLETED', record)
        self.assertEqual(record['apple_watch_biometrics']['heart_rate_bpm'], 137)
        self.assertEqual(record['apple_watch_biometrics']['user_id'], 'alice')

    def test_stale_watch_receipt_fails_instead_of_inventing_data(self):
        metrics = etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=140)
        db.save_live_watch_telemetry('alice', metrics)
        db._LATEST_WATCH_METRICS['alice']['sampled_at'] = '2000-01-01T00:00:00+00:00'
        with patch.object(main, 'extract_pose_from_video', return_value={
            'used_fallback': False, 'status': 'pose_extracted'}):
            response = self.client.post('/pipeline/analyze-stroke', data={'user_name': 'alice'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('Shortcut', response.json()['detail'])

    def test_health_and_views(self):
        for route in ('/health', '/dashboard', '/architecture'):
            self.assertEqual(self.client.get(route).status_code, 200, route)
        pair = db.create_watch_pairing_session('alice')
        self.assertEqual(self.client.get('/watch-companion', params={'code': pair['pairing_code'], 'user': 'alice'}).status_code, 200)

    def test_video_required_outside_demo(self):
        self.assertEqual(self.client.post('/pipeline/analyze-stroke').status_code, 422)

    def test_demo_pipeline_is_explicit_and_stages_locally(self):
        with patch.dict(os.environ, {'TEMPO_DEMO_MODE': 'true'}), patch.object(agent, 'dispatch_saint_webhook') as dispatch:
            response = self.client.post('/pipeline/analyze-stroke', data={'user_name': 'alice'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['demo_mode'])
        self.assertTrue(response.json()['pose_analysis']['used_fallback'])
        dispatch.assert_not_called()

    def test_telemetry_never_returns_other_users_latest(self):
        db.save_live_watch_telemetry('alice', etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=130))
        self.assertIsNone(db.get_latest_watch_telemetry('bob'))
        self.assertEqual(db.get_watch_timeseries_window('bob')['sample_count'], 0)

    def test_pairing_resolves_user_before_window_query(self):
        pair = db.create_watch_pairing_session('alice')
        response = self.client.post('/pipeline/etl-apple-watch', json={'sampled_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'pairing_code': pair['pairing_code'], 'user_name': 'wrong', 'heart_rate_bpm': 140})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['watch_timeseries_window']['user_name'], 'alice')
        self.assertEqual(response.json()['watch_timeseries_window']['sample_count'], 1)

    def test_bad_and_expired_pairing_rejected(self):
        self.assertEqual(self.client.post('/pipeline/etl-apple-watch', json={'sampled_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'pairing_code': 'unknown', 'heart_rate_bpm': 140}).status_code, 400)
        pair = db.create_watch_pairing_session('alice')
        pair['expires_at'] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):
            db.save_live_watch_telemetry('alice', {}, pair['pairing_code'])

    def test_pair_codes_have_adequate_space(self):
        codes = [db.create_watch_pairing_session()['pairing_code'] for _ in range(200)]
        self.assertEqual(len(set(codes)), 200)
        self.assertTrue(all(len(c) == 13 for c in codes))

    def test_pair_url_preserves_https_and_encodes_user(self):
        with patch.dict(os.environ, {'TEMPO_PUBLIC_BASE_URL': 'https://tempo.example'}):
            response = self.client.post('/pipeline/pair-watch', json={'user_name': 'Alice & Bob'})
        self.assertTrue(response.json()['companion_url'].startswith('https://tempo.example/'))
        self.assertIn('Alice+%26+Bob', response.json()['companion_url'])

    def test_missing_user_has_no_fabricated_analytics(self):
        result = db.get_fatigue_biomechanics_analytics('unknown')
        self.assertEqual(result['hr_zone_buckets'], [])
        self.assertFalse(result['has_comparable_zones'])

    def test_analytics_use_saved_data(self):
        self.session()
        result = db.get_fatigue_biomechanics_analytics('alice')
        self.assertEqual(result['hr_zone_buckets'][0]['avg_elbow_contact_deg'], 170)
        self.assertEqual(result['overall_summary']['total_sessions'], 1)

    def test_window_limit_is_validated(self):
        for limit in (0, -1, 1001):
            self.assertEqual(self.client.get(f'/pipeline/watch-timeseries/alice?limit={limit}').status_code, 422)

    def test_approval_requires_explicit_session_and_decision(self):
        for body in ({}, {'session_id': 'unknown'}, {'approved': True}):
            self.assertIn(self.client.post('/pipeline/approve-saint-action', json=body).status_code, (400, 422))

    def test_unknown_session_cannot_dispatch_or_change_latest(self):
        sid = self.session()
        with patch.object(main, 'dispatch_saint_webhook') as dispatch:
            response = self.client.post('/pipeline/approve-saint-action', json={
                'session_id': 'unknown', 'user_name': 'alice', 'approved': True})
        self.assertEqual(response.status_code, 404)
        dispatch.assert_not_called()
        self.assertEqual(db.get_analysis_session(sid)['saint_approval_status'], 'PENDING_HUMAN_APPROVAL')

    def test_wrong_user_cannot_approve(self):
        sid = self.session()
        self.assertEqual(self.client.post('/pipeline/approve-saint-action', json={
            'session_id': sid, 'user_name': 'bob', 'approved': True}).status_code, 403)

    def test_saved_job_and_duplicate_prevention(self):
        sid = self.session()
        body = {'session_id': sid, 'user_name': 'alice', 'approved': True}
        with patch.object(main, 'dispatch_saint_webhook', return_value={'dispatched': True, 'webhook_configured': True}) as dispatch:
            first = self.client.post('/pipeline/approve-saint-action', json=body)
            second = self.client.post('/pipeline/approve-saint-action', json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.kwargs['saint_agent_job']['venue'], 'Saved venue')
        self.assertEqual(first.json()['execution_summary']['court_booking_status'], 'DISPATCHED_AWAITING_CONFIRMATION')

    def test_missing_webhook_does_not_confirm_booking(self):
        sid = self.session()
        response = self.client.post('/pipeline/approve-saint-action', json={
            'session_id': sid, 'user_name': 'alice', 'approved': True})
        self.assertEqual(response.json()['saint_approval_status'], 'APPROVED_AWAITING_WEBHOOK')
        self.assertEqual(response.json()['execution_summary']['court_booking_status'], 'NOT_EXECUTED')

    def test_rejection_does_not_dispatch(self):
        sid = self.session()
        with patch.object(main, 'dispatch_saint_webhook') as dispatch:
            response = self.client.post('/pipeline/approve-saint-action', json={
                'session_id': sid, 'user_name': 'alice', 'approved': False})
        self.assertEqual(response.json()['saint_approval_status'], 'REJECTED_BY_USER')
        dispatch.assert_not_called()

    def test_payload_job_override_is_rejected(self):
        sid = self.session()
        response = self.client.post('/pipeline/approve-saint-action', json={
            'session_id': sid, 'user_name': 'alice', 'approved': True, 'saint_agent_job': {'venue': 'Other venue'}})
        self.assertEqual(response.status_code, 400)

    def test_invalid_telemetry_does_not_store_defaults(self):
        for value in ('{broken', '<broken', 'C:/Windows/win.ini', ''):
            response = self.client.post('/pipeline/etl-apple-watch', data={'apple_watch_payload': value})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(len(db._MEMORY_WATCH_TS), 0)

    def test_numeric_validation(self):
        for value in (-1, float('nan'), float('inf'), 300):
            with self.assertRaises(ValueError):
                etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=value)
        for angle in (-1, 181, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                agent.verify_biomechanical_threshold(angle)

    def test_sample_health_exports(self):
        from pathlib import Path
        for path in Path(__file__).with_name('sample_data').iterdir():
            if path.suffix not in ('.json', '.xml'):
                continue
            result = etl_pose.parse_apple_watch_metrics(payload=path.read_bytes())
            self.assertGreater(result['heart_rate_bpm'], 0)

    def test_rolling_window(self):
        for hr in (120, 150, 180, 160):
            db.save_live_watch_telemetry('alice', etl_pose.parse_apple_watch_metrics(sampled_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), heart_rate_bpm=hr))
        samples = db.get_watch_timeseries_window('alice', limit=1)['samples']
        self.assertEqual(samples[0]['rolling_avg_hr_bpm'], 163.3)

    def test_atlas_latest_lookup_is_scoped(self):
        database = MagicMock()
        database[db.PLAYERS_COLLECTION].find_one.return_value = None
        with patch.object(db, 'get_db', return_value=database):
            self.assertIsNone(db.get_latest_watch_telemetry('bob'))
        query = database[db.PLAYERS_COLLECTION].find_one.call_args.args[0]
        self.assertEqual(query['user_name'], 'bob')

    def test_atlas_window_never_drops_user_filter(self):
        database = MagicMock()
        database[db.WATCH_TS_COLLECTION].aggregate.return_value = []
        with patch.object(db, 'get_db', return_value=database):
            db.get_watch_timeseries_window('bob')
        pipeline = database[db.WATCH_TS_COLLECTION].aggregate.call_args.args[0]
        self.assertEqual(pipeline[0], {'$match': {'metadata.user_name': 'bob'}})

    def test_atomic_claim_allows_one_concurrent_approval(self):
        from concurrent.futures import ThreadPoolExecutor
        sid = self.session()
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: db.claim_saint_action(sid, 'alice'), range(20)))
        self.assertEqual(sum(claims), 1)

    def test_gemini_sdk_call_and_output_parsing(self):
        client = MagicMock()
        client.interactions.create.return_value = SimpleNamespace(steps=[
            SimpleNamespace(content=[SimpleNamespace(type='text', text='{"ok":true}')])])
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test', 'GEMINI_MODEL': 'configured-model'}), patch.object(agent.genai, 'Client', return_value=client):
            self.assertEqual(agent._call_gemini_4_argon('prompt', {'type': 'object'}), '{"ok":true}')
        call = client.interactions.create.call_args.kwargs
        self.assertEqual(call['model'], 'configured-model')
        self.assertEqual(call['response_format']['mime_type'], 'application/json')
        self.assertEqual(call['generation_config']['thinking_level'], 'high')


if __name__ == '__main__':
    unittest.main()
