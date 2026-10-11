"""Video decoding and frame extraction.

This module performs **real** decoding with OpenCV and extracts sampled frames
to disk. It does not fabricate metadata or results: if a file cannot be decoded
it raises a structured :class:`ProcessingError` and the job is marked failed.

Design notes
------------
* The whole video is **never** loaded into memory. Frames are pulled one at a
  time; only sampled frames are decoded and saved (non-sampled frames are only
  ``grab()``-ed, which demuxes without full decode).
* Every write goes to a temporary directory that is atomically renamed into
  place on success, so a failed job cannot leave partial "completed" output.
* Resource limits (duration, resolution, decoded frames, extracted frames) are
  enforced before and during extraction.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.video import FrameListResponse, FramePreview, JobResponse, JobStatus
from app.services.storage import ProcessedStore
from app.services.uploads import UploadService

logger = get_logger(__name__)

VIDEO_METADATA_KEYS = (
    "width",
    "height",
    "fps",
    "frame_count",
    "duration_seconds",
    "duration_estimated",
    "sample_interval_seconds",
    "frames_extracted",
    "processed_at",
)


class ProcessingError(Exception):
    """A structured, user-presentable processing failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _safe_int(value: float) -> int:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(f):
        return 0
    return int(f)


def _safe_float(value: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def validate_video_metadata(width: int, height: int, fps: float) -> None:
    """Reject videos whose decoded metadata cannot be trusted."""
    if width <= 0 or height <= 0:
        raise ProcessingError(
            "invalid_metadata",
            "The video reports invalid dimensions and cannot be processed.",
        )
    if not math.isfinite(fps) or fps <= 0:
        raise ProcessingError(
            "invalid_fps",
            "The video reports an invalid frame rate (FPS) and cannot be sampled reliably.",
        )


class VideoProcessor:
    """Extracts sampled frames from a single video file using OpenCV."""

    def __init__(self, settings: Settings, processed: ProcessedStore) -> None:
        self.settings = settings
        self.processed = processed

    def extract(self, job_id: str, video_path: Path) -> dict:
        """Decode ``video_path`` and write sampled frames for ``job_id``.

        Returns the full processing metadata dict (including the per-frame list).
        Raises :class:`ProcessingError` on any handled failure.
        """
        if not video_path.is_file():
            raise ProcessingError(
                "video_missing",
                "The uploaded video file is no longer available. Please upload it again.",
                status_code=404,
            )

        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                raise ProcessingError(
                    "unreadable_video",
                    "The file could not be decoded as a video. It may be corrupt or use an unsupported codec.",
                )

            width = _safe_int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = _safe_int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = _safe_float(capture.get(cv2.CAP_PROP_FPS))
            reported_frames = _safe_int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

            validate_video_metadata(width, height, fps)

            if max(width, height) > self.settings.max_video_dimension:
                raise ProcessingError(
                    "resolution_exceeded",
                    f"The video is {width}×{height}, larger than the "
                    f"{self.settings.max_video_dimension}px limit.",
                )

            if reported_frames > 0:
                estimated_duration = reported_frames / fps
                if estimated_duration > self.settings.max_video_duration_seconds:
                    raise ProcessingError(
                        "duration_exceeded",
                        f"The video is about {estimated_duration:.0f}s long, beyond the "
                        f"{self.settings.max_video_duration_seconds:.0f}s limit.",
                    )

            interval = self.settings.frame_sample_interval_seconds
            step = max(1, int(round(fps * interval)))
            if reported_frames > 0:
                expected = math.ceil(reported_frames / step)
                if expected > self.settings.max_extracted_frames:
                    raise ProcessingError(
                        "extracted_frames_exceeded",
                        f"Sampling every {interval:g}s would produce about {expected} frames, "
                        f"beyond the {self.settings.max_extracted_frames}-frame limit. "
                        "Use a shorter clip or a larger sampling interval.",
                    )

            temp = self.processed.begin(job_id)
            frames: list[dict] = []
            frame_index = 0
            next_sample = 0
            max_dur = self.settings.max_video_duration_seconds

            while True:
                if not capture.grab():
                    break

                if frame_index >= next_sample:
                    ok, frame = capture.retrieve()
                    if not ok or frame is None:
                        raise ProcessingError(
                            "decode_failed",
                            f"Decoding failed at frame {frame_index}. The video may be corrupt.",
                        )

                    timestamp = round(frame_index / fps, 3)
                    if timestamp > max_dur + (1.0 / fps):
                        raise ProcessingError(
                            "duration_exceeded",
                            f"The video exceeds the {max_dur:.0f}s duration limit.",
                        )

                    stored = self._write_frame(temp, job_id, len(frames), frame)
                    frames.append(
                        {
                            "index": len(frames),
                            "timestamp_seconds": timestamp,
                            "source_frame": frame_index,
                            "width": stored["width"],
                            "height": stored["height"],
                        }
                    )

                    if len(frames) > self.settings.max_extracted_frames:
                        raise ProcessingError(
                            "extracted_frames_exceeded",
                            f"More than {self.settings.max_extracted_frames} frames would be "
                            "extracted. Use a shorter clip or a larger sampling interval.",
                        )

                    next_sample += step

                frame_index += 1
                if frame_index > self.settings.max_decoded_frames:
                    raise ProcessingError(
                        "decoded_frames_exceeded",
                        f"The video needs more than {self.settings.max_decoded_frames} frames to "
                        "be scanned, beyond the configured limit.",
                    )

            if not frames:
                raise ProcessingError(
                    "no_frames_extracted",
                    "No decodable frames were found in the video.",
                )

            total_frames = reported_frames if reported_frames > 0 else frame_index
            duration_seconds = round(total_frames / fps, 3)
            metadata = {
                "job_id": job_id,
                "width": width,
                "height": height,
                "fps": round(fps, 3),
                "frame_count": total_frames,
                "duration_seconds": duration_seconds,
                "duration_estimated": True,
                "sample_interval_seconds": interval,
                "frames_extracted": len(frames),
                "decoded_frames": frame_index,
                "store_max_width": self.settings.frame_store_max_width,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "frames": frames,
            }

            self.processed.write_metadata(job_id, metadata, root=temp)
            self.processed.commit(job_id)
            logger.info(
                "Extracted %d frame(s) for job %s (%dx%d, %.1f fps, ~%.1fs)",
                len(frames),
                job_id,
                width,
                height,
                fps,
                duration_seconds,
            )
            return metadata
        except ProcessingError:
            self.processed.discard(job_id)
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self.processed.discard(job_id)
            logger.exception("Unexpected failure processing job %s", job_id)
            raise ProcessingError(
                "processing_failed",
                "An unexpected error occurred while processing the video.",
                status_code=500,
            ) from exc
        finally:
            capture.release()

    def _write_frame(self, temp: Path, job_id: str, index: int, frame) -> dict:
        height, width = frame.shape[:2]
        max_width = self.settings.frame_store_max_width
        if max_width and width > max_width:
            scale = max_width / width
            new_size = (max_width, max(1, round(height * scale)))
            frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
            height, width = frame.shape[:2]

        target = self.processed.frames_dir(job_id, root=temp) / self.processed.frame_filename(index)
        written = cv2.imwrite(
            str(target),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.settings.jpeg_quality],
        )
        if not written:
            raise ProcessingError(
                "frame_write_failed",
                "Extracted frames could not be written to disk.",
                status_code=500,
            )
        return {"width": width, "height": height}


