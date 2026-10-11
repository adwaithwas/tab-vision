"""FastAPI route handlers."""

from app.api.routes.health import router as health_router
from app.api.routes.capabilities import router as capabilities_router
from app.api.routes.videos import router as videos_router
from app.api.routes.frames import router as frames_router
from app.api.routes.vision import router as vision_router

__all__ = ["capabilities_router", "frames_router", "health_router", "videos_router", "vision_router"]