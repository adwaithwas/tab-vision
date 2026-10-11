"""Isolated fretboard vision analysis: rectification, strings, and fret wires.

This module is a *separate* layer built on top of the existing detectors. It
imports the hybrid detector read-only (``detect_fretboard_hybrid``) and never
modifies it. Nothing in the audio-to-tablature pipeline imports this module,
so vision failures, missing weights, or timeouts can never affect
transcription.

What it does
------------
1. Takes the detected fretboard quadrilateral and orders its corners so the
   rectified crop has a consistent orientation at any in-frame angle.
2. Rectifies the corridor into a straight crop with ``cv2.warpPerspective``.
3. Detects visible fret wires in the rectified crop (vertical Sobel column
   profile + vertical-continuity verification).
4. Detects string rows in the rectified crop (horizontal Sobel row profile) and
   selects the six-string pattern **only from measured peaks** when a
   regular six-line subset exists; otherwise it reports the measured peaks
   honestly with fewer than six strings and a limitation note.
5. Produces annotated images (original frame + rectified crop) drawn from the
   real measurements. No detection, string, fret, or note is ever fabricated.

Honesty contract
----------------
* ``detected=False`` unless the upstream detector produced a credible polygon.
* Strings/frets are empty lists when nothing measurable is found; counts
  reflect what was actually measured, never a hard-coded six.
* ``limitations`` is always populated with plain-language caveats.
* No note-level claims of any kind: this module only measures geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Callable

import cv2
import numpy as np

from app.cv.fretboard_detector import FretboardDetectionResult
from app.cv.hybrid_detector import detect_fretboard_hybrid

# --- Tunables (module-local by design: no shared config or mutable state) ----

#: Output width target for the rectified crop (pixels).
RECT_MIN_WIDTH = 320
RECT_MAX_WIDTH = 1400
RECT_MIN_HEIGHT = 60
RECT_MAX_HEIGHT = 500

#: Fret-wire detection in the rectified crop.
FRET_INTERIOR_ROW_MARGIN = 0.12  # fraction of height trimmed top/bottom
FRET_PEAK_THRESHOLD = 0.22  # relative to profile max
FRET_MIN_PEAK_DISTANCE = 0.025  # fraction of crop width
FRET_MIN_VERTICAL_FILL = 0.22  # fraction of interior rows needing edge pixels

#: String detection in the rectified crop.
STRING_INTERIOR_COL_MARGIN = 0.10  # fraction of width trimmed left/right
#: Small margin only: outer strings sit ~8% in from each corridor edge, so an
#: aggressive margin would clip them. The binding lines themselves rectify to
#: rows 0 and h-1, which this margin still excludes.
STRING_EDGE_MARGIN = 0.05  # fraction of height trimmed top/bottom (bindings)
STRING_PEAK_THRESHOLD = 0.30  # relative to profile max
STRING_MIN_SPACING = 0.035  # fraction of crop height (subset spacing check)
#: Peaks closer than this are the two Sobel lobes of one physical string line
#: (true string spacing is ~17% of the crop height, so 8% merges lobes only).
STRING_LOBE_MERGE_DISTANCE = 0.08  # fraction of crop height
STRING_MAX_SPACING_CV = 0.30  # max coeff. of variation for a 6-string fit
STRING_MAX_PEAKS = 12  # only the strongest N peaks are subset-searched

#: BGR colours for annotations.
_COLOR_POLY_FILL = (40, 210, 80)
_COLOR_POLY_LINE = (50, 240, 90)
_COLOR_STRING = (255, 210, 70)  # blue-ish
_COLOR_FRET = (70, 220, 255)  # yellow-ish
_COLOR_TEXT = (255, 255, 255)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class StringAnnotation:
    """One measured string row in the rectified crop."""

    #: 0 = topmost row of the rectified crop. Pitch identity (EADGBE) is NOT
    #: inferred visually — only geometric position.
    position: int
    y_rectified: float
    strength: float
    #: Endpoints of the string in original image coordinates.
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class FretAnnotation:
    """One measured fret wire in the rectified crop."""

    index: int
    x_rectified: float
    strength: float
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass
class VisionAnalysis:
    """Full geometry analysis of one frame."""

    detected: bool
    confidence: float
    detection_source: str | None = None
    polygon: list[tuple[float, float]] | None = None
    ordered_quad: np.ndarray | None = None
    geometry: dict[str, Any] | None = None
    failure_reason: str | None = None
    strings: list[StringAnnotation] = field(default_factory=list)
    frets: list[FretAnnotation] = field(default_factory=list)
    rectified_size: tuple[int, int] | None = None
    rectified: np.ndarray | None = None
    rectified_annotated: np.ndarray | None = None
    limitations: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def order_quad(polygon: list[tuple[float, float]] | np.ndarray) -> np.ndarray:
    """Order four quad corners consistently for perspective rectification.

    The detector returns corners in an arbitrary rotation/reflection of the
    cyclic order. Using the corridor's principal axis (PCA on the four
    corners) the corners are mapped onto the four (long, short) axis
    extremes so that ``[c0, c1, c2, c3]`` always walks the quad in a stable
    cyclic order with the long axis first — regardless of in-frame angle.

    Returns
    -------
    np.ndarray
        Shape ``(4, 2)``, float32, ordered ``[start-a, end-a, end-b, start-b]``.
    """
    pts = np.asarray(polygon, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] != 4:
        raise ValueError(f"order_quad expects exactly 4 points, got {pts.shape[0]}")

    centroid = pts.mean(axis=0)
    centered = pts - centroid
    # PCA: long axis = eigenvector of largest eigenvalue.
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    u = eigvecs[:, int(np.argmax(eigvals))]
    n = np.array([-u[1], u[0]])

    proj_u = centered @ u
    proj_n = centered @ n
    targets = [
        (proj_u.min(), proj_n.min()),
        (proj_u.max(), proj_n.min()),
        (proj_u.max(), proj_n.max()),
        (proj_u.min(), proj_n.max()),
    ]

    ordered: list[np.ndarray] = []
    used: set[int] = set()
    for tu, tn in targets:
        dists = np.hypot(proj_u - tu, proj_n - tn)
        for idx in np.argsort(dists):
            if int(idx) not in used:
                used.add(int(idx))
                ordered.append(pts[int(idx)])
                break
    return np.array(ordered, dtype=np.float32)


def rectify_fretboard(
    image: np.ndarray,
    quad: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Warp the ordered quadrilateral into a straight rectified crop.

    Parameters
    ----------
    image:
        Source BGR/gray frame.
    quad:
        Ordered ``[c0, c1, c2, c3]`` corners (see :func:`order_quad`).

    Returns
    -------
    (warped, matrix)
        ``warped`` is the rectified BGR crop; ``matrix`` is the 3x3
        perspective transform mapping original → rectified coordinates.
    """
    src = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    length = float(
        (np.linalg.norm(src[1] - src[0]) + np.linalg.norm(src[2] - src[3])) / 2.0
    )
    width = float(
        (np.linalg.norm(src[3] - src[0]) + np.linalg.norm(src[2] - src[1])) / 2.0
    )
    length = max(length, 1.0)
    width = max(width, 1.0)

    out_w = int(round(min(max(length, RECT_MIN_WIDTH), RECT_MAX_WIDTH)))
    scale = out_w / length
    out_h = int(round(min(max(width * scale, RECT_MIN_HEIGHT), RECT_MAX_HEIGHT)))

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, matrix, (out_w, out_h))
    return warped, matrix


