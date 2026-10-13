# GuitarTab AI — Computer-Vision Model Evaluation Report

- **Repository:** `D:\code\PROJECTS\tab creator`
- **Report file:** `MODEL_EVALUATION_REPORT.md`
- **Model under evaluation:** `backend/models/fretboard_rcnn.pt`
- **Architecture:** `fasterrcnn_mobilenet_v3_large_fpn` (MobileNetV3-Large + FPN backbone, 2-class Faster R-CNN head)
- **Evaluation set:** held-out `data/extracted_fretboard/test/` (105 frames), `annotations/test.json`
- **Audit type:** Read-only, standalone evaluation of the **existing** checkpoint. No training, no fine-tuning, no source modification.
- **Date of evaluation:** 2026-10-12
- **Status:** ✅ Evaluation performed successfully with genuine, artifact-backed metrics.

### Evidence classification legend

| Tag | Meaning |
|---|---|
| `[V-S]` | Verified from source code / repository text |
| `[V-A]` | Verified by inspecting an artifact on disk |
| `[R-X]` | Verified by execution performed **in this evaluation** |
| `[H-A]` | Supported by a pre-existing artifact from an earlier run |
| `[INF]` | Inferred with stated reasoning |
| `[UNK]` | Unknown / not verified |

---

## 1. Executive Summary

The existing `fretboard_rcnn.pt` checkpoint was evaluated, standalone, on the full held-out 105-frame test split using the project's own model implementation and preprocessing. `[R-X]`

**Headline result (confidence ≥ 0.40, IoU ≥ 0.50):** Precision **1.0000**, Recall **0.9048**, F1 **0.9500**, with a mean IoU of **0.7154** on matched detections. `[R-X]`

Three interpretations matter for an academic audience:

1. **Detection confidence is strong for most frames.** On 95/105 frames the top detection scored ≥ 0.40; on 70/105 it scored ≥ 0.90. Median IoU is 0.725. `[R-X]`
2. **Box overlap is "loose-but-adequate", not tight.** No frame reaches IoU ≥ 0.90; only 38/105 reach IoU ≥ 0.75. At a strict IoU ≥ 0.75 operating point recall collapses to 0.333. This reflects approximate region localization rather than precise edges. `[R-X]`
3. **Precision = 1.0 is structurally trivial and must NOT be presented as robustness.** The test set contains **no background/negative images** and exactly **one ground-truth box per image**, and the model always proposes a top-1 box. Precision therefore *cannot* drop below 1.0 unless a prediction falls below IoU 0.5 — which none did (minimum IoU = 0.531). `[R-X]` `[INF]`

The 10 "misses" are almost entirely **confidence** failures (not localization failures), concentrated in one video sequence: 9 of 10 are from sequence `32_*`, and several of those have good boxes (IoU 0.815, 0.795) but low scores (0.10–0.40). `[R-X]`

No claim of "good" or "poor" overall performance is made here; the numbers are reported with their operating point and their structural limitations.

---

## 2. Evaluation Configuration (Step 1 — Setup Verification)

### 2.1 Files read for verification `[V-S]`

- `backend/scripts/train_fretboard.py` — defines `evaluate(weights_path, test_img_dir, ann_path, device_str)`.
- `backend/app/cv/ml_detector.py` — defines `MLFretboardDetector`, `build_fretboard_model`, and `FretboardCocoDataset`.

### 2.2 Verified test image directory and annotation JSON `[V-S]` `[V-A]`

| Item | Value | Source |
|---|---|---|
| Test images | `data/extracted_fretboard/test/` — **105** PNG files | disk enumeration |
| Test annotations | `data/extracted_fretboard/annotations/test.json` | `train_fretboard.py:190` |
| Train images | `data/extracted_fretboard/train/` — **250** PNG files | disk enumeration |
| Train annotations | `data/extracted_fretboard/annotations/train.json` | `ml_detector.py` extraction logic |

These match the training script's `--extract-dir` default (`data/extracted_fretboard`) and its `test_img_dir`/`ann_path` (`evaluate` call at `train_fretboard.py:189-190`). `[V-S]`

### 2.3 Target class and annotation semantics (verified, not assumed) `[V-A]`

- `categories` = `[{"id": 1, "name": "fret"}]` in **both** train and test JSON. `[V-A]`
- **Exactly one annotation per image** (train 250/250, test 105/105); all `category_id=1`, all `iscrowd=0`. `[V-A]`
- Every annotation is a **polygon segmentation** plus a COCO `bbox` `[x, y, w, h]`:
  - Test: **all 105 are 4-point polygons** (quadrilaterals).
  - Train: 221 four-point, 24 five-point, 4 six-point, 1 eight-point — i.e., simple convex region polygons.
