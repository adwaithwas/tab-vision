"""Shared API schemas: health, capabilities, errors."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Machine-readable error payload returned on any failure."""

    code: str = Field(description="Stable, machine-readable error identifier.")
    message: str = Field(description="Human-readable error message.")
    field: str | None = Field(default=None, description="Related input field, if any.")


class StandardError(BaseModel):
    detail: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    time: datetime


class UploadCapability(BaseModel):
    supported: bool
    max_file_size_mb: int
    allowed_extensions: list[str]
    allowed_content_types: list[str]


class CapabilityStage(BaseModel):
    key: str = Field(description="Stable identifier for the pipeline stage.")
    label: str
    implemented: bool
    status: Literal["implemented", "planned", "in_progress"]
    description: str


class CvCapability(BaseModel):
    implemented: bool
    stages: list[CapabilityStage]


class FrameExtractionCapability(BaseModel):
    """Real frame-extraction capability and the limits that guard it."""

    implemented: bool
    sample_interval_seconds: float
    supported_formats: list[str]
    max_video_duration_seconds: float
    max_video_dimension: int
    max_decoded_frames: int
    max_extracted_frames: int
    frame_store_max_width: int


class CapabilitiesResponse(BaseModel):
    service: str
    version: str
    video_upload: UploadCapability
    frame_extraction: FrameExtractionCapability
    cv_pipeline: CvCapability
    notes: list[str]
    extra: dict[str, Any] = Field(default_factory=dict)