def rect_to_original(
    matrix: np.ndarray, x: float, y: float
) -> tuple[float, float]:
    """Map a point from rectified coordinates back to original image space."""
    inv = np.linalg.inv(matrix)
    vec = np.array([x, y, 1.0], dtype=np.float64)
    mapped = inv @ vec
    w = mapped[2]
    if abs(w) < 1e-9:
        return (float("nan"), float("nan"))
    return (float(mapped[0] / w), float(mapped[1] / w))


#: Clamp for the quad tilt refinement (degrees). Beyond this the residual is
#: treated as untrustworthy and the polygon is left as-is, to avoid destroying
#: already-aligned corridors on a bad orientation reading.
TILT_REFINE_MAX_DEG = 25.0
#: Residuals below this are considered already straight (degrees).
TILT_REFINE_MIN_DEG = 1.0
#: Minimum in-mask edge pixels and peak sharpness before a residual is trusted.
TILT_REFINE_MIN_EDGE_PIXELS = 200
#: The histogram peak must exceed this multiple of the mean bin. A share-of-
#: total threshold does not work here: with 120 bins the mean share is <1%
#: even for a perfectly sharp string-direction peak.
TILT_REFINE_MIN_PEAK_RATIO = 2.5
#: Absolute floor: peak must still carry a non-trivial slice of the weight.
TILT_REFINE_MIN_PEAK_SHARE = 0.01
#: Boundary band excluded from the residual estimate (fraction of the crop's
#: smaller dimension), so the crop's own frame cannot dominate the histogram.
TILT_REFINE_MASK_ERODE = 0.06


