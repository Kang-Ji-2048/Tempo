from test_auth_helpers import auth_headers
"""Offline geometry, quality-gate, Tasks API, and HTTP integration regressions."""
import io
import math
import os
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import MagicMock, patch

for key in ('MONGODB_URI', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'SAINT_WEBHOOK_URL'):
    os.environ[key] = ''
os.environ['TEMPO_DEMO_MODE'] = 'false'

import numpy as np
from fastapi.testclient import TestClient
import etl_pose as pose
import main
import db_mongo
import setup_pose_model as setup


def landmarks():
    image = [NS(x=.5, y=.5, z=0., visibility=.99, presence=.99) for _ in range(33)]
    image[0].y, image[12].y, image[14].y, image[16].y = .25, .4, .3, .1
    world = [NS(x=0., y=0., z=0.) for _ in range(33)]
    points = {0: (0, -1, 0), 12: (0, 0, 0), 14: (1, 0, 0), 16: (1, 1, 0),
              24: (0, 1, 0), 26: (1, 2, 0), 28: (1, 3, 0),
              11: (-1, 0, 0), 13: (-2, 0, 0), 23: (-1, 1, 0)}
    for idx, (x, y, z) in points.items():
        world[idx] = NS(x=x, y=y, z=z)
    return image, world


def result(image=None, world=None):
    if image is None:
        image, world = landmarks()
    return NS(pose_landmarks=[image], pose_world_landmarks=[world])


