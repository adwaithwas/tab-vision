"""Frame-processing and extracted-frame endpoints.

* ``POST /api/jobs/{job_id}/process``      — decode the video and extract frames
* ``GET  /api/jobs/{job_id}/frames``       — metadata for a small frame preview list
* ``GET  /api/jobs/{job_id}/frames/{index}`` — the actual JPEG for one frame

Processing runs synchronously inside a worker thread (FastAPI runs ``def``
handlers in its threadpool), which keeps the existing file-based architecture
reliable without a queue or database. Concurrent duplicate processing of the
same job is refused with HTTP 409.
"""

from __future__ import annotations

from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse

from app.api.deps import ProcessingServiceDep
from app.core.logging import get_logger
from app.cv import detect_fretboard_hybrid, visualize_detection
from app.schemas.common import ErrorDetail
from app.schemas.fretboard import (
    FretboardDetectionResponse,
    FretboardGeometrySchema,
    FretboardPoint,
)
from app.schemas.video import FrameListResponse, JobResponse, JobStatus
from app.services.processing import ProcessingError

router = APIRouter(tags=["frames"])
logger = get_logger(__name__)



def _raise(exc: ProcessingError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=ErrorDetail(code=exc.code, message=exc.message).model_dump(),
    )


from fastapi import APIRouter, HTTPException, Query, Response

@router.post(
    "/api/jobs/{job_id}/process",
    response_model=JobResponse,
    summary="Decode the uploaded video and extract frames",
    responses={
        404: {"description": "Unknown job or missing video file"},
        409: {"description": "Processing already in progress"},
        422: {"description": "Video could not be decoded or violated a resource limit"},
    },
)
def process_job(job_id: str, service: ProcessingServiceDep) -> JobResponse:
    """Run real frame extraction and return the updated job.

    The job transitions ``received → processing → completed`` (or ``failed``).
    Nothing is reported complete until frames are genuinely on disk.
    """
    try:
        return service.process(job_id)
    except ProcessingError as exc:
        logger.warning("Processing rejected job=%s code=%s", job_id, exc.code)
        _raise(exc)
        raise  # pragma: no cover - _raise always raises


@router.get(
    "/api/jobs/{job_id}/frames",
    response_model=FrameListResponse,
    summary="Preview metadata for extracted frames",
    responses={
        404: {"description": "Unknown job"},
        409: {"description": "Frame extraction has not completed"},
    },
)
def list_frames(
    job_id: str,
    service: ProcessingServiceDep,
    limit: int = Query(default=24, ge=1, le=200, description="Maximum frames to return."),
) -> FrameListResponse:
    """Return a small, ordered list of extracted-frame previews with timestamps."""
    try:
        return service.list_frames(job_id, limit=limit)
    except ProcessingError as exc:
        _raise(exc)
        raise  # pragma: no cover


@router.get(
    "/api/jobs/{job_id}/frames/{frame_index}",
    summary="A single extracted frame as a JPEG image",
    response_class=FileResponse,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "The extracted frame."},
        404: {"description": "Unknown job or frame index"},
        409: {"description": "Frame extraction has not completed"},
    },
)
def get_frame(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
    max_width: int | None = Query(
        default=None,
        ge=16,
        le=4096,
        description="Optionally return a downscaled copy no wider than this many pixels.",
    ),
) -> Response:
    """Serve one extracted frame. The index is validated against real output."""
    try:
        path = service.frame_file_path(job_id, frame_index)
    except ProcessingError as exc:
        _raise(exc)
        raise  # pragma: no cover

    if max_width is None:
        return FileResponse(path, media_type="image/jpeg")

    resized = _read_resized(path, max_width)
    if resized is None:
        return FileResponse(path, media_type="image/jpeg")
    return Response(content=resized, media_type="image/jpeg")


def _read_resized(path: Path, max_width: int) -> bytes | None:
    """Return a downscaled JPEG, or ``None`` if resizing is not possible."""
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    if width <= max_width:
        return None
    scale = max_width / width
    resized = cv2.resize(
        image, (max_width, max(1, round(height * scale))), interpolation=cv2.INTER_AREA
    )
    ok, buffer = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return None
    return buffer.tobytes()


@router.get(
    "/api/jobs/{job_id}/frames/{frame_index}/fretboard",
    response_model=FretboardDetectionResponse,
    summary="Localize guitar fretboard in an extracted frame using classical CV",
    responses={
        200: {"description": "Structured fretboard detection result."},
        404: {"description": "Unknown job or frame index"},
        409: {"description": "Frame extraction has not completed"},
        500: {"description": "Could not read or decode frame from disk"},
    },
)
def detect_frame_fretboard(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
) -> FretboardDetectionResponse:
    """Run classical fretboard localization on the given extracted frame."""
    try:
        path = service.frame_file_path(job_id, frame_index)
    except ProcessingError as exc:
        _raise(exc)
        raise  # pragma: no cover

    image = cv2.imread(str(path))
    if image is None:
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code="frame_read_failed",
                message=f"Could not read frame {frame_index} from disk.",
            ).model_dump(),
        )

    result = detect_fretboard_hybrid(image)

    polygon = (
        [FretboardPoint(x=pt[0], y=pt[1]) for pt in result.polygon]
        if result.polygon is not None
        else None
    )
    geometry = (
        FretboardGeometrySchema(
            orientation_deg=result.geometry.orientation_deg,
            estimated_length=result.geometry.estimated_length,
            estimated_width=result.geometry.estimated_width,
            aspect_ratio=result.geometry.aspect_ratio,
            fret_count_estimate=result.geometry.fret_count_estimate,
            transverse_edge_density=result.geometry.transverse_edge_density,
        )
        if result.geometry is not None
        else None
    )

    return FretboardDetectionResponse(
        job_id=job_id,
        frame_index=frame_index,
        detected=result.detected,
        confidence=result.confidence,
        polygon=polygon,
        geometry=geometry,
        failure_reason=result.failure_reason,
        diagnostics=result.diagnostics,
    )


@router.get(
    "/api/jobs/{job_id}/frames/{frame_index}/fretboard-debug",
    summary="Get JPEG debug overlay of classical fretboard localization",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Visualized detection overlay."},
        404: {"description": "Unknown job or frame index"},
        409: {"description": "Frame extraction has not completed"},
        500: {"description": "Failed to generate visualization"},
    },
)
def get_frame_fretboard_debug(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
) -> Response:
    """Run localization and return an annotated debug JPEG."""
    try:
        path = service.frame_file_path(job_id, frame_index)
    except ProcessingError as exc:
        _raise(exc)
        raise  # pragma: no cover

    image = cv2.imread(str(path))
    if image is None:
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code="frame_read_failed",
                message=f"Could not read frame {frame_index} from disk.",
            ).model_dump(),
        )

    result = detect_fretboard_hybrid(image)
    overlay = visualize_detection(image, result)

    ok, buffer = cv2.imencode(".jpg", overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code="debug_render_failed",
                message="Failed to encode debug image.",
            ).model_dump(),
        )

    return Response(content=buffer.tobytes(), media_type="image/jpeg")