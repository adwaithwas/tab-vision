"""Classical OpenCV fretboard localization for guitar videos.

This module implements a classical computer vision pipeline to detect and localize
a guitar fretboard in a single video frame without requiring deep neural networks.

Detection Pipeline
------------------
1. Preprocessing & Normalization:
   - Grayscale conversion and bilateral/Gaussian smoothing to suppress sensor noise.
   - Contrast Limited Adaptive Histogram Equalization (CLAHE) to balance lighting
     variations across the instrument body and neck.
2. Adaptive Edge Detection:
   - Canny edge detection with thresholds dynamically computed from median intensity.
3. Multi-Scale Probabilistic Hough Line Detection:
   - Extracts candidate line segments parameterized by orientation angle, midpoint,
     and length.
4. Boundary Pair Clustering (Longitudinal Neck Edges):
   - Identifies candidate pairs of approximately parallel lines (allowing slight taper
     from perspective / nut convergence).
   - Filters pairs by plausible physical separation (neck width relative to frame scale)
     and longitudinal span overlap.
   - Enforces minimum aspect ratio (elongated neck corridor >= 2.2:1).
5. Perspective Rectification & Transverse Fret Verification:
   - Warps the candidate corridor into a canonical rectified rectangle.
   - Computes vertical edge gradient / projection profile across the longitudinal axis.
   - Detects quasi-periodic transverse edge peaks corresponding to fret wires.
   - Rejects candidate regions lacking transverse fret signatures (e.g. table edges,
     door frames, walls, or plain rulers).
6. Multi-Factor Confidence Scoring:
   - Combines longitudinal edge support, transverse fret count and distribution,
     and geometric plausibility into a calibrated 0.0 to 1.0 score.
   - Rejects candidates below the credibility threshold (default 0.35).
   - Detection is never fabricated: if no credible candidate exists, returns
     ``detected=False`` with detailed diagnostics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class FretboardDetectorConfig:
    """Configurable hyperparameters for classical fretboard localization."""

    min_confidence: float = 0.35
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: tuple[int, int] = (8, 8)
    gaussian_blur_ksize: tuple[int, int] = (5, 5)
    gaussian_blur_sigma: float = 1.0
    canny_sigma: float = 0.33
    min_neck_aspect_ratio: float = 2.2
    max_neck_angle_diff_deg: float = 14.0
    min_frets_required: int = 2
    min_neck_width_fraction: float = 0.02
    max_neck_width_fraction: float = 0.18
    min_neck_length_fraction: float = 0.12
    #: Reject corridors whose interior median luminance exceeds this value (disabled by default).
    max_corridor_median_lum: float = 255.0
    #: Reject when Sobel_y dominates Sobel_x by this factor.
    max_longitudinal_vs_transverse_ratio: float = 3.5


@dataclass
class FretboardGeometry:
    """Geometric attributes of a localized fretboard candidate."""

    orientation_deg: float
    estimated_length: float
    estimated_width: float
    aspect_ratio: float
    fret_count_estimate: int
    transverse_edge_density: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "orientation_deg": round(self.orientation_deg, 2),
            "estimated_length": round(self.estimated_length, 2),
            "estimated_width": round(self.estimated_width, 2),
            "aspect_ratio": round(self.aspect_ratio, 2),
            "fret_count_estimate": self.fret_count_estimate,
            "transverse_edge_density": round(self.transverse_edge_density, 4),
        }


@dataclass
class FretboardDetectionResult:
    """Structured result from fretboard localization.

    Confidence Interpretation:
    --------------------------
    - 0.00 to 0.34: Insufficient evidence or rejected candidate (detected=False).
    - 0.35 to 0.59: Moderate confidence; partial fretboard visibility or subtle frets.
    - 0.60 to 0.79: Strong confidence; distinct parallel boundaries and fret peaks.
    - 0.80 to 1.00: High confidence; sharp neck boundaries, clear transverse frets.
    """

    detected: bool
    confidence: float
    polygon: list[tuple[float, float]] | None
    geometry: FretboardGeometry | None
    failure_reason: str | None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "confidence": round(self.confidence, 4),
            "polygon": [
                [round(pt[0], 2), round(pt[1], 2)] for pt in self.polygon
            ]
            if self.polygon is not None
            else None,
            "geometry": self.geometry.to_dict() if self.geometry is not None else None,
            "failure_reason": self.failure_reason,
            "diagnostics": self.diagnostics,
        }


class FretboardDetector:
    """Modular classical computer vision fretboard detector."""

    def __init__(self, config: FretboardDetectorConfig | None = None) -> None:
        self.config = config or FretboardDetectorConfig()

    def detect(self, image: np.ndarray) -> FretboardDetectionResult:
        """Run fretboard localization on a source image.

        Parameters
        ----------
        image : np.ndarray
            BGR, RGB, or grayscale input image (uint8).

        Returns
        -------
        FretboardDetectionResult
            Structured localization outcome.
        """
        # 1. Input validation
        val_res = self._validate_image(image)
        if val_res is not None:
            return val_res

        height, width = image.shape[:2]

        # 2. Preprocessing & contrast enhancement
        gray = self._to_grayscale(image)
        clahe = cv2.createCLAHE(
            clipLimit=self.config.clahe_clip_limit,
            tileGridSize=self.config.clahe_tile_grid,
        )
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(
            enhanced,
            self.config.gaussian_blur_ksize,
            self.config.gaussian_blur_sigma,
        )

        # 3. Adaptive Canny edge detection
        median_val = float(np.median(blurred))
        low_thresh = int(max(20, (1.0 - self.config.canny_sigma) * median_val))
        high_thresh = int(min(240, max(low_thresh + 30, (1.0 + self.config.canny_sigma) * median_val)))
        edges = cv2.Canny(blurred, low_thresh, high_thresh)

        edge_pixels = int(np.count_nonzero(edges))
        total_pixels = height * width
        edge_density = edge_pixels / float(total_pixels)

        if edge_density < 0.0008:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="insufficient_edge_detail",
                diagnostics={
                    "image_size": [width, height],
                    "edge_density": round(edge_density, 5),
                    "note": "Image is nearly uniform or lacks discernible edges.",
                },
            )

        if edge_density > 0.22:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="excessive_image_noise",
                diagnostics={
                    "image_size": [width, height],
                    "edge_density": round(edge_density, 5),
                    "note": "Image edge clutter or noise is excessively high (> 22%).",
                },
            )


        # 4. Multi-scale line segment detection
        diag = math.hypot(width, height)
        min_line_len = max(24, int(diag * 0.08))
        max_line_gap = max(6, int(diag * 0.025))
        hough_thresh = max(20, int(min_line_len * 0.35))

        lines_p = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=hough_thresh,
            minLineLength=min_line_len,
            maxLineGap=max_line_gap,
        )

        if lines_p is None or len(lines_p) < 2:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="no_line_segments_found",
                diagnostics={
                    "image_size": [width, height],
                    "edge_density": round(edge_density, 5),
                    "lines_found": 0 if lines_p is None else len(lines_p),
                },
            )

        # 5. Parameterize line segments
        segments = []
        for line in lines_p:
            x1, y1, x2, y2 = map(float, line.flatten()[:4])
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            if length < min_line_len:
                continue
            angle = math.degrees(math.atan2(dy, dx))
            # Canonicalize angle in [-90, 90)
            if angle >= 90.0:
                angle -= 180.0
            elif angle < -90.0:
                angle += 180.0
            mid_x, mid_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            segments.append({
                "p1": (x1, y1),
                "p2": (x2, y2),
                "mid": (mid_x, mid_y),
                "length": length,
                "angle": angle,
            })

        if len(segments) < 2:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="insufficient_long_line_segments",
                diagnostics={
                    "image_size": [width, height],
                    "lines_found": len(lines_p),
                    "valid_segments": len(segments),
                },
            )

        # 6. Search for candidate boundary pairs
        min_width = max(8.0, min(width, height) * self.config.min_neck_width_fraction)
        max_width = min(width, height) * self.config.max_neck_width_fraction
        min_length = min(width, height) * self.config.min_neck_length_fraction

        candidates = []
        num_pairs_evaluated = 0

        # Sort segments by length descending for priority evaluation
        segments.sort(key=lambda s: s["length"], reverse=True)
        eval_limit = min(60, len(segments))

        for i in range(eval_limit):
            s1 = segments[i]
            for j in range(i + 1, eval_limit):
                s2 = segments[j]
                num_pairs_evaluated += 1

                # Angle difference check (allow slight taper/perspective)
                d_angle = abs(s1["angle"] - s2["angle"])
                if d_angle > 90.0:
                    d_angle = 180.0 - d_angle
                if d_angle > self.config.max_neck_angle_diff_deg:
                    continue

                # Mean orientation angle
                rad1 = math.radians(s1["angle"])
                rad2 = math.radians(s2["angle"])
                mean_ux = (math.cos(rad1) + math.cos(rad2)) / 2.0
                mean_uy = (math.sin(rad1) + math.sin(rad2)) / 2.0
                u_norm = math.hypot(mean_ux, mean_uy)
                if u_norm < 1e-6:
                    continue
                ux, uy = mean_ux / u_norm, mean_uy / u_norm
                nx, ny = -uy, ux  # Normal vector

                # Project segments onto longitudinal axis (u) and transverse axis (n)
                s1_long1 = s1["p1"][0] * ux + s1["p1"][1] * uy
                s1_long2 = s1["p2"][0] * ux + s1["p2"][1] * uy
                s1_min, s1_max = min(s1_long1, s1_long2), max(s1_long1, s1_long2)
                t1 = (s1["p1"][0] * nx + s1["p1"][1] * ny + s1["p2"][0] * nx + s1["p2"][1] * ny) / 2.0

                s2_long1 = s2["p1"][0] * ux + s2["p1"][1] * uy
                s2_long2 = s2["p2"][0] * ux + s2["p2"][1] * uy
                s2_min, s2_max = min(s2_long1, s2_long2), max(s2_long1, s2_long2)
                t2 = (s2["p1"][0] * nx + s2["p1"][1] * ny + s2["p2"][0] * nx + s2["p2"][1] * ny) / 2.0

                # Perpendicular separation distance (neck width)
                dist = abs(t1 - t2)
                if dist < min_width or dist > max_width:
                    continue

                # Longitudinal overlap and total span
                overlap_min = max(s1_min, s2_min)
                overlap_max = min(s1_max, s2_max)
                overlap_len = overlap_max - overlap_min

                min_seg_len = min(s1["length"], s2["length"])
                # Require either meaningful overlap or cohesive longitudinal span
                if overlap_len < 0.25 * min_seg_len and overlap_len < 25.0:
                    continue

                # Defined longitudinal corridor bounds
                span_start = min(s1_min, s2_min)
                span_end = max(s1_max, s2_max)
                span_len = span_end - span_start

                if span_len < min_length:
                    continue

                aspect_ratio = span_len / dist
                if aspect_ratio < self.config.min_neck_aspect_ratio:
                    continue

                # Construct 4 quadrilateral corners in image space
                # C0: start on line 1, C1: end on line 1, C2: end on line 2, C3: start on line 2
                c0 = (span_start * ux + t1 * nx, span_start * uy + t1 * ny)
                c1 = (span_end * ux + t1 * nx, span_end * uy + t1 * ny)
                c2 = (span_end * ux + t2 * nx, span_end * uy + t2 * ny)
                c3 = (span_start * ux + t2 * nx, span_start * uy + t2 * ny)

                poly = [c0, c1, c2, c3]
                # Check polygon bounds validity
                if not self._is_polygon_valid(poly, width, height):
                    continue

                # Verify internal transverse fret pattern
                fret_analysis = self._verify_transverse_frets(
                    enhanced, edges, poly, span_len, dist
                )

                # Reject corridors that are dominated by longitudinal (string) edges
                if fret_analysis.get("rejected_string_lines", False):
                    continue

                # Reject corridors whose interior is too bright (background/wall)
                if self.config.max_corridor_median_lum < 255.0:
                    crop_lum = self._sample_corridor_luminance(enhanced, poly)
                    if crop_lum > self.config.max_corridor_median_lum:
                        continue

                candidate_score = self._compute_candidate_score(
                    s1["length"],
                    s2["length"],
                    span_len,
                    dist,
                    aspect_ratio,
                    d_angle,
                    fret_analysis,
                )

                orientation_deg = math.degrees(math.atan2(uy, ux))
                if orientation_deg >= 90.0:
                    orientation_deg -= 180.0
                elif orientation_deg < -90.0:
                    orientation_deg += 180.0

                # Store candidate projection properties
                t_low, t_high = min(t1, t2), max(t1, t2)
                candidates.append({
                    "score": candidate_score,
                    "polygon": poly,
                    "geometry": FretboardGeometry(
                        orientation_deg=orientation_deg,
                        estimated_length=span_len,
                        estimated_width=dist,
                        aspect_ratio=aspect_ratio,
                        fret_count_estimate=fret_analysis["fret_count"],
                        transverse_edge_density=fret_analysis["transverse_density"],
                    ),
                    "fret_analysis": fret_analysis,
                    "angle_diff": d_angle,
                    "t1": t_low,
                    "t2": t_high,
                    "span_start": span_start,
                    "span_end": span_end,
                })

        # 7. Evaluate candidates and suppress internal sub-corridors
        if not candidates:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="no_fretboard_candidate_found",
                diagnostics={
                    "image_size": [width, height],
                    "lines_found": len(segments),
                    "pairs_evaluated": num_pairs_evaluated,
                    "note": (
                        "Line segments were detected, but no pair met neck parallelism, "
                        "aspect ratio, or boundary constraints."
                    ),
                },
            )

        # Suppress sub-corridors (e.g. inner string pairs) that lie entirely inside a wider neck corridor
        filtered_candidates = []
        for c_idx, c in enumerate(candidates):
            is_subsumed = False
            for other_idx, other in enumerate(candidates):
                if c_idx == other_idx:
                    continue
                if (
                    other["geometry"].fret_count_estimate >= self.config.min_frets_required
                    and other["geometry"].estimated_width > c["geometry"].estimated_width * 1.35
                    and other["score"] >= c["score"]
                ):
                    d_ang = abs(c["geometry"].orientation_deg - other["geometry"].orientation_deg)
                    if d_ang > 90.0:
                        d_ang = 180.0 - d_ang
                    if d_ang <= 10.0:
                        # Check transverse containment
                        if c["t1"] >= other["t1"] - 4.0 and c["t2"] <= other["t2"] + 4.0:
                            ov_start = max(c["span_start"], other["span_start"])
                            ov_end = min(c["span_end"], other["span_end"])
                            if (ov_end - ov_start) >= 0.5 * c["geometry"].estimated_length:
                                is_subsumed = True
                                break
            if not is_subsumed:
                filtered_candidates.append(c)

        if filtered_candidates:
            candidates = filtered_candidates

        # Select candidate with highest confidence score
        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]
        best_score = best["score"]

        # Credibility threshold and fret requirement check
        has_min_frets = best["geometry"].fret_count_estimate >= self.config.min_frets_required
        is_credible = best_score >= self.config.min_confidence and has_min_frets

        if not is_credible:
            reason = "low_confidence"
            if not has_min_frets:
                reason = "insufficient_transverse_frets"

            return FretboardDetectionResult(
                detected=False,
                confidence=round(best_score, 4),
                polygon=None,
                geometry=None,
                failure_reason=reason,
                diagnostics={
                    "image_size": [width, height],
                    "best_candidate_score": round(best_score, 4),
                    "threshold": self.config.min_confidence,
                    "fret_count_found": best["geometry"].fret_count_estimate,
                    "required_frets": self.config.min_frets_required,
                    "pairs_evaluated": num_pairs_evaluated,
                },
            )

        return FretboardDetectionResult(
            detected=True,
            confidence=round(best_score, 4),
            polygon=best["polygon"],
            geometry=best["geometry"],
            failure_reason=None,
            diagnostics={
                "image_size": [width, height],
                "candidates_evaluated": len(candidates),
                "pairs_evaluated": num_pairs_evaluated,
                "fret_peaks": best["fret_analysis"].get("peaks", []),
            },
        )

    def _validate_image(self, image: Any) -> FretboardDetectionResult | None:
        """Validate input array type and dimensions."""
        if image is None or not isinstance(image, np.ndarray):
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="invalid_image_type",
                diagnostics={"error": "Input must be a valid NumPy ndarray."},
            )

        if image.size == 0 or len(image.shape) < 2:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="empty_image",
                diagnostics={"error": "Image buffer is empty."},
            )

        h, w = image.shape[:2]
        if h < 24 or w < 24:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="image_dimensions_too_small",
                diagnostics={"size": [w, h], "error": "Minimum dimension is 24x24 px."},
            )

        return None

    def _to_grayscale(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return image
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def _is_polygon_valid(
        self, poly: list[tuple[float, float]], width: int, height: int
    ) -> bool:
        """Verify quadrilateral is within image margins and has plausible area."""
        pts = np.array(poly, dtype=np.float32)
        margin = max(width, height) * 0.15
        if np.any(pts[:, 0] < -margin) or np.any(pts[:, 0] > width + margin):
            return False
        if np.any(pts[:, 1] < -margin) or np.any(pts[:, 1] > height + margin):
            return False

        area = cv2.contourArea(pts.astype(np.int32))
        total_area = width * height
        if area < total_area * 0.005 or area > total_area * 0.55:
            return False
        return True

    def _sample_corridor_luminance(self, gray: np.ndarray, poly: list[tuple[float, float]]) -> float:
        """Return median pixel luminance inside the candidate quadrilateral."""
        h, w = gray.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        pts = np.array(poly, dtype=np.float32)
        pts_clipped = pts.copy()
        pts_clipped[:, 0] = np.clip(pts_clipped[:, 0], 0, w - 1)
        pts_clipped[:, 1] = np.clip(pts_clipped[:, 1], 0, h - 1)
        cv2.fillPoly(mask, [pts_clipped.astype(np.int32)], 255)
        pixels = gray[mask > 0]
        if pixels.size == 0:
            return 0.0
        return float(np.median(pixels))

    def _verify_transverse_frets(
        self,
        gray: np.ndarray,
        edges: np.ndarray,
        poly: list[tuple[float, float]],
        span_len: float,
        dist: float,
    ) -> dict[str, Any]:
        """Rectify the candidate corridor and detect transverse fret wire signals."""
        rect_w = int(max(60, min(800, span_len)))
        rect_h = int(max(20, min(200, dist)))

        src_pts = np.array(poly, dtype=np.float32)
        dst_pts = np.array(
            [
                [0, 0],
                [rect_w - 1, 0],
                [rect_w - 1, rect_h - 1],
                [0, rect_h - 1],
            ],
            dtype=np.float32,
        )

        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped_gray = cv2.warpPerspective(gray, matrix, (rect_w, rect_h))
        warped_edges = cv2.warpPerspective(edges, matrix, (rect_w, rect_h))

        # Inspect interior (avoiding the longitudinal boundary edges themselves)
        y_start = int(rect_h * 0.18)
        y_end = int(rect_h * 0.82)
        if y_end <= y_start:
            y_start = 0
            y_end = rect_h

        interior_edges = warped_edges[y_start:y_end, :]
        interior_gray = warped_gray[y_start:y_end, :]

        # 1. Transverse edge density
        edge_density = float(np.count_nonzero(interior_edges)) / float(interior_edges.size)
        if edge_density < 0.015:
            # Interior is flat or lacks transverse structure
            return {
                "fret_count": 0,
                "transverse_density": edge_density,
                "regularity_score": 0.0,
                "peaks": [],
                "rejected_string_lines": False,
            }

        # 2. Vertical Sobel gradient (transverse, fret wires) vs Horizontal Sobel (strings)
        sobel_x = np.abs(cv2.Sobel(interior_gray, cv2.CV_32F, 1, 0, ksize=3))
        sobel_y = np.abs(cv2.Sobel(interior_gray, cv2.CV_32F, 0, 1, ksize=3))
        mean_sx = float(sobel_x.mean())
        mean_sy = float(sobel_y.mean())

        # If horizontal edges (Sobel_y) dominate strongly over vertical (Sobel_x),
        # the interior structure is guitar strings, not fret wires.
        if mean_sx < 1e-4:
            longitudinal_ratio = float("inf")
        else:
            longitudinal_ratio = mean_sy / mean_sx

        if longitudinal_ratio > self.config.max_longitudinal_vs_transverse_ratio:
            return {
                "fret_count": 0,
                "transverse_density": edge_density,
                "regularity_score": 0.0,
                "peaks": [],
                "rejected_string_lines": True,
                "longitudinal_ratio": round(longitudinal_ratio, 2),
            }

        col_sobel = np.mean(sobel_x, axis=0)
        sobel_max = float(col_sobel.max())
        if sobel_max > 1e-4:
            col_sobel_norm = col_sobel / sobel_max
        else:
            col_sobel_norm = col_sobel

        # Column edge profile
        col_edges = np.mean(interior_edges, axis=0) / 255.0
        combined_profile = 0.5 * col_sobel_norm + 0.5 * col_edges

        # 1D smoothing
        kernel = np.array([0.15, 0.7, 0.15], dtype=np.float32)
        smoothed = np.convolve(combined_profile, kernel, mode="same")

        # Peak detection for frets strictly within the interior of the corridor
        x_margin = max(8, int(rect_w * 0.05))
        x_end = max(x_margin + 1, rect_w - x_margin)

        min_peak_dist = max(4, int(rect_w * 0.025))
        threshold = 0.22

        peaks: list[int] = []
        last_peak = -min_peak_dist
        interior_h = max(1, y_end - y_start)

        for x in range(x_margin, x_end):
            val = smoothed[x]
            if val > threshold and val >= smoothed[x - 1] and val >= smoothed[x + 1]:
                if (x - last_peak) >= min_peak_dist:
                    # Require vertical continuity across at least 25% of the interior height
                    col_span = interior_edges[:, max(0, x - 1) : min(rect_w, x + 2)]
                    vert_fill = np.count_nonzero(col_span) / float(interior_h)
                    if vert_fill >= 0.25:
                        peaks.append(int(x))
                        last_peak = x

        fret_count = len(peaks)

        # Fret spacing regularity metric (if multiple frets detected)
        regularity_score = 0.5
        if fret_count >= 3:
            spacings = [peaks[k + 1] - peaks[k] for k in range(fret_count - 1)]
            mean_sp = float(np.mean(spacings))
            std_sp = float(np.std(spacings))
            if mean_sp > 0:
                cv_val = std_sp / mean_sp
                regularity_score = max(0.0, min(1.0, 1.0 - cv_val * 0.7))

        return {
            "fret_count": fret_count,
            "transverse_density": edge_density,
            "regularity_score": regularity_score,
            "peaks": peaks,
            "rejected_string_lines": False,
            "longitudinal_ratio": round(longitudinal_ratio, 2),
        }

    def _compute_candidate_score(
        self,
        l1: float,
        l2: float,
        span_len: float,
        width: float,
        aspect_ratio: float,
        d_angle: float,
        fret_analysis: dict[str, Any],
    ) -> float:
        """Combine geometric features into a unified 0.0 to 1.0 confidence score."""
        # 1. Longitudinal boundary edge coverage
        mean_seg_len = (l1 + l2) / 2.0
        s_coverage = min(1.0, mean_seg_len / max(1.0, span_len))

        # 2. Transverse fret evidence
        fret_count = fret_analysis["fret_count"]
        s_frets = min(1.0, fret_count / 6.0)
        s_fret_density = min(1.0, fret_analysis["transverse_density"] / 0.04)
        s_regularity = fret_analysis.get("regularity_score", 0.5)

        s_transverse = 0.55 * s_frets + 0.25 * s_fret_density + 0.20 * s_regularity

        # 3. Geometry plausibility
        s_aspect = min(1.0, aspect_ratio / 5.0)
        s_parallel = max(0.0, 1.0 - (d_angle / self.config.max_neck_angle_diff_deg))
        s_geom = 0.6 * s_aspect + 0.4 * s_parallel

        # 4. Enclosing width preference (favor wider corridors encompassing frets over adjacent string pairs)
        s_width = min(1.0, width / 40.0)

        # Combined weighted confidence
        total_confidence = (
            0.25 * s_coverage
            + 0.45 * s_transverse
            + 0.15 * s_geom
            + 0.15 * s_width
        )

        return float(np.clip(total_confidence, 0.0, 1.0))



def detect_fretboard(
    image: np.ndarray, config: FretboardDetectorConfig | None = None
) -> FretboardDetectionResult:
    """Convenience functional wrapper for fretboard detection."""
    return FretboardDetector(config).detect(image)


def visualize_detection(
    image: np.ndarray,
    result: FretboardDetectionResult,
    show_hud: bool = True,
) -> np.ndarray:
    """Overlay detection polygon and diagnostic HUD on a frame.

    Parameters
    ----------
    image : np.ndarray
        Source BGR or grayscale image.
    result : FretboardDetectionResult
        Outcome from :meth:`FretboardDetector.detect`.
    show_hud : bool
        Whether to render the diagnostic banner.

    Returns
    -------
    np.ndarray
        Annotated BGR image.
    """
    if image is None or image.size == 0:
        return np.zeros((100, 200, 3), dtype=np.uint8)

    if len(image.shape) == 2:
        vis = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        vis = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        vis = image.copy()

    h, w = vis.shape[:2]

    if result.detected and result.polygon is not None:
        poly_pts = np.array(result.polygon, dtype=np.int32)

        # 1. Translucent polygon fill
        overlay = vis.copy()
        cv2.fillPoly(overlay, [poly_pts], (40, 210, 80))
        cv2.addWeighted(overlay, 0.28, vis, 0.72, 0, vis)

        # 2. Crisp boundary lines
        cv2.polylines(vis, [poly_pts], isClosed=True, color=(50, 240, 90), thickness=2)

        # 3. Corner markers and labels
        for idx, pt in enumerate(result.polygon):
            px, py = int(round(pt[0])), int(round(pt[1]))
            cv2.circle(vis, (px, py), 4, (0, 255, 255), -1)
            cv2.putText(
                vis,
                f"P{idx}",
                (px + 4, py - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # 4. Central longitudinal axis
        c0, c1, c2, c3 = result.polygon
        mid_start = (int((c0[0] + c3[0]) / 2), int((c0[1] + c3[1]) / 2))
        mid_end = (int((c1[0] + c2[0]) / 2), int((c1[1] + c2[1]) / 2))
        cv2.line(vis, mid_start, mid_end, (255, 200, 50), 2, cv2.LINE_AA)

    # Diagnostic HUD Banner
    if show_hud:
        box_w = min(w - 20, 320)
        box_h = 110 if result.detected else 75
        hud = vis.copy()
        cv2.rectangle(hud, (10, 10), (10 + box_w, 10 + box_h), (20, 20, 20), -1)
        cv2.addWeighted(hud, 0.82, vis, 0.18, 0, vis)
        cv2.rectangle(vis, (10, 10), (10 + box_w, 10 + box_h), (80, 80, 80), 1)

        if result.detected and result.geometry is not None:
            geom = result.geometry
            source = result.diagnostics.get("source", "classical")
            cv2.putText(
                vis,
                f"FRETBOARD DETECTED  [{source}]",
                (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                (60, 230, 90),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"Confidence: {result.confidence:.2f}",
                (20, 52),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"Orientation: {geom.orientation_deg:+.1f} deg",
                (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"Dim: {geom.estimated_length:.0f}x{geom.estimated_width:.0f}px (AR: {geom.aspect_ratio:.1f})",
                (20, 88),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"Est. Frets: {geom.fret_count_estimate}",
                (20, 106),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (220, 220, 220),
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
            reason = result.failure_reason or "unknown"
            cv2.putText(
                vis,
                f"Reason: {reason}",
                (20, 54),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                vis,
                f"Confidence: {result.confidence:.2f}",
                (20, 72),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (180, 180, 180),
                1,
                cv2.LINE_AA,
            )

    return vis
