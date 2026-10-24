from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.db.mongodb import MongoDBManager

def test_async_settings_use_the_shared_database():
    assert Settings(_env_file=None).MONGODB_DB_NAME == 'sports_coach_db'
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MONGODB_DB_NAME='legacy_database')

@pytest.mark.asyncio
async def test_async_manager_selects_the_shared_database():
    client=MagicMock()
    with patch('app.db.mongodb.AsyncIOMotorClient',return_value=client):
        await MongoDBManager.connect_to_mongo(uri='mongodb://localhost:27017')
    client.__getitem__.assert_called_once_with('sports_coach_db')
    await MongoDBManager.close_mongo_connection()

@pytest.mark.asyncio
async def test_async_manager_rejects_a_different_database():
    with patch('app.db.mongodb.AsyncIOMotorClient') as connect:
        with pytest.raises(ValueError):
            await MongoDBManager.connect_to_mongo(db_name='legacy_database')
        connect.assert_not_called()
