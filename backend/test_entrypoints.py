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
