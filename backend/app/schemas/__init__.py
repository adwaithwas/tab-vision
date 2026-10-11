"""API request/response models."""

from app.schemas.common import (
    CapabilitiesResponse,
    CapabilityStage,
    ErrorDetail,
    FrameExtractionCapability,
    HealthResponse,
    StandardError,
    UploadCapability,
)
from app.schemas.fretboard import (
    FretboardDetectionResponse,
    FretboardGeometrySchema,
    FretboardPoint,
)
from app.schemas.video import (
    FrameListResponse,
    FramePreview,
    JobResponse,
    JobStatus,
    UploadResponse,
    VideoMetadata,
)

__all__ = [
    "CapabilitiesResponse",
    "CapabilityStage",
    "ErrorDetail",
    "FretboardDetectionResponse",
    "FretboardGeometrySchema",
    "FretboardPoint",
    "FrameExtractionCapability",
    "FrameListResponse",
    "FramePreview",
    "HealthResponse",
    "JobResponse",
    "JobStatus",
    "StandardError",
    "UploadCapability",
    "UploadResponse",
    "VideoMetadata",
]