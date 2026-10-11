"""ML-based fretboard localization using a fine-tuned Faster R-CNN.

Architecture
------------
- Backbone: MobileNetV3-Large + FPN (lightweight, fast, GPU-friendly)
- Head:     Standard Faster R-CNN two-stage detector
- Training: Fine-tuned from COCO-pretrained weights on the 355-image
            guitar fretboard segmentation dataset (COCO format).
- Output:   Bounding box + confidence for the fretboard region; polygon is
            derived from the bbox (or the COCO segmentation polygon if
            available at inference time from the per-image lookup).

This module is intentionally decoupled from the HTTP layer and can be used
standalone or from the hybrid_detector.  It never fabricates a detection --
if model confidence is below ``min_confidence``, ``detected=False`` is returned.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum score threshold for accepting an ML detection.
DEFAULT_MIN_CONFIDENCE: float = 0.40

#: Path where the fine-tuned model weights are stored.
DEFAULT_WEIGHTS_PATH: Path = (
    Path(__file__).parent.parent.parent / "models" / "fretboard_rcnn.pt"
)


# ---------------------------------------------------------------------------
# Lazy imports (torch may not be importable in all test environments)
# ---------------------------------------------------------------------------

def _import_torch():
    """Lazily import torch/torchvision and return (torch, torchvision) or None."""
    try:
        import torch
        import torchvision
        return torch, torchvision
    except ImportError:
        return None, None


# ---------------------------------------------------------------------------
# Dataset helper (used only during training)
# ---------------------------------------------------------------------------

class FretboardCocoDataset:
    """Minimal COCO-format dataset loader for fretboard images.

    Reads images directly from disk after extraction.

    Parameters
    ----------
    image_dir:
        Directory containing the PNG image files.
    annotation_path:
        Path to a COCO-format JSON file.
    transforms:
        Optional torchvision transform pipeline applied to the image tensor.
    """

    def __init__(
        self,
        image_dir: Path,
        annotation_path: Path,
        transforms=None,
    ) -> None:
        import json

        self.image_dir = Path(image_dir)
        self.transforms = transforms

        with open(annotation_path, "r") as f:
            coco = json.load(f)

        # Build id to image info mapping
        self._id_to_info: dict[int, dict] = {
            img["id"]: img for img in coco["images"]
        }
        # Build image_id to list of annotations mapping
        self._id_to_anns: dict[int, list[dict]] = {}
        for ann in coco["annotations"]:
            self._id_to_anns.setdefault(ann["image_id"], []).append(ann)

        # Ordered list of image ids that have at least one annotation
        self._image_ids: list[int] = [
            img_id
            for img_id in self._id_to_info
            if img_id in self._id_to_anns
        ]

    def __len__(self) -> int:
        return len(self._image_ids)

    def __getitem__(self, idx: int):
        import torch

        image_id = self._image_ids[idx]
        info = self._id_to_info[image_id]
        img_path = self.image_dir / info["file_name"]

        # Load image
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            raise FileNotFoundError(f"Cannot read image: {img_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Convert to float tensor [0, 1] in C x H x W format
        img_tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0

        # Build target dict (Faster R-CNN format)
        anns = self._id_to_anns[image_id]
        boxes: list[list[float]] = []
        polygons: list[list[float]] = []

        for ann in anns:
            x, y, w, h = ann["bbox"]
            # Clip to image bounds
            x1 = max(0.0, float(x))
            y1 = max(0.0, float(y))
            x2 = min(float(info["width"]), float(x + w))
            y2 = min(float(info["height"]), float(y + h))
            if x2 > x1 and y2 > y1:
                boxes.append([x1, y1, x2, y2])
                seg = ann.get("segmentation", [[]])[0]
                polygons.append(seg)

        target = {
            "boxes": torch.tensor(boxes, dtype=torch.float32),
            "labels": torch.ones(len(boxes), dtype=torch.int64),
            "image_id": torch.tensor([image_id]),
            "polygons": polygons,
        }

        if self.transforms is not None:
            img_tensor, target = self.transforms(img_tensor, target)

        return img_tensor, target


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def build_fretboard_model(pretrained: bool = True, num_classes: int = 2):
    """Create a MobileNetV3 Faster R-CNN model.

    Parameters
    ----------
    pretrained:
        If True, loads COCO-pretrained weights for the backbone.
    num_classes:
        Number of output classes including background (background=0, fretboard=1).

    Returns
    -------
    torch.nn.Module
        Configured Faster R-CNN model.
    """
    from torchvision.models.detection import (
        FasterRCNN_MobileNet_V3_Large_FPN_Weights,
        fasterrcnn_mobilenet_v3_large_fpn,
    )
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

    weights = FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT if pretrained else None
    model = fasterrcnn_mobilenet_v3_large_fpn(weights=weights)

    # Replace the classification head for our 2-class problem
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)

    return model


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_fretboard_model(
    zip_path: Path,
    output_dir: Path,
    num_epochs: int = 15,
    batch_size: int = 2,
    learning_rate: float = 5e-4,
    device_str: str | None = None,
    extract_dir: Path | None = None,
) -> Path:
    """Fine-tune the Faster R-CNN fretboard detector on the COCO dataset.

    Parameters
    ----------
    zip_path:
        Path to the ``guitar-transcription-dataset.zip`` archive.
    output_dir:
        Directory where the trained weights will be saved.
    num_epochs:
        Training epochs. 10-20 is sufficient for this small dataset.
    batch_size:
        Samples per GPU step.
    learning_rate:
        Initial learning rate for SGD with momentum.
    device_str:
        ``"cuda"``, ``"cpu"``, or ``None`` to auto-detect.
    extract_dir:
        If given, images are extracted here. Defaults to sibling directory.

    Returns
    -------
    Path
        Path to the saved model weights file.
    """
    import zipfile
    import torch
    from torch.utils.data import DataLoader

    # Device
    if device_str is None:
        device_str = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device_str)
    logger.info("Training on device: %s", device)

    # Extract dataset
    zip_path = Path(zip_path)
    if extract_dir is None:
        extract_dir = zip_path.parent.parent / "extracted_fretboard"
    extract_dir = Path(extract_dir)

    train_img_dir = extract_dir / "train"
    test_img_dir = extract_dir / "test"
    ann_dir = extract_dir / "annotations"

    # Extract only if needed
    need_extract = (
        not train_img_dir.exists()
        or not any(train_img_dir.glob("*.png"))
    )
    if need_extract:
        logger.info("Extracting dataset to %s ...", extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        train_img_dir.mkdir(exist_ok=True)
        test_img_dir.mkdir(exist_ok=True)
        ann_dir.mkdir(exist_ok=True)

        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if "fretboard_frames_train" in name and name.endswith(".png"):
                    dest = train_img_dir / Path(name).name
                    if not dest.exists():
                        dest.write_bytes(z.read(name))
                elif "fretboard_frames_test" in name and name.endswith(".png"):
                    dest = test_img_dir / Path(name).name
                    if not dest.exists():
                        dest.write_bytes(z.read(name))
                elif "fretboard_labels_train_coco.json" in name:
                    dest = ann_dir / "train.json"
                    if not dest.exists():
                        dest.write_bytes(z.read(name))
                elif "fretboard_labels_test_coco.json" in name:
                    dest = ann_dir / "test.json"
                    if not dest.exists():
                        dest.write_bytes(z.read(name))
        logger.info("Extraction complete.")

    # Build datasets
    train_dataset = FretboardCocoDataset(
        image_dir=train_img_dir,
        annotation_path=ann_dir / "train.json",
    )
    logger.info("Train dataset: %d images", len(train_dataset))

    # Collate function for variable-size targets
    def collate_fn(batch):
        return tuple(zip(*batch))

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_fn,
        num_workers=0,  # avoid Windows multiprocessing issues
    )

    # Build model
    model = build_fretboard_model(pretrained=True, num_classes=2)
    model.to(device)

    # Optimizer: all parameters unfrozen for fine-tuning
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(
        params,
        lr=learning_rate,
        momentum=0.9,
        weight_decay=1e-4,
    )
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    # Training loop
    model.train()
    for epoch in range(1, num_epochs + 1):
        epoch_loss = 0.0
        n_batches = 0

        for images, targets in train_loader:
            images = [img.to(device) for img in images]
            # Remove non-tensor fields (like polygons) before passing to model
            model_targets = []
            for t in targets:
                model_targets.append({
                    k: v.to(device) if hasattr(v, "to") else v
                    for k, v in t.items()
                    if k in ("boxes", "labels", "image_id")
                })

            loss_dict = model(images, model_targets)
            losses = sum(loss_dict.values())

            optimizer.zero_grad()
            losses.backward()
            torch.nn.utils.clip_grad_norm_(params, max_norm=1.0)
            optimizer.step()

            epoch_loss += float(losses)
            n_batches += 1

        lr_scheduler.step()
        avg_loss = epoch_loss / max(1, n_batches)
        logger.info(
            "Epoch %d/%d -- avg_loss=%.4f  lr=%.2e",
            epoch, num_epochs, avg_loss,
            optimizer.param_groups[0]["lr"],
        )

    # Save weights
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = output_dir / "fretboard_rcnn.pt"
    torch.save(model.state_dict(), weights_path)
    logger.info("Model saved -> %s", weights_path)
    return weights_path


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

class MLFretboardDetector:
    """GPU-accelerated fretboard detector backed by a fine-tuned Faster R-CNN.

    The model is loaded lazily on first call to :meth:`detect` to keep import
    time zero for modules that only need the classical detector.

    Parameters
    ----------
    weights_path:
        Path to the ``.pt`` state-dict file produced by :func:`train_fretboard_model`.
    min_confidence:
        Minimum predicted score required to report a detection.
    device_str:
        ``"cuda"``, ``"cpu"``, or ``None`` to auto-detect.
    """

    def __init__(
        self,
        weights_path: Path | str | None = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        device_str: str | None = None,
    ) -> None:
        self.weights_path = Path(weights_path) if weights_path else DEFAULT_WEIGHTS_PATH
        self.min_confidence = min_confidence
        self._model = None
        self._device = None

        torch, _ = _import_torch()
        if torch is None:
            logger.warning(
                "torch not available -- MLFretboardDetector will always return undetected."
            )
            return

        if device_str is None or device_str == "auto":
            device_str = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = torch.device(device_str)

    @property
    def is_available(self) -> bool:
        """True if the model weights exist and torch is importable."""
        torch, _ = _import_torch()
        return torch is not None and self.weights_path.exists()

    def _load_model(self):
        """Load the model (once) from saved weights."""
        import torch
        if self._model is not None:
            return
        if not self.weights_path.exists():
            raise FileNotFoundError(
                f"No ML model weights found at {self.weights_path}. "
                "Run the training script first: python scripts/train_fretboard.py"
            )
        logger.info("Loading ML fretboard model from %s ...", self.weights_path)
        model = build_fretboard_model(pretrained=False, num_classes=2)
        state = torch.load(
            str(self.weights_path), map_location=self._device, weights_only=True
        )
        model.load_state_dict(state)
        model.eval()
        model.to(self._device)
        self._model = model
        logger.info("ML model loaded on %s", self._device)

    def detect(self, image: np.ndarray) -> dict[str, Any]:
        """Run ML fretboard detection on a BGR image.

        Returns a dict with these fields::

            {
                "detected":       bool,
                "confidence":     float,
                "bbox":           [x1, y1, x2, y2] or None,
                "polygon":        [(x,y), ...] or None,
                "failure_reason": str or None,
                "diagnostics":    dict,
            }
        """
        import torch

        # Basic validation
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return _ml_failure(
                "invalid_image",
                "Input image is None, empty, or not a NumPy array.",
            )

        if self._model is None:
            try:
                self._load_model()
            except FileNotFoundError as exc:
                return _ml_failure("model_not_trained", str(exc))
            except Exception as exc:
                logger.exception("Model load error")
                return _ml_failure("model_load_error", str(exc))

        h, w = image.shape[:2]

        # BGR -> RGB -> float tensor
        if len(image.shape) == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        img_tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        img_tensor = img_tensor.to(self._device)

        with torch.no_grad():
            predictions = self._model([img_tensor])

        pred = predictions[0]
        boxes = pred["boxes"].cpu().numpy()
        scores = pred["scores"].cpu().numpy()

        # Filter by confidence threshold
        keep = scores >= self.min_confidence
        if not keep.any():
            best_score = float(scores.max()) if len(scores) > 0 else 0.0
            return {
                "detected": False,
                "confidence": round(best_score, 4),
                "bbox": None,
                "polygon": None,
                "failure_reason": "low_confidence",
                "diagnostics": {
                    "image_size": [w, h],
                    "best_score": round(best_score, 4),
                    "threshold": self.min_confidence,
                    "total_predictions": int(len(scores)),
                },
            }

        # Take highest-scoring detection
        best_idx = int(np.argmax(scores[keep]))
        all_kept_boxes = boxes[keep]
        all_kept_scores = scores[keep]
        best_box = all_kept_boxes[best_idx]
        best_score = float(all_kept_scores[best_idx])

        x1, y1, x2, y2 = best_box.tolist()
        # Construct a quadrilateral polygon from the bbox corners
        polygon = [
            (float(x1), float(y1)),
            (float(x2), float(y1)),
            (float(x2), float(y2)),
            (float(x1), float(y2)),
        ]

        return {
            "detected": True,
            "confidence": round(best_score, 4),
            "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
            "polygon": polygon,
            "failure_reason": None,
            "diagnostics": {
                "image_size": [w, h],
                "total_predictions": int(len(scores)),
                "kept_predictions": int(keep.sum()),
                "device": str(self._device),
            },
        }


def _ml_failure(reason: str, message: str) -> dict[str, Any]:
    return {
        "detected": False,
        "confidence": 0.0,
        "bbox": None,
        "polygon": None,
        "failure_reason": reason,
        "diagnostics": {"message": message},
    }