- **Geometric meaning:** the polygon encloses a **single elongated region** — test bbox median `695.6 × 93.5 px` on a `1920 × 1080` image, **median aspect ratio 7.57:1**. This is the **fretboard/neck region**, **not individual fret wires** (which would appear as many separate thin regions per image). `[V-A]` `[INF]`
- ⚠️ **Naming caveat:** despite the class label literally being `"fret"`, the annotated geometry is the **fretboard region**. The model predicts this region. It does **not** detect individual frets. `[V-A]` `[INF]`

### 2.4 Class-label / coordinate consistency check `[V-S]` `[V-A]`

- Training (`FretboardCocoDataset.__getitem__`) assigns `labels = torch.ones(...)` (label `1`) for every box, and builds `boxes` as `[x1, y1, x2, y2]` from `ann["bbox"]` clipped to image bounds. Model `num_classes=2` (0 = background, 1 = fret-region). `[V-S]`
- Evaluation (`train_fretboard.py::evaluate`) converts GT to `[x, y, x+w, y+h]` and compares to the predicted `[x1,y1,x2,y2]` box. Consistent coordinate convention (`x1,y1,x2,y2`). `[V-S]`
- **No class-label mismatch** was found: single category, label 1 throughout, consistent with the 2-class head. `[V-S]`
- The GT polygons were **not** required for comparison: the COCO `bbox` field (axis-aligned bounding box of the region) was used, identical to the training script. `[V-S]`

### 2.5 Split separation check `[R-X]` `[V-A]`

- Filename intersection between train and test = **0**. Train filenames `0_*`–`24_*`; test filenames `28_*`–`34_*`. `[V-A]`
- All 355 referenced files exist on disk; no missing/extra files. `[R-X]`
- **Conclusion:** the test split is genuinely disjoint from the training images. `[R-X]`

### 2.6 Distribution note (validity-relevant) `[R-X]`

| Statistic | Train | Test |
|---|---|---|
| Median bbox aspect ratio (w/h) | 3.85 | 7.57 |
| bbox height min–max | 76–308 px | 79–154 px |
| Polygon points | 4–8 | 4 only |

The test regions are systematically **wider/thinner** than training regions. This is a real train→test distribution shift worth stating in the presentation. `[R-X]`

---

## 3. Model & Checkpoint [V-A]

| Property | Value |
|---|---|
| Path | `backend/models/fretboard_rcnn.pt` |
| Size | **76,020,762 bytes** |
| SHA256 | `63994486A524738ACACDA4E40CF282741B5FAC0185EABE48F3648DBD10281835` |
| Format | pure `state_dict` (no embedded metadata) |
| Loader | `MLFretboardDetector._load_model()` → `build_fretboard_model(pretrained=False, num_classes=2)` + `load_state_dict(weights_only=True)` |
| Device used | **cuda** (torch 2.6.0+cu124, torchvision 0.21.0+cu124) |
| Preprocessing | BGR→RGB, `permute(2,0,1)`, `float()/255.0`; **no resize/normalisation in user code** (Faster R-CNN resizes internally to min-size 800 / max-size 1333) `[V-S]` |

The checkpoint was **not** modified, retrained, or altered. `[R-X]`

---

## 4. Methodology — Exact Procedure (Step 2)

