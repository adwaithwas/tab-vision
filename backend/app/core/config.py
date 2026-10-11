"""Application configuration.

Values are read from environment variables and an optional ``.env`` file
(see ``backend/.env.example``). The settings object is the single source of
truth for runtime configuration so that no machine-specific path or secret
is ever hard-coded in application code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration for the GuitarTab AI backend."""

    model_config = SettingsConfigDict(
        env_prefix="GUITARTAB_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GuitarTab AI"
    version: str = "0.1.0"
    environment: str = Field(default="development", description="runtime environment label")

    # --- Upload handling -------------------------------------------------
    upload_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "uploads",
        description="Directory where uploaded videos + metadata sidecars are stored.",
    )
    max_upload_size_mb: int = Field(default=100, ge=1, le=2048)
    allowed_extensions: tuple[str, ...] = Field(
        default=(".mp4", ".mov", ".webm"),
        description="Video file extensions accepted by the upload endpoint.",
    )
    allowed_content_types: tuple[str, ...] = Field(
        default=(
            "video/mp4",
            "video/quicktime",
            "video/webm",
            "application/octet-stream",
        ),
        description=(
            "Content types accepted by the upload endpoint. octet-stream is "
            "allowed because some browsers send it for known video files."
        ),
    )
    upload_timeout_seconds: int = Field(default=300)
    keep_uploads_days: int = Field(
        default=30,
        description="Uploads older than this are eligible for cleanup (see scripts/cleanup_uploads.py).",
    )

    # --- Frame extraction (Milestone 2) ---------------------------------
    processed_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "processed",
        description="Directory where extracted frames + processing metadata are stored, per job.",
    )
    frame_sample_interval_seconds: float = Field(
        default=1.0,
        gt=0,
        le=60,
        description="Extract one frame every N seconds of video. Default: 1 frame/second.",
    )
    frame_store_max_width: int = Field(
        default=1280,
        ge=0,
        description=(
            "Downscale stored frames so their width does not exceed this. 0 stores "
            "frames at native resolution. Bounds on-disk size for high-res video."
        ),
    )
    jpeg_quality: int = Field(default=85, ge=1, le=100)

    # Resource limits — refuse anything that could exhaust the process.
    max_video_duration_seconds: float = Field(
        default=600.0,
        gt=0,
        description="Reject videos longer than this (default 10 minutes).",
    )
    max_video_dimension: int = Field(
        default=4096,
        ge=1,
        description="Reject videos whose width or height exceeds this many pixels.",
    )
    max_decoded_frames: int = Field(
        default=100_000,
        ge=1,
        description=(
            "Maximum number of frames scanned while sampling (guards videos whose "
            "frame count is unknown). ~10 min at up to ~166 fps."
        ),
    )
    max_extracted_frames: int = Field(
        default=600,
        ge=1,
        description="Maximum number of frames saved per job (10 min at 1 fps).",
    )

    # --- CORS ------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Origins allowed to call the API from a browser.",
    )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_dir_absolute(self) -> Path:
        return self.upload_dir.expanduser().resolve()

    @property
    def processed_dir_absolute(self) -> Path:
        return self.processed_dir.expanduser().resolve()

    def validate_upload_dir(self) -> None:
        """Ensure the upload directory exists and is a directory."""
        base = self.upload_dir_absolute
        base.mkdir(parents=True, exist_ok=True)
        if not base.is_dir():
            raise RuntimeError(f"Upload path is not a directory: {base}")

    def validate_processed_dir(self) -> None:
        """Ensure the processed-data directory exists and is a directory."""
        base = self.processed_dir_absolute
        base.mkdir(parents=True, exist_ok=True)
        if not base.is_dir():
            raise RuntimeError(f"Processed path is not a directory: {base}")

    def validate_directories(self) -> None:
        self.validate_upload_dir()
        self.validate_processed_dir()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_directories()
    return settings