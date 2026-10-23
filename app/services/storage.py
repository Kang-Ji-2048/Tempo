"""
app/services/storage.py - Asynchronous, non-blocking video storage abstractions
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import aiofiles
import aiofiles.os
from fastapi import UploadFile

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StorageService(ABC):
    """Abstract storage interface for video practice sets."""

    @abstractmethod
    async def store_file(self, file: UploadFile, session_id: str) -> str:
        """Stores an uploaded file stream and returns its destination URI or path."""
        pass

    @abstractmethod
    async def delete_file(self, file_path_or_uri: str) -> bool:
        """Deletes a stored video file."""
        pass


class LocalStorageService(StorageService):
    """
    Local filesystem storage with asynchronous, non-blocking chunked writes
    using aiofiles to prevent event-loop starvation during 1080p video ingest.
    """

    def __init__(self, base_dir: Optional[str] = None, chunk_size_bytes: Optional[int] = None) -> None:
        settings = get_settings()
        self.base_dir = base_dir or settings.UPLOAD_DIR
        self.chunk_size = chunk_size_bytes or settings.CHUNK_SIZE_BYTES

    async def store_file(self, file: UploadFile, session_id: str) -> str:
        """
        Asynchronously writes the UploadFile stream to local disk in 1MB chunks.
        """
        session_dir = os.path.join(self.base_dir, session_id)
        # Ensure session storage directory exists
        await aiofiles.os.makedirs(session_dir, exist_ok=True)

        raw_filename = file.filename or f"{session_id}.mp4"
        safe_filename = os.path.basename(raw_filename)
        dest_path = os.path.join(session_dir, safe_filename)

        logger.info("Storing upload for session %s to %s in %d-byte chunks", session_id, dest_path, self.chunk_size)

        bytes_written = 0
        async with aiofiles.open(dest_path, "wb") as out_file:
            while True:
                chunk = await file.read(self.chunk_size)
                if not chunk:
                    break
                await out_file.write(chunk)
                bytes_written += len(chunk)

        logger.info("Successfully wrote %d bytes to %s", bytes_written, dest_path)
        return dest_path

    async def delete_file(self, file_path_or_uri: str) -> bool:
        """Deletes a local file asynchronously."""
        try:
            if await aiofiles.os.path.exists(file_path_or_uri):
                await aiofiles.os.remove(file_path_or_uri)
                logger.info("Deleted local file %s", file_path_or_uri)
                return True
            return False
        except Exception as exc:
            logger.warning("Failed to delete local file %s: %s", file_path_or_uri, exc)
            return False


class CloudStorageService(StorageService):
    """
    Mockable cloud storage interface for GCS / AWS S3 buckets.
    """

    def __init__(self, bucket_name: str = "tempo-practice-videos-prod") -> None:
        self.bucket_name = bucket_name

    async def store_file(self, file: UploadFile, session_id: str) -> str:
        """Simulates writing to GCS or S3 and returns a gs:// or s3:// URI."""
        raw_filename = file.filename or f"{session_id}.mp4"
        cloud_uri = f"gs://{self.bucket_name}/{session_id}/{os.path.basename(raw_filename)}"
        logger.info("Mock cloud upload: stored %s to %s", raw_filename, cloud_uri)
        return cloud_uri

    async def delete_file(self, file_path_or_uri: str) -> bool:
        """Simulates cloud object deletion."""
        logger.info("Mock cloud deletion of %s", file_path_or_uri)
        return True


# Dependency injection provider for FastAPI
_default_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Provides the active StorageService instance (defaults to LocalStorageService)."""
    global _default_storage_service
    if _default_storage_service is None:
        _default_storage_service = LocalStorageService()
    return _default_storage_service


def set_storage_service(service: StorageService) -> None:
    """Overrides the active storage service (useful for testing)."""
    global _default_storage_service
    _default_storage_service = service
