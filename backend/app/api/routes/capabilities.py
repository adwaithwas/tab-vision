"""GET /api/capabilities — reports what works today vs. what is planned."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.common import (
    CapabilitiesResponse,
    CvCapability,
    FrameExtractionCapability,
    UploadCapability,
)
from app.cv import describe_pipeline

router = APIRouter(tags=["system"])

NOTES = [
    "Video upload and validation are implemented for real.",
    "Real video decoding and frame extraction (OpenCV) are implemented: one frame "
    "per second by default, saved per job.",
    "No note detection, fretboard detection, hand detection or tablature "
    "generation is implemented. The cv_pipeline section lists those as planned.",
    "Extracted frames are available through the frames endpoints; no analysis "
    "result is produced yet.",
    "Target input: single six-string guitar, controlled camera angle and lighting, "
    "short clips within the configured limits.",
]


@router.get(
    "/api/capabilities",
    response_model=CapabilitiesResponse,
    summary="Implemented vs. planned capabilities",
)
def capabilities(settings: SettingsDep) -> CapabilitiesResponse:
    stages = describe_pipeline()
    return CapabilitiesResponse(
        service=settings.app_name,
        version=settings.version,
        video_upload=UploadCapability(
            supported=True,
            max_file_size_mb=settings.max_upload_size_mb,
            allowed_extensions=list(settings.allowed_extensions),
            allowed_content_types=list(settings.allowed_content_types),
        ),
        frame_extraction=FrameExtractionCapability(
            implemented=True,
            sample_interval_seconds=settings.frame_sample_interval_seconds,
            supported_formats=list(settings.allowed_extensions),
            max_video_duration_seconds=settings.max_video_duration_seconds,
            max_video_dimension=settings.max_video_dimension,
            max_decoded_frames=settings.max_decoded_frames,
            max_extracted_frames=settings.max_extracted_frames,
            frame_store_max_width=settings.frame_store_max_width,
        ),
        cv_pipeline=CvCapability(
            implemented=any(s.implemented for s in stages),
            stages=stages,
        ),
        notes=NOTES,
    )