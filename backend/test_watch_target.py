import os
import unittest
from unittest.mock import MagicMock, patch

os.environ['MONGODB_URI'] = ''
import db_mongo as db


class WatchTargetTests(unittest.TestCase):
    def test_default_and_watch_handles_target_the_same_database(self):
        client = MagicMock()
        with patch.object(db, 'get_mongo_client', return_value=client):
            db.get_db('sports_coach_db')
            client.__getitem__.assert_called_with('sports_coach_db')
            db.get_db()
            client.__getitem__.assert_called_with('sports_coach_db')

    def test_watch_readings_and_latest_player_state_share_the_database(self):
        client, database = MagicMock(), MagicMock()
        client.__getitem__.return_value = database
        database.list_collection_names.return_value = [db.WATCH_TS_COLLECTION]
        database[db.WATCH_TS_COLLECTION].options.return_value = {
            'timeseries': {'timeField': 'timestamp', 'metaField': 'metadata'}}
        database[db.WATCH_TS_COLLECTION].insert_one.return_value.acknowledged = True
        with patch.object(db, 'get_mongo_client', return_value=client):
            result = db.save_live_watch_telemetry('routing_test', {'heart_rate_bpm':130})
        self.assertTrue(all(call.args == ('sports_coach_db',) for call in client.__getitem__.call_args_list))
        database[db.WATCH_TS_COLLECTION].insert_one.assert_called_once()
        database[db.PLAYERS_COLLECTION].update_one.assert_called_once()
        self.assertTrue(result['storage']['persisted'])

    def test_other_database_overrides_are_rejected_before_connecting(self):
        with patch.object(db, 'get_mongo_client') as connect:
            with self.assertRaises(ValueError): db.get_db('legacy_database')
        connect.assert_not_called()

    def test_queries_follow_watch_database(self):
        with patch.object(db, 'WATCH_DB_NAME', 'sports_coach_db'), patch.object(db, 'get_db', return_value=None) as get_db:
            result = db.get_watch_timeseries_window('routing_test')
        get_db.assert_called_once_with('sports_coach_db')
        self.assertEqual(result['database'], 'sports_coach_db')

    def test_failed_write_is_not_reported_as_persisted(self):
        watch = MagicMock()
        watch.list_collection_names.side_effect = RuntimeError('offline')
        with patch.object(db, 'get_db', return_value=watch):
            result = db.save_live_watch_telemetry('routing_test', {'heart_rate_bpm': 130})
        self.assertFalse(result['storage']['persisted'])
        self.assertEqual(result['storage']['error'], 'watch_storage_write_failed')

    def test_incompatible_existing_collection_is_rejected(self):
        watch = MagicMock()
        watch.list_collection_names.return_value = [db.WATCH_TS_COLLECTION]
        watch[db.WATCH_TS_COLLECTION].options.return_value = {}
        with self.assertRaises(ValueError):
            db._ensure_watch_collection(watch)


if __name__ == '__main__':
    unittest.main()