# In-process guard against concurrent duplicate processing of the same job.
_process_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(job_id: str) -> threading.Lock:
    with _locks_guard:
        return _process_locks.setdefault(job_id, threading.Lock())


class ProcessingService:
    """Orchestrates the job lifecycle around :class:`VideoProcessor`."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.uploads = UploadService(settings)
        self.processed = ProcessedStore(settings.processed_dir_absolute)
        self.processor = VideoProcessor(settings, self.processed)

    def run_tabvision(self, job_id: str, video_path: Path) -> str | None:
        import subprocess
        
        # Path to tabvision venv
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        tabvision_exe = repo_root / "scratch" / "tab_vision" / "tabvision" / ".venv" / "Scripts" / "tabvision.exe"
        
        if not tabvision_exe.exists():
            logger.warning("TabVision executable not found at %s", tabvision_exe)
            return None
            
        temp_dir = self.processed.begin(job_id)
        out_tab = temp_dir / "out.tab"
        
        logger.info("Running TabVision for %s...", job_id)
        try:
            result = subprocess.run(
                [str(tabvision_exe), "transcribe", str(video_path), "--format", "ascii", "-o", str(out_tab)],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("TabVision finished successfully for %s", job_id)
            if out_tab.exists():
                # Read the file and also save a copy to the persistent frame directory
                content = out_tab.read_text(encoding="utf-8")
                final_tab_path = self.processed.job_dir(job_id) / "out.tab"
                final_tab_path.parent.mkdir(parents=True, exist_ok=True)
                final_tab_path.write_text(content, encoding="utf-8")
                return content
        except subprocess.CalledProcessError as e:
            logger.error("TabVision failed with exit code %d:\nSTDOUT: %s\nSTDERR: %s", e.returncode, e.stdout, e.stderr)
        except Exception:
            logger.exception("Failed to run TabVision")
            
        return None

    # --- processing -----------------------------------------------------
    def process(self, job_id: str) -> JobResponse:
        if not ProcessedStore.is_valid_job_id(job_id):
            raise ProcessingError("job_not_found", f"No job found for id '{job_id}'.", status_code=404)

        lock = _lock_for(job_id)
        if not lock.acquire(blocking=False):
            raise ProcessingError(
                "processing_in_progress",
                "This job is already being processed.",
                status_code=409,
            )
        try:
            meta = self.uploads.get_job_meta(job_id)
            if meta is None:
                raise ProcessingError(
                    "job_not_found", f"No job found for id '{job_id}'.", status_code=404
                )

            status = meta.get("status")
            if status == JobStatus.PROCESSING.value:
                raise ProcessingError(
                    "processing_in_progress",
                    "This job is already being processed.",
                    status_code=409,
                )
            if status == JobStatus.COMPLETED.value and self.processed.exists(job_id):
                existing = self.uploads.get_job(job_id)
                if existing is not None:
                    return existing

            video_path = self.uploads.resolve_video_path(job_id)
            if video_path is None:
                self._fail(
                    job_id,
                    "video_missing",
                    "The uploaded video file is no longer available. Please upload it again.",
                )
                raise ProcessingError(
                    "video_missing",
                    "The uploaded video file is no longer available. Please upload it again.",
                    status_code=404,
                )

            self.uploads.update_job(
                job_id, status=JobStatus.PROCESSING.value, error=None, error_code=None
            )
            try:
                full = self.processor.extract(job_id, video_path)
            except ProcessingError as exc:
                self._fail(job_id, exc.code, exc.message)
                raise

            video = {key: full[key] for key in VIDEO_METADATA_KEYS}
            
            # Run TabVision Audio Transcription
            tab_content = self.run_tabvision(job_id, video_path)
            analysis = None
            if tab_content:
                analysis = {"tablature": tab_content}
                
            self.uploads.update_job(
                job_id,
                status=JobStatus.COMPLETED.value,
                video=video,
                analysis=analysis,
                error=None,
                error_code=None,
            )
            result = self.uploads.get_job(job_id)
            assert result is not None  # noqa: S101 - invariant: job just written
            return result
        finally:
            lock.release()

    def _fail(self, job_id: str, code: str, message: str) -> None:
        self.uploads.update_job(
            job_id,
            status=JobStatus.FAILED.value,
            error=message,
            error_code=code,
        )

    # --- frame access ---------------------------------------------------
    def _completed_metadata(self, job_id: str) -> dict:
        if not ProcessedStore.is_valid_job_id(job_id):
            raise ProcessingError("job_not_found", f"No job found for id '{job_id}'.", status_code=404)
        meta = self.uploads.get_job_meta(job_id)
        if meta is None:
            raise ProcessingError(
                "job_not_found", f"No job found for id '{job_id}'.", status_code=404
            )
        if meta.get("status") != JobStatus.COMPLETED.value:
            raise ProcessingError(
                "frames_not_ready",
                "Frame extraction has not completed for this job.",
                status_code=409,
            )
        metadata = self.processed.read_metadata(job_id)
        if metadata is None:
            raise ProcessingError(
                "frames_not_ready",
                "No extracted frames are available for this job.",
                status_code=409,
            )
        return metadata

    def list_frames(self, job_id: str, limit: int = 24) -> FrameListResponse:
        metadata = self._completed_metadata(job_id)
        all_frames = metadata.get("frames", [])
        total = len(all_frames)
        selected = all_frames[:limit]
        previews = [
            FramePreview(
                index=item["index"],
                timestamp_seconds=item["timestamp_seconds"],
                url=f"/api/jobs/{job_id}/frames/{item['index']}",
                width=item["width"],
                height=item["height"],
            )
            for item in selected
        ]
        return FrameListResponse(
            job_id=job_id,
            total_frames=total,
            count=len(previews),
            truncated=total > len(previews),
            sample_interval_seconds=metadata.get(
                "sample_interval_seconds", self.settings.frame_sample_interval_seconds
            ),
            frames=previews,
        )

    def frame_file_path(self, job_id: str, index: int) -> Path:
        metadata = self._completed_metadata(job_id)
        if index < 0 or index >= len(metadata.get("frames", [])):
            raise ProcessingError(
                "frame_not_found",
                f"No extracted frame with index {index}.",
                status_code=404,
            )
        try:
            path = self.processed.frame_path(job_id, index)
        except ValueError:
            raise ProcessingError(
                "frame_not_found", f"No extracted frame with index {index}.", status_code=404
            ) from None
        if not path.is_file():
            raise ProcessingError(
                "frame_not_found",
                f"No extracted frame with index {index}.",
                status_code=404,
            )
        return path