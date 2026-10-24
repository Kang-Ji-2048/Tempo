"""Install the pinned official model. Run explicitly; request handling never downloads files."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
MODEL_SHA256 = '5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1'


def install_model(destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == MODEL_SHA256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.download', delete=False) as output:
            staging = Path(output.name)
            digest = hashlib.sha256()
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != MODEL_SHA256:
            raise ValueError('Downloaded model checksum mismatch; destination was not replaced')
        staging.replace(destination)
        return destination
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


if __name__ == '__main__':
    path = Path(os.environ.get('TEMPO_POSE_MODEL_PATH') or Path(__file__).parent / 'models' / 'pose_landmarker_full.task')
    print(f'Pose model ready: {install_model(path)}')
