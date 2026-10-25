from test_auth_helpers import auth_headers
"""Contract tests for the feature/android-initialization bridge."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

for key in ('MONGODB_URI', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'SAINT_WEBHOOK_URL'):
    os.environ[key] = ''
os.environ['TEMPO_DEMO_MODE'] = 'false'

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import android_api


def analysis_payload():
    return {
        'session_id': 'canonical-analysis-id', 'coaching_model': 'deterministic-verified-fallback',
        'pro_comparison': {'matched_pro': 'Demo reference'},
        'biomechanical_diagnosis': 'Measured elbow extension is 170 degrees.',
        'live_drill_prescription': 'Comfortable overhead reach practice.',
        'verification_status': 'PASS', 'demo_mode': False,
        'pose_analysis': {'pose_vector': [.94, .8, .9, .8, .7, .9], 'used_fallback': False},
    }


class AndroidBridgeTests(unittest.TestCase):
    def setUp(self):
        android_api._MEMORY.clear()
        self.db = patch.object(android_api.db_mongo, 'get_db', return_value=None)
        self.db.start()
        self.addCleanup(self.db.stop)
        self.analyze = AsyncMock(return_value=analysis_payload())
        self.events = []
        app = FastAPI()
        app.include_router(android_api.create_android_router(self.analyze, lambda *args: self.events.append(args)))
        self.client = TestClient(app, headers=auth_headers())
        self.metadata = {'user_id': 'alice', 'sport': 'badminton', 'stroke_type': 'overhead_clear',
                         'telemetry': [{'timestamp_ms': int(__import__('time').time() * 1000) - 1000, 'heart_rate': 120},
                                       {'timestamp_ms': int(__import__('time').time() * 1000), 'heart_rate': 140}]}

    def upload(self, metadata=None, filename='practice.mp4', content=b'video content'):
        return self.client.post('/api/v1/sessions/ingest', data={
            'metadata': json.dumps(self.metadata if metadata is None else metadata)},
            files={'video': (filename, content, 'video/mp4')})

    def test_ingest_202_then_poll_completed_real_contract(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.text)
        body = response.json()
        self.assertEqual(body['status'], 'PENDING')
        record = self.client.get('/api/v1/sessions/' + body['session_id']).json()
        for key in ('session_id', 'user_id', 'sport', 'stroke_type', 'status', 'gemini_feedback', 'active_widgets'):
            self.assertIn(key, record)
        self.assertEqual(record['status'], 'COMPLETED')
        self.assertEqual(record['user_id'], 'alice')
        self.assertEqual(record['telemetry_count'], 2)
        self.assertEqual(record['kinematic_vector'], analysis_payload()['pose_analysis']['pose_vector'])
        self.assertEqual(record['pipeline_session_id'], 'canonical-analysis-id')
        self.assertEqual(record['active_widgets'][0]['widget_type'], 'DrillCardWidget')
        # The measured, threshold-consistent score drives the adaptive curriculum, so it is reported.
        self.assertEqual(record['gemini_feedback']['overall_score'], record['overall_score'])
        self.assertEqual(record['adaptation']['action'], 'no_active_lesson')
        self.assertEqual(record['storage_mode'], 'in_memory_fallback')
        self.assertNotIn('telemetry', record)

    def test_android_client_id_is_preserved_and_retries_do_not_reanalyze(self):
        metadata = {**self.metadata, 'session_id': 'android-session-123', 'user_intent': 'Reach comfortably'}
        first = self.upload(metadata)
        self.assertEqual(first.json()['session_id'], metadata['session_id'])
        self.assertEqual(self.client.get('/api/v1/sessions/android-session-123').json()['status'], 'COMPLETED')
        second = self.upload(metadata)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()['status'], 'COMPLETED')
        self.analyze.assert_awaited_once()

    def test_id_reuse_with_different_player_or_clip_is_rejected(self):
        metadata = {**self.metadata, 'session_id': 'stable-id'}
        self.upload(metadata)
        self.assertEqual(self.upload({**metadata, 'user_id': 'bob'}).status_code, 409)
        self.assertEqual(self.upload(metadata, content=b'other clip').status_code, 409)
        self.analyze.assert_awaited_once()

    def test_invalid_client_id_is_rejected(self):
        self.assertEqual(self.upload({**self.metadata, 'session_id': '../unsafe'}).status_code, 422)

    def test_phase_timing_is_only_returned_when_measured(self):
        payload = analysis_payload()
        self.assertEqual(android_api._feedback(payload)['kinetic_phases'], [])
        payload['pose_analysis']['peak_contact_timestamp_ms'] = 1234
        phase = android_api._feedback(payload)['kinetic_phases'][0]
        self.assertEqual(phase['timestamp_ms'], 1234)
        self.assertIsNone(phase['form_accuracy_score'])
        payload['pose_analysis']['used_fallback'] = True
        self.assertEqual(android_api._feedback(payload)['kinetic_phases'], [])

    def test_drill_matches_android_required_fields(self):
        response = self.upload()
        record = self.client.get('/api/v1/sessions/' + response.json()['session_id']).json()
        drill = record['active_widgets'][0]
        self.assertTrue({'id', 'title', 'instruction', 'target_reps', 'focus_cue'} <= drill.keys())
        self.assertGreater(drill['target_reps'], 0)

    def test_maps_health_connect_samples_to_pipeline_metrics(self):
        self.upload()
        args = self.analyze.call_args.kwargs
        self.assertEqual(args['user_name'], 'alice')
        self.assertEqual(args['heart_rate_bpm'], 130)
        self.assertIsNone(args['active_calories_kcal'])
        self.assertIsNone(args['apple_watch_payload'])

    def test_empty_telemetry_uses_paired_watch_path(self):
        self.upload({**self.metadata, 'telemetry': []})
        self.assertIsNone(self.analyze.call_args.kwargs['heart_rate_bpm'])
        self.assertEqual(self.analyze.call_args.kwargs['user_name'], 'alice')

    def test_pipeline_422_becomes_failed_session(self):
        self.analyze.side_effect = HTTPException(status_code=422, detail={'pose_status': 'multiple_players_detected'})
        response = self.upload()
        self.assertEqual(response.status_code, 202)
        record = self.client.get('/api/v1/sessions/' + response.json()['session_id']).json()
        self.assertEqual(record['status'], 'FAILED')
        self.assertEqual(record['error_code'], 422)
        self.assertIn('multiple_players_detected', record['error_message'])

    def test_model_missing_error_is_visible(self):
        self.analyze.side_effect = HTTPException(status_code=503, detail='Pose engine unavailable')
        response = self.upload()
        record = self.client.get('/api/v1/sessions/' + response.json()['session_id']).json()
        self.assertEqual(record['error_code'], 503)
        self.assertEqual(record['status'], 'FAILED')

    def test_rejects_missing_video(self):
        response = self.client.post('/api/v1/sessions/ingest', data={'metadata': json.dumps(self.metadata)})
        self.assertEqual(response.status_code, 422)
        self.analyze.assert_not_called()

    def test_rejects_invalid_metadata_and_unsupported_strokes(self):
        for metadata in ({}, {**self.metadata, 'stroke_type': 'backhand'},
                         {**self.metadata, 'telemetry': [{'timestamp_ms': 1, 'heart_rate': -1}]}):
            self.assertEqual(self.upload(metadata).status_code, 422)
        self.analyze.assert_not_called()

    def test_rejects_bad_file_extension_and_empty_video(self):
        self.assertEqual(self.upload(filename='malware.exe').status_code, 415)
        self.assertEqual(self.upload(content=b'').status_code, 422)
        self.analyze.assert_not_called()

    def test_upload_size_bound(self):
        with patch.object(android_api, 'MAX_UPLOAD_BYTES', 4):
            self.assertEqual(self.upload(content=b'12345').status_code, 413)
        self.analyze.assert_not_called()

    def test_upload_files_cleaned_on_success_and_failure(self):
        real_factory = tempfile.NamedTemporaryFile
        with tempfile.TemporaryDirectory() as directory:
            def factory(*args, **kwargs):
                return real_factory(*args, dir=directory, **kwargs)
            with patch.object(android_api.tempfile, 'NamedTemporaryFile', side_effect=factory):
                self.upload()
                self.analyze.side_effect = HTTPException(status_code=422, detail='Bad pose')
                self.upload()
                self.upload(content=b'')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_session_is_404(self):
        self.assertEqual(self.client.get('/api/v1/sessions/unknown').status_code, 404)

    def test_schedule_roundtrip_is_separate_per_user(self):
        schedule = self.client.get('/api/v1/cadence/schedule/alice').json()
        schedule['target_time_utc'] = '19:30'
        self.assertEqual(self.client.post('/api/v1/cadence/schedule', json=schedule).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/cadence/schedule/alice').json()['target_time_utc'], '19:30')
        self.assertEqual(self.client.get('/api/v1/cadence/schedule/bob').json()['target_time_utc'], '18:00')

    def test_schedule_rejects_invalid_time(self):
        self.assertEqual(self.client.post('/api/v1/cadence/schedule', json={
            'user_id': 'alice', 'target_time_utc': '99:99'}).status_code, 422)

    def test_live_contract_is_explicitly_rule_based(self):
        with self.client.websocket_connect('/api/v1/live/stream') as ws:
            ws.send_json({'heart_rate': 140, 'sport': 'badminton', 'stroke_type': 'smash'})
            reply = ws.receive_json()
            self.assertFalse(reply['vision_analyzed'])
            self.assertEqual(reply['source'], 'heart_rate_rule_only')

    def test_live_validation_does_not_close_connection(self):
        with self.client.websocket_connect('/api/v1/live/stream') as ws:
            ws.send_json({'heart_rate': -1})
            self.assertIn('error', ws.receive_json())
            ws.send_json({'heart_rate': 140})
            self.assertIn('cue', ws.receive_json())


if __name__ == '__main__':
    unittest.main()
