"""Tests for classical fretboard localization (Milestone 1).

Covers:
1. Standalone classical detector on synthetic ground-truth fretboards across angles,
   lighting, and noise.
2. Rejection of negative cases (blank, noise, table edges without frets, square boxes).
3. Rejection and diagnostic reporting on invalid inputs.
4. Debug visualization generation.
5. FastAPI frame fretboard localization and debug overlay endpoints.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.cv import (
    FretboardDetectionResult,
    FretboardDetector,
    FretboardDetectorConfig,
    detect_fretboard,
    visualize_detection,
)
from tests import video_factory
from tests.fretboard_factory import (
    compute_polygon_iou,
    create_negative_blank,
    create_negative_noise,
    create_negative_square_box,
    create_negative_table_edge,
    create_synthetic_fretboard,
)


# --- Standalone Detector: Positive Cases ------------------------------------


@pytest.mark.parametrize("angle_deg", [0.0, 15.0, -25.0, 35.0])
def test_detects_synthetic_fretboard_various_orientations(angle_deg: float) -> None:
    gt = create_synthetic_fretboard(angle_deg=angle_deg, noise_sigma=3.0)
    res = detect_fretboard(gt.image)

    assert res.detected is True
    assert res.confidence >= 0.50
    assert res.polygon is not None
    assert len(res.polygon) == 4
    assert res.geometry is not None
    assert res.failure_reason is None

    # Check orientation angle within tolerance (allowing 180° wrap)
    detected_ang = res.geometry.orientation_deg
    diff = abs(detected_ang - angle_deg)
    if diff > 90.0:
        diff = abs(180.0 - diff)
    assert diff <= 7.0

    # Check frets detected
    assert res.geometry.fret_count_estimate >= 4

    # Check spatial overlap against ground truth polygon
    iou = compute_polygon_iou(gt.polygon, res.polygon)
    assert iou >= 0.65


def test_detects_synthetic_fretboard_with_maple_neck() -> None:
    # Lighter wood (Maple neck)
    gt = create_synthetic_fretboard(
        angle_deg=10.0,
        wood_color=(170, 205, 230),  # Light BGR
        noise_sigma=2.0,
    )
    res = detect_fretboard(gt.image)
    assert res.detected is True
    assert res.confidence >= 0.50
    assert res.geometry is not None
    assert res.geometry.fret_count_estimate >= 3


def test_detects_synthetic_fretboard_with_motion_blur() -> None:
    gt = create_synthetic_fretboard(angle_deg=0.0, blur_ksize=5, noise_sigma=2.0)
    res = detect_fretboard(gt.image)
    assert res.detected is True
    assert res.confidence >= 0.45


# --- Standalone Detector: Negative Cases (Must Reject) -----------------------


def test_rejects_table_edge_without_transverse_frets() -> None:
    """A linear object with parallel boundaries but no fret wires must not be accepted."""
    table = create_negative_table_edge()
    res = detect_fretboard(table)

    assert res.detected is False
    assert res.polygon is None
    assert res.failure_reason in ("insufficient_transverse_frets", "no_fretboard_candidate_found")


def test_rejects_blank_solid_image() -> None:
    blank = create_negative_blank()
    res = detect_fretboard(blank)

    assert res.detected is False
    assert res.polygon is None
    assert res.failure_reason == "insufficient_edge_detail"
    assert res.confidence == 0.0


def test_rejects_random_noise_image() -> None:
    noise = create_negative_noise()
    res = detect_fretboard(noise)

    assert res.detected is False
    assert res.polygon is None
    assert res.failure_reason in ("excessive_image_noise", "no_fretboard_candidate_found")


def test_rejects_square_box() -> None:
    """Objects with aspect ratio ~1:1 must be rejected by geometry filters."""
    box = create_negative_square_box()
    res = detect_fretboard(box)

    assert res.detected is False
    assert res.polygon is None


# --- Standalone Detector: Invalid Inputs -------------------------------------


def test_rejects_none_and_non_array_inputs() -> None:
    res = detect_fretboard(None)  # type: ignore[arg-type]
    assert res.detected is False
    assert res.failure_reason == "invalid_image_type"

    res_str = detect_fretboard("not-an-image")  # type: ignore[arg-type]
    assert res_str.detected is False
    assert res_str.failure_reason == "invalid_image_type"


def test_rejects_empty_and_undersized_images() -> None:
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    res_empty = detect_fretboard(empty)
    assert res_empty.detected is False
    assert res_empty.failure_reason == "empty_image"

    tiny = np.zeros((12, 12, 3), dtype=np.uint8)
    res_tiny = detect_fretboard(tiny)
    assert res_tiny.detected is False
    assert res_tiny.failure_reason == "image_dimensions_too_small"


# --- Debug Visualization -----------------------------------------------------


def test_visualize_detection_positive() -> None:
    gt = create_synthetic_fretboard(angle_deg=10.0)
    res = detect_fretboard(gt.image)
    vis = visualize_detection(gt.image, res)

    assert isinstance(vis, np.ndarray)
    assert vis.shape == gt.image.shape
    assert vis.dtype == np.uint8


def test_visualize_detection_negative() -> None:
    table = create_negative_table_edge()
    res = detect_fretboard(table)
    vis = visualize_detection(table, res)

    assert isinstance(vis, np.ndarray)
    assert vis.shape == table.shape
    assert vis.dtype == np.uint8


# --- API Endpoint Integration ------------------------------------------------


def _upload_and_process_clip(client, frames: int = 15, fps: float = 10.0) -> str:
    clip_bytes = video_factory.video_bytes(frames=frames, fps=fps)
    upload_resp = client.post(
        "/api/videos/upload",
        files={"file": ("test_clip.mp4", clip_bytes, "video/mp4")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    job_id = upload_resp.json()["job_id"]

    proc_resp = client.post(f"/api/jobs/{job_id}/process")
    assert proc_resp.status_code == 200, proc_resp.text
    return job_id


def test_api_fretboard_detection_on_extracted_frame(client) -> None:
    job_id = _upload_and_process_clip(client)

    # Call localization endpoint on frame 0
    resp = client.get(f"/api/jobs/{job_id}/frames/0/fretboard")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["job_id"] == job_id
    assert data["frame_index"] == 0
    assert "detected" in data
    assert "confidence" in data
    assert 0.0 <= data["confidence"] <= 1.0
    assert "failure_reason" in data
    assert "diagnostics" in data


def test_api_fretboard_debug_image(client) -> None:
    job_id = _upload_and_process_clip(client)

    resp = client.get(f"/api/jobs/{job_id}/frames/0/fretboard-debug")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 100


def test_api_fretboard_404_for_unknown_job(client) -> None:
    resp = client.get("/api/jobs/0123456789abcdef0123456789abcdef/frames/0/fretboard")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "job_not_found"


def test_api_fretboard_404_for_invalid_frame_index(client) -> None:
    job_id = _upload_and_process_clip(client)
    resp = client.get(f"/api/jobs/{job_id}/frames/999/fretboard")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "frame_not_found"
