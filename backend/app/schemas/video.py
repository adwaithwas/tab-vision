"""Video upload and analysis-job schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    QUEUED = "queued"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoMetadata(BaseModel):
    """Real metadata read from the decoded video plus extraction summary."""

    width: int = Field(ge=1, description="Decoded frame width in pixels.")
    height: int = Field(ge=1, description="Decoded frame height in pixels.")
    fps: float = Field(gt=0, description="Frames per second reported by the container.")
    frame_count: int = Field(ge=0, description="Total frames reported/ scanned.")
    duration_seconds: float = Field(ge=0)
    duration_estimated: bool = Field(
        description="True when duration is derived from frame_count / fps rather than a trusted container value."
    )
    sample_interval_seconds: float = Field(gt=0)
    frames_extracted: int = Field(ge=0)
    processed_at: datetime


class FramePreview(BaseModel):
    """A single extracted frame, addressed by a safe, validated index."""

    index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    url: str = Field(description="Relative API URL for the frame image.")
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class FrameListResponse(BaseModel):
    job_id: str
    total_frames: int = Field(ge=0, description="Total frames extracted for the job.")
    count: int = Field(ge=0, description="Number of frames returned in this response.")
    truncated: bool = Field(description="True when more frames exist than were returned.")
    sample_interval_seconds: float
    frames: list[FramePreview]


class UploadResponse(BaseModel):
    job_id: str = Field(description="Identifier used to reference the upload/analysis job.")
    status: JobStatus
    original_name: str
    extension: str
    size_bytes: int = Field(ge=0)
    content_type: str
    uploaded_at: datetime
    retention_note: str = Field(
        description="Human-readable statement about how long the upload is retained."
    )


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    original_name: str
    extension: str
    size_bytes: int
    content_type: str
    created_at: datetime
    updated_at: datetime | None = None
    video: VideoMetadata | None = Field(
        default=None,
        description="Real decoded-video metadata. Present once frame extraction has completed.",
    )
    analysis: dict | None = Field(
        default=None,
        description="Populated once the CV pipeline is implemented. Always null in this milestone.",
    )
    error: str | None = Field(
        default=None,
        description="Human-readable message when the job ends in a failed state.",
    )
    error_code: str | None = Field(
        default=None,
        description="Stable machine-readable error code when the job failed.",
    )