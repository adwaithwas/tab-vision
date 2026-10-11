"""Video upload and analysis-job endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.api.deps import UploadServiceDep
from app.core.logging import get_logger
from app.schemas.common import ErrorDetail
from app.schemas.video import JobResponse, UploadResponse
from app.services.uploads import UploadService, UploadValidationError

router = APIRouter(tags=["videos"])
logger = get_logger(__name__)

_MULTIPART_OVERHEAD_BYTES = 1024 * 1024  # generous allowance for multipart framing


def _detail(exc: UploadValidationError) -> dict:
    """Convert a domain validation error into a FastAPI ``detail`` payload."""
    return ErrorDetail(code=exc.code, message=exc.message).model_dump()


@router.post(
    "/api/videos/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a guitar video for later analysis",
    responses={
        400: {"description": "Validation failure (detail: code, message)"},
        413: {"description": "File exceeds the configured size limit"},
        422: {"description": "Missing multipart field"},
        500: {"description": "Storage failure"},
    },
)
async def upload_video(
    request: Request,
    service: UploadServiceDep,
    file: UploadFile = File(..., description="Video file (.mp4, .mov or .webm)"),
) -> UploadResponse:
    """Validate and store a video.

    The upload is real and persisted; **no analysis is performed**. The
    returned ``status`` is always ``received`` until the CV pipeline exists.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        limit = service.settings.max_upload_size_bytes + _MULTIPART_OVERHEAD_BYTES
        if int(declared) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=ErrorDetail(
                    code="file_too_large",
                    message=(
                        f"The file exceeds the configured maximum of "
                        f"{service.settings.max_upload_size_mb} MB."
                    ),
                ).model_dump(),
            )

    try:
        return service.save_upload(file.filename, file.content_type, file.file)
    except UploadValidationError as exc:
        logger.warning("Upload rejected code=%s filename=%r", exc.code, file.filename)
        raise HTTPException(status_code=exc.status_code, detail=_detail(exc)) from exc
    finally:
        await file.close()


@router.get(
    "/api/jobs/{job_id}",
    response_model=JobResponse,
    summary="Fetch the status of an upload / analysis job",
    responses={404: {"description": "Unknown job (detail: code, message)"}},
)
def get_job(job_id: str, service: UploadServiceDep) -> JobResponse:
    """Return persisted job metadata.

    Until the CV pipeline is implemented every job stays ``received`` and
    ``analysis`` remains null.
    """
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorDetail(
                code="job_not_found", message=f"No job found for id '{job_id}'."
            ).model_dump(),
        )
    return job