1. Loaded `test.json` (105 images, 105 annotations).
2. Instantiated the **existing** detector: `MLFretboardDetector(weights_path=backend/models/fretboard_rcnn.pt, device_str=None)` (auto → CUDA). `[V-S]`
3. Ran inference **once per image** in `eval` mode with `torch.no_grad()` (inside `MLFretboardDetector.detect`), using its exact preprocessing. `[V-S]`
4. Captured the **top-1** detection (highest-scoring box) and its confidence for every image, then applied thresholds analytically.
5. Ground truth = COCO `bbox` `[x,y,w,h]` → `[x1,y1,x2,y2]`, identical to the project's own `evaluate()`.
6. Matching rule: a top-1 prediction matches a GT box if **IoU ≥ 0.50** (the project's threshold). Confidence gate: **score ≥ 0.40** (the class default `DEFAULT_MIN_CONFIDENCE`).
7. Reported the primary metrics under the project's convention and additionally under the standard convention (no difference here), plus IoU/confidence sweeps and VOC-style AP.
8. **Cross-checked** the primary metrics by directly calling the project's `train_fretboard.evaluate()` — results matched **exactly**. `[R-X]`

**One prediction and one ground-truth box per image** (no background images), so:
- FP can only arise from a top box with IoU < 0.50;
- FN can only arise from a below-threshold top box.

### Reproducible commands used

```powershell
# from repo root; temporary scripts live OUTSIDE the repo (Temp\opencode)
backend\.venv\Scripts\python.exe C:\Users\PC\AppData\Local\Temp\opencode\gt_analysis.py     # dataset/annotation verification
backend\.venv\Scripts\python.exe C:\Users\PC\AppData\Local\Temp\opencode\ml_eval.py         # standalone ML evaluation
backend\.venv\Scripts\python.exe C:\Users\PC\AppData\Local\Temp\opencode\confirm_eval.py    # calls project evaluate() to cross-check
```

The **equivalent in-repo one-liner** (no temp file needed) would be:

```powershell
cd backend
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; from train_fretboard import evaluate; print(evaluate(Path('models/fretboard_rcnn.pt'), Path('../data/extracted_fretboard/test'), Path('../data/extracted_fretboard/annotations/test.json'), 'auto'))"
```

---

## 5. Results (Step 2 output)

### 5.1 Primary metrics — reproduces `train_fretboard.evaluate()` (conf ≥ 0.40, IoU ≥ 0.50) `[R-X]`

| Metric | Value |
|---|---|
| Images evaluated | **105 / 105** (0 read failures) |
| IoU threshold | **0.50** |
| Confidence threshold | **0.40** |
| True Positives | **95** |
| False Positives | **0** |
| False Negatives | **10** |
| Precision | **1.0000** |
| Recall | **0.9048** |
| F1-score | **0.9500** |
| Mean IoU (matched/TP) | **0.7154** (n = 95) |

Cross-check: the project's own `evaluate()` returned `{'tp': 95, 'fp': 0, 'fn': 10, 'precision': 1.0, 'recall': 0.9048, 'f1': 0.95, 'mean_iou': 0.7154, 'iou_threshold': 0.5, 'total_test_images': 105}` — **identical**. `[R-X]`

### 5.2 IoU distribution (all 105) `[R-X]`

| | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|
| IoU | 0.531 | 0.666 | **0.725** | 0.772 | 0.885 |

- Frames with IoU ≥ 0.75: **38/105**
- Frames with IoU ≥ 0.90: **0/105**

### 5.3 Confidence distribution (all 105) `[R-X]`

| | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|
| top-1 score | 0.097 | 0.822 | **0.962** | 0.987 | 0.996 |

- score ≥ 0.90: **70/105** · score ≥ 0.50: **91/105** · score ≥ 0.40: **95/105**

### 5.4 Detection at stricter IoU (conf ≥ 0.40, standard convention) `[R-X]`

| IoU threshold | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| ≥ 0.30 | 95 | 0 | 10 | 1.0000 | 0.9048 | 0.9500 |
| ≥ 0.50 | 95 | 0 | 10 | 1.0000 | 0.9048 | 0.9500 |
| ≥ 0.75 | 35 | 60 | 70 | 0.3684 | 0.3333 | 0.3500 |

### 5.5 Confidence sweep (IoU ≥ 0.50, standard convention) `[R-X]`

| conf ≥ | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.05 | 105 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| 0.10 | 104 | 0 | 1 | 1.0000 | 0.9905 | 0.9952 |
| 0.20 | 100 | 0 | 5 | 1.0000 | 0.9524 | 0.9756 |
| 0.30 | 97 | 0 | 8 | 1.0000 | 0.9238 | 0.9604 |
| **0.40** | **95** | **0** | **10** | **1.0000** | **0.9048** | **0.9500** |
| 0.50 | 91 | 0 | 14 | 1.0000 | 0.8667 | 0.9286 |
| 0.70 | 85 | 0 | 20 | 1.0000 | 0.8095 | 0.8947 |
| 0.90 | 70 | 0 | 35 | 1.0000 | 0.6667 | 0.8000 |

### 5.6 Average Precision (VOC all-point interpolation; single class) `[R-X]`

| Metric | Value | Notes |
|---|---|---|
| AP@0.50 | **1.0000** | Inflated by single-positive-per-image design (see §7) |
| AP@0.75 | **0.2272** | Reflects loose box localization |

AP method: predictions ranked by top-1 confidence; a prediction is a TP if its IoU with the image's GT ≥ threshold; precision–recall curve integrated with all-point interpolation. Because the stride-0.10 confidence sweep already shows recall = 1.0 at conf ≥ 0.05 with zero below-IoU-0.5 boxes, AP@0.50 saturates trivially. `[R-X]` `[INF]`

---

## 6. Error Analysis (Step 2 output)

At conf ≥ 0.40, IoU ≥ 0.50, the 10 non-TP cases are **all `missed_low_confidence`** (score < 0.40); there are **no localization-miss FPs**. `[R-X]`

The 10 missed frames, with their (good) IoUs showing localization was often still correct: `[R-X]`

| Frame | score | IoU |
|---|---|---|
| 32_4.png | 0.097 | 0.576 |
| 32_3.png | 0.100 | 0.662 |
| 31_1.png | 0.117 | **0.815** |
| 32_7.png | 0.118 | 0.702 |
| 32_8.png | 0.163 | 0.737 |
| 32_1.png | 0.253 | 0.667 |
| 32_6.png | 0.283 | **0.772** |
| 32_11.png | 0.292 | 0.731 |
| 32_12.png | 0.356 | 0.742 |
| 32_9.png | 0.399 | 0.795 |

**Error category breakdown (thr 0.40 / IoU 0.50):** `[R-X]`

- `true_positive`: 95
- `missed_low_confidence`: 10
- `localization_miss (IoU<0.5)`: 0
- `read_failure`: 0

**Pattern:** 9 of the 10 misses come from sequence **`32_*`** (plus `31_1`). This clustering suggests that one source video is under-represented or visually out-of-distribution relative to training (consistent with the aspect-ratio shift in §2.6), rather than a uniform weakness. `[R-X]` `[INF]`

**Worst-IoU frames** (all still above 0.50): `34_7 (0.531)`, `33_12 (0.540)`, `33_8 (0.544)`, `33_11 (0.551)`, `32_4 (0.576)` — sequences `32–34` dominate the low end, again consistent with the train/test shift. `[R-X]`

---

## 7. Validity Warnings & Caveats (must accompany any citation of these numbers)

1. **Precision = 1.0 and FP = 0 are structurally trivial.** The test split has **no negative (no-guitar) images** and exactly **one GT box per image**, and the detector always emits a top-1 box. Precision can only fall if a top box has IoU < 0.5; none did (min IoU 0.531). These numbers therefore say **nothing** about the model's false-positive rate in real, cluttered video. `[R-X]` `[INF]`
2. **AP@0.50 = 1.0 is likewise inflated** by the same single-positive design. Treat **AP@0.75 = 0.2272** and the IoU distribution as the more honest localization signal. `[R-X]` `[INF]`
3. **The class is named `"fret"` but annotates the fretboard region** (one elongated quadrilateral per frame). Do not describe this model as detecting individual frets, strings, or notes. `[V-A]` `[INF]`
4. **Box tightness is approximate and partly annotation-driven.** Only 38/105 frames reach IoU ≥ 0.75 and none reach 0.90. Training GT heights vary 76–308 px (aspect ratio 2.34–8.82), indicating inconsistent box tightness in the source annotations. IoU here should not be read as precise edge accuracy. `[R-X]` `[V-A]`
5. **Train→test distribution shift exists** (median aspect ratio 3.85 → 7.57; test heights capped at 154 px). The 10 confidence misses cluster in one sequence, reinforcing this. `[R-X]`
6. **Single deterministic pass.** Inference was run once in `eval` mode on CUDA; no averaging over seeds. FRCNN inference is deterministic in eval mode; CUDA may introduce negligible nondeterminism. `[INF]`
7. **The model's training quality cannot be fully audited** because the checkpoint contains no embedded metadata (epochs, loss, dataset hash) and no training log exists. `[V-A]` `[UNK]`

---

## 8. Comparison With Existing Results (kept strictly separate — Step 3)

> ⚠️ The classical-detector figures below belong to a **different algorithm** (OpenCV geometric detector). They are **not** attributable to the `fretboard_rcnn.pt` ML checkpoint. `[H-A]`

| Result set | Algorithm | Dataset | Outcome | Source |
|---|---|---|---|---|
| Classical — synthetic | OpenCV geometric (`FretboardDetector`) | 16 synthetic cases | 16/16 correct; mean IoU **0.9029**; mean latency 112.64 ms | `data/processed/evaluation/evaluation_report.json` `[H-A]` |
| Classical — real footage | OpenCV geometric | 9 real frames | **9/9** detected; mean latency 614.21 ms | same file `[H-A]` |
| **ML — this evaluation** | **Faster R-CNN (`fretboard_rcnn.pt`)** | **105 held-out test frames** | **P 1.0000 / R 0.9048 / F1 0.9500 / mean IoU 0.7154 @ thr 0.40, IoU 0.50; AP@0.75 0.2272** | this report `[R-X]` |

**Do not cross-attribute.** The ML number (0.7154 mean IoU, 105 frames, real region annotations) is measured differently from the classical synthetic number (0.9029 mean IoU, 16 synthetic images). They are not directly comparable. `[INF]`

A pre-existing `real_hybrid` artifact also exists (`data/processed/evaluation/real_hybrid/evaluation_report.json`) but reports `source: "classical"` for all 9 frames — i.e., it did **not** measure the ML model, so it is **not** used as an ML result here. `[H-A]`

---

## 9. Presentation-Ready Results Table

**Faster R-CNN fretboard-region detector (`fretboard_rcnn.pt`) — 105-frame held-out test split**

| Metric | Value |
|---|---|
| Images evaluated | 105 |
| Inference device | CUDA |
| Confidence threshold | 0.40 |
| IoU threshold | 0.50 |
| True positives | 95 |
| False positives | 0 |
| False negatives | 10 |
| **Precision** | **1.0000** |
| **Recall** | **0.9048** |
| **F1-score** | **0.9500** |
| **Mean IoU (matched)** | **0.7154** |
| AP@0.50 | 1.0000 |
| AP@0.75 | 0.2272 |
| Median box IoU | 0.725 |
| Median confidence | 0.962 |

**Footnote for the slide:** *Precision/FP are structurally saturated (no negative images; one GT per image). AP@0.50 is likewise saturated; AP@0.75 and the IoU distribution are the meaningful localization indicators. The class label "fret" denotes the fretboard region, not individual frets.*

**Operating-point comparison (same checkpoint):**

| Operating point | Recall | F1 |
|---|---|---|
| conf ≥ 0.40, IoU ≥ 0.50 (project default) | 0.9048 | 0.9500 |
| conf ≥ 0.40, IoU ≥ 0.75 | 0.3333 | 0.3500 |
| conf ≥ 0.90, IoU ≥ 0.50 | 0.6667 | 0.8000 |

---

## 10. Conclusion

- A genuine, reproducible, standalone evaluation of the **existing** ML checkpoint was completed on all **105** held-out test images. `[R-X]`
- At the project's operating point (conf 0.40 / IoU 0.50): **P 1.0000, R 0.9048, F1 0.9500, mean IoU 0.7154** — confirmed by two independent implementations. `[R-X]`
- The model reliably localizes the fretboard region on most frames, but with **moderate box tightness** (no IoU ≥ 0.90; only 38/105 ≥ 0.75) and a **concentration of failures in one video sequence** (`32_*`), consistent with a documented train→test distribution shift. `[R-X]`
- The headline precision/AP@0.50 values are **structurally saturated** and should not be over-claimed. `[R-X]` `[INF]`

---

## 11. Statement of Non-Modification

- **No project file was modified, added to, or deleted** by this evaluation. `[R-X]`
- Git working tree after the evaluation contained only: the **pre-existing** unstaged edit `guitartab-lovable/src/routes/index.tsx`, and the previously created untracked `PROJECT_AUDIT_REPORT.md`. No other changes. `[R-X]`
- The model weights, datasets, annotations, training code, and application source were **not touched**. `[R-X]`
- The only files created by this evaluation are: this report (`MODEL_EVALUATION_REPORT.md`), and three temporary scripts plus one JSON record file under `C:\Users\PC\AppData\Local\Temp\opencode\` (**outside** the repository). Nothing was committed or pushed. `[R-X]`

---

## Appendix — Evidence Index

- `backend/models/fretboard_rcnn.pt` — 76,020,762 bytes, SHA256 `63994486…10281835` `[V-A]`
- `backend/scripts/train_fretboard.py` — `evaluate()` (metrics convention) `[V-S]`
- `backend/app/cv/ml_detector.py` — `MLFretboardDetector`, `build_fretboard_model`, `FretboardCocoDataset` `[V-S]`
- `data/extracted_fretboard/{train,test}/*.png` — 250 + 105 frames `[V-A]`
- `data/extracted_fretboard/annotations/{train,test}.json` — COCO, 1 class (`fret`), 1 region/image `[V-A]`
- `data/processed/evaluation/evaluation_report.json` — classical synthetic/real results (kept separate) `[H-A]`
- `data/processed/evaluation/real_hybrid/evaluation_report.json` — hybrid run, all `source: classical` `[H-A]`
- Temp evaluation scripts/records: `C:\Users\PC\AppData\Local\Temp\opencode\{gt_analysis.py, ml_eval.py, confirm_eval.py, ml_eval_records.json}` `[R-X]`

---

*End of report. Generated by a read-only evaluation; no source, dataset, checkpoint, or Git state was modified. The only files added are this report and temporary files outside the repository.*
