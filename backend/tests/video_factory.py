"""Real (tiny) video generation helpers for processing tests.

These write genuine files with OpenCV's ``mp4v`` codec so the extraction code
exercises the same decode path as production input, rather than a mock.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np


def _draw(index: int, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = ((index * 17) % 256, (index * 31) % 256, (index * 47) % 256)
    cv2.putText(
        frame,
        str(index),
        (2, max(8, height - 4)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return frame


def write_video(
    path: Path,
    *,
    frames: int = 30,
    fps: float = 10.0,
    size: tuple[int, int] = (64, 48),
    fourcc: str = "mp4v",
) -> Path:
    """Write a deterministic ``frames``-long video and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*fourcc), fps, size
    )
    if not writer.isOpened():  # pragma: no cover - environment dependent
        raise RuntimeError(f"OpenCV could not open a VideoWriter for {path}")
    try:
        for index in range(frames):
            writer.write(_draw(index, size))
    finally:
        writer.release()
    return path


def video_bytes(**kwargs) -> bytes:
    """Return the bytes of a generated video (deleted from disk afterwards)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = write_video(Path(tmp) / "clip.mp4", **kwargs)
        return path.read_bytes()
