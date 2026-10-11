"""GET /api/health — reports the real service health."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Service health check",
)
def health(settings: SettingsDep) -> HealthResponse:
    """Return the current service health (no database, no model calls)."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        time=datetime.now(timezone.utc),
    )