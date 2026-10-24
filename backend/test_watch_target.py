import os
import unittest
from unittest.mock import MagicMock, patch

os.environ['MONGODB_URI'] = ''
import db_mongo as db


class WatchTargetTests(unittest.TestCase):
    def test_database_handle_can_target_watch_database_independently(self):
        client = MagicMock()
        with patch.object(db, 'get_mongo_client', return_value=client):
            db.get_db('sports_coach_db')
            client.__getitem__.assert_called_with('sports_coach_db')
            db.get_db()
            client.__getitem__.assert_called_with('badminton_coach')

    def test_writes_watch_database_but_keeps_player_state_in_core_database(self):
        watch, core = MagicMock(), MagicMock()
        watch.list_collection_names.return_value = [db.WATCH_TS_COLLECTION]
        watch[db.WATCH_TS_COLLECTION].options.return_value = {
            'timeseries': {'timeField': 'timestamp', 'metaField': 'metadata'}}
        watch[db.WATCH_TS_COLLECTION].insert_one.return_value.acknowledged = True
        with patch.object(db, 'WATCH_DB_NAME', 'sports_coach_db'), patch.object(db, 'get_db', side_effect=lambda name=None: watch if name else core):
            result = db.save_live_watch_telemetry('routing_test', {'heart_rate_bpm': 130})
        watch[db.WATCH_TS_COLLECTION].insert_one.assert_called_once()
        core[db.WATCH_TS_COLLECTION].insert_one.assert_not_called()
        core[db.PLAYERS_COLLECTION].update_one.assert_called_once()
        watch[db.PLAYERS_COLLECTION].update_one.assert_not_called()
        self.assertEqual(result['storage'], {'database': 'sports_coach_db', 'collection': 'watch_telemetry_ts', 'persisted': True})

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
