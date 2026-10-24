"""
tests/conftest.py - Pytest fixtures and mock database setup
"""

import json
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.db.mongodb import get_database
from app.api.v1.sessions import router as sessions_router
from app.api.v1.live import router as live_router
from app.api.v1.cadence import router as cadence_router
from app.api.v1.onboarding import router as onboarding_router


def create_application():
    """Isolated legacy service harness; production uses backend.main."""
    application = FastAPI()
    for router in (sessions_router, live_router, cadence_router, onboarding_router):
        application.include_router(router, prefix='/api/v1')
    return application
from app.services.storage import LocalStorageService, get_storage_service


class MockCursor:
    """Mock asynchronous MongoDB cursor supporting find(), sort(), limit(), and to_list()."""

    def __init__(self, items: List[Dict[str, Any]]) -> None:
        self.items = list(items)

    def sort(self, key: str, direction: int = 1) -> "MockCursor":
        return self

    def limit(self, count: int) -> "MockCursor":
        self.items = self.items[:count]
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is not None:
            return self.items[:length]
        return list(self.items)


class MockAsyncCollection:
    """In-memory mock of AsyncIOMotorCollection for fast, deterministic unit testing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.list_docs: List[Dict[str, Any]] = []

    async def insert_one(self, document: Dict[str, Any]) -> Any:
        doc_copy = dict(document)
        doc_id = str(doc_copy.get("_id") or doc_copy.get("session_id") or len(self.documents))
        doc_copy["_id"] = doc_id
        self.documents[doc_id] = doc_copy
        self.list_docs.append(doc_copy)

        class InsertOneResult:
            inserted_id = doc_id

        return InsertOneResult()

    async def insert_many(self, documents: List[Dict[str, Any]]) -> Any:
        inserted_ids = []
        for doc in documents:
            res = await self.insert_one(doc)
            inserted_ids.append(res.inserted_id)

        class InsertManyResult:
            def __init__(self, ids: List[str]):
                self.inserted_ids = ids

        return InsertManyResult(inserted_ids)

    async def update_one(
        self,
        filter_query: Dict[str, Any],
        update_query: Dict[str, Any],
        upsert: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        target_id = filter_query.get("_id") or filter_query.get("session_id")
        doc = self.documents.get(target_id)
        if not doc and target_id is None:
            for d in self.documents.values():
                if all(d.get(k) == v for k, v in filter_query.items()):
                    doc = d
                    target_id = d.get("_id")
                    break

        if doc and "$set" in update_query:
            doc.update(update_query["$set"])
        elif not doc and upsert:
            new_doc = dict(filter_query)
            if "$set" in update_query:
                new_doc.update(update_query["$set"])
            doc_id = str(new_doc.get("_id") or len(self.documents))
            new_doc["_id"] = doc_id
            self.documents[doc_id] = new_doc
            self.list_docs.append(new_doc)
            doc = new_doc

        class UpdateResult:
            matched_count = 1 if doc else 0
            modified_count = 1 if doc else 0

        return UpdateResult()

    async def find_one(self, filter_query: Dict[str, Any]) -> Any:
        target_id = filter_query.get("_id") or filter_query.get("session_id")
        if target_id and target_id in self.documents:
            return dict(self.documents[target_id])
        for doc in self.documents.values():
            match = True
            for k, v in filter_query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    def find(self, filter_query: Optional[Dict[str, Any]] = None) -> MockCursor:
        matched = []
        query = filter_query or {}
        for doc in self.documents.values():
            if not query or all(doc.get(k) == v for k, v in query.items()):
                matched.append(dict(doc))
        return MockCursor(matched)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> MockCursor:
        return MockCursor(list(self.documents.values()))


class MockAsyncDatabase:
    """In-memory mock of AsyncIOMotorDatabase."""

    def __init__(self, name: str = "sports_coach_db") -> None:
        self.name = name
        self.collections: Dict[str, MockAsyncCollection] = {}

    def __getitem__(self, name: str) -> MockAsyncCollection:
        if name not in self.collections:
            self.collections[name] = MockAsyncCollection(name)
        return self.collections[name]

    async def command(self, cmd: str, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"ok": 1.0}


@pytest.fixture
def mock_db() -> MockAsyncDatabase:
    """Fixture providing a fresh mock MongoDB database."""
    return MockAsyncDatabase(name="sports_coach_db")


@pytest.fixture
def test_settings(tmp_path: Any) -> Settings:
    """Fixture providing test settings with a temporary upload directory."""
    return Settings(
        APP_NAME="Tempo Test Ingest",
        DEBUG=True,
        UPLOAD_DIR=str(tmp_path / "uploads"),
        MONGODB_DB_NAME="sports_coach_db",
        SESSIONS_COLLECTION="sessions",
        TELEMETRY_COLLECTION="telemetry_timeseries",
        POSE_ARCHETYPES_COLLECTION="pose_archetypes",
        ESTIMATED_ANALYSIS_TIME_SEC=8,
    )


@pytest.fixture
def storage_service(test_settings: Settings) -> LocalStorageService:
    """Fixture providing a LocalStorageService targeting the temporary directory."""
    return LocalStorageService(
        base_dir=test_settings.UPLOAD_DIR,
        chunk_size_bytes=test_settings.CHUNK_SIZE_BYTES,
    )


@pytest.fixture
def app(
    mock_db: MockAsyncDatabase, storage_service: LocalStorageService, test_settings: Settings
) -> Generator[FastAPI, None, None]:
    """Fixture providing the FastAPI app instance with dependency overrides."""
    application = create_application()

    # Override dependencies
    application.dependency_overrides[get_database] = lambda: mock_db
    application.dependency_overrides[get_storage_service] = lambda: storage_service

    yield application

    application.dependency_overrides.clear()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Fixture providing an async httpx test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def valid_telemetry_payload() -> List[Dict[str, Any]]:
    """Sample Android Health Connect biometric telemetry."""
    return [
        {
            "timestamp_ms": 1729724400000,
            "heart_rate": 158,
            "cadence": 38,
            "active_energy_burned": 10.2,
        },
        {
            "timestamp_ms": 1729724401000,
            "heart_rate": 165,
            "cadence": 42,
            "active_energy_burned": 11.5,
        },
        {
            "timestamp_ms": 1729724402000,
            "heart_rate": 172,
            "cadence": 44,
            "active_energy_burned": 12.8,
        },
    ]


@pytest.fixture
def valid_metadata_json(valid_telemetry_payload: List[Dict[str, Any]]) -> str:
    """Valid metadata JSON string conforming to SessionIngestRequest."""
    return json.dumps(
        {
            "user_id": "usr_sumanth_001",
            "sport": "badminton",
            "stroke_type": "overhead_clear",
            "target_archetype": "Axelsen",
            "telemetry": valid_telemetry_payload,
        }
    )


@pytest.fixture
def mock_mp4_bytes() -> bytes:
    """Mock MP4 file binary content with valid ftyp header signature."""
    # Standard MP4 box header: size (32 bytes) + 'ftyp' + 'isom'
    return b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free" + (b"\x00" * 1024)
