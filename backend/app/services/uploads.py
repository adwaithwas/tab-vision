"""Video upload service: validation, persistence, and the job registry.

Keeps business rules out of the route handlers. The upload itself is real;
the analysis job is persistent but always in ``received`` state until the CV
pipeline exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.video import JobResponse, JobStatus, UploadResponse
from app.services.storage import UploadStore

logger = get_logger(__name__)

RETENTION_NOTE = (
    "Uploads are retained for up to {keep_days} days and can be removed manually "
    "with scripts/cleanup_uploads.py at any time."
)


class UploadValidationError(Exception):
    """A user-contributed video failed validation."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _validate_extension(filename: str, settings: Settings) -> str:
    """Return the lower-cased extension, or raise if not acceptable."""
    name = Path(filename).name  # strip any directory components
    ext = Path(name).suffix.lower()
    if not ext:
        raise UploadValidationError(
            "missing_extension",
            "The file has no extension. Please provide a video with a .mp4, .mov, or .webm extension.",
        )
    if ext not in settings.allowed_extensions:
        raise UploadValidationError(
            "unsupported_extension",
            f"Unsupported file type '.{ext.lstrip('.')}'. "
            f"Accepted extensions: {', '.join(e.lstrip('.') for e in settings.allowed_extensions)}.",
        )
    return ext


def _validate_content_type(content_type: str | None, settings: Settings) -> str:
    """Normalise and validate the declared content type (lenient on octet-stream)."""
    ct = (content_type or "").strip().lower()
    if ct and ct not in settings.allowed_content_types and "video/" not in ct:
        raise UploadValidationError(
            "unsupported_content_type",
            f"Content type '{ct}' is not recognised as video.",
        )
    return ct or "application/octet-stream"


class UploadService:
    """Owns the upload store and per-job metadata."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = UploadStore(settings.upload_dir_absolute)

    def save_upload(
        self,
        filename: str | None,
        content_type: str | None,
        file_stream: BinaryIO,
    ) -> UploadResponse:
        """Validate and persist an uploaded video, returning real metadata."""
        if not filename or not filename.strip():
            raise UploadValidationError("missing_file", "No file was provided.")
        original_name = filename.strip().replace("\\", "/").split("/")[-1]

        ext = _validate_extension(original_name, self.settings)
        ct = _validate_content_type(content_type, self.settings)

        stored_name = self.store.generate_stored_name(ext)
        job_id = Path(stored_name).stem
        now = datetime.now(timezone.utc)

        try:
            size = self.store.stream_to_disk(
                file_stream, stored_name, self.settings.max_upload_size_bytes
            )
        except OverflowError:
            raise UploadValidationError(
                "file_too_large",
                f"The file exceeds the configured maximum of "
                f"{self.settings.max_upload_size_mb} MB.",
                status_code=413,
            )
        except OSError as exc:
            raise UploadValidationError(
                "storage_error", "Could not store the file. Please try again.", status_code=500
            ) from exc

        if size == 0:
            self.store.remove(stored_name)
            raise UploadValidationError(
                "empty_file", "The uploaded file is empty. Please choose a non-empty video."
            )

        meta = {
            "job_id": job_id,
            "status": JobStatus.RECEIVED.value,
            "original_name": original_name,
            "stored_name": stored_name,
            "extension": ext,
            "size_bytes": size,
            "content_type": ct,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self.store.write_json(job_id, meta)
        logger.info("Upload accepted job_id=%s name=%r size=%d", job_id, original_name, size)

        return UploadResponse(
            job_id=job_id,
            status=JobStatus.RECEIVED,
            original_name=original_name,
            extension=ext.lstrip("."),
            size_bytes=size,
            content_type=ct,
            uploaded_at=now,
            retention_note=RETENTION_NOTE.format(keep_days=self.settings.keep_uploads_days),
        )

    def get_job(self, job_id: str) -> JobResponse | None:
        """Return persisted job metadata, or ``None`` if unknown."""
        meta = self.store.read_json(job_id)
        if meta is None:
            return None
        return self._meta_to_response(meta)

    def get_job_meta(self, job_id: str) -> dict | None:
        """Return the raw stored job record (or ``None``)."""
        return self.store.read_json(job_id)

    def update_job(self, job_id: str, **fields) -> dict | None:
        """Merge ``fields`` into a stored job record and persist it."""
        meta = self.store.read_json(job_id)
        if meta is None:
            return None
        meta.update(fields)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.store.write_json(job_id, meta)
        return meta

    def resolve_video_path(self, job_id: str) -> Path | None:
        """Return the on-disk path of a job's uploaded video, if it still exists."""
        meta = self.store.read_json(job_id)
        if not meta:
            return None
        stored_name = meta.get("stored_name")
        if not stored_name:
            return None
        try:
            path = self.store.file_path(stored_name)
        except ValueError:
            return None
        return path if path.is_file() else None

    def _meta_to_response(self, meta: dict) -> JobResponse:
        created = datetime.fromisoformat(meta["created_at"])
        updated_raw = meta.get("updated_at")
        updated = datetime.fromisoformat(updated_raw) if updated_raw else None
        return JobResponse(
            job_id=meta["job_id"],
            status=meta.get("status", JobStatus.RECEIVED.value),
            original_name=meta["original_name"],
            extension=meta["extension"].lstrip("."),
            size_bytes=meta["size_bytes"],
            content_type=meta["content_type"],
            created_at=created,
            updated_at=updated,
            video=meta.get("video"),
            analysis=meta.get("analysis"),
            error=meta.get("error"),
            error_code=meta.get("error_code"),
        )