"""Computer vision package.

Contains classical OpenCV detection, ML-based detection, hybrid detection,
and the pipeline module.  All CV/ML logic lives in Python here;
React components never touch CV code directly.
"""

from app.cv.fretboard_detector import (
    FretboardDetectionResult,
    FretboardDetector,
    FretboardDetectorConfig,
    FretboardGeometry,
    detect_fretboard,
    visualize_detection,
)
from app.cv.hybrid_detector import (
    HybridDetectorConfig,
    HybridFretboardDetector,
    detect_fretboard_hybrid,
    get_hybrid_detector,
)
from app.cv.ml_detector import (
    MLFretboardDetector,
    build_fretboard_model,
    train_fretboard_model,
)
from app.cv.pipeline import describe_pipeline, run_pipeline

__all__ = [
    # Classical
    "FretboardDetectionResult",
    "FretboardDetector",
    "FretboardDetectorConfig",
    "FretboardGeometry",
    "detect_fretboard",
    "visualize_detection",
    # Hybrid
    "HybridDetectorConfig",
    "HybridFretboardDetector",
    "detect_fretboard_hybrid",
    "get_hybrid_detector",
    # ML
    "MLFretboardDetector",
    "build_fretboard_model",
    "train_fretboard_model",
    # Pipeline
    "describe_pipeline",
    "run_pipeline",
]