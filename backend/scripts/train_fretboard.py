#!/usr/bin/env python
"""Train the ML fretboard detector on the Kaggle guitar-transcription dataset.

Usage (from the repository root)::

    cd backend
    .venv\\Scripts\\python.exe scripts\\train_fretboard.py

Options::

    --zip PATH       Path to guitar-transcription-dataset.zip
                     (default: data/raw/guitar-transcription-dataset.zip)
    --epochs INT     Training epochs (default: 15)
    --batch INT      Batch size (default: 2)
    --lr FLOAT       Learning rate (default: 5e-4)
    --device STR     cuda | cpu | auto (default: auto)
    --output PATH    Directory for model weights (default: backend/models)
    --eval           Run evaluation on test set after training

The script saves the trained model to ``backend/models/fretboard_rcnn.pt``,
which is the default path used by :class:`MLFretboardDetector` at inference time.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure we can import from the backend package
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    repo_root = BACKEND_DIR.parent
    parser = argparse.ArgumentParser(description="Train GuitarTab AI fretboard detector.")
    parser.add_argument(
        "--zip",
        type=Path,
        default=repo_root / "data" / "raw" / "guitar-transcription-dataset.zip",
        help="Path to the dataset zip archive.",
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument(
        "--device",
        choices=["cuda", "cpu", "auto"],
        default="auto",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_DIR / "models",
    )
    parser.add_argument(
        "--extract-dir",
        type=Path,
        default=repo_root / "data" / "extracted_fretboard",
        help="Directory for extracted images (avoids re-extraction).",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Evaluate on test set after training.",
    )
    return parser.parse_args()


def evaluate(weights_path: Path, test_img_dir: Path, ann_path: Path, device_str: str) -> dict:
    """Compute precision/recall/IoU on the test split."""
    import json
    import cv2
    import numpy as np
    import torch
    from app.cv.ml_detector import MLFretboardDetector

    logger.info("Evaluating on test set ...")
    detector = MLFretboardDetector(weights_path=weights_path, device_str=device_str)

    with open(ann_path) as f:
        coco = json.load(f)

    id_to_ann = {}
    for ann in coco["annotations"]:
        id_to_ann[ann["image_id"]] = ann

    tp = fp = fn = 0
    iou_scores: list[float] = []
    iou_threshold = 0.5

    for img_info in coco["images"]:
        img_path = test_img_dir / img_info["file_name"]
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            logger.warning("Cannot read %s — skipping.", img_path)
            fn += 1
            continue

        result = detector.detect(bgr)
        ann = id_to_ann.get(img_info["id"])

        if ann is None:
            if result["detected"]:
                fp += 1
            continue

        # Ground-truth bounding box
        gx, gy, gw, gh = ann["bbox"]
        gt_box = [gx, gy, gx + gw, gy + gh]

        if not result["detected"]:
            fn += 1
            continue

        pred_box = result["bbox"]
        iou = _bbox_iou(gt_box, pred_box)
        iou_scores.append(iou)

        if iou >= iou_threshold:
            tp += 1
        else:
            fp += 1

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-6, precision + recall)
    mean_iou = float(np.mean(iou_scores)) if iou_scores else 0.0

    metrics = {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_iou": round(mean_iou, 4),
        "iou_threshold": iou_threshold,
        "total_test_images": len(coco["images"]),
    }
    logger.info("Evaluation: %s", json.dumps(metrics, indent=2))
    return metrics


def _bbox_iou(a: list[float], b: list[float]) -> float:
    """Compute IoU between two [x1,y1,x2,y2] bounding boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / max(1e-6, union)


def main() -> None:
    args = parse_args()

    if not args.zip.exists():
        logger.error("Dataset zip not found: %s", args.zip)
        sys.exit(1)

    device_str = None if args.device == "auto" else args.device

    from app.cv.ml_detector import train_fretboard_model

    weights_path = train_fretboard_model(
        zip_path=args.zip,
        output_dir=args.output,
        num_epochs=args.epochs,
        batch_size=args.batch,
        learning_rate=args.lr,
        device_str=device_str,
        extract_dir=args.extract_dir,
    )
    logger.info("Training complete. Weights: %s", weights_path)

    if args.eval:
        test_img_dir = args.extract_dir / "test"
        ann_path = args.extract_dir / "annotations" / "test.json"
        if test_img_dir.exists() and ann_path.exists():
            metrics = evaluate(weights_path, test_img_dir, ann_path, device_str or "auto")
            # Save evaluation metrics
            eval_path = args.output / "eval_metrics.json"
            eval_path.write_text(json.dumps(metrics, indent=2))
            logger.info("Evaluation metrics saved -> %s", eval_path)
        else:
            logger.warning(
                "Test set not found at %s — skipping evaluation.", test_img_dir
            )


if __name__ == "__main__":
    main()
