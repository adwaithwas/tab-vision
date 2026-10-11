"""Isolated computer-vision endpoints (experimental, opt-in).

These routes are deliberately namespaced under ``/api/vision`` and live in
their own module so that:

* No existing audio-pipeline route, schema, or response field is changed.
* Vision work only runs when a client explicitly calls these endpoints —
  never automatically during upload or transcription.
* Vision failures are contained: every error returns a structured JSON
  ``detail`` scoped to this request and is never surfaced by the audio flow.
* Frame reuse is strictly read-only via ``ProcessingService.frame_file_path``
  (a pure lookup already used by the frames routes); no job state, metadata,
  or on-disk frame is modified.

Endpoints
---------
* ``GET /api/vision/jobs/{job_id}/frames/{frame_index}``           — JSON geometry analysis
* ``GET /api/vision/jobs/{job_id}/frames/{frame_index}/annotated`` — annotated JPEG overlay
* ``GET /api/vision/jobs/{job_id}/frames/{frame_index}/rectified`` — rectified crop JPEG
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Response

from app.api.deps import ProcessingServiceDep
from app.core.logging import get_logger
from app.cv.vision_analysis import VisionAnalysis, analyze_frame
from app.schemas.common import ErrorDetail
from app.schemas.vision import (
    RectifiedSize,
    VisionAnalysisResponse,
    VisionFret,
    VisionPoint,
    VisionString,
)
from app.services.processing import ProcessingError

router = APIRouter(prefix="/api/vision", tags=["vision"])
logger = get_logger(__name__)

_JPEG_QUALITY = 90


def _raise(exc: ProcessingError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=ErrorDetail(code=exc.code, message=exc.message).model_dump(),
    )


def _load_frame(job_id: str, frame_index: int, service: Any) -> tuple[Path, np.ndarray]:
    """Resolve and decode one extracted frame (read-only reuse)."""
    try:
        path = service.frame_file_path(job_id, frame_index)
    except ProcessingError as exc:
        logger.info(
            "Vision frame lookup failed job=%s frame=%s code=%s",
            job_id,
            frame_index,
            exc.code,
        )
        _raise(exc)
        raise  # pragma: no cover - _raise always raises

    image = cv2.imread(str(path))
    if image is None:
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code="frame_read_failed",
                message=f"Could not read frame {frame_index} from disk.",
            ).model_dump(),
        )
    return path, image


def _run_analysis(
    job_id: str, frame_index: int, image: np.ndarray
) -> VisionAnalysis:
    """Run vision analysis with full error containment."""
    try:
        return analyze_frame(image)
    except Exception as exc:  # noqa: BLE001 - containment boundary
        logger.exception(
            "Vision analysis crashed job=%s frame=%s", job_id, frame_index
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code="vision_analysis_failed",
                message=(
                    "The vision analyzer could not process this frame. "
                    "Audio transcription is unaffected."
                ),
            ).model_dump(),
        ) from exc


def _encode_jpeg(image: np.ndarray, code: str, message: str) -> bytes:
    ok, buffer = cv2.imencode(
        ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
    )
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(code=code, message=message).model_dump(),
        )
    return buffer.tobytes()


def _to_response(job_id: str, frame_index: int, analysis: VisionAnalysis) -> VisionAnalysisResponse:
    base = f"/api/vision/jobs/{job_id}/frames/{frame_index}"
    images: dict[str, str | None] = {
        "annotated": f"{base}/annotated",
        "rectified": f"{base}/rectified" if analysis.rectified is not None else None,
    }
    return VisionAnalysisResponse(
        job_id=job_id,
        frame_index=frame_index,
        detected=analysis.detected,
        confidence=round(float(analysis.confidence), 4),
        detection_source=analysis.detection_source,
        polygon=(
            [VisionPoint(x=p[0], y=p[1]) for p in analysis.polygon]
            if analysis.polygon
            else None
        ),
        rectified=(
            RectifiedSize(width=analysis.rectified_size[0], height=analysis.rectified_size[1])
            if analysis.rectified_size is not None
            else None
        ),
        strings=[
            VisionString(
                position=s.position,
                y_in_rectified=round(s.y_rectified, 2),
                strength=s.strength,
                start=VisionPoint(x=s.start[0], y=s.start[1]),
                end=VisionPoint(x=s.end[0], y=s.end[1]),
            )
            for s in analysis.strings
        ],
        strings_detected=len(analysis.strings),
        frets=[
            VisionFret(
                index=f.index,
                x_in_rectified=round(f.x_rectified, 2),
                strength=f.strength,
                start=VisionPoint(x=f.start[0], y=f.start[1]),
                end=VisionPoint(x=f.end[0], y=f.end[1]),
            )
            for f in analysis.frets
        ],
        frets_detected=len(analysis.frets),
        failure_reason=analysis.failure_reason,
        limitations=list(analysis.limitations),
        diagnostics=analysis.diagnostics,
        images=images,
    )


@router.get(
    "/jobs/{job_id}/frames/{frame_index}",
    response_model=VisionAnalysisResponse,
    summary="Analyze one extracted frame: fretboard, strings and fret wires (experimental)",
    responses={
        200: {"description": "Geometry analysis (detected may be false; see limitations)."},
        404: {"description": "Unknown job or frame index"},
        409: {"description": "Frame extraction has not completed"},
        500: {"description": "Frame could not be read or vision analysis failed"},
    },
)
def analyze_vision(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
) -> VisionAnalysisResponse:
    """Run the isolated vision analysis on one extracted frame.

    Detection, rectification, string rows and fret wires are measured from
    real image evidence only. When nothing credible is found the response
    reports ``detected=false`` with a diagnostic ``failure_reason`` — the
    endpoint never fabricates geometry.
    """
    _, image = _load_frame(job_id, frame_index, service)
    analysis = _run_analysis(job_id, frame_index, image)
    return _to_response(job_id, frame_index, analysis)


@router.get(
    "/jobs/{job_id}/frames/{frame_index}/annotated",
    summary="Annotated JPEG: polygon + measured strings (blue) and frets (yellow)",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Annotated overlay."},
        404: {"description": "Unknown job or frame index"},
        409: {"description": "Frame extraction has not completed"},
        500: {"description": "Frame could not be read or analysis failed"},
    },
)
def annotated_frame(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
) -> Response:
    """Return the original frame with real detections drawn on top."""
    _, image = _load_frame(job_id, frame_index, service)
    analysis = _run_analysis(job_id, frame_index, image)

    from app.cv.vision_analysis import annotate_frame

    overlay = annotate_frame(image, analysis)
    payload = _encode_jpeg(overlay, "vision_render_failed", "Failed to encode annotated image.")
    return Response(content=payload, media_type="image/jpeg")


@router.get(
    "/jobs/{job_id}/frames/{frame_index}/rectified",
    summary="Perspective-rectified fretboard crop (detected frames only)",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Rectified crop with annotations."},
        404: {"description": "Unknown job/frame, or no fretboard was detected"},
        409: {"description": "Frame extraction has not completed"},
        500: {"description": "Frame could not be read or analysis failed"},
    },
)
def rectified_frame(
    job_id: str,
    frame_index: int,
    service: ProcessingServiceDep,
) -> Response:
    """Return the straightened fretboard crop with string/fret annotations."""
    _, image = _load_frame(job_id, frame_index, service)
    analysis = _run_analysis(job_id, frame_index, image)

    if analysis.rectified is None or analysis.rectified_annotated is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="not_detected",
                message="No fretboard was localized in this frame, so no crop exists.",
            ).model_dump(),
        )

    payload = _encode_jpeg(
        analysis.rectified_annotated,
        "vision_render_failed",
        "Failed to encode rectified image.",
    )
    return Response(content=payload, media_type="image/jpeg")
