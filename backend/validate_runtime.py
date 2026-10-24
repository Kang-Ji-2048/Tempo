"""Reproducible checks without pretending inferred angles are ground truth."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

try:
    from .etl_pose import extract_pose_from_video, get_pose_runtime_status
    from . import agent_argon_saint as agent
    from .auth import identities
except ImportError:
    from etl_pose import extract_pose_from_video, get_pose_runtime_status
    import agent_argon_saint as agent
    from auth import identities


def run(video=None, probe_model=False):
    model = os.environ.get('GEMINI_MODEL', 'gemini-4-argon')
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    report = {
        'demo_mode': os.environ.get('TEMPO_DEMO_MODE', 'false').lower() == 'true',
        'pose_runtime': get_pose_runtime_status(),
        'model': model, 'model_key_configured': bool(key),
        'model_probe': 'not_requested' if not probe_model else 'missing_key',
        'authentication_configured': bool(identities()),
        'reference_status': 'illustrative_unvalidated',
        'accuracy_validated': False,
        'accuracy_note': 'A detected overhead pose is an integration check. Ground-truth joint annotations and coach review are required for accuracy claims.',
    }
    if probe_model and key:
        try:
            result = agent._call_gemini_4_argon('Return exactly a JSON object with ok set to true. No personal data is supplied.',
                {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']})
            report['model_probe'] = 'passed' if json.loads(result or '{}').get('ok') is True else 'invalid_response'
        except Exception as exc:
            report['model_probe'] = 'failed'
            report['model_error_type'] = type(exc).__name__
    if video:
        pose = extract_pose_from_video(str(video))
        report['video_sha256'] = __import__('hashlib').sha256(Path(video).read_bytes()).hexdigest()
        report['pose_result'] = pose
        report['measured_pose_extracted'] = not pose['used_fallback']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', type=Path)
    parser.add_argument('--probe-model', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.video, args.probe_model)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'pose_result'}}, indent=2))
