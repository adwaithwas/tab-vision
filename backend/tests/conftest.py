"""Shared fixtures for backend tests.

Tests run against a throwaway upload directory inside the pytest tmp dir so
the developer's ``data/uploads`` is never touched. Requests go through
starlette's ``TestClient`` (synchronous ASGI harness).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def processed_dir(tmp_path: Path) -> Path:
    return tmp_path / "processed"


@pytest.fixture
def settings(upload_dir: Path, processed_dir: Path) -> Settings:
    return Settings(
        environment="test",
        upload_dir=upload_dir,
        processed_dir=processed_dir,
        max_upload_size_mb=2,
        keep_uploads_days=30,
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def make_video_bytes(size: int = 2048) -> bytes:
    """Produce a tiny, deterministic non-empty payload for upload tests."""
    return (bytes(range(256)) * (size // 256 + 1))[: size or 1]


@pytest.fixture
def sample_mp4() -> bytes:
    return make_video_bytes(2048)


@pytest.fixture
def sample_mov() -> bytes:
    return make_video_bytes(4096)