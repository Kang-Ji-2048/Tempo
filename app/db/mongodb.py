"""
app/db/mongodb.py - Async MongoDB Atlas Manager using Motor
"""

from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.core.config import get_settings
from backend.database_config import validate_database_name

logger = logging.getLogger(__name__)


class MongoDBManager:
    """Manages the lifecycle of AsyncIOMotorClient and database instances."""

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_to_mongo(cls, uri: Optional[str] = None, db_name: Optional[str] = None) -> None:
        """Connects to MongoDB Atlas using Motor async client."""
        settings = get_settings()
        target_uri = uri or settings.MONGODB_URI
        target_db = validate_database_name(db_name or settings.MONGODB_DB_NAME)

        logger.info("Connecting to MongoDB (DB: %s)...", target_db)
        cls.client = AsyncIOMotorClient(target_uri)
        cls.database = cls.client[target_db]
        logger.info("Connected to MongoDB successfully.")

    @classmethod
    async def close_mongo_connection(cls) -> None:
        """Closes the MongoDB async client connection pool."""
        if cls.client is not None:
            logger.info("Closing MongoDB connection pool...")
            cls.client.close()
            cls.client = None
            cls.database = None
            logger.info("MongoDB connection closed.")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Returns the active async database handle."""
        if cls.database is None:
            settings = get_settings()
            # If not connected yet via lifespan, instantiate client dynamically
            cls.client = AsyncIOMotorClient(settings.MONGODB_URI)
            cls.database = cls.client[validate_database_name(settings.MONGODB_DB_NAME)]
        return cls.database

    @classmethod
    def set_database(cls, db: AsyncIOMotorDatabase) -> None:
        """Overrides the active database (useful for testing & mocks)."""
        validate_database_name(db.name)
        cls.database = db


def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency for accessing the async database."""
    return MongoDBManager.get_database()


def get_sessions_collection() -> AsyncIOMotorCollection:
    """Returns the sessions collection handle."""
    settings = get_settings()
    db = get_database()
    return db[settings.SESSIONS_COLLECTION]


def get_telemetry_collection() -> AsyncIOMotorCollection:
    """Returns the telemetry time-series collection handle."""
    settings = get_settings()
    db = get_database()
    return db[settings.TELEMETRY_COLLECTION]
