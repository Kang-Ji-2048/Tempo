"""
app/main.py - Main FastAPI Application Entrypoint
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.cadence import router as cadence_router
from app.api.v1.live import router as live_router
from app.api.v1.sessions import router as sessions_router
from app.core.config import get_settings
from app.db.mongodb import MongoDBManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("tempo")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown lifecycle events."""
    settings = get_settings()
    logger.info("Initializing %s...", settings.APP_NAME)
    try:
        await MongoDBManager.connect_to_mongo()
        # Seed pro reference pose archetypes
        from app.services.vector_matcher import VectorMatcher

        await VectorMatcher.seed_reference_archetypes()
    except Exception as exc:
        logger.warning("MongoDB initial connection or seed deferred: %s", exc)

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)
    await MongoDBManager.close_mongo_connection()


def create_application() -> FastAPI:
    """Factory creating and configuring the FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Tempo - Multimodal Sports Coaching Ingestion & Biomechanics Pipeline. "
            "Ingests 1080p practice sets and Android Health Connect telemetry, "
            "persists sessions to MongoDB Atlas, and triggers Gemini Argon biomechanical reasoning."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health", tags=["system"])
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint validating service and database status."""
        mongo_connected = False
        try:
            db = MongoDBManager.get_database()
            # Send a quick ping command
            await db.command("ping")
            mongo_connected = True
        except Exception:
            mongo_connected = False

        return {
            "status": "healthy",
            "service": "tempo-session-ingestion-api",
            "version": "1.0.0",
            "mongodb_connected": mongo_connected,
            "database_name": settings.MONGODB_DB_NAME,
            "storage_upload_dir": settings.UPLOAD_DIR,
        }

    # Mount API v1 routers
    app.include_router(sessions_router, prefix=settings.API_V1_STR)
    app.include_router(live_router, prefix=settings.API_V1_STR)
    app.include_router(cadence_router, prefix=settings.API_V1_STR)

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
