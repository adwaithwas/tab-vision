"""Dependency helpers for route handlers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.services.processing import ProcessingService
from app.services.uploads import UploadService


def get_settings(request: Request) -> Settings:
    """Read the settings object attached to the app at startup."""
    return request.app.state.settings


def get_upload_service(request: Request) -> UploadService:
    """Return the upload service bound to this app's settings."""
    return UploadService(request.app.state.settings)


def get_processing_service(request: Request) -> ProcessingService:
    """Return the video-processing service bound to this app's settings."""
    return ProcessingService(request.app.state.settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
UploadServiceDep = Annotated[UploadService, Depends(get_upload_service)]
ProcessingServiceDep = Annotated[ProcessingService, Depends(get_processing_service)]