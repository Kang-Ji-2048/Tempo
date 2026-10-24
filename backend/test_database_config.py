import os
import unittest
from unittest.mock import patch
from database_config import DATABASE_NAME, validate_database_environment

class DatabaseConfigTests(unittest.TestCase):
    def test_one_database_name_is_shared(self):
        import db_mongo
        self.assertEqual(DATABASE_NAME, 'sports_coach_db')
        self.assertEqual(db_mongo.DB_NAME, DATABASE_NAME)
        self.assertEqual(db_mongo.WATCH_DB_NAME, DATABASE_NAME)

    def test_stale_environment_overrides_cannot_redirect_writes(self):
        for name in ('MONGODB_DB_NAME','MONGODB_DATABASE','MONGODB_WATCH_DATABASE'):
            with patch.dict(os.environ,{name:'legacy_database'}):
                with self.assertRaises(ValueError): validate_database_environment()