class PoseTests(unittest.TestCase):
    def extract(self, results, fps=30, timestamps=None):
        runtime = MagicMock()
        detector = runtime.tasks.vision.PoseLandmarker.create_from_options.return_value.__enter__.return_value
        detector.detect_for_video.side_effect = results
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(True, np.zeros((20, 30, 3), dtype=np.uint8)) for _ in results] + [(False, None)]
        timestamps = iter(timestamps or [0] * len(results))
        capture.get.side_effect = lambda prop: fps if prop == pose.cv2.CAP_PROP_FPS else next(timestamps)
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / 'input.mp4'
            model = Path(directory) / 'pose.task'
            video.touch()
            model.touch()
            with patch.object(pose, 'mp', runtime), patch.object(pose, '_ensure_mediapipe_loaded', return_value=True), patch.object(pose, 'pose_model_path', return_value=model), patch.object(pose.cv2, 'VideoCapture', return_value=capture):
                response = pose.extract_pose_from_video(str(video))
        self.assertEqual(capture.release.call_count, 1)
        return response, detector, runtime

    def test_world_angles_not_image_geometry(self):
        image, world = landmarks()
        angles = pose._angles_from_landmarks(world, image)
        self.assertEqual(angles['right_elbow_contact_deg'], 90)
        self.assertEqual(angles['contact_height_norm'], .9)
        self.assertEqual(len(pose.build_pose_vector(angles)), 6)

    def test_valid_clip_uses_tasks_video_and_peak_frame(self):
        first_image, first_world = landmarks()
        second_image, second_world = landmarks()
        first_image[16].y = .15
        response, detector, runtime = self.extract([result(first_image, first_world), result(second_image, second_world)])
        self.assertEqual(response['status'], 'detected')
        self.assertFalse(response['used_fallback'])
        self.assertEqual(response['peak_contact_frame'], 1)
        self.assertEqual(response['coordinate_space'], 'estimated_world_meters')
        options = runtime.tasks.vision.PoseLandmarkerOptions.call_args.kwargs
        self.assertEqual(options['running_mode'], runtime.tasks.vision.RunningMode.VIDEO)
        self.assertEqual(options['num_poses'], 2)
        self.assertEqual(response['valid_pose_frames'], 2)

    def test_timestamps_strictly_increase_even_with_duplicate_decoder_times(self):
        response, detector, _ = self.extract([result() for _ in range(4)], fps=2000, timestamps=[0, 0, 0, 0])
        times = [c.args[1] for c in detector.detect_for_video.call_args_list]
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))
        self.assertFalse(response['fps_estimated'])

    def test_invalid_fps_and_nan_decoder_timestamp(self):
        response, detector, _ = self.extract([result(), result()], fps=float('nan'), timestamps=[float('nan'), float('nan')])
        self.assertTrue(response['fps_estimated'])
        self.assertEqual([c.args[1] for c in detector.detect_for_video.call_args_list], [0, 33])

    def test_bad_joint_visibility_is_rejected(self):
        image, world = landmarks()
        image[14].visibility = .1
        response, _, _ = self.extract([result(image, world)])
        self.assertTrue(response['used_fallback'])

    def test_missing_presence_is_rejected(self):
        image, world = landmarks()
        image[16].presence = None
        self.assertFalse(pose._reliable_overhead_pose(image, world))

    def test_nonfinite_world_coordinate_is_rejected(self):
        image, world = landmarks()
        world[14].z = float('nan')
        self.assertFalse(pose._reliable_overhead_pose(image, world))

    def test_out_of_frame_joint_is_rejected(self):
        image, world = landmarks()
        image[28].y = 1.1
        self.assertFalse(pose._reliable_overhead_pose(image, world))

    def test_sideways_arm_is_not_overhead(self):
        image, world = landmarks()
        image[16].y = .39  # Above shoulder but below head.
        self.assertFalse(pose._reliable_overhead_pose(image, world))

    def test_missing_world_landmarks_cannot_be_measured(self):
        response, _, _ = self.extract([NS(pose_landmarks=[landmarks()[0]], pose_world_landmarks=[])])
        self.assertTrue(response['used_fallback'])

    def test_multiple_players_reject_entire_clip(self):
        image, world = landmarks()
        multiple = NS(pose_landmarks=[image, image], pose_world_landmarks=[world, world])
        response, _, _ = self.extract([result(), multiple])
        self.assertEqual(response['status'], 'multiple_players_detected')
        self.assertTrue(response['used_fallback'])

    def test_zero_length_segments_do_not_become_straight_elbows(self):
        with self.assertRaises(ValueError):
            pose.compute_angle_3d([0, 0, 0], [0, 0, 0], [1, 0, 0])
        image, world = landmarks()
        world[14] = world[12]
        response, _, _ = self.extract([result(image, world)])
        self.assertTrue(response['used_fallback'])

    def test_missing_model_has_specific_status(self):
        with tempfile.NamedTemporaryFile() as video, patch.object(pose, 'pose_model_path', return_value=Path('missing.task')):
            self.assertEqual(pose.extract_pose_from_video(video.name)['status'], 'pose_model_missing')

    def test_no_video_remains_explicit_demo_fallback(self):
        response = pose.extract_pose_from_video('')
        self.assertTrue(response['used_fallback'])
        self.assertIsNone(response['peak_contact_frame'])
        self.assertEqual(response['coordinate_space'], 'synthetic_demo')

    def test_inference_failure_releases_capture(self):
        with self.assertLogs(pose.logger, level='ERROR'):
            response, _, _ = self.extract([RuntimeError('inference failed')])
        self.assertEqual(response['status'], 'pose_inference_failed')

    def test_service_failure_is_503_and_stops_pipeline(self):
        with patch.object(main, 'extract_pose_from_video', return_value=pose._pose_unavailable('pose_model_missing')), patch.object(main, 'run_argon_and_saint_agent') as agent:
            response = TestClient(main.app, headers=auth_headers()).post('/pipeline/analyze-stroke')
        self.assertEqual(response.status_code, 503)
        agent.assert_not_called()

    def test_non_overhead_swing_uses_fastest_full_body_frame(self):
        """A forehand/drive never raises the wrist overhead: measure the fastest full-body frame instead of failing."""
        frames = []
        for wrist_x in (.50, .52, .70, .72):  # biggest jump lands on the third frame
            image, world = landmarks()
            image[16].y, image[16].x = .55, wrist_x  # wrist below the head: not overhead
            frames.append(result(image, world))
        measured, _, _ = self.extract(frames, timestamps=[0, 33, 66, 100])
        self.assertFalse(measured['used_fallback'])
        self.assertEqual(measured['status'], 'detected_no_overhead_contact')
        self.assertFalse(measured['overhead_contact_detected'])
        self.assertEqual(measured['contact_selection'], 'fastest_right_wrist_full_body_frame')
        self.assertEqual(measured['peak_contact_frame'], 2)
        self.assertIn('right_elbow_contact_deg', measured['raw_angles'])

    def test_background_player_frames_are_skipped_not_fatal(self):
        two = NS(pose_landmarks=[landmarks()[0], landmarks()[0]], pose_world_landmarks=[landmarks()[1], landmarks()[1]])
        measured, _, _ = self.extract([two, result(), result()])
        self.assertFalse(measured['used_fallback'])
        self.assertTrue(any('more than one person' in w for w in measured['warnings']))

    def test_unmeasurable_pose_still_coaches_without_numbers(self):
        """No reliable body (here: another player dominates) completes with filming guidance, not a 422."""
        with patch.object(db_mongo, 'get_db', return_value=None), \
                patch.object(main, 'extract_pose_from_video', return_value=pose._pose_unavailable('multiple_players_detected')), \
                patch.object(main, 'find_closest_pro_pose') as vector_search:
            response = TestClient(main.app, headers=auth_headers()).post('/pipeline/analyze-stroke', data={'user_name': 'pose-test'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body['overall_score'])
        self.assertEqual(body['verification_status'], 'NOT_MEASURED')
        self.assertEqual(body['pose_analysis']['raw_angles'], {})
        self.assertIn('Another player', body['biomechanical_diagnosis'])
        vector_search.assert_not_called()  # no fake angles reach $vectorSearch

    def test_missing_video_is_still_422(self):
        with patch.object(main, 'extract_pose_from_video', return_value=pose._pose_unavailable('fallback_no_video')):
            response = TestClient(main.app, headers=auth_headers()).post('/pipeline/analyze-stroke')
        self.assertEqual(response.status_code, 422)

    def test_measured_metadata_survives_pipeline(self):
        measured, _, _ = self.extract([result()])
        with patch.object(db_mongo, 'get_db', return_value=None), patch.object(main, 'extract_pose_from_video', return_value=measured):
            response = TestClient(main.app, headers=auth_headers()).post('/pipeline/analyze-stroke', data={'user_name': 'pose-test', 'sampled_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), 'heart_rate_bpm': '130'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['pose_analysis']['coordinate_space'], 'estimated_world_meters')
        self.assertEqual(response.json()['pose_analysis']['contact_selection'], 'highest_visible_overhead_wrist_proxy')

    def test_installer_checksum_failure_preserves_existing_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'pose.task'
            destination.write_bytes(b'original')
            with patch.object(setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'corrupted')):
                with self.assertRaises(ValueError):
                    setup.install_model(destination)
            self.assertEqual(destination.read_bytes(), b'original')
            self.assertEqual(list(Path(directory).glob('*.download')), [])

    def test_installer_valid_asset_needs_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'pose.task'
            destination.write_bytes(b'test')
            with patch.object(setup, 'MODEL_SHA256', setup.hashlib.sha256(b'test').hexdigest()), patch.object(setup.urllib.request, 'urlopen') as request:
                self.assertEqual(setup.install_model(destination), destination.resolve())
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
