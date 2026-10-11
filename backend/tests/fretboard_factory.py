"""Synthetic test frame generator for fretboard localization evaluation.

Generates controlled test images with ground-truth fretboard geometry,
as well as negative cases (blank, noise, non-guitar linear objects, etc.)
to verify detector behavior without external dataset dependencies.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import cv2
import numpy as np


class SyntheticFretboardGroundTruth(NamedTuple):
    image: np.ndarray
    polygon: list[tuple[float, float]]
    angle_deg: float
    length: float
    width: float
    fret_count: int


def create_synthetic_fretboard(
    canvas_size: tuple[int, int] = (640, 480),
    center: tuple[int, int] | None = None,
    length: float = 380.0,
    width: float = 46.0,
    angle_deg: float = 0.0,
    num_frets: int = 12,
    wood_color: tuple[int, int, int] = (45, 55, 80),  # Rosewood (BGR)
    noise_sigma: float = 0.0,
    blur_ksize: int = 0,
) -> SyntheticFretboardGroundTruth:
    """Render a synthetic guitar fretboard on a realistic background.

    Returns the generated image and ground-truth bounding polygon corners.
    """
    img_w, img_h = canvas_size
    cx = center[0] if center else img_w // 2
    cy = center[1] if center else img_h // 2

    # Background: gentle gradient
    y_coords, x_coords = np.mgrid[0:img_h, 0:img_w]
    bg = 180 - (x_coords * 40 // img_w) - (y_coords * 30 // img_h)
    image = np.stack([bg, bg + 5, bg + 10], axis=-1).astype(np.uint8)

    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def to_canvas(lx: float, ly: float) -> tuple[float, float]:
        gx = cx + (lx * cos_a - ly * sin_a)
        gy = cy + (lx * sin_a + ly * cos_a)
        return (float(gx), float(gy))

    # 4 local corners
    half_l = length / 2.0
    half_w = width / 2.0

    c0 = to_canvas(-half_l, -half_w)
    c1 = to_canvas(half_l, -half_w)
    c2 = to_canvas(half_l, half_w)
    c3 = to_canvas(-half_l, half_w)
    gt_polygon = [c0, c1, c2, c3]

    # Fill fretboard wood body
    poly_arr = np.array(gt_polygon, dtype=np.int32)
    cv2.fillPoly(image, [poly_arr], wood_color)

    # Neck binding edges (darker outline)
    cv2.polylines(image, [poly_arr], isClosed=True, color=(20, 25, 35), thickness=2)

    # Frets (transverse wires)
    # Using musical fret spacing formula: d_n = scale * (1 - 2^(-n/12))
    # Scaled to fit visible length
    fret_positions = []
    scale_len = length * 1.8
    for n in range(1, num_frets + 1):
        fret_x = -half_l + (scale_len * (1.0 - (2.0 ** (-n / 12.0))))
        if fret_x < half_l - 10:
            fret_positions.append(fret_x)

    for fx in fret_positions:
        # Fret slot edge / shadow
        p_top_s = to_canvas(fx - 0.5, -half_w + 1)
        p_bot_s = to_canvas(fx - 0.5, half_w - 1)
        pt1_s = (int(round(p_top_s[0])), int(round(p_top_s[1])))
        pt2_s = (int(round(p_bot_s[0])), int(round(p_bot_s[1])))
        cv2.line(image, pt1_s, pt2_s, (35, 40, 45), 1, cv2.LINE_AA)

        # Nickel silver fret wire crown
        p_top = to_canvas(fx + 0.5, -half_w + 1)
        p_bot = to_canvas(fx + 0.5, half_w - 1)
        pt1 = (int(round(p_top[0])), int(round(p_top[1])))
        pt2 = (int(round(p_bot[0])), int(round(p_bot[1])))
        cv2.line(image, pt1, pt2, (235, 240, 250), 1, cv2.LINE_AA)

    # 6 Longitudinal strings
    for s_idx in range(6):
        sy = -half_w + (s_idx + 0.5) * (width / 6.0)
        s_start = to_canvas(-half_l, sy)
        s_end = to_canvas(half_l, sy)
        pt1 = (int(round(s_start[0])), int(round(s_start[1])))
        pt2 = (int(round(s_end[0])), int(round(s_end[1])))
        str_color = (215, 220, 230) if s_idx < 3 else (170, 185, 205)
        cv2.line(image, pt1, pt2, str_color, 1, cv2.LINE_AA)

    # Optional blur
    if blur_ksize > 1:
        k = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
        image = cv2.GaussianBlur(image, (k, k), 0)

    # Optional noise
    if noise_sigma > 0:
        noise = np.random.normal(0, noise_sigma, image.shape).astype(np.float32)
        noisy = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        image = noisy

    return SyntheticFretboardGroundTruth(
        image=image,
        polygon=gt_polygon,
        angle_deg=angle_deg,
        length=length,
        width=width,
        fret_count=len(fret_positions),
    )


def create_negative_table_edge(canvas_size: tuple[int, int] = (640, 480)) -> np.ndarray:
    """Create a negative test image: parallel table edge lines with NO frets."""
    w, h = canvas_size
    img = np.full((h, w, 3), 160, dtype=np.uint8)
    # Desk strip (parallel lines, uniform color, zero transverse fret wires)
    cv2.rectangle(img, (80, 180), (560, 240), (70, 80, 110), -1)
    cv2.line(img, (80, 180), (560, 180), (20, 20, 30), 2)
    cv2.line(img, (80, 240), (560, 240), (20, 20, 30), 2)
    return img


def create_negative_blank(
    canvas_size: tuple[int, int] = (640, 480), color: int = 128
) -> np.ndarray:
    """Create a solid uniform image."""
    w, h = canvas_size
    return np.full((h, w, 3), color, dtype=np.uint8)


def create_negative_noise(canvas_size: tuple[int, int] = (640, 480)) -> np.ndarray:
    """Create random white noise."""
    w, h = canvas_size
    return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)


def create_negative_square_box(canvas_size: tuple[int, int] = (640, 480)) -> np.ndarray:
    """Create an object with low aspect ratio (square 1:1)."""
    w, h = canvas_size
    img = np.full((h, w, 3), 200, dtype=np.uint8)
    cv2.rectangle(img, (200, 120), (440, 360), (40, 40, 40), -1)
    return img


def compute_polygon_iou(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
    canvas_shape: tuple[int, int] = (480, 640),
) -> float:
    """Calculate Intersection over Union (IoU) of two polygons via raster masks."""
    h, w = canvas_shape
    mask1 = np.zeros((h, w), dtype=np.uint8)
    mask2 = np.zeros((h, w), dtype=np.uint8)

    p1_int = np.array(poly1, dtype=np.int32)
    p2_int = np.array(poly2, dtype=np.int32)

    cv2.fillPoly(mask1, [p1_int], 1)
    cv2.fillPoly(mask2, [p2_int], 1)

    intersection = np.logical_and(mask1, mask2).sum()
    union = np.logical_or(mask1, mask2).sum()

    if union == 0:
        return 0.0
    return float(intersection) / float(union)
