"""GuitarTab AI — FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload

See the README for full instructions.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    capabilities_router,
    frames_router,
    health_router,
    videos_router,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.schemas.common import ErrorDetail

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application, honouring the supplied or default settings."""
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.validate_directories()
        logger.info(
            "Starting %s v%s (%s); uploads -> %s (max %d MB); frames -> %s (1 per %.1fs)",
            settings.app_name,
            settings.version,
            settings.environment,
            settings.upload_dir_absolute,
            settings.max_upload_size_mb,
            settings.processed_dir_absolute,
            settings.frame_sample_interval_seconds,
        )
        yield

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.version,
        description=(
            "Research prototype that will turn guitar-playing videos into six-string "
            "tablature. Upload pipeline is live; the CV pipeline is not yet implemented."
        ),
        lifespan=lifespan,
    )

    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": ErrorDetail(
                code="internal_error",
                message="The server encountered an unexpected error. Details were logged.",
            ).model_dump()},
        )

    @app.get("/", include_in_schema=False, tags=["system"])
    def root() -> dict:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
            "capabilities": "/api/capabilities",
        }

    app.include_router(health_router)
    app.include_router(capabilities_router)
    app.include_router(videos_router)
    app.include_router(frames_router)

    return app


app = create_app()