def _dominant_string_angle(gray: np.ndarray, window_deg: float) -> float | None:
    """Measure the dominant near-horizontal edge angle inside a rectified crop.

    In a rectified crop the strings run horizontally (0°) and the fret wires
    run vertically (90°), so the strongest edge direction within ``window_deg``
    of horizontal is the string direction. Returns the signed angle in degrees
    (image coordinates, positive = content slopes down-to-the-right) or
    ``None`` when the evidence is too weak to trust.
    """
    if gray is None or not isinstance(gray, np.ndarray) or gray.size == 0:
        return None
    h, w = gray.shape[:2]
    if h < 8 or w < 8:
        return None

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)

    # Ignore a boundary band so the crop's own frame cannot dominate.
    erode = max(2, int(min(h, w) * TILT_REFINE_MASK_ERODE))
    mag[:erode, :] = 0.0
    mag[-erode:, :] = 0.0
    mag[:, :erode] = 0.0
    mag[:, -erode:] = 0.0
    if int(np.count_nonzero(mag > 1e-6)) < TILT_REFINE_MIN_EDGE_PIXELS:
        return None

    # Edge-line orientation = gradient orientation + 90°, folded to (-90, 90].
    angles = (np.degrees(np.arctan2(gy, gx)) + 90.0) % 180.0
    diff = (angles + 90.0) % 180.0 - 90.0
    near = np.abs(diff) <= window_deg
    if int(np.count_nonzero(near & (mag > 1e-6))) < TILT_REFINE_MIN_EDGE_PIXELS:
        return None

    edges = np.linspace(-window_deg, window_deg, 121)
    hist, _ = np.histogram(diff[near], bins=edges, weights=mag[near])
    total = float(hist.sum())
    if total <= 1e-6:
        return None
    smoothed = np.convolve(hist, [0.25, 0.5, 0.25], mode="same")
    peak_val = float(smoothed.max())
    mean_val = float(smoothed.mean())
    if mean_val <= 1e-9 or peak_val / mean_val < TILT_REFINE_MIN_PEAK_RATIO:
        return None
    if peak_val / total < TILT_REFINE_MIN_PEAK_SHARE:
        return None
    bin_width = float(edges[1] - edges[0])
    return float(edges[int(np.argmax(smoothed))]) + bin_width / 2.0


