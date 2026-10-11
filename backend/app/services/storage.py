"""Low-level file storage helpers for video uploads.

All paths are derived from :class:`~app.core.config.Settings`; no
user-supplied string is ever interpolated into a filesystem path. Stored
filenames are server-generated UUIDs plus a validated extension.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Job ids are server-generated: 32 lowercase hex characters (uuid4().hex).
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
FRAME_FILENAME_PATTERN = re.compile(r"^frame_(\d{6})\.jpg$")


class UploadStore:
    """Manages the on-disk upload directory."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def ensure_dir(self) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def generate_stored_name(self, extension: str) -> str:
        """Return a server-generated filename with a validated extension."""
        return f"{uuid.uuid4().hex}{extension}"

    def file_path(self, stored_name: str) -> Path:
        """Resolve a stored name to an absolute path, rejecting traversal."""
        candidate = (self.base_dir / stored_name).resolve()
        if candidate.parent != self.base_dir:
            raise ValueError("Refusing to resolve a path outside the upload directory.")
        return candidate

    def stream_to_disk(self, source, stored_name: str, max_bytes: int) -> int:
        """Stream ``source`` to the upload directory in chunks.

        Returns the number of bytes written. Raises ``OverflowError`` if the
        upload grows beyond ``max_bytes``; the partial file is removed so no
        junk accumulates.
        """
        self.ensure_dir()
        target = self.file_path(stored_name)
        written = 0
        try:
            with target.open("wb") as out:
                while True:
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise OverflowError(f"Upload exceeds {max_bytes} byte limit")
                    out.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        logging_note = f"stored upload to {target.name} ({written} bytes)"
        logger.info(logging_note)
        return written

    def write_json(self, stored_name: str, payload: dict) -> None:
        """Write a JSON sidecar next to an upload (used for the job registry)."""
        import json

        self.ensure_dir()
        target = self.file_path(f"{stored_name}.json")
        tmp = self.file_path(f"{stored_name}.json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True, separators=(",", ":"))
        tmp.replace(target)

    def read_json(self, stored_name: str) -> dict | None:
        import json

        try:
            sidecar = self.file_path(f"{stored_name}.json")
        except ValueError:
            # Traversal-shaped id — treat as not found, never as a path.
            logger.warning("Rejected malformed job id: %r", stored_name)
            return None
        if not sidecar.exists():
            return None
        try:
            with sidecar.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("Unreadable job sidecar: %s", sidecar.name)
            return None

    def list_jobs(self) -> list[str]:
        """Return stored names of all uploads present in the directory."""
        return sorted(p.stem for p in self.base_dir.glob("*.json"))

    def remove(self, stored_name: str) -> None:
        self.file_path(stored_name).unlink(missing_ok=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"UploadStore({str(self.base_dir)!r})"


def copy_to_store(source_file, store: UploadStore, stored_name: str, max_bytes: int) -> int:
    """Stream a starlette ``UploadFile`` into the store."""
    return store.stream_to_disk(source_file.file, stored_name, max_bytes)


class ProcessedStore:
    """Manages per-job frame output under the processed-data directory.

    Layout::

        <base>/<job_id>/metadata.json
        <base>/<job_id>/frames/frame_000000.jpg

    Writes go to ``<base>/.tmp-<job_id>`` first and are atomically renamed into
    place on success, so a failed or interrupted job can never leave behind
    partial results that look complete. Every path is derived from a validated
    job id and frame index — never from client-supplied strings.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # --- validation -----------------------------------------------------
    @staticmethod
    def validate_job_id(job_id: str) -> str:
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.match(job_id):
            raise ValueError(f"Invalid job id: {job_id!r}")
        return job_id

    @staticmethod
    def is_valid_job_id(job_id: object) -> bool:
        return isinstance(job_id, str) and bool(JOB_ID_PATTERN.match(job_id))

    @staticmethod
    def frame_filename(index: int) -> str:
        if not isinstance(index, int) or index < 0:
            raise ValueError(f"Invalid frame index: {index!r}")
        return f"frame_{index:06d}.jpg"

    # --- paths ----------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        self.validate_job_id(job_id)
        candidate = (self.base_dir / job_id).resolve()
        if candidate.parent != self.base_dir:
            raise ValueError("Refusing a path outside the processed directory.")
        return candidate

    def temp_dir(self, job_id: str) -> Path:
        self.validate_job_id(job_id)
        candidate = (self.base_dir / f".tmp-{job_id}").resolve()
        if candidate.parent != self.base_dir:
            raise ValueError("Refusing a path outside the processed directory.")
        return candidate

    def frames_dir(self, job_id: str, *, root: Path | None = None) -> Path:
        base = root if root is not None else self.job_dir(job_id)
        return base / "frames"

    def frame_path(self, job_id: str, index: int) -> Path:
        return self.frames_dir(job_id) / self.frame_filename(index)

    def metadata_path(self, job_id: str, *, root: Path | None = None) -> Path:
        base = root if root is not None else self.job_dir(job_id)
        return base / "metadata.json"

    def exists(self, job_id: str) -> bool:
        try:
            return self.job_dir(job_id).is_dir()
        except ValueError:
            return False

    # --- lifecycle ------------------------------------------------------
    def begin(self, job_id: str) -> Path:
        """Create (or reset) the temporary working directory for a job."""
        temp = self.temp_dir(job_id)
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)
        self.frames_dir(job_id, root=temp).mkdir(parents=True, exist_ok=True)
        return temp

    def commit(self, job_id: str) -> None:
        """Atomically move the temporary directory into its final location."""
        temp = self.temp_dir(job_id)
        final = self.job_dir(job_id)
        if not temp.exists():
            raise FileNotFoundError(f"Nothing to commit for job {job_id}")
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        os.replace(temp, final)

    def discard(self, job_id: str) -> None:
        """Remove temporary and final artifacts for a job (best effort)."""
        try:
            shutil.rmtree(self.temp_dir(job_id), ignore_errors=True)
            shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
        except ValueError:
            logger.warning("Refused to discard unexpected job id: %r", job_id)

    # --- metadata -------------------------------------------------------
    def write_metadata(self, job_id: str, payload: dict, *, root: Path | None = None) -> None:
        import json

        base = root if root is not None else self.job_dir(job_id)
        base.mkdir(parents=True, exist_ok=True)
        target = self.metadata_path(job_id, root=base)
        tmp = target.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True, separators=(",", ":"))
        tmp.replace(target)

    def read_metadata(self, job_id: str) -> dict | None:
        import json

        try:
            target = self.metadata_path(job_id)
        except ValueError:
            return None
        if not target.exists():
            return None
        try:
            with target.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            logger.warning("Unreadable processing metadata for job %s", job_id)
            return None

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"ProcessedStore({str(self.base_dir)!r})"