import unittest
from datetime import datetime, timezone, timedelta
from telemetry_time import normalize, require_recent
from etl_pose import parse_apple_watch_metrics

class SampleTimeTests(unittest.TestCase):
    def test_timezone_normalization_preserves_the_instant(self):
        self.assertEqual(normalize('2026-10-24T15:00:00+01:00'), '2026-10-24T14:00:00+00:00')

    def test_missing_and_naive_times_are_rejected(self):
        for value in (None, '2026-10-24T12:00:00', 'bad'):
            with self.assertRaises(ValueError): require_recent(value)

    def test_missing_heart_rate_cannot_invent_a_measurement(self):
        with self.assertRaises(ValueError):
            parse_apple_watch_metrics(payload={'sampled_at': datetime.now(timezone.utc).isoformat()})
        result = parse_apple_watch_metrics(payload={'heart_rate_bpm':140})
        self.assertIn('active_calories_kcal', result['estimated_fields'])

    def test_json_parser_keeps_sensor_time(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        for payload in ({'heart_rate_bpm':140, 'sampled_at':timestamp},
                        '{"heart_rate_bpm":140,"sampled_at":"'+timestamp+'"}'):
            self.assertEqual(parse_apple_watch_metrics(payload=payload)['sampled_at'], timestamp)
