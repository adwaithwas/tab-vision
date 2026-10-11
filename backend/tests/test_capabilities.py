"""Tests for GET /api/capabilities."""

from __future__ import annotations


def test_capabilities_shape(client) -> None:
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    body = resp.json()

    assert body["service"] == "GuitarTab AI"
    assert body["video_upload"]["supported"] is True
    assert body["video_upload"]["max_file_size_mb"] == 2
    assert ".mp4" in body["video_upload"]["allowed_extensions"]
    assert "video/mp4" in body["video_upload"]["allowed_content_types"]

    # Frame extraction is real and reported as implemented.
    fx = body["frame_extraction"]
    assert fx["implemented"] is True
    assert fx["sample_interval_seconds"] == 1.0
    assert ".mp4" in fx["supported_formats"]
    assert fx["max_video_duration_seconds"] > 0
    assert fx["max_extracted_frames"] > 0

    # Preprocessing (decode + frame extraction) is implemented; every real
    # CV stage (fretboard, hands, notes, tab) remains honestly "planned".
    assert body["cv_pipeline"]["implemented"] is True
    stages = body["cv_pipeline"]["stages"]
    assert len(stages) == 7
    by_key = {s["key"]: s for s in stages}
    assert by_key["preprocess"]["implemented"] is True
    assert by_key["preprocess"]["status"] == "implemented"
    for key, stage in by_key.items():
        if key == "preprocess":
            continue
        assert stage["implemented"] is False
        assert stage["status"] == "planned"
    keys = [s["key"] for s in stages]
    assert "fretboard_detection" in keys
    assert "tab_generation" in keys