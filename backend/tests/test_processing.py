"""Tests for real video decoding and frame extraction (Milestone 2).

Every test uses a genuine, if tiny, ``mp4v`` video written by OpenCV so the
extraction path (decode → sample → encode JPEG → atomic commit) is exercised
end-to-end. Nothing is mocked. Tests are skipped wholesale only if the local
OpenCV build cannot write/read a scratch video.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.processing import ProcessingError, validate_video_metadata
from app.services.uploads import UploadService

from tests import video_factory


@pytest.fixture(scope="module", autouse=True)
def _require_video_support(tmp_path_factory: pytest.TempPathFactory) -> None:
    probe_dir = tmp_path_factory.mktemp("probe")
    try:
        probe = video_factory.write_video(probe_dir / "probe.mp4", frames=3, fps=5.0)
        capture = cv2.VideoCapture(str(probe))
        try:
            ok = capture.isOpened() and capture.get(cv2.CAP_PROP_FRAME_COUNT) >= 1
        finally:
            capture.release()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"OpenCV cannot write/read mp4v here: {exc}")
    if not ok:  # pragma: no cover - environment dependent
        pytest.skip("OpenCV could not read back a generated mp4v video")


def _settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        environment="test",
        upload_dir=tmp_path / "uploads",
        processed_dir=tmp_path / "processed",
        max_upload_size_mb=5,
    )
    base.update(overrides)
    return Settings(**base)


def _upload(client: TestClient, data: bytes, name: str = "clip.mp4"):
    return client.post(
        "/api/videos/upload", files={"file": (name, data, "video/mp4")}
    )


def _process(client: TestClient, job_id: str):
    return client.post(f"/api/jobs/{job_id}/process")


def _detail(resp) -> dict:
    return resp.json()["detail"]


# --- happy path ---------------------------------------------------------
def test_process_extracts_one_frame_per_second(client, processed_dir) -> None:
    data = video_factory.video_bytes(frames=30, fps=10.0)
    job_id = _upload(client, data).json()["job_id"]

    resp = _process(client, job_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["error_code"] is None

    video = body["video"]
    assert video["frame_count"] == 30
    assert video["fps"] == pytest.approx(10.0, abs=0.5)
    assert video["width"] == 64
    assert video["height"] == 48
    assert video["duration_seconds"] == pytest.approx(3.0, abs=0.5)

    # 3-second clip sampled at 1 fps → 3 frames, committed to disk.
    assert (processed_dir / job_id / "metadata.json").is_file()
    frames = client.get(f"/api/jobs/{job_id}/frames?limit=100").json()
    assert frames["total_frames"] == 3
    assert frames["count"] == 3
    assert frames["truncated"] is False
    assert frames["sample_interval_seconds"] == pytest.approx(1.0)
    timestamps = [f["timestamp_seconds"] for f in frames["frames"]]
    assert timestamps == pytest.approx([0.0, 1.0, 2.0], abs=0.2)
    assert [f["index"] for f in frames["frames"]] == [0, 1, 2]
    assert frames["frames"][0]["url"] == f"/api/jobs/{job_id}/frames/0"


def test_process_is_idempotent_when_completed(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]

    first = _process(client, job_id)
    assert first.status_code == 200
    second = _process(client, job_id)
    assert second.status_code == 200
    assert second.json()["status"] == "completed"
    assert second.json()["video"] == first.json()["video"]


def test_list_frames_reports_truncation(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=30, fps=10.0)).json()["job_id"]
    _process(client, job_id)

    limited = client.get(f"/api/jobs/{job_id}/frames?limit=2").json()
    assert limited["total_frames"] == 3
    assert limited["count"] == 2
    assert limited["truncated"] is True
    assert [f["index"] for f in limited["frames"]] == [0, 1]


def test_frame_store_max_width_downscales(tmp_path) -> None:
    settings = _settings(tmp_path, frame_store_max_width=32)
    with TestClient(create_app(settings)) as client:
        job_id = _upload(
            client, video_factory.video_bytes(frames=10, fps=10.0, size=(64, 48))
        ).json()["job_id"]
        assert _process(client, job_id).status_code == 200
        frames = client.get(f"/api/jobs/{job_id}/frames?limit=100").json()
        assert frames["frames"][0]["width"] == 32
        assert frames["frames"][0]["height"] == 24


def test_frame_image_is_served_and_can_be_resized(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]
    _process(client, job_id)

    resp = client.get(f"/api/jobs/{job_id}/frames/0")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:2] == b"\xff\xd8"  # JPEG start-of-image

    resized = client.get(f"/api/jobs/{job_id}/frames/0?max_width=32")
    assert resized.status_code == 200
    image = cv2.imdecode(np.frombuffer(resized.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    assert image.shape[1] == 32


# --- access control / not-ready ----------------------------------------
def test_frames_not_ready_before_processing(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=5, fps=5.0)).json()["job_id"]
    resp = client.get(f"/api/jobs/{job_id}/frames")
    assert resp.status_code == 409
    assert _detail(resp)["code"] == "frames_not_ready"


def test_process_unknown_job_returns_404(client) -> None:
    resp = client.post("/api/jobs/not-a-real-job/process")
    assert resp.status_code == 404
    assert _detail(resp)["code"] == "job_not_found"


def test_process_rejects_traversal_job_id(client) -> None:
    resp = client.post("/api/jobs/..%2f..%2fetc%2fpasswd/process")
    # A slash-containing id cannot match a single path segment → 404 from routing.
    assert resp.status_code in {404, 422}


def test_process_conflict_when_already_processing(client, settings) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]
    UploadService(settings).update_job(job_id, status="processing")

    resp = _process(client, job_id)
    assert resp.status_code == 409
    assert _detail(resp)["code"] == "processing_in_progress"


def test_process_missing_video_returns_404(client, settings) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]
    video_path = UploadService(settings).resolve_video_path(job_id)
    assert video_path is not None
    video_path.unlink()

    resp = _process(client, job_id)
    assert resp.status_code == 404
    assert _detail(resp)["code"] == "video_missing"
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_code"] == "video_missing"


# --- failure handling ---------------------------------------------------
def test_corrupt_upload_fails_and_leaves_no_artifacts(
    client, processed_dir
) -> None:
    job_id = _upload(client, b"this is definitely not a video file").json()["job_id"]

    resp = _process(client, job_id)
    assert resp.status_code == 422
    assert _detail(resp)["code"] in {
        "unreadable_video",
        "invalid_metadata",
        "invalid_fps",
        "no_frames_extracted",
        "decode_failed",
    }

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_code"] == _detail(resp)["code"]

    # Nothing partial may survive a failure.
    assert not (processed_dir / job_id).exists()
    assert list(processed_dir.glob(".tmp-*")) == []


# --- resource limits ----------------------------------------------------
def _process_with_limits(tmp_path: Path, data: bytes, **overrides):
    settings = _settings(tmp_path, **overrides)
    with TestClient(create_app(settings)) as client:
        job_id = _upload(client, data).json()["job_id"]
        return _process(client, job_id)


def test_resolution_limit_rejected(tmp_path) -> None:
    resp = _process_with_limits(
        tmp_path,
        video_factory.video_bytes(frames=5, fps=5.0, size=(64, 48)),
        max_video_dimension=32,
    )
    assert resp.status_code == 422
    assert _detail(resp)["code"] == "resolution_exceeded"


def test_duration_limit_rejected(tmp_path) -> None:
    resp = _process_with_limits(
        tmp_path,
        video_factory.video_bytes(frames=30, fps=10.0),
        max_video_duration_seconds=1.0,
    )
    assert resp.status_code == 422
    assert _detail(resp)["code"] == "duration_exceeded"


def test_extracted_frames_limit_rejected(tmp_path) -> None:
    resp = _process_with_limits(
        tmp_path,
        video_factory.video_bytes(frames=30, fps=10.0),
        max_extracted_frames=2,
    )
    assert resp.status_code == 422
    assert _detail(resp)["code"] == "extracted_frames_exceeded"


def test_decoded_frames_limit_rejected(tmp_path) -> None:
    resp = _process_with_limits(
        tmp_path,
        video_factory.video_bytes(frames=30, fps=10.0),
        max_decoded_frames=5,
    )
    assert resp.status_code == 422
    assert _detail(resp)["code"] == "decoded_frames_exceeded"


# --- frame access validation --------------------------------------------
def test_frame_index_out_of_range(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]
    _process(client, job_id)
    resp = client.get(f"/api/jobs/{job_id}/frames/999")
    assert resp.status_code == 404
    assert _detail(resp)["code"] == "frame_not_found"


def test_frame_index_must_be_integer(client) -> None:
    job_id = _upload(client, video_factory.video_bytes(frames=10, fps=10.0)).json()["job_id"]
    _process(client, job_id)
    resp = client.get(f"/api/jobs/{job_id}/frames/not-a-number")
    assert resp.status_code == 422


def test_list_frames_before_upload_of_frames(client) -> None:
    resp = client.get("/api/jobs/deadbeef/frames")
    assert resp.status_code == 404
    assert _detail(resp)["code"] == "job_not_found"


# --- unit: metadata validation ------------------------------------------
@pytest.mark.parametrize(
    ("width", "height", "fps", "code"),
    [
        (0, 100, 30.0, "invalid_metadata"),
        (100, 0, 30.0, "invalid_metadata"),
        (100, 100, 0.0, "invalid_fps"),
        (100, 100, float("nan"), "invalid_fps"),
    ],
)
def test_validate_video_metadata_rejects(width, height, fps, code) -> None:
    with pytest.raises(ProcessingError) as exc:
        validate_video_metadata(width, height, fps)
    assert exc.value.code == code


def test_validate_video_metadata_accepts_valid() -> None:
    validate_video_metadata(1920, 1080, 29.97)  # must not raise
