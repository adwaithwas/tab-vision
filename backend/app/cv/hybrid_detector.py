"""Hybrid fretboard detector: ML-first with classical OpenCV fallback.

Strategy
--------
1. If trained ML model weights exist, run the Faster R-CNN detector.
   - If ML confidence >= ``ml_threshold``, return the ML result directly.
   - If ML confidence is between ``ml_threshold`` and ``blend_threshold``,
     merge ML bbox with classical polygon validation.
2. Fall back to the classical OpenCV detector (always runs if ML is absent
   or uncertain).
3. Return ``detected=False`` with detailed diagnostics when neither
   produces a credible result.

This module is the primary public entry point for all API routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.cv.fretboard_detector import (
    FretboardDetectionResult,
    FretboardDetectorConfig,
    FretboardGeometry,
    detect_fretboard,
)
from app.cv.ml_detector import MLFretboardDetector


@dataclass(frozen=True)
class HybridDetectorConfig:
    """Configuration for the hybrid detection strategy."""

    #: ML confidence above which we trust the ML result entirely.
    ml_high_threshold: float = 0.60
    #: ML confidence above which we attempt ML+classical blending.
    ml_blend_threshold: float = 0.40
    #: Classical detector configuration (passed through unchanged).
    classical_config: FretboardDetectorConfig = field(
        default_factory=FretboardDetectorConfig
    )
    #: Minimum confidence to prefer ML over classical in a tie.
    prefer_ml_above: float = 0.50


class HybridFretboardDetector:
    """Combined ML + classical fretboard detector.

    The ML model is loaded lazily. When no weights exist, the detector
    transparently degrades to classical-only mode — no errors raised.

    Parameters
    ----------
    weights_path:
        Explicit path to the ML model weights. ``None`` uses the default
        location (``backend/models/fretboard_rcnn.pt``).
    config:
        Hybrid strategy configuration.
    """

    def __init__(
        self,
        weights_path: Path | str | None = None,
        config: HybridDetectorConfig | None = None,
    ) -> None:
        self.config = config or HybridDetectorConfig()
        self._ml = MLFretboardDetector(weights_path=weights_path)

    @property
    def ml_available(self) -> bool:
        """True if trained ML weights exist."""
        return self._ml.is_available

    def detect(self, image: np.ndarray) -> FretboardDetectionResult:
        """Detect fretboard using ML-first, classical-fallback strategy.

        Parameters
        ----------
        image : np.ndarray
            BGR or grayscale input image (uint8).

        Returns
        -------
        FretboardDetectionResult
            Structured localization outcome.
        """
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return FretboardDetectionResult(
                detected=False,
                confidence=0.0,
                polygon=None,
                geometry=None,
                failure_reason="invalid_image_type",
                diagnostics={"error": "Input must be a valid NumPy ndarray."},
            )

        ml_result: dict[str, Any] | None = None
        classical_result: FretboardDetectionResult | None = None

        # -- ML pass ----------------------------------------------------------
        if self.ml_available:
            ml_result = self._ml.detect(image)

            # High-confidence ML result: return directly
            if (
                ml_result["detected"]
                and ml_result["confidence"] >= self.config.ml_high_threshold
            ):
                return self._ml_to_detection_result(ml_result, source="ml")

        # -- Classical pass ---------------------------------------------------
        classical_result = detect_fretboard(image, self.config.classical_config)

        # -- Merge / choose best ----------------------------------------------
        if ml_result is not None and ml_result["detected"]:
            ml_conf = ml_result["confidence"]
            cl_conf = classical_result.confidence if classical_result.detected else 0.0

            # Both found something: pick higher confidence
            if classical_result.detected:
                if ml_conf >= cl_conf or ml_conf >= self.config.prefer_ml_above:
                    return self._ml_to_detection_result(ml_result, source="ml+classical")
                else:
                    return _mark_source(classical_result, "classical+ml")

            # Only ML detected: accept if above blend threshold
            if ml_conf >= self.config.ml_blend_threshold:
                return self._ml_to_detection_result(ml_result, source="ml_only")

        # Classical result wins (or both failed)
        if classical_result.detected:
            return _mark_source(classical_result, "classical")

        # Both failed — return the one with higher (partial) confidence
        ml_conf = (ml_result or {}).get("confidence", 0.0) or 0.0
        cl_conf = classical_result.confidence if classical_result else 0.0

        if ml_conf > cl_conf and ml_result is not None:
            return self._ml_to_detection_result(ml_result, source="ml_failed")

        # Return classical failure (most informative)
        return classical_result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ml_to_detection_result(
        ml: dict[str, Any], source: str
    ) -> FretboardDetectionResult:
        """Convert an ML detector dict to a FretboardDetectionResult."""
        polygon = ml.get("polygon")

        geometry: FretboardGeometry | None = None
        if polygon and len(polygon) == 4:
            (x1, y1), (x2, _), (x3, y3), (x4, _) = polygon
            width = abs(x2 - x1)
            height = abs(y3 - y1)
            length = max(width, height)
            narrow = min(width, height)
            aspect = length / max(1.0, narrow)
            import math
            orientation = math.degrees(math.atan2(y3 - y1, x3 - x1)) if height > 0 else 0.0
            geometry = FretboardGeometry(
                orientation_deg=round(orientation, 2),
                estimated_length=round(length, 2),
                estimated_width=round(narrow, 2),
                aspect_ratio=round(aspect, 2),
                fret_count_estimate=0,  # Not estimated by detection head
                transverse_edge_density=0.0,
            )

        diagnostics = dict(ml.get("diagnostics", {}))
        diagnostics["source"] = source

        return FretboardDetectionResult(
            detected=ml["detected"],
            confidence=ml["confidence"],
            polygon=polygon,
            geometry=geometry,
            failure_reason=ml.get("failure_reason"),
            diagnostics=diagnostics,
        )


def _mark_source(result: FretboardDetectionResult, source: str) -> FretboardDetectionResult:
    """Return a copy of the result with ``source`` added to diagnostics."""
    diag = dict(result.diagnostics)
    diag["source"] = source
    return FretboardDetectionResult(
        detected=result.detected,
        confidence=result.confidence,
        polygon=result.polygon,
        geometry=result.geometry,
        failure_reason=result.failure_reason,
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Convenience singleton (avoids re-loading the model on every request)
# ---------------------------------------------------------------------------

_DETECTOR: HybridFretboardDetector | None = None


def get_hybrid_detector() -> HybridFretboardDetector:
    """Return the process-wide singleton HybridFretboardDetector."""
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = HybridFretboardDetector()
    return _DETECTOR


def detect_fretboard_hybrid(image: np.ndarray) -> FretboardDetectionResult:
    """Convenience wrapper: detect fretboard using the singleton hybrid detector."""
    return get_hybrid_detector().detect(image)
