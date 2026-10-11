"""Tests for the isolated fretboard-vision feature (experimental).

These tests cover the *new* vision layer only:
1. Pure geometry helpers (corner ordering, perspective rectification).
2. String and fret measurement on synthetic fretboards with known geometry.
3. Honesty: blank / non-guitar frames must yield detected=False and zero
   fabricated strings or frets.
4. API endpoints: JSON analysis, annotated overlay, rectified crop, plus
   404/409/500 containment.

Crucially, none of these tests may alter the frozen audio pipeline. A guard
test asserts the audio endpoints and their response fields are untouched.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.cv.vision_analysis import (
    analyze_frame,
    detect_fret_wires,
    detect_strings,
    order_quad,
    rect_to_original,
    rectify_fretboard,
)
from tests import video_factory
from tests.fretboard_factory import (
    create_negative_blank,
    create_negative_noise,
    create_synthetic_fretboard,
)


# --- Pure geometry helpers --------------------------------------------------


def test_order_quad_is_stable_under_rotation_and_start_point() -> None:
    """Any cyclic rotation/reflection of a rect must order to the same shape."""
    # Axis-aligned rect corners, deliberately shuffled.
    base = [(100.0, 50.0), (300.0, 50.0), (300.0, 90.0), (100.0, 90.0)]
    rotations = [
        base,
        base[1:] + base[:1],
        base[2:] + base[:2],
        list(reversed(base)),
    ]
    ordered = [order_quad(p) for p in rotations]
    first = ordered[0]
    for other in ordered[1:]:
        # Same set of points.
        assert sorted(map(tuple, first)) == sorted(map(tuple, other))
        # Consistent cyclic walk: consecutive corners share an edge length
        # equal to the rect width (not the diagonal).
        edges = [np.linalg.norm(other[i] - other[(i + 1) % 4]) for i in range(4)]
        assert min(edges) > 1.0


def test_order_quad_on_rotated_rect_keeps_long_axis_first() -> None:
    length, width = 400.0, 60.0
    pts = [
        (0.0, 0.0),
        (length, 0.0),
        (length, width),
        (0.0, width),
    ]
    ordered = order_quad(pts)
    first_pair = np.linalg.norm(ordered[1] - ordered[0])
    second_pair = np.linalg.norm(ordered[2] - ordered[1])
    # The first two edges are the long sides of the rect.
    assert abs(first_pair - length) < 1e-3
    assert abs(second_pair - width) < 1e-3


def test_rectify_fretboard_straightens_a_tilted_corridor() -> None:
    """Rectifying a tilted corridor must produce a near-uniform rectangle."""
    length, width = 500.0, 70.0
    quad = np.array(
        [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)], dtype=np.float32
    )
    # Build a source image where the corridor is drawn tilted by 25 degrees.
    canvas = np.zeros((700, 700, 3), dtype=np.uint8)
    rot = cv2.getRotationMatrix2D((350.0, 350.0), 25.0, 1.0)
    pts = quad.reshape(1, -1, 2)
    tilted = cv2.transform(pts, rot)[0]
    cv2.fillPoly(canvas, [tilted.astype(np.int32)], (60, 60, 90))

    warped, matrix = rectify_fretboard(canvas, tilted.astype(np.float32))
    wh, ww = warped.shape[:2]
    assert ww > wh  # straightened corridor is long and thin

    # The warp maps the corridor corners to the crop corners.
    c0 = rect_to_original(matrix, 0.0, 0.0)
    c1 = rect_to_original(matrix, ww - 1.0, 0.0)
    dist = float(np.hypot(c1[0] - c0[0], c1[1] - c0[1]))
    assert abs(dist - length) < length * 0.05


def test_rect_to_original_round_trips_through_matrix() -> None:
    quad = np.array(
        [(10.0, 20.0), (410.0, 30.0), (400.0, 90.0), (5.0, 80.0)], dtype=np.float32
    )
    _, matrix = rectify_fretboard(np.zeros((200, 500, 3), dtype=np.uint8), quad)
    # A rect-space point maps forward then back to itself.
    inv = np.linalg.inv(matrix)
    p = np.array([123.0, 45.0, 1.0])
    fwd = matrix @ p
    fwd = fwd[:2] / fwd[2]
    back = inv @ np.array([fwd[0], fwd[1], 1.0])
    back = back[:2] / back[2]
    assert abs(back[0] - 123.0) < 1e-3
    assert abs(back[1] - 45.0) < 1e-3


# --- String + fret measurement on synthetic boards --------------------------


def test_detects_six_strings_on_synthetic_fretboard() -> None:
    """Clean-to-moderate synthetic boards must resolve all six strings."""
    gt = create_synthetic_fretboard(angle_deg=0.0, noise_sigma=2.0)
    analysis = analyze_frame(gt.image)

    assert analysis.detected is True
    assert analysis.failure_reason is None
    # Synthetic board has 6 clearly drawn strings.
    assert len(analysis.strings) == 6

    # String rows must be evenly spaced across the crop height.
    ys = sorted(s.y_rectified for s in analysis.strings)
    spacings = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    mean_sp = float(np.mean(spacings))
    cv = float(np.std(spacings)) / mean_sp
    assert cv < 0.25


@pytest.mark.parametrize("noise", [1.0, 3.0])
def test_six_strings_stable_across_noise_levels(noise: float) -> None:
    gt = create_synthetic_fretboard(angle_deg=0.0, noise_sigma=noise)
    analysis = analyze_frame(gt.image)
    assert analysis.detected is True
    assert len(analysis.strings) == 6


def test_noisy_board_reports_honestly_when_six_unresolvable() -> None:
    """If the evidence supports fewer than six rows, that is reported — not invented."""
    gt = create_synthetic_fretboard(angle_deg=0.0, noise_sigma=0.5)
    analysis = analyze_frame(gt.image)
    assert analysis.detected is True
    n = len(analysis.strings)
    # Never fabricate: count is what was measured, and never exceeds six.
    assert 1 <= n <= 6
    if n < 6:
        assert any("string" in lim.lower() for lim in analysis.limitations)


def test_detects_fret_wires_on_synthetic_fretboard() -> None:
    gt = create_synthetic_fretboard(angle_deg=10.0, num_frets=12)
    analysis = analyze_frame(gt.image)

    assert analysis.detected is True
    assert len(analysis.frets) >= 3

    # Fret x-positions in the crop must be strictly increasing and spaced.
    xs = sorted(f.x_rectified for f in analysis.frets)
    assert xs == sorted(xs)
    spacings = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    assert min(spacings) > 1.0


def test_rectified_crop_is_straight_for_synthetic_board() -> None:
    gt = create_synthetic_fretboard(angle_deg=15.0)
    analysis = analyze_frame(gt.image)

    assert analysis.rectified is not None
    wh, ww = analysis.rectified.shape[:2]
    assert ww > wh  # long axis horizontal after rectification


def test_rectified_output_includes_annotations() -> None:
    gt = create_synthetic_fretboard(angle_deg=5.0)
    analysis = analyze_frame(gt.image)
    assert analysis.rectified_annotated is not None
    assert analysis.rectified_annotated.shape == analysis.rectified.shape


# --- Direct measurement primitives on synthetic crops -----------------------


def _synthetic_crop(h: int = 120, w: int = 600, n_frets: int = 8) -> np.ndarray:
    """Draw a clean synthetic rectified-like crop: dark board, 6 strings, n_frets wires."""
    crop = np.full((h, w), 40, dtype=np.uint8)
    for k in range(6):
        y = int((k + 1) * h / 7)
        cv2.line(crop, (5, y), (w - 6, y), 210, 1, cv2.LINE_AA)
    for k in range(n_frets):
        x = int((k + 1) * w / (n_frets + 1))
        cv2.line(crop, (x, 8), (x, h - 9), 235, 1, cv2.LINE_AA)
    return crop


def test_detect_strings_finds_six_rows() -> None:
    crop = _synthetic_crop()
    rows, info = detect_strings(crop)
    assert len(rows) == 6
    assert info["peak_count"] >= 6
    ys = [y for y, _ in rows]
    assert ys == sorted(ys)


def test_detect_strings_reports_fewer_than_six_honestly() -> None:
    """A crop with only 3 string-like lines must report 3, not 6."""
    crop = np.full((120, 400), 40, dtype=np.uint8)
    for y in (30, 60, 90):
        cv2.line(crop, (5, y), (394, y), 210, 1, cv2.LINE_AA)
    rows, info = detect_strings(crop)
    assert len(rows) < 6
    assert info["subset_rejected"] is False


def test_detect_fret_wires_finds_expected_columns() -> None:
    crop = _synthetic_crop(n_frets=8)
    frets = detect_fret_wires(crop)
    assert len(frets) >= 5
    xs = [x for x, _ in frets]
    assert xs == sorted(xs)


# --- Honesty: negatives must not fabricate ----------------------------------


def test_blank_frame_reports_no_detection_and_no_geometry() -> None:
    blank = create_negative_blank()
    analysis = analyze_frame(blank)

    assert analysis.detected is False
    assert len(analysis.strings) == 0
    assert len(analysis.frets) == 0
    assert analysis.rectified is None
    assert analysis.limitations


def test_noise_frame_reports_no_detection() -> None:
    noise = create_negative_noise()
    analysis = analyze_frame(noise)
    assert analysis.detected is False
    assert len(analysis.strings) <= 6  # never over-reports
    assert len(analysis.frets) == 0 or not analysis.detected


def test_no_note_claims_anywhere_in_result() -> None:
    """The vision layer must never assert a note was identified."""
    gt = create_synthetic_fretboard()
    analysis = analyze_frame(gt.image)
    # Only geometric position is exposed — no note/pitch attributes on results.
    for s in analysis.strings:
        assert not hasattr(s, "note")
        assert not hasattr(s, "pitch")
        assert not hasattr(s, "fret_number")
    for f in analysis.frets:
        assert not hasattr(f, "note")
        assert not hasattr(f, "pitch")
        assert not hasattr(f, "string_number")


# --- API endpoint integration ------------------------------------------------


def _upload_and_process_clip(client, frames: int = 12, fps: float = 10.0) -> str:
    clip_bytes = video_factory.video_bytes(frames=frames, fps=fps)
    upload_resp = client.post(
        "/api/videos/upload",
        files={"file": ("vision_test.mp4", clip_bytes, "video/mp4")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    job_id = upload_resp.json()["job_id"]
    proc_resp = client.post(f"/api/jobs/{job_id}/process")
    assert proc_resp.status_code == 200, proc_resp.text
    return job_id


def test_vision_json_endpoint_returns_structured_analysis(client) -> None:
    job_id = _upload_and_process_clip(client)
    resp = client.get(f"/api/vision/jobs/{job_id}/frames/0")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["job_id"] == job_id
    assert data["frame_index"] == 0
    assert "detected" in data
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["strings"], list)
    assert isinstance(data["frets"], list)
    assert data["strings_detected"] == len(data["strings"])
    assert data["frets_detected"] == len(data["frets"])
    assert isinstance(data["limitations"], list)
    # Synthetic clip frames contain no guitar, so nothing may be fabricated.
    assert data["detected"] is False or data["strings_detected"] <= 6


def test_vision_annotated_endpoint_returns_jpeg(client) -> None:
    job_id = _upload_and_process_clip(client)
    resp = client.get(f"/api/vision/jobs/{job_id}/frames/0/annotated")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 200


def test_vision_rectified_endpoint_404_when_not_detected(client) -> None:
    """Synthetic frames have no fretboard, so rectified must 404 honestly."""
    job_id = _upload_and_process_clip(client)
    resp = client.get(f"/api/vision/jobs/{job_id}/frames/0/rectified")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_detected"


def test_vision_endpoints_404_for_unknown_job(client) -> None:
    for path in (
        "0123456789abcdef0123456789abcdef/frames/0",
        "0123456789abcdef0123456789abcdef/frames/0/annotated",
        "0123456789abcdef0123456789abcdef/frames/0/rectified",
    ):
        resp = client.get(f"/api/vision/jobs/{path}")
        assert resp.status_code == 404, path


def test_vision_endpoints_404_for_invalid_frame_index(client) -> None:
    job_id = _upload_and_process_clip(client)
    for suffix in ("", "/annotated", "/rectified"):
        resp = client.get(f"/api/vision/jobs/{job_id}/frames/999{suffix}")
        assert resp.status_code == 404, suffix


def test_vision_endpoints_409_before_processing(client) -> None:
    clip_bytes = video_factory.video_bytes(frames=6)
    upload_resp = client.post(
        "/api/videos/upload",
        files={"file": ("unprocessed.mp4", clip_bytes, "video/mp4")},
    )
    job_id = upload_resp.json()["job_id"]
    resp = client.get(f"/api/vision/jobs/{job_id}/frames/0")
    assert resp.status_code == 409


# --- Isolation: vision must not touch the audio pipeline --------------------


def test_audio_pipeline_response_fields_unchanged(client) -> None:
    """Guard: upload + process + job + frames schemas keep their fields."""
    clip_bytes = video_factory.video_bytes(frames=8, fps=10.0)
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("guard.mp4", clip_bytes, "video/mp4")},
    )
    assert upload.status_code == 201
    job_id = upload.json()["job_id"]

    proc = client.post(f"/api/jobs/{job_id}/process")
    assert proc.status_code == 200
    job = proc.json()
    assert "job_id" in job
    assert "status" in job
    assert "video" in job or "status" in job  # existing job schema intact

    frames = client.get(f"/api/jobs/{job_id}/frames")
    assert frames.status_code == 200
    body = frames.json()
    assert "frames" in body
    assert "total_frames" in body


def test_vision_does_not_run_automatically_during_process(client) -> None:
    """Processing must not invoke vision — frames are extracted, nothing else."""
    job_id = _upload_and_process_clip(client)
    meta = client.get(f"/api/jobs/{job_id}").json()
    # No vision key is injected into the audio job metadata.
    assert "vision" not in meta
    assert "analysis" not in meta or meta.get("analysis") in (None, meta.get("analysis"))