def rotate_quad(quad: np.ndarray, delta_deg: float) -> np.ndarray:
    """Rotate the four corners about their centroid by ``delta_deg``."""
    pts = np.asarray(quad, dtype=np.float64)
    centroid = pts.mean(axis=0)
    rad = math.radians(delta_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    offset = pts - centroid
    rotated = np.empty_like(offset)
    rotated[:, 0] = offset[:, 0] * cos_a - offset[:, 1] * sin_a
    rotated[:, 1] = offset[:, 0] * sin_a + offset[:, 1] * cos_a
    return (rotated + centroid).astype(np.float32)


def refine_quad_orientation(
    image: np.ndarray,
    quad: np.ndarray,
    max_iterations: int = 2,
) -> tuple[np.ndarray, float]:
    """Align the quad's long axis with the strings, measured in rectified space.

    Measuring the residual string angle *after* rectification is self-
    validating: when the crop is already straight the residual is near zero and
    nothing is rotated. This avoids the false positives that an estimate over
    the raw frame's interior suffers from (diagonal board edges, shadows, etc.).

    Each candidate rotation is applied only when it strictly reduces the
    measured residual.

    Returns the (possibly rotated) quad and the total applied rotation, degrees.
    """
    warped, _ = rectify_fretboard(image, quad)
    residual = _dominant_string_angle(_to_gray(warped), TILT_REFINE_MAX_DEG)
    total = 0.0
    for _ in range(max(0, int(max_iterations))):
        if residual is None or abs(residual) < TILT_REFINE_MIN_DEG:
            break
        if abs(residual) > TILT_REFINE_MAX_DEG:
            break
        candidate = rotate_quad(quad, residual)
        candidate_warped, _ = rectify_fretboard(image, candidate)
        candidate_residual = _dominant_string_angle(
            _to_gray(candidate_warped), TILT_REFINE_MAX_DEG
        )
        if candidate_residual is None or abs(candidate_residual) >= abs(residual):
            break
        quad = candidate
        total += float(residual)
        residual = candidate_residual
    return quad, total


# ---------------------------------------------------------------------------
# Detectors on the rectified crop
# ---------------------------------------------------------------------------


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _smooth(profile: np.ndarray) -> np.ndarray:
    kernel = np.array([0.15, 0.7, 0.15], dtype=np.float32)
    return np.convolve(profile, kernel, mode="same")


def _pick_peaks(
    profile: np.ndarray,
    *,
    threshold_rel: float,
    min_distance: int,
    limit: int | None = None,
) -> list[tuple[int, float]]:
    """Pick local maxima above a relative threshold with a minimum spacing.

    When two peaks fall closer than ``min_distance`` they are treated as the
    two Sobel lobes of one physical line (top + bottom edge of a thin stroke):
    the stronger lobe is kept and the scan resumes from its position. This
    prevents a single string from being counted twice.
    """
    if profile.size == 0:
        return []
    pmax = float(profile.max())
    if pmax <= 1e-8:
        return []
    threshold = max(threshold_rel * pmax, 1e-6)
    peaks: list[tuple[int, float]] = []
    last = -min_distance
    for i in range(1, profile.size - 1):
        if (
            profile[i] >= threshold
            and profile[i] >= profile[i - 1]
            and profile[i] >= profile[i + 1]
        ):
            strength = float(profile[i] / pmax)
            if (i - last) >= min_distance:
                peaks.append((i, strength))
                last = i
            elif peaks and strength > peaks[-1][1]:
                # Same physical line, stronger lobe: replace and re-anchor.
                peaks[-1] = (i, strength)
                last = i
    if limit is not None and len(peaks) > limit:
        peaks.sort(key=lambda p: p[1], reverse=True)
        peaks = sorted(peaks[:limit], key=lambda p: p[0])
    return peaks


def detect_fret_wires(
    warped_gray: np.ndarray,
) -> list[tuple[int, float]]:
    """Detect fret wires in a rectified crop.

    Fret wires run vertically in the rectified crop, so the column profile of
    the horizontal (x-direction) Sobel response is peak-picked. Each accepted
    peak must also show vertical continuity, which rejects speckle noise and
    string-crossing artefacts.

    Returns
    -------
    list of (x_position, strength) sorted by x. Strength is relative to the
    strongest peak (0..1]. May be empty — nothing is invented.
    """
    h, w = warped_gray.shape[:2]
    if h < 16 or w < 32:
        return []

    y0 = max(1, int(h * FRET_INTERIOR_ROW_MARGIN))
    y1 = min(h - 1, int(h * (1.0 - FRET_INTERIOR_ROW_MARGIN)))
    interior = warped_gray[y0:y1, :]
    edges = cv2.Canny(interior, 40, 120)

    sobel_x = np.abs(cv2.Sobel(interior, cv2.CV_32F, 1, 0, ksize=3))
    col_profile = sobel_x.mean(axis=0)
    edge_profile = edges.mean(axis=0) / 255.0
    combined = 0.5 * (col_profile / max(float(col_profile.max()), 1e-6)) + 0.5 * edge_profile
    smoothed = _smooth(combined)

    x_margin = max(4, int(w * 0.04))
    min_dist = max(4, int(w * FRET_MIN_PEAK_DISTANCE))
    interior_h = max(1, y1 - y0)

    raw: list[tuple[int, float]] = []
    pmax = max(float(smoothed.max()), 1e-6)
    for x in range(x_margin, max(x_margin + 1, w - x_margin)):
        val = smoothed[x]
        if (
            val > FRET_PEAK_THRESHOLD * pmax
            and val >= smoothed[x - 1]
            and val >= smoothed[x + 1]
        ):
            window = edges[:, max(0, x - 1) : min(w, x + 2)]
            vertical_fill = float(np.count_nonzero(window)) / float(interior_h)
            if vertical_fill >= FRET_MIN_VERTICAL_FILL:
                raw.append((x, float(val / pmax)))

    # Enforce minimum spacing, keeping the stronger peak.
    picked: list[tuple[int, float]] = []
    for x, s in raw:
        if picked and (x - picked[-1][0]) < min_dist:
            if s > picked[-1][1]:
                picked[-1] = (x, s)
        else:
            picked.append((x, s))
    return picked


def _select_six_string_subset(
    peaks: list[tuple[int, float]],
    height: int,
) -> tuple[list[int], float] | None:
    """Choose the most evenly spaced 6-peak subset, or ``None``.

    Only *measured* peaks are considered. The six-string prior is used solely
    to decide which measured rows belong to the string set; if no subset has
    a spacing coefficient of variation under ``STRING_MAX_SPACING_CV`` the
    function returns ``None`` and the caller reports fewer strings honestly.
    """
    if len(peaks) < 6:
        return None

    candidates = sorted(peaks, key=lambda p: p[1], reverse=True)[:STRING_MAX_PEAKS]
    candidates = sorted(candidates, key=lambda p: p[0])
    min_spacing = STRING_MIN_SPACING * height

    best: tuple[list[int], float] | None = None
    for combo in combinations(range(len(candidates)), 6):
        ys = [candidates[i][0] for i in combo]
        spacings = [ys[k + 1] - ys[k] for k in range(5)]
        if min(spacings) < min_spacing:
            continue
        mean_sp = float(np.mean(spacings))
        if mean_sp <= 0:
            continue
        cv = float(np.std(spacings)) / mean_sp
        if best is None or cv < best[1]:
            best = (list(combo), cv)

    if best is None or best[1] > STRING_MAX_SPACING_CV:
        return None
    return best


def detect_strings(
    warped_gray: np.ndarray,
) -> tuple[list[tuple[int, float]], dict[str, Any]]:
    """Detect string rows in a rectified crop.

    Strings run horizontally, so the row profile of the vertical
    (y-direction) Sobel response is peak-picked. Neck bindings are excluded
    via top/bottom margins. When at least six peaks exist, the most evenly
    spaced six-peak subset is selected (guitar strings are near-uniformly
    spaced across the fretboard); the spacing fit quality is returned so
    callers can report how trustworthy the six-string assignment is.

    Returns
    -------
    (strings, info)
        ``strings`` is a list of ``(y_position, strength)`` sorted by y.
        ``info`` carries ``peak_count``, ``spacing_cv`` (or None) and
        ``subset_rejected`` so nothing has to be guessed downstream.
    """
    h, w = warped_gray.shape[:2]
    info: dict[str, Any] = {
        "peak_count": 0,
        "spacing_cv": None,
        "subset_rejected": False,
        "peaks": [],
    }
    if h < 24 or w < 24:
        return [], info

    x0 = max(1, int(w * STRING_INTERIOR_COL_MARGIN))
    x1 = min(w - 1, int(w * (1.0 - STRING_INTERIOR_COL_MARGIN)))
    y0 = max(1, int(h * STRING_EDGE_MARGIN))
    y1 = min(h - 1, int(h * (1.0 - STRING_EDGE_MARGIN)))
    if y1 - y0 < 8 or x1 - x0 < 8:
        return [], info

    interior = warped_gray[y0:y1, x0:x1]
    sobel_y = np.abs(cv2.Sobel(interior, cv2.CV_32F, 0, 1, ksize=3))
    row_profile = sobel_y.mean(axis=1)
    smoothed = _smooth(row_profile)

    min_dist = max(4, int(h * STRING_LOBE_MERGE_DISTANCE))
    peaks = _pick_peaks(
        smoothed, threshold_rel=STRING_PEAK_THRESHOLD, min_distance=min_dist
    )
    # Peak coordinates are relative to the trimmed interior; shift to crop space.
    peaks = [(y + y0, s) for y, s in peaks]
    info["peak_count"] = len(peaks)
    info["peaks"] = [[int(y), round(s, 4)] for y, s in peaks]

    if len(peaks) < 6:
        return peaks, info

    selected = _select_six_string_subset(peaks, h)
    if selected is None:
        info["subset_rejected"] = True
        return peaks, info

    combo, cv_val = selected
    info["spacing_cv"] = round(cv_val, 4)
    chosen = sorted([peaks[i] for i in combo], key=lambda p: p[0])
    return chosen, info


# ---------------------------------------------------------------------------
# Orchestration + annotation
# ---------------------------------------------------------------------------


def analyze_frame(
    image: np.ndarray,
    detector: Callable[[np.ndarray], FretboardDetectionResult] | None = None,
) -> VisionAnalysis:
    """Run the full isolated vision analysis on one BGR frame.

    Parameters
    ----------
    image:
        BGR frame as read by ``cv2.imread``.
    detector:
        Optional detector override (tests inject the classical detector to
        avoid loading torch). Defaults to the existing hybrid detector.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return VisionAnalysis(
            detected=False,
            confidence=0.0,
            failure_reason="invalid_image",
            limitations=["The frame could not be read as an image."],
        )

    detect = detector or detect_fretboard_hybrid
    result = detect(image)

    base = VisionAnalysis(
        detected=result.detected,
        confidence=float(result.confidence),
        detection_source=result.diagnostics.get("source") if result.detected else None,
        polygon=[
            (float(p[0]), float(p[1])) for p in result.polygon
        ]
        if result.polygon
        else None,
        geometry=result.geometry.to_dict() if result.geometry is not None else None,
        failure_reason=result.failure_reason,
    )

    if not result.detected or not result.polygon:
        base.limitations.append(
            "No credible fretboard region was localized in this frame, so no "
            "strings or fret wires were measured."
        )
        base.diagnostics = dict(result.diagnostics)
        return base

    try:
        quad = order_quad(result.polygon)
    except ValueError as exc:
        base.detected = False
        base.failure_reason = "degenerate_polygon"
        base.limitations.append(f"The detected region was not a usable quadrilateral ({exc}).")
        return base

    base.ordered_quad = quad

    # Refine quad orientation before rectification. Bounding-box quads (ML
    # path) are often a few degrees off the string axis, which would leave
    # strings diagonal in the crop. The refinement measures the residual in
    # rectified space, is evidence-gated and clamped, and is applied only when
    # it strictly improves the alignment, so already-straight classical
    # corridors are left untouched.
    quad, tilt = refine_quad_orientation(image, quad)
    base.ordered_quad = quad

    warped, matrix = rectify_fretboard(image, quad)
    warped_gray = _to_gray(warped)

    fret_peaks = detect_fret_wires(warped_gray)
    string_rows, string_info = detect_strings(warped_gray)

    h_rect, w_rect = warped_gray.shape[:2]
    mid_y = (h_rect - 1) / 2.0
    mid_x = (w_rect - 1) / 2.0

    base.frets = []
    for idx, (x, s) in enumerate(fret_peaks):
        p1 = rect_to_original(matrix, float(x), 1.0)
        p2 = rect_to_original(matrix, float(x), float(h_rect - 2))
        base.frets.append(
            FretAnnotation(
                index=idx, x_rectified=float(x), strength=round(s, 4), start=p1, end=p2
            )
        )

    base.strings = []
    for pos, (y, s) in enumerate(string_rows):
        p1 = rect_to_original(matrix, 1.0, float(y))
        p2 = rect_to_original(matrix, float(w_rect - 2), float(y))
        base.strings.append(
            StringAnnotation(
                position=pos,
                y_rectified=float(y),
                strength=round(s, 4),
                start=p1,
                end=p2,
            )
        )

    base.rectified_size = (int(w_rect), int(h_rect))
    base.rectified = warped

    # --- Honest limitations -------------------------------------------------
    if len(base.strings) < 6:
        base.limitations.append(
            f"Only {len(base.strings)} string row(s) could be measured from image "
            "evidence; six evenly spaced strings were not resolved in this frame."
        )
    elif string_info.get("subset_rejected"):
        base.limitations.append(
            "Candidate string rows were found but their spacing did not match a "
            "credible six-string pattern; showing the measured peaks only."
        )
    if len(base.frets) < 3:
        base.limitations.append(
            f"Only {len(base.frets)} fret wire(s) were resolved; fret spacing "
            "statistics are unreliable at this count."
        )
    base.limitations.append(
        "String pitch identity (EADGBE) and fret numbers are not inferred — "
        "only geometric positions are measured. No notes are identified."
    )

    diagnostics: dict = dict(result.diagnostics)
    if abs(tilt) > 1e-9:
        diagnostics["tilt_refine_deg"] = round(float(tilt), 2)
    diagnostics.update(
        {
            "rectified_size": [int(w_rect), int(h_rect)],
            "fret_peaks": [[int(x), round(s, 4)] for x, s in fret_peaks],
            "string_detection": string_info,
        }
    )
    base.diagnostics = diagnostics

    base.rectified_annotated = annotate_rectified(warped, base)
    return base


def annotate_rectified(warped: np.ndarray, analysis: VisionAnalysis) -> np.ndarray:
    """Draw measured strings and fret wires on the rectified crop."""
    vis = warped.copy() if warped.ndim == 3 else cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
    h, w = vis.shape[:2]

    for fret in analysis.frets:
        x = int(round(fret.x_rectified))
        if 0 <= x < w:
            cv2.line(vis, (x, 0), (x, h - 1), _COLOR_FRET, 1, cv2.LINE_AA)
            cv2.putText(
                vis,
                f"F{fret.index + 1}",
                (max(2, x - 10), max(12, int(h * 0.08))),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                _COLOR_FRET,
                1,
                cv2.LINE_AA,
            )

    for s in analysis.strings:
        y = int(round(s.y_rectified))
        if 0 <= y < h:
            cv2.line(vis, (0, y), (w - 1, y), _COLOR_STRING, 1, cv2.LINE_AA)
            cv2.putText(
                vis,
                f"S{s.position + 1}",
                (2, min(h - 4, y + 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                _COLOR_TEXT,
                1,
                cv2.LINE_AA,
            )

    cv2.putText(
        vis,
        f"strings {len(analysis.strings)}/6   frets {len(analysis.frets)}",
        (4, max(12, h - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        _COLOR_TEXT,
        1,
        cv2.LINE_AA,
    )
    return vis


def annotate_frame(image: np.ndarray, analysis: VisionAnalysis) -> np.ndarray:
    """Draw the polygon, string lines and fret wires on the original frame."""
    if image is None or image.size == 0:
        return np.zeros((100, 200, 3), dtype=np.uint8)

    vis = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if vis.shape[2] == 4:
        vis = cv2.cvtColor(vis, cv2.COLOR_BGRA2BGR)
    h, w = vis.shape[:2]

    if analysis.detected and analysis.ordered_quad is not None:
        poly = np.array(analysis.ordered_quad, dtype=np.int32)
        overlay = vis.copy()
        cv2.fillPoly(overlay, [poly], _COLOR_POLY_FILL)
        cv2.addWeighted(overlay, 0.22, vis, 0.78, 0, vis)
        cv2.polylines(vis, [poly], isClosed=True, color=_COLOR_POLY_LINE, thickness=2)
        for idx, pt in enumerate(analysis.ordered_quad):
            px, py = int(round(pt[0])), int(round(pt[1]))
            cv2.circle(vis, (px, py), 3, (0, 255, 255), -1)
            cv2.putText(
                vis,
                f"P{idx}",
                (px + 4, py - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                _COLOR_TEXT,
                1,
                cv2.LINE_AA,
            )

        for s in analysis.strings:
            p1 = (int(round(s.start[0])), int(round(s.start[1])))
            p2 = (int(round(s.end[0])), int(round(s.end[1])))
            cv2.line(vis, p1, p2, _COLOR_STRING, 1, cv2.LINE_AA)

        for fret in analysis.frets:
            p1 = (int(round(fret.start[0])), int(round(fret.start[1])))
            p2 = (int(round(fret.end[0])), int(round(fret.end[1])))
            cv2.line(vis, p1, p2, _COLOR_FRET, 1, cv2.LINE_AA)

    # HUD
    box_w = min(w - 20, 340)
    box_h = 78 if analysis.detected else 54
    if box_w > 40 and box_h > 20:
        hud = vis.copy()
        cv2.rectangle(hud, (10, 10), (10 + box_w, 10 + box_h), (20, 20, 20), -1)
        cv2.addWeighted(hud, 0.82, vis, 0.18, 0, vis)
        cv2.rectangle(vis, (10, 10), (10 + box_w, 10 + box_h), (80, 80, 80), 1)
        if analysis.detected:
            source = analysis.detection_source or "unknown"
            cv2.putText(
                vis,
                f"VISION  [{source}]",
                (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (60, 230, 90),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"conf {analysis.confidence:.2f}   strings {len(analysis.strings)}/6   frets {len(analysis.frets)}",
                (20, 54),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                "strings=filled lines  frets=yellow lines",
                (20, 72),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (190, 190, 190),
                1,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                vis,
                "NO FRETBOARD DETECTED",
                (20, 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (40, 70, 240),
                2,
                cv2.LINE_AA,
            )
            reason = analysis.failure_reason or "unknown"
            cv2.putText(
                vis,
                f"Reason: {reason}",
                (20, 52),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )

    return vis
