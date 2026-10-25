"""Both server commands expose the canonical measured pipeline, offline."""
import os
import sys
from pathlib import Path
import unittest

for key in ('MONGODB_URI', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'SAINT_WEBHOOK_URL'):
    os.environ[key] = ''
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class EntryPointTests(unittest.TestCase):
    def test_root_entry_point_is_the_canonical_application(self):
        from app.main import app, create_application
        from backend.main import app as canonical
        self.assertIs(app, canonical)
        self.assertIs(create_application(), canonical)
        paths = app.openapi()['paths']
        for path in ('/api/v1/sessions/ingest', '/pipeline/pair-watch', '/pipeline/etl-apple-watch', '/dashboard'):
            self.assertIn(path, paths)

    def test_startup_does_not_import_legacy_motor_stack(self):
        import subprocess
        script = '''
import importlib.abc
import sys
class BlockLegacyDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'motor', 'aiofiles', 'pydantic_settings'}:
            raise AssertionError('Unexpected legacy dependency: ' + fullname)
sys.meta_path.insert(0, BlockLegacyDependencies())
from app.main import app
from fastapi.testclient import TestClient
assert TestClient(app).get('/health').status_code == 200
assert '/api/v1/onboarding/next' in app.openapi()['paths']
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
