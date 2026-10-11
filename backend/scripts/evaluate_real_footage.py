#!/usr/bin/env python
"""Evaluate the hybrid fretboard detector on the real guitar footage frames.

Usage (from the repository root, after training)::

    cd backend
    .venv\\Scripts\\python.exe scripts\\evaluate_real_footage.py

Runs detection on the 9 frames already extracted from test video.mp4,
saves annotated debug overlays alongside, and prints a summary table.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    import cv2
    from app.cv import detect_fretboard_hybrid, visualize_detection

    # Find the job with extracted frames
    processed_dir = REPO_ROOT / "data" / "processed"
    frame_dirs = [
        d for d in processed_dir.iterdir()
        if d.is_dir() and (d / "frames").exists()
    ]

    if not frame_dirs:
        logger.error("No processed frame directories found in %s", processed_dir)
        sys.exit(1)

    job_dir = frame_dirs[0]
    frames_dir = job_dir / "frames"
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    logger.info("Found %d frames in %s", len(frame_files), job_dir.name)

    # Output directory
    out_dir = processed_dir / "evaluation" / "real_hybrid"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    print(f"\n{'Frame':<25}  {'Detected':<9}  {'Confidence':<12}  {'Source':<20}  {'Reason'}")
    print("-" * 90)

    for frame_path in frame_files:
        bgr = cv2.imread(str(frame_path))
        if bgr is None:
            logger.warning("Cannot read %s", frame_path)
            continue

        result = detect_fretboard_hybrid(bgr)
        source = result.diagnostics.get("source", "unknown")

        print(
            f"{frame_path.name:<25}  "
            f"{'YES' if result.detected else 'NO':<9}  "
            f"{result.confidence:<12.4f}  "
            f"{source:<20}  "
            f"{result.failure_reason or '-'}"
        )

        # Save debug overlay
        overlay = visualize_detection(bgr, result)
        out_path = out_dir / f"debug_{frame_path.stem}.jpg"
        cv2.imwrite(str(out_path), overlay)

        # Collect metadata
        entry = {
            "frame": frame_path.name,
            "detected": result.detected,
            "confidence": result.confidence,
            "failure_reason": result.failure_reason,
            "source": source,
            "polygon": [list(pt) for pt in result.polygon] if result.polygon else None,
        }
        if result.geometry:
            entry["geometry"] = result.geometry.to_dict()
        results.append(entry)

    detected_count = sum(1 for r in results if r["detected"])
    print("-" * 90)
    print(f"\nTotal: {len(results)} frames  |  Detected: {detected_count}  |  Missed: {len(results) - detected_count}")
    print(f"Detection rate: {detected_count / max(1, len(results)):.1%}")
    print(f"\nDebug overlays saved to: {out_dir}")

    # Save JSON report
    report = {
        "frames_evaluated": len(results),
        "detected": detected_count,
        "detection_rate": detected_count / max(1, len(results)),
        "results": results,
    }
    report_path = out_dir / "evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    logger.info("Report saved -> %s", report_path)


if __name__ == "__main__":
    main()
