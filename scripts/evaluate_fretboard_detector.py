"""Reproducible evaluation script for classical OpenCV fretboard localization.

Evaluates the detector on:
1. Synthetic benchmark test suite covering multiple neck orientations, wood tones,
   blur, sensor noise, and negative non-guitar objects.
2. Local real guitar frames / extracted jobs (if available).

Usage
-----
From the repository root (using the backend virtual environment)::

    backend\\.venv\\Scripts\\python.exe scripts\\evaluate_fretboard_detector.py
    backend\\.venv\\Scripts\\python.exe scripts\\evaluate_fretboard_detector.py --output-dir data/processed/evaluation
    backend\\.venv\\Scripts\\python.exe scripts\\evaluate_fretboard_detector.py --real-job-id <job_id>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2
import numpy as np

from app.cv import (
    FretboardDetector,
    FretboardDetectorConfig,
    detect_fretboard,
    visualize_detection,
)
from tests.fretboard_factory import (
    compute_polygon_iou,
    create_negative_blank,
    create_negative_noise,
    create_negative_square_box,
    create_negative_table_edge,
    create_synthetic_fretboard,
)


def create_negative_door_frame(canvas_size: tuple[int, int] = (640, 480)) -> np.ndarray:
    """Create vertical door frame / beam without frets."""
    w, h = canvas_size
    img = np.full((h, w, 3), 210, dtype=np.uint8)
    # Vertical beam: x from 260 to 340 (width 80)
    cv2.rectangle(img, (260, 20), (340, 460), (90, 100, 120), -1)
    cv2.line(img, (260, 20), (260, 460), (40, 40, 50), 2)
    cv2.line(img, (340, 20), (340, 460), (40, 40, 50), 2)
    return img


def run_synthetic_benchmark(
    output_dir: Path,
) -> dict[str, object]:
    """Run detection across synthetic positive and negative test cases."""
    synth_out = output_dir / "synthetic"
    synth_out.mkdir(parents=True, exist_ok=True)

    test_cases: list[dict] = [
        # Positive cases
        {
            "name": "horizontal_standard_rosewood",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=0.0, length=380, width=46),
        },
        {
            "name": "angled_15deg_standard",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=15.0, length=380, width=46),
        },
        {
            "name": "angled_30deg_tilted",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=30.0, length=360, width=44),
        },
        {
            "name": "angled_neg25deg_tilted",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=-25.0, length=380, width=46),
        },
        {
            "name": "angled_neg45deg_steep",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=-45.0, length=340, width=44),
        },
        {
            "name": "maple_neck_blonde_wood",
            "is_positive": True,
            "gt": create_synthetic_fretboard(
                angle_deg=10.0,
                wood_color=(140, 180, 215),
                length=380,
                width=46,
            ),
        },
        {
            "name": "narrow_neck_profile",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=5.0, length=380, width=34),
        },
        {
            "name": "wide_neck_profile",
            "is_positive": True,
            "gt": create_synthetic_fretboard(angle_deg=-10.0, length=380, width=56),
        },
        {
            "name": "motion_blurred_k5",
            "is_positive": True,
            "gt": create_synthetic_fretboard(
                angle_deg=0.0,
                blur_ksize=5,
                noise_sigma=2.0,
            ),
        },
        {
            "name": "webcam_noise_sigma4",
            "is_positive": True,
            "gt": create_synthetic_fretboard(
                angle_deg=20.0,
                noise_sigma=4.0,
            ),
        },
        {
            "name": "heavy_noise_sigma8",
            "is_positive": True,
            "gt": create_synthetic_fretboard(
                angle_deg=-15.0,
                noise_sigma=8.0,
            ),
        },
        # Negative cases (Must be rejected)
        {
            "name": "negative_table_edge",
            "is_positive": False,
            "image": create_negative_table_edge(),
        },
        {
            "name": "negative_blank_solid",
            "is_positive": False,
            "image": create_negative_blank(),
        },
        {
            "name": "negative_random_noise",
            "is_positive": False,
            "image": create_negative_noise(),
        },
        {
            "name": "negative_square_box",
            "is_positive": False,
            "image": create_negative_square_box(),
        },
        {
            "name": "negative_door_frame",
            "is_positive": False,
            "image": create_negative_door_frame(),
        },
    ]

    detector = FretboardDetector()

    results: list[dict] = []
    latencies: list[float] = []
    ious: list[float] = []
    angle_errors: list[float] = []

    tp = 0
    fp = 0
    tn = 0
    fn = 0

    print("\n" + "=" * 80)
    print("  SYNTHETIC FRETBOARD LOCALIZATION BENCHMARK")
    print("=" * 80)
    print(f"{'Case Name':<32} {'Expected':<10} {'Detected':<10} {'Conf':<7} {'IoU':<7} {'Frets':<7} {'Status'}")
    print("-" * 80)

    for case in test_cases:
        name = case["name"]
        is_pos = case["is_positive"]

        if is_pos:
            gt = case["gt"]
            image = gt.image
            expected = "Positive"
        else:
            image = case["image"]
            expected = "Negative"

        t0 = time.perf_counter()
        res = detector.detect(image)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(latency_ms)

        # Render and save debug visualization
        vis = visualize_detection(image, res)
        debug_path = synth_out / f"{name}.jpg"
        cv2.imwrite(str(debug_path), vis)

        iou = None
        ang_err = None

        if is_pos:
            if res.detected and res.polygon is not None:
                tp += 1
                status = "PASS (TP)"
                iou = compute_polygon_iou(case["gt"].polygon, res.polygon)
                ious.append(iou)
                if res.geometry is not None:
                    ang_diff = abs(res.geometry.orientation_deg - case["gt"].angle_deg)
                    if ang_diff > 90.0:
                        ang_diff = abs(180.0 - ang_diff)
                    ang_err = ang_diff
                    angle_errors.append(ang_err)
            else:
                fn += 1
                status = "FAIL (FN)"
        else:
            if res.detected:
                fp += 1
                status = "FAIL (FP)"
            else:
                tn += 1
                status = "PASS (TN)"

        fret_count_str = str(res.geometry.fret_count_estimate) if res.geometry else "-"
        iou_str = f"{iou:.3f}" if iou is not None else "-"

        print(
            f"{name:<32} {expected:<10} {str(res.detected):<10} {res.confidence:<7.2f} "
            f"{iou_str:<7} {fret_count_str:<7} {status}"
        )

        results.append({
            "name": name,
            "expected_positive": is_pos,
            "detected": res.detected,
            "confidence": res.confidence,
            "iou": iou,
            "angle_error_deg": ang_err,
            "fret_count": res.geometry.fret_count_estimate if res.geometry else 0,
            "failure_reason": res.failure_reason,
            "latency_ms": round(latency_ms, 2),
            "debug_image": str(debug_path.relative_to(ROOT)),
        })

    total = len(test_cases)
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    mean_iou = float(np.mean(ious)) if ious else 0.0
    mean_latency = float(np.mean(latencies))
    mean_ang_err = float(np.mean(angle_errors)) if angle_errors else 0.0

    print("-" * 80)
    print(f"Summary: TP={tp}, TN={tn}, FP={fp}, FN={fn} (Total={total})")
    print(f"Accuracy:  {accuracy * 100:.1f}%")
    print(f"Precision: {precision * 100:.1f}%")
    print(f"Recall:    {recall * 100:.1f}%")
    print(f"Mean IoU (Positive cases): {mean_iou:.3f}")
    print(f"Mean Orientation Error:    {mean_ang_err:.2f}°")
    print(f"Mean Latency per Frame:    {mean_latency:.1f} ms")
    print(f"Debug overlays saved to:   {synth_out.relative_to(ROOT)}")
    print("=" * 80)

    return {
        "dataset": "synthetic_benchmark",
        "total_cases": total,
        "true_positives": tp,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "mean_iou_positives": round(mean_iou, 4),
        "mean_orientation_error_deg": round(mean_ang_err, 2),
        "mean_latency_ms": round(mean_latency, 2),
        "cases": results,
    }


def find_local_real_frames(job_id: str | None = None, custom_dir: Path | None = None) -> list[Path]:
    """Search for real frames in local processed jobs or custom folders."""
    frames: list[Path] = []

    if custom_dir and custom_dir.is_dir():
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            frames.extend(custom_dir.glob(ext))

    processed_dir = ROOT / "data" / "processed"
    if job_id:
        target = processed_dir / job_id / "frames"
        if target.is_dir():
            frames.extend(sorted(target.glob("*.jpg")))
    elif processed_dir.is_dir():
        for job_folder in processed_dir.iterdir():
            if job_folder.is_dir() and not job_folder.name.startswith("."):
                frame_sub = job_folder / "frames"
                if frame_sub.is_dir():
                    frames.extend(sorted(frame_sub.glob("*.jpg")))

    raw_dir = ROOT / "data" / "raw"
    if raw_dir.is_dir():
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            frames.extend(raw_dir.glob(ext))

    return frames


def run_real_footage_evaluation(
    real_frames: list[Path], output_dir: Path
) -> dict[str, object]:
    """Run detector on real guitar frames if available."""
    real_out = output_dir / "real"
    real_out.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("  REAL GUITAR FOOTAGE EVALUATION")
    print("=" * 80)

    detector = FretboardDetector()
    results: list[dict] = []
    latencies: list[float] = []
    detected_count = 0

    print(f"{'Frame Name':<32} {'Detected':<10} {'Conf':<7} {'Frets':<7} {'Orientation':<12} {'Latency'}")
    print("-" * 80)

    for p in real_frames:
        img = cv2.imread(str(p))
        if img is None:
            continue

        t0 = time.perf_counter()
        res = detector.detect(img)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat_ms)

        vis = visualize_detection(img, res)
        debug_p = real_out / f"debug_{p.name}"
        cv2.imwrite(str(debug_p), vis)

        if res.detected:
            detected_count += 1
            frets = str(res.geometry.fret_count_estimate) if res.geometry else "-"
            orient = f"{res.geometry.orientation_deg:+.1f}°" if res.geometry else "-"
        else:
            frets = "-"
            orient = "-"

        print(
            f"{p.name:<32} {str(res.detected):<10} {res.confidence:<7.2f} "
            f"{frets:<7} {orient:<12} {lat_ms:.1f}ms"
        )

        results.append({
            "frame": p.name,
            "detected": res.detected,
            "confidence": res.confidence,
            "geometry": res.geometry.to_dict() if res.geometry else None,
            "failure_reason": res.failure_reason,
            "latency_ms": round(lat_ms, 2),
            "debug_image": str(debug_p.relative_to(ROOT)),
        })

    rate = (detected_count / len(real_frames)) * 100.0 if real_frames else 0.0
    print("-" * 80)
    print(f"Evaluated {len(real_frames)} real frame(s). Detected fretboard in {detected_count} ({rate:.1f}%).")
    print(f"Debug overlays saved to: {real_out.relative_to(ROOT)}")
    print("=" * 80)

    return {
        "dataset": "real_guitar_footage",
        "total_frames": len(real_frames),
        "detected_count": detected_count,
        "detection_rate_pct": round(rate, 2),
        "mean_latency_ms": round(float(np.mean(latencies)), 2) if latencies else 0.0,
        "frames": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate classical OpenCV fretboard localization.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "evaluation",
        help="Directory where evaluation metrics and debug overlays are saved.",
    )
    parser.add_argument(
        "--real-frames-dir",
        type=Path,
        default=None,
        help="Optional directory containing real guitar video frames.",
    )
    parser.add_argument(
        "--real-job-id",
        type=str,
        default=None,
        help="Job id of an uploaded & processed video to evaluate.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run Synthetic Benchmark
    synthetic_summary = run_synthetic_benchmark(args.output_dir)

    # 2. Check for local real guitar footage
    real_frames = find_local_real_frames(job_id=args.real_job_id, custom_dir=args.real_frames_dir)

    report_payload: dict[str, object] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "synthetic_evaluation": synthetic_summary,
    }

    if real_frames:
        real_summary = run_real_footage_evaluation(real_frames, args.output_dir)
        report_payload["real_footage_evaluation"] = real_summary
    else:
        print("\n" + "=" * 80)
        print("  REAL FOOTAGE STATUS: NOT LOCALLY AVAILABLE")
        print("=" * 80)
        print("Note: No real guitar video files or extracted frames are present locally in the repository.")
        print("Synthetic test success must NOT be mistaken for real-world detection accuracy.")
        print("\nHow to test on your own guitar video:")
        print("1. Start the app:")
        print("   Terminal 1: cd backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000")
        print("   Terminal 2: cd frontend && npm run dev")
        print("2. Upload your guitar video via the web UI (http://localhost:5173)")
        print("3. Process frames via: POST http://localhost:8000/api/jobs/<job_id>/process")
        print("4. Inspect localized fretboard:")
        print("   GET http://localhost:8000/api/jobs/<job_id>/frames/0/fretboard")
        print("5. View visual debug overlay directly in your browser:")
        print("   GET http://localhost:8000/api/jobs/<job_id>/frames/0/fretboard-debug")
        print("6. Run this evaluation script against the uploaded job:")
        print("   backend\\.venv\\Scripts\\python.exe scripts\\evaluate_fretboard_detector.py --real-job-id <job_id>")
        print("=" * 80 + "\n")
        report_payload["real_footage_evaluation"] = {
            "status": "unavailable",
            "message": "No local real guitar video or extracted frames found in repository.",
        }

    # Save structured evaluation report JSON
    report_file = args.output_dir / "evaluation_report.json"
    report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"Full evaluation report written to: {report_file.relative_to(ROOT)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
