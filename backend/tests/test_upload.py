"""Tests for POST /api/videos/upload and GET /api/jobs/{id}."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.uploads import UploadService, UploadValidationError


def test_upload_valid_mp4(client, upload_dir: Path) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("intro.mp4", b"\x00\x01\x02\x03" * 512, "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "received"
    assert body["original_name"] == "intro.mp4"
    assert body["extension"] == "mp4"
    assert body["content_type"] == "video/mp4"
    assert body["size_bytes"] == 2048
    assert body["job_id"]

    # Real file was written to the configured upload directory.
    stored = list(upload_dir.glob(f"{body['job_id']}.mp4"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == b"\x00\x01\x02\x03" * 512
    # Sidecar metadata exists next to it.
    assert upload_dir.joinpath(f"{body['job_id']}.json").exists()


def test_upload_valid_mov(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("clip.mov", b"MOV" * 100, "video/quicktime")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["extension"] == "mov"


def test_upload_valid_webm(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("clip.webm", b"WEBM" * 100, "video/webm")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["extension"] == "webm"


def test_upload_reject_content_type(client, upload_dir: Path) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("clip.mp4", b"\x00" * 100, "text/plain")},
    )
    assert resp.status_code == 400
    body = resp.json()["detail"]
    assert body["code"] == "unsupported_content_type"
    # Nothing should be persisted.
    assert list(upload_dir.glob("*")) == []


def test_upload_reject_extension(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_extension"


def test_upload_extension_without_dot(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("video-with-no-extension", b"\x00" * 10, "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "missing_extension"


def test_upload_empty_file(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("empty.mp4", b"", "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "empty_file"


def test_upload_missing_header_file(client) -> None:
    # FastAPI requires the multipart field named exactly `file`.
    resp = client.post(
        "/api/videos/upload", files={"video": ("clip.mp4", b"\x00" * 8, "video/mp4")}
    )
    assert resp.status_code == 422


def test_upload_too_large_by_header(client) -> None:
    # Settings cap = 2 MB; send 3 MB. Content-Length pre-check should trip.
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("big.mp4", b"\x00" * (3 * 1024 * 1024), "video/mp4")},
    )
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "file_too_large"


def test_stream_overflow_maps_to_413(settings: Settings) -> None:
    """A file that exceeds the limit *during streaming* is also a 413.

    The header pre-check is bypassed here by calling the service directly, so
    this exercises the chunked read/OverflowError branch.
    """
    service = UploadService(settings)
    oversized = io.BytesIO(b"\x00" * (settings.max_upload_size_bytes + 1))

    with pytest.raises(UploadValidationError) as excinfo:
        service.save_upload("clip.mp4", "video/mp4", oversized)

    assert excinfo.value.code == "file_too_large"
    assert excinfo.value.status_code == 413
    # The partial file must be removed — nothing lingers on disk.
    assert list(settings.upload_dir_absolute.glob("*")) == []


def test_safe_filename_handling(client, upload_dir: Path) -> None:
    """Uploaded names with traversal / separators are normalised and never used as paths."""
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("..%2f..%2f..%2fetc%2fpasswd.mp4", b"\x00" * 64, "video/mp4")},
    )
    # Server must accept the *extension*, not honour the path.
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["original_name"] == "..%2f..%2f..%2fetc%2fpasswd.mp4"

    # Every stored file lives flat inside the upload dir; no subdirectories are created.
    stored_files = [p for p in upload_dir.iterdir() if p.is_file()]
    assert all(p.parent == upload_dir.resolve() for p in stored_files)


def test_safe_filename_forward_slashes(client, upload_dir: Path) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("dir/sub/../../evil.mp4", b"\x00" * 64, "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["original_name"] == "evil.mp4"
    stored_files = list(upload_dir.iterdir())
    assert all(p.parent == upload_dir.resolve() for p in stored_files)


def test_stored_name_is_server_generated(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("clip.mp4", b"\x00" * 64, "video/mp4")},
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    # UUID-hex job ids: 32 hex chars, no separators, never the client's filename.
    assert len(job_id) == 32
    assert all(c in "0123456789abcdef" for c in job_id)


def test_job_lookup_roundtrip(client) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("song.mov", b"\x00" * 128, "video/quicktime")},
    ).json()

    resp = client.get(f"/api/jobs/{upload['job_id']}")
    assert resp.status_code == 200
    job = resp.json()
    assert job["job_id"] == upload["job_id"]
    assert job["status"] == "received"
    assert job["original_name"] == "song.mov"
    assert job["extension"] == "mov"  # matches UploadResponse (no leading dot)
    assert job["size_bytes"] == 128
    # No fabricated analysis payload.
    assert job["analysis"] is None
    assert job["error"] is None


def test_job_lookup_unknown(client) -> None:
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "job_not_found"


def test_job_lookup_rejects_traversal_ids(client, upload_dir: Path) -> None:
    """Malformed ids resolve to 404 — never to a filesystem path."""
    for raw in ("..", "....", "%2e%2e%2f%2e%2e%2fetc%2fpasswd"):
        resp = client.get(f"/api/jobs/{raw}")
        assert resp.status_code == 404, f"{raw} -> {resp.status_code}"
        # The error body must never leak the filesystem layout.
        body = resp.text
        assert "uploads" not in body
        assert "C:" not in body


def test_upload_response_does_not_expose_paths(client) -> None:
    resp = client.post(
        "/api/videos/upload",
        files={"file": ("clip.mp4", b"\x00" * 64, "video/mp4")},
    )
    body = resp.json()
    assert "upload_dir" not in body
    assert "stored_name" not in body
    assert "\\" not in body["original_name"]