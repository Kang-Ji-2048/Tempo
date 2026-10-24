# Pose model setup

Run `python setup_pose_model.py` from the backend directory. It installs Google's
Pose Landmarker Full float16 version 1 bundle and verifies SHA-256 before an atomic
replacement. Existing valid assets are reused. The 9 MB binary is not checked into Git.

The default path is resolved relative to `etl_pose.py`, independently of the current
working directory. Set `TEMPO_POSE_MODEL_PATH` to an absolute path for a custom asset;
the installer honors the same variable. Request handling never downloads models.

Runtime: MediaPipe Tasks VIDEO mode, CPU inference, estimated world coordinates for
joint angles, image coordinates for contact height. The six-value vector contract
remains `[elbow/180, shoulder/180, trunk/180, knee/180, left_arm/180, height]`.

The gate requires visible, present landmarks for all measured joints and the nose,
finite world coordinates, nonzero joint segments, and a wrist above the head and
shoulder. A clip where the model detects more than one player is rejected. This is
a single-player right-handed overhead estimator. A high wrist is only a candidate
contact frame; actual racket/shuttle contact is not detected. `configured` in
`/health` checks dependencies and model presence, not model integrity or inference.

Run tests with `python -m unittest discover -s . -p "test_*.py" -v`.
The pose regression tests mock landmarks and decoding; real model smoke tests are
reported separately. Use a real full-body overhead clip to validate sports accuracy.

Model source: https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker#models

Pinned URL: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task

SHA-256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`
