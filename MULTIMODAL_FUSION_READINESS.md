# MULTIMODAL_FUSION_READINESS.md

**GuitarTab AI — Multimodal Pipeline Survey & Fusion Readiness Audit**

Type: investigation only (no code, config, data, checkpoints or reports were modified).
Scope: `backend/`, `guitartab-lovable/`, `scratch/tab_vision/` (including gitignored content), `frontend/` (deprecated, noted only for contrast), `data/`.
All claims carry `file:line` citations verified against current source. Measured numbers are quoted from existing evaluation documents with their source; **no results are invented**.

---

## 1. Executive Summary

**What the product genuinely does today.** A user drops an MP4/MOV/WebM into the active frontend (`guitartab-lovable/`). The file is uploaded (`POST /api/videos/upload`), then a **single blocking HTTP call** (`POST /api/jobs/{id}/process`) runs the entire pipeline synchronously: OpenCV extracts frames at **1 fps** into `data/processed/<job>/frames/`, and an external subprocess `tabvision.exe transcribe <video> --format ascii -o out.tab` performs **audio-only** note transcription and renders ASCII tablature. The backend returns `analysis = {"tablature": "<ascii text>"}` and the frontend renders it. **This end-to-end path genuinely works** (verified against on-disk job artifacts).

**What it does not do.** No vision code runs during transcription (enforced by test `backend/tests/test_vision.py:373`). Vision exists only as **opt-in, per-frame, geometry-only HTTP endpoints** (`/api/vision/...`, `/api/jobs/{id}/frames/{i}/fretboard[-debug]`): fretboard localization, perspective rectification, string-row and fret-wire positions — **no nut detection, no fret numbering, no string pitch identity, no hands, no contact detection** (`backend/app/cv/vision_analysis.py:702-704`). The in-repo CV "pipeline" stage `run_pipeline()` is a stub that always raises `NotImplementedError` (`backend/app/cv/pipeline.py:82-89`).

**Audio pipeline.** `scratch/tab_vision/tabvision/` is a substantial, production-quality package: ffmpeg demux → Spotify Basic Pitch (baseline) or an Onsets-and-Frames-style guitar transcription model (`hf-midi-transcription`, checkpoints `guitar-gaps.pth` / `guitar-fl.pth`) → `AudioEvent[]` (onset, offset, pitch, velocity, confidence, pitch logits, fret prior) → evidence composition (corpus position priors from GuitarSet/GAPS + acoustic inharmonicity physics) → chord-cluster Viterbi decode over all playable (string, fret) candidates → `TabEvent[]` → ASCII/GP5/MusicXML/MIDI renderers. **The audio model never predicts string/fret**; string assignment is inferred by the decoder. Reported baseline: aggregate Tab F1 ≈ 0.61, ambiguous-pitch top-1 string accuracy 0.677, top-3 0.9986 (`scratch/tab_vision/docs/EVAL_REPORTS/string_assignment_phase0_2026-07-27.md:22`).

**Fusion.** Audio+vision fusion **is implemented — in three separate places, all in `scratch/tab_vision/`, none used by the active backend**:
1. `tabvision/fusion/` — the modern package actually called by the shipped `fuse()` (`tabvision/pipeline.py:503`), with a vision emission term, neck/position/contact priors — but `video_enabled=False` by default (`pipeline.py:201`) and the protective gating layer (`fusion/vision_evidence.py`) is imported only by eval scripts/tests.
2. `tabvision-server/app/fusion_engine.py` — a 2,216-line legacy v0 engine with `fuse_audio_video()`; not imported by production.
3. The active backend invokes `tabvision` **without `--video`** (`backend/app/services/processing.py:316`), so the vision half never executes in the shipped product.

**Why vision is off (measured, not accidental).** The ungated legacy video chain measured **−0.15 to −0.20 aggregate Tab F1** vs audio-only (`tabvision/pipeline.py:9-13`; `scratch/tab_vision/docs/DECISIONS.md:5937-5940`); the safety gate never fires because measured frame coverage (0.48–0.52) never clears its 0.71 threshold (gated video = exactly +0.0000, `DECISIONS.md:5944`); and video is **anti-complementary** where audio fails — `P(video right | audio wrong) = 0.285` vs a 0.574 video marginal, oracle-router ceiling +0.058 (`docs/EVAL_REPORTS/a14_video_complementarity_2026-07-06.md:7,32-33`).

**Bottom line for the multimodal program.** The hard problem (ambiguous string assignment) is real and quantified (≈32% of ambiguous notes get the wrong string; `string_assignment_phase0_2026-07-27.md:22`). The fusion machinery exists and is well engineered. What is missing is: (a) **contact-level vision** (fingertip→string/fret) that is accurate enough to beat the audio prior it would displace (deployable video string accuracy 0.689 vs audio prior 0.778, `DECISIONS.md:5946-5949`), (b) **musically identified fretboard geometry** (nut, fret numbers, string orientation) in the active backend, (c) a **structured note-event contract** between TabVision and the backend (today only lossy ASCII text crosses that boundary), and (d) an **alignment + gating layer** that only accepts vision when it is actually right.

**Smallest useful improvement first:** consume TabVision's structured `--json` / `--editor-output` note events in the backend (mechanical, low-risk, unlocks timestamps/confidence/candidate lattices for every later stage), **and**, as the first vision milestone, add **nut-end detection + fret numbering + string orientation** to `backend/app/cv/vision_analysis.py` so rectified coordinates become musically meaningful. Details in §15.

---

## 2. Current System: What GuitarTab AI Does Today

### 2.1 Component inventory

| Component | Path | Role | Status |
|---|---|---|---|
| Active frontend | `guitartab-lovable/` | Upload, results, frame gallery with server-rendered overlays | Implemented |
| Deprecated frontend | `frontend/` | Earlier copy of same UI; not part of active flow | Deprecated |
| FastAPI backend | `backend/app/` | Upload, frame extraction, job sidecars, opt-in CV endpoints | Implemented |
| Backend CV | `backend/app/cv/` | Per-frame fretboard geometry (hybrid ML + classical) | Implemented, opt-in |
| Fretboard detector weights | `backend/models/fretboard_rcnn.pt` (76,020,762 B) | Fine-tuned Faster R-CNN (MobileNetV3-FPN, 2 classes) | Present |
| TabVision (audio) | `scratch/tab_vision/tabvision/` | Audio→note events→string/fret decode→tab render | Implemented, invoked by backend |
| TabVision video stack | `scratch/tab_vision/tabvision/tabvision/video/` | YOLO-OBB + MediaPipe + fingertip posterior | Experimental, default-off |
| FretCam | `scratch/tab_vision/fretcam/` | Stabilized position/contact prototype | Quarantined prototype |
| Legacy server | `scratch/tab_vision/tabvision-server/` | v0 FastAPI/Modal stack incl. `fusion_engine.py` | Legacy, not called by backend |
| Fretboard dataset | `data/extracted_fretboard/` | COCO boxes: 250 train + 105 test PNGs + `annotations/{train,test}.json` | Present |

### 2.2 What genuinely works vs. what is a placeholder

**Genuinely works (verified in source and on disk):**
- Upload validation/persistence: `backend/app/api/routes/videos.py:24-67` → `backend/app/services/uploads.py:73-136` → `data/uploads/<uuid>.mp4` + JSON sidecar.
- Frame extraction with resource limits: `backend/app/services/processing.py:97-254` → `data/processed/<job>/metadata.json` + `frames/frame_%06d.jpg`.
- TabVision ASCII transcription end-to-end: `backend/app/services/processing.py:299-334,392` (confirmed by stored sidecars and `out.tab` files on disk).
- Per-frame fretboard detection + debug overlay: `backend/app/api/routes/frames.py:150-261`.
- Per-frame vision geometry + annotated/rectified JPEGs: `backend/app/api/routes/vision.py:168-255`.
- Frontend result rendering: `guitartab-lovable/src/components/gt/Results.tsx:32-90`, frame gallery `Frames.tsx:15-65`.

**Placeholders / stale / dead:**
- `backend/app/cv/pipeline.py:82-89` — `run_pipeline()` **always raises `NotImplementedError`**; exported (`cv/__init__.py:27,47`) but never called by any route.
- `pipeline.py:15-69` stage flags: 6 of 7 stages say `implemented=False, status="planned"` — stale (fretboard detection *is* implemented; tablature *is* produced via TabVision).
- `backend/app/api/routes/capabilities.py:18-28` NOTES claim "No note detection … or tablature generation is implemented" — stale.
- `JobResponse.analysis` docstring "Always null in this milestone" (`backend/app/schemas/video.py:83-84`) — stale.
- Frontend dead code: `tab-service.ts:106 overlayUrl`, `vision-service.ts:122-138 analyzeFrame()`, `vision-service.ts:145-146 rectifiedUrl` — exported, never imported.
- Frontend expects `tuning` / `noteCount` from the response (`tab-service.ts:82-83`) but the backend only sends `analysis.tablature` — both stay `undefined`, so `Results.tsx:51-52` never renders them.
- Hard-coded, Windows-only TabVision path with no config, no feature flag, no timeout: `processing.py:303-315`; contradicts `backend/app/core/config.py:4-7`.
- Silent degradation: if `tabvision.exe` is missing or fails, the job still completes with `analysis=null` (`processing.py:306-308,329-334,393-404`) and the frontend shows a non-retryable error (`tab-service.ts:81`).
- Side-effect bug: `processing.py:310` calls `ProcessedStore.begin()` *after* `extract()` already committed, leaving orphan `data/processed/.tmp-<job>/` directories (**20 exist on disk now**).

---

## 3. Current Frontend-to-Backend Workflow

### 3.1 Sequence (all steps verified)

```
1.  File pick/drop           guitartab-lovable/src/components/gt/Upload.tsx:30-40,60-64
                             validate: ext ∈ {mp4,mov,webm}, ≤100 MB (src/lib/tab-service.ts:4-33)
2.  run()                    src/routes/index.tsx:45-58  (AbortController; stage="uploading")
3.  POST /api/videos/upload  tab-service.ts:52-69 (XHR, FormData "file")
      → videos.py:24-67      content-length pre-check :46-59
      → uploads.py:73-136    writes data/uploads/<uuid>.mp4 + <uuid>.json {status:"received"}
      ← 201 {job_id}         schemas/video.py:55-65
4.  stage="transcribing"     tab-service.ts:113-115
5.  POST /api/jobs/{id}/process   tab-service.ts:71-91   [BLOCKING; client timeout 180 s, :6]
      → frames.py:47-68      sync handler → threadpool (module docstring frames.py:7-10)
      → processing.py:337-409 ProcessingService.process:
         a. per-job lock (409 if busy)                 :341-347
         b. status="processing"                        :380-382
         c. VideoProcessor.extract                     :384  (1 fps sampling, step=round(fps*interval),
                                                            interval=1.0 s → config.py:68-73;
                                                            downscale to 1280 px → config.py:74-77)
            → data/processed/<id>/{metadata.json, frames/frame_%06d.jpg} (atomic commit :230-231)
         d. run_tabvision                              :392 → :299-334
            subprocess argv = [tabvision.exe, "transcribe", <video>,
                               "--format", "ascii", "-o", <tmp>/out.tab]   :316
            (path hard-coded: scratch/tab_vision/tabvision/.venv/Scripts/tabvision.exe  :304)
            → copy text to data/processed/<id>/out.tab  :325-327
         e. analysis = {"tablature": <ascii>} or None   :393-395
         f. status="completed", sidecar updated         :397-404
      ← JobResponse {status, video: VideoMetadata, analysis:{tablature}}  schemas/video.py:68-92
6.  TabResult {jobId, tablature, tuning:undefined, noteCount:undefined}   tab-service.ts:79-84
7.  state="done"
      → <Results> renders ASCII tab                    Results.tsx:79-87 (copy :36-40, download :41-48)
      → <Frames>  GET /api/jobs/{id}/frames (limit 24) frames.py:71-90
         thumbnails GET /frames/{i}                    frames.py:93-127
         "Analysis" toggle → GET /api/vision/jobs/{id}/frames/{i}/annotated
                                 vision.py:196-219 → analyze_frame (cv/vision_analysis.py:583)
                                 → server-rendered JPEG overlay   Frames.tsx:50
```

### 3.2 Sync/async, models, data passed between components

- **Everything is synchronous inside one HTTP request.** No `BackgroundTasks`, no Celery, no polling, no WebSocket anywhere in `backend/app` or `guitartab-lovable/src`. `GET /api/jobs/{id}` exists (`videos.py:70-90`) but the active frontend never calls it.
- **Models in the active path:** exactly one — TabVision's audio transcription model (see §4), executed in a subprocess. The backend's Faster R-CNN runs **only** when a user explicitly opens a vision/fretboard endpoint.
- **Data handed across boundaries:**
  - Frontend → backend: raw video bytes (multipart).
  - Backend → TabVision: file path only (video path; no tuning, no capo, no ROI, no `--json`).
  - TabVision → backend: **ASCII text file only** (no structured note events, no confidences, no candidates — although TabVision supports `--json` at `cli.py:748-775` and `--editor-output` at `cli.py:210-217`).
  - Backend → frontend: `JobResponse.analysis = {"tablature": str}` (loose dict, `schemas/video.py:81-84`), frame list with `timestamp_seconds` (`schemas/video.py:36-43`), and on demand JPEGs/JSON from the vision routes.

### 3.3 What runs when (and what does not)

| Trigger | What runs | Model/algorithm |
|---|---|---|
| Upload | Validation + stream to disk | none |
| `POST /process` | Frame extraction + TabVision **audio-only** | ffmpeg/OpenCV; Basic Pitch or Onsets-and-Frames guitar checkpoints; Viterbi decode |
| `GET .../fretboard[-debug]` | Per-frame hybrid detection | Faster R-CNN (`fretboard_rcnn.pt`) + classical Hough corridor |
| `GET /api/vision/...[/annotated|/rectified]` | Per-frame geometry analysis | Hybrid detection → rectification → Sobel string rows + fret-wire columns |
| Anything else | — | **No vision, no fusion, no hand detection** |

Frame timestamps exist in extraction metadata (`processing.py:171-187`, `timestamp = round(frame_index/fps, 3)`) but the `VisionAnalysisResponse` carries only `job_id` + `frame_index` (`schemas/vision.py:51-52`) — vision results are **not** timestamp-addressable through the API today.

---

## 4. Audio Pipeline: Models, Algorithms and Outputs

Root: `scratch/tab_vision/tabvision/tabvision/` (package `tabvision`, entry `pyproject.toml:92-94`).

### 4.1 Orchestration

`run_pipeline_with_artifacts()` (`pipeline.py:190-517`) stages: `demux` → `model_load` → `audio_inference` → (string evidence) → (position prior) → (`video_analysis`, gated) → (vision priors, gated) → `decode` (`fuse()` at `pipeline.py:503`) → `PipelineArtifacts` (`pipeline.py:156-187`). CLI `transcribe` (`cli.py:606-778`) wraps it; the backend uses **all defaults** because it passes only `--format ascii -o`.

### 4.2 Audio extraction and preprocessing

- `demux()` (`demux/__init__.py:28-62`): requires ffmpeg/ffprobe on PATH; extracts **mono 22 050 Hz float32** (`DEFAULT_SAMPLE_RATE`, `demux/__init__.py:25`; `_extract_audio` `:118-142`); probes duration/fps (`:73-115`); builds a lazy frame iterator with timestamps re-based onto the decoded-audio clock (`_probe_frame_clock` `:181-256`) — this is the audio↔video synchronization substrate (§6.3).
- High-res backend resamples to **16 kHz** (`highres.py:38`, `_resample_if_needed` `:321-335`).

### 4.3 Exact models / checkpoints

| Backend (registry `audio/backend.py:76-80`) | Model | Checkpoint | Source |
|---|---|---|---|
| `basicpitch` (Phase-1 baseline; forced by `--accuracy-mode fast`) | **Spotify Basic Pitch** (ICASSP 2022) | bundled `ICASSP_2022_MODEL_PATH` | `audio/basicpitch.py:87-88` |
| `highres` (default workhorse) | `MidiTranscriptionModel(instrument="guitar")` wrapping `piano_transcription_inference.PianoTranscription` — Onsets-and-Frames lineage, 100 fps, 88 classes, heads `reg_onset/reg_offset/frame/velocity` (`highres.py:60-69`) | `guitar-gaps.pth` (Cwitkowitz GAPS) from HF `xavriley/midi-transcription-models` (`highres.py:40,52-58`) | `highres.py:1-19,223-265` |
| `highres-fl` | same | `guitar-fl.pth` (Francois Leduc) | `audio/backend.py:57` |
| `highres-ensemble` (auto for clean acoustic, `pipeline.py:693-709`) | GAPS + FL sequential passes with frozen logistic calibrators | `audio/ensemble_v1.json` (dev Tab F1 0.6017, GuitarSet players 00–04 → confirmed on player 05) | `highres_ensemble.py:115-138`, `checkpoint_ensemble.py:142-174` |
| `highres-electric` | **not trained** — raises `BackendError` if `TABVISION_HIGHRES_ELECTRIC_CKPT` unset | — | `highres.py:44-47,210-218` |
| `tabcnn` | **stub, no implementation** | — | `audio/tabcnn.py:1-5` |

Post-detection filters (`audio/filters.py:241-264`): low-quality drop, same-pitch merge, sustain re-detection drop, harmonic/sub-harmonic drop, trailing trim — default **on** for basicpitch, **off** for highres (`pipeline.py:227-232`).

### 4.4 What the model predicts — and what it does not

The models predict **note events + frame posteriors, never string, fret, or tablature**:
- Basic Pitch → `(start, end, midi, amplitude, bends)` tuples (`basicpitch.py:115-152`), amplitude mapped to `confidence = 0.3 + 0.7·amp/max` (`:135`).
- High-res → MIDI notes + 4 posterior matrices `(frames, 88)` (`highres.py:306-313,370-404`).

**Shared note-event structures** (`tabvision/types.py`):
```python
AudioEvent   (types.py:44-53): onset_s, offset_s, pitch_midi, velocity, confidence,
                                pitch_logits (128-wide onset log-odds, highres only),
                                fret_prior (6×(max_fret+1) evidence matrix — THE vision/prior hook),
                                tags (e.g. "bend")
TabEvent     (types.py:145-153): onset_s, duration_s, string_idx (0=low E…5=high E), fret,
                                pitch_midi, confidence (= string-assignment confidence, §6.5),
                                techniques (never populated by any detector)
FrameFingering (types.py:127-142): t, finger_pos_logits, homography_confidence,
                                marginal_string_fret() → (n_strings, max_fret+1) softmax
GuitarConfig (types.py:25-32): tuning_midi (default (40,45,50,55,59,64)), capo, max_fret=24, n_strings=6
```
Onsets/offsets/durations are continuous seconds; there is **no beat quantization applied to note times** — beat grid detection is explicitly advisory (`audio/beats.py:1-7`: "Nothing here moves note onsets").

### 4.5 String/fret assignment — inferred by a decoder, not predicted

1. **Enumerate every playable position:** `candidate_positions()` (`fusion/candidates.py:25-45`) — for each string, `fret = pitch_midi - open_midi`, accept iff `capo ≤ fret ≤ max_fret`, sort by `(fret, string_idx)`. A pitch with ≥2 candidates is ambiguous; 0 candidates ⇒ dropped as unplayable (`fusion/viterbi.py:112-114`).
2. **Attach evidence to each event** (product-of-experts, `fusion/evidence.py:13-70`) into `AudioEvent.fret_prior`:
   - **Corpus position prior** `P(string,fret|pitch)` from GuitarSet/GAPS count tables, Dirichlet-smoothed, power-2 sharpened, capo re-indexed (`fusion/position_prior.py:30-68,71-148`; loaded `pipeline.py:372-385`).
   - **Acoustic physics (inharmonicity):** fit stiffness coefficient `B` from partials in the raw wav, Gaussian match against per-string predicted `log B(s,n)` (`fusion/inharmonicity.py:249-329,471-503`; table `fusion/string_physics.py:86-93`; loaded `pipeline.py:349-370`). Domain-gated: clean acoustic, standard tuning, capo 0 (`string_physics.py:245-282`).
   - **(Optional, video-on) vision priors:** neck anchors (`fusion/neck_prior.py:24-51`), position windows (capped ≤1 nat, `position_window_prior.py:35`), finger contacts (capped ≤2 nat, `contact_prior.py:64`) — all applied at `pipeline.py:446-486`.
3. **Cluster onsets within 80 ms** into chord states (`fusion/chord.py:28,34-98`) enforcing per-string monophony and hand span ≤5 frets.
4. **Viterbi decode** (`fusion/viterbi.py:185-299`, complexity O(N·S²)):
   - Emission (`fusion/playability.py:180-218`) = `−log(confidence)` + `FRET_PRIOR_WEIGHT(1.0)·−log(fret_prior[s,f])` + `λ_vision·homography_conf·−log(P_vision)` (floor `VISION_FLOOR=1e-3`, `playability.py:51,212`) + `LOW_FRET_BIAS(0.10)·fret` (`:214`) − `OPEN_STRING_BONUS(0.5)` if open (`:216`), plus chord-shape bonus (`chord_shapes.py:49-61`).
   - Transition (`playability.py:235-277`) = position-shift cost 2.5·|Δfret|/12 + hand-span barrier 5.0 beyond 5 frets − same-string bonus 0.5 + optional learned sequence prior.
5. **Output confidence = string-flip margin:** extra cost of the cheapest full decode that puts the note on a *different* string, mapped via `1 − exp(−margin/1.0)` (`viterbi.py:287-318`, `playability.py:113-123`) — an actionable "check-the-string" signal, rendered as `?` when <0.5 (`render/ascii.py:24`).

**Ambiguity handling:** multiple candidates are *always* generated and scored; the decoder picks one path through the lattice; per-note K-best/min-marginal ranking exists on the eval path (`viterbi.py:141-182`, `fusion/segment_decoder.py:607-715`) and in the assisted editor (`assist/candidates.py:33-92`, top-3 recall 0.9986 per its docstring). The production decoder `auto` resolves to **`baseline`** (`fusion/inference_policy.py:329-334`); `segment-v1` is opt-in, `context-v1` (learned reranker) is **hard-blocked** at runtime (`inference_policy.py:350-358`).

**Tuning/capo:** standard tuning default (`types.py:17-18`); alternate tunings are user-declared CLI presets only (`cli.py:95-103`) — **no automatic tuning detection**; automatic priors are standard-tuning-only (`inference_policy.py:264-278`); capo 0–12 supported with a capo-covariant prior (`position_prior.py:30-68`), sequence prior suppressed under capo (`inference_policy.py:111-123`). Video capo estimate exists but is **report-only** (`preflight/capo.py:94`).

### 4.6 ASCII tablature generation and what is lost

`render/ascii.py:38-71`: sort by onset → one column per event → 6 rows with high-E on top (`:152-171`, labels `E A D G B e` `:27-29`) → 80-col wrap (`:26`) → header with tuning/capo/note count (`:215-227`) → `?` suffix when confidence <0.5 (`:24`).

**Information lost between model output and final ASCII tab:**
- **All timing/rhythm** — no time grid, no rests, no beat/measure lines (docstring `ascii.py:7-8`), even though a `BeatGrid` was detected (`pipeline.py:309`).
- **Simultaneity** — chord-cluster notes become *consecutive columns*; a strummed chord reads as a run.
- **Durations** (`duration_s` never rendered), **velocity**, and most of **confidence** (reduced to `?`).
- **Pitch and technique** are only implicit; `techniques` is never populated by any detector (README technique baseline 0.00).
- All of the above *are* available in `TabEvent[]` and in the `--json` / `--editor-output` envelopes — the backend simply doesn't request them.

### 4.7 Outputs saved

Rendered file `-o` (`cli.py:713-715`); optional `--json` envelope `{status, output_path, low_confidence_flags[], timings}` (`cli.py:748-775`); optional `--editor-output` document with per-note `{string(1-6), fret, confidence, confidenceLevel, detectedMidiNote, candidates[]}` and metadata including `videoEnabled`, `notesAffectedByVideo`, prior versions (`assist/document.py:43-113`); read-only prior artifacts with SHA-256 manifests and pre-registered gates (`fusion/artifact_registry.py:22-109`). **The production backend consumes only the ASCII file** (`processing.py:322-328`).

---

## 5. Vision Pipeline: Models, Algorithms and Outputs

Three separate vision stacks exist. They are **not** the same code.

### 5.1 Stack A — active backend CV (`backend/app/cv/`), implemented, opt-in, per-frame

**Fretboard localization — hybrid** (`hybrid_detector.py:78-146`, entry point documented `:1-15`):
- **ML path:** torchvision Faster R-CNN (MobileNetV3-Large + FPN, COCO-pretrained), **2 classes** (background/fretboard, `ml_detector.py:159-185`), weights `backend/models/fretboard_rcnn.pt`, `DEFAULT_MIN_CONFIDENCE=0.40` (`ml_detector.py:35`), top-1 box; **polygon = the 4 corners of the axis-aligned bbox** (`ml_detector.py:503-510`) — not an anatomical quad. Trained on the 355-image COCO subset in `data/extracted_fretboard/` (250 train / 105 test, verified on disk).
- **Classical path:** CLAHE → adaptive Canny → `HoughLinesP` → boundary-pair corridor search with constraints (angle diff ≤14°, width 2–18% of frame, aspect ≥2.2:1, ≥2 transverse frets; `fretboard_detector.py:47-66,269-405`), quad from projected segment endpoints (`:343-350`), internal fret-verification warp (`:572-700`), confidence = weighted coverage/transverse/geometry/width (`:702-741`), accept ≥0.35.
- **Merge policy:** ML trusted outright ≥0.60; ML-only accepted if classical failed ≥0.40; tie-break preference ≥0.50 (`hybrid_detector.py:34-47,104-146`).
- Reported metrics (documented, not re-run): Precision 1.0000 / Recall 0.9048 / F1 0.9500 / mean IoU 0.7154 at conf ≥0.40, IoU ≥0.50 on 105 test images (`MODEL_EVALUATION_REPORT.md:29,162`).

**Perspective rectification** (`vision_analysis.py`):
- `order_quad()` `:136-180` — centroid+PCA ordering; `refine_quad_orientation()` `:321-356` tilt refinement; `rectify_fretboard()` `:183-222` — `cv2.getPerspectiveTransform` + `warpPerspective`, output 320–1400 × 60–500 px; inverse `rect_to_original()` `:225-235`.
- **Rectified coordinate system:** x ∈ [0,w) runs **along the neck**, y ∈ [0,h) **across the strings**; strings are horizontal rows, fret wires vertical columns (`vision_analysis.py:260-264,424-426,519-520`). **The nut end is not determined** — x=0 is an arbitrary end of the corridor.

**String detection & ordering** — `detect_strings()` `:514-575`: interior-trimmed `|Sobel_y|` row profile → peak picking with lobe merging (`:377-416`, threshold 0.30, min spacing 0.035) → optional six-string subset selection (most evenly spaced 6, spacing CV ≤0.30, `:478-511`). Rows sorted by y; `position=0` is the **topmost row of the crop**; labels `S1..S6` are **purely geometric** — "Pitch identity (EADGBE) is NOT inferred" (`vision_analysis.py:90-92,702-704`).

**Fret-wire detection & ordering** — `detect_fret_wires()` `:419-475`: normalized `|Sobel_x|` + Canny column density → peaks (threshold 0.22, min distance 2.5% width, vertical-continuity ≥22%) → sorted by x, `index = enumerate order` (schema `schemas/vision.py:34`: "0 = nearest x=0 edge"). **No nut detection, no rule-of-18 fit, no fret numbers** anywhere in `backend/app/cv/*`; `F1` means "first wire from the crop edge", not fret 1.

**Hands/fingers/contact:** **absent** — zero references to `mediapipe`/`ultralytics`/`yolo` in `backend/`. Capability metadata still lists `hand_detection` as planned (`cv/pipeline.py:41-47`).

**Temporal:** strictly per-frame and stateless (`vision.py:57-102`); no tracker, no optical flow in the backend. Frames carry `timestamp_seconds` in extraction metadata, but the vision API response does not expose it.

**Routing:** only via `GET /api/jobs/{id}/frames/{i}/fretboard[-debug]` (`frames.py:150-261`) and `GET /api/vision/jobs/{id}/frames/{i}[/annotated|/rectified]` (`vision.py:168-255`). Never during transcription (`tests/test_vision.py:373`).

### 5.2 Stack B — scratch TabVision video chain (`scratch/tab_vision/tabvision/tabvision/video/`), experimental, default-off

- **Guitar localization:** YOLO-OBB (`yolo11n-obb.pt`; `video/guitar/yolo_backend.py`, classes incl. `fret`/`nut` at `:43-49`) with an EMA bbox tracker (`video/guitar/tracker.py:16-65`) — tracker used only by tests.
- **Fretboard geometry:** keypoint-based homography from unit square → ordered quad (`video/fretboard/keypoint.py:341-356`), canonical frame **x = along neck with 0 = nut, y = across strings with 0 = high-E side** (`keypoint.py:14-28`, `geometric.py:87-96`); rule-of-18 fret map + nut-end disambiguation by spacing decay (`video/fretboard/calibrate.py:103-127,150-229`) — audit marks this "eval-harness only, never threaded to production" (`scratch/tab_vision/docs/VIDEO_CHAIN_AUDIT_2026-07-28.md:218`).
- **Hand detection:** MediaPipe Tasks `HandLandmarker` (21 landmarks, max 2 hands, `video/hand/mediapipe_backend.py:1-13,144-172`), fingertip pixel coords + z + curl ratio (`:248-263`), fretting-hand selection (`:201-228`), coarse `HandNeckAnchor` (`video/hand/neck_anchor.py:43-94`).
- **Fingertip → (string, fret) posterior:** `compute_fingering()` (`video/hand/fingertip_to_fret.py:95-220`) — inverse-homography projection (`:223-235`), Gaussian distance kernel over the (6 × 25) cell grid (`σ_fret=1.0`, `σ_string=0.6`, `:70-71,172-175`), curl gate `<0.95 → −2.0` (`:73-77`), z-press bonus `+0.5` (`:79-83`), log-sum-exp over 4 fingers → softmax `marginal_string_fret()` (`:196-220`). Outputs a **soft posterior, never a hard decision**.
- **Learned string resolver:** ResNet-18 6-way head (`video/hand/learned_string.py:31-47`) — "banked negatives, not shipped" (`VIDEO_CHAIN_AUDIT_2026-07-28.md:219`).
- **Timestamps:** yes — frames arrive as `(timestamp_s, frame_bgr)` re-based onto the audio clock (`demux/__init__.py:181-256,307-350`); production legacy loop is raw per-frame with `video_stride=3` and **no smoothing** (`pipeline.py:611-639`); EMA homography tracker exists but is test-only (`video/fretboard/tracker.py:16-65`).
- **Wiring:** reached only via `tabvision … --video [--video-backend legacy|fretcam]` (`cli.py:291-345,801-819`); `video_enabled=False` default (`pipeline.py:201`); **the backend never passes these flags** (`processing.py:316`). Additionally the YOLO/MediaPipe weights are not installed at their default paths in this environment, so enabling the stack would currently raise `BackendError` (`yolo_backend.py:135-140`, `mediapipe_backend.py:148-154`).

### 5.3 Stack C — FretCam (`scratch/tab_vision/fretcam/`), quarantined prototype

MediaPipe VIDEO-mode tracking + optical flow (`fretcam/src/fretcam/hand_tracking.py:5,11,359,642`; `tracking.py:43`) producing `FingerContact(name, fret, string, pressing, barre, quality…)` (`detection.py:507-524`) via `compute_finger_contacts()` (`:1338-1398`), bridged to TabVision with a string-index convention flip (`tabvision/tabvision/video/position.py:40-47`). Status: "quarantined prototype … not run" (`VIDEO_CHAIN_AUDIT_2026-07-28.md:221`).

### 5.4 Capability verdict: geometry vs. contact

| Capability | Active backend | Scratch TabVision | Notes |
|---|---|---|---|
| Fretboard localization (box/quad) | **Implemented** | Implemented (YOLO-OBB) | Hybrid ML+classical is solid |
| Perspective rectification | **Implemented** | Implemented | Backend lacks nut-end orientation |
| String row detection (geometric) | **Implemented** (may return ≠6, honestly reported) | Implemented | No pitch identity in backend |
| Fret-wire detection (positions) | **Implemented** | Implemented + rule-of-18 fit (eval-only) | **No fret numbers in backend** |
| Nut identification / fret numbering | **Not implemented** | Partial (YOLO nut class + spacing decay, eval-only) | Prerequisite for contact→fret mapping |
| String pitch identity (which string is which) | **Not implemented** (explicitly disclaimed) | Canonical orientation exists | Orientation also undetermined in backend |
| Hand/fingertip detection | **Missing** | Implemented (MediaPipe), default-off, weights absent | |
| Which string/fret is **pressed** | **Not implemented** | **Experimental** (posterior only), default-off | Contact ≠ geometry |
| Finger–string contact (pressing/barre) | **Missing** | FretCam: experimental/quarantined | |
| Temporal tracking across frames | **Not implemented** (per-frame) | EMA trackers exist, test-only | |
| Timestamps available to vision | In frame metadata only; not in vision API response | Yes (audio-aligned frame clock) | |
| Vision → tablature | **Not implemented** | Possible via priors but gated off | |

**Key distinction:** the active system does **fretboard geometry** (where the board, rows and wires are in a still image). It does **not** do **contact detection** (which fingertip presses which string at which fret), and it does not identify strings/frets musically. Geometry is the *coordinate frame*; contact is the *observation*; neither alone is a note.

---

## 6. Existing Fusion Implementation

### 6.1 Where fusion lives (three places, none in the active product path)

| # | Location | What it is | Used by active backend? |
|---|---|---|---|
| 1 | `scratch/tab_vision/tabvision/tabvision/fusion/` (21 modules) | The modern fusion package imported by the shipped `fuse()` (`fusion/__init__.py` → `pipeline.py:503`) | **Yes in code, no in effect** — `video_enabled=False` so all vision inputs are empty |
| 2 | `scratch/tab_vision/tabvision-server/app/fusion_engine.py` (2,216 lines) | Legacy v0 engine with `fuse_audio_only()` (`:575`) and `fuse_audio_video()` (`:1806`), video matching with 0.1 s tolerance (`:1731-1752`), confidence boosts (`:1159-1189`) | **No** — production routes to `v1_adapter` when `TABVISION_PIPELINE=v1` (`studio.ps1:84`); audit says port pending (`scratch/tab_vision/AUDIT.md:109`) |
| 3 | `backend/app/services/processing.py:299-334` | Subprocess invocation of TabVision | Runs **audio-only** (no `--video` at `:316`) |

Grep confirms zero references to `fusion`, `vision_evidence`, or `lambda_vision` anywhere in `backend/app/**`.

### 6.2 What `tabvision/fusion/` actually does

It is **real production code** for audio-side string assignment (§4.5), plus a **vision half that is wired but inert**:

- **Vision emission term:** `playability.emission_cost` adds `λ_vision · homography_confidence · −log(P_vision[s,f])` (`playability.py:208-212`), looking up the nearest `FrameFingering` to the note onset (`find_fingering_at`, `playability.py:156-177` — **no max-gap tolerance in v1**, unlike legacy's 0.1 s). With `video_enabled=False` there are never any fingerings (`pipeline.py:391-396`), so the term never executes.
- **Vision priors (applied before decode):** `apply_neck_anchor_priors` (`neck_prior.py:24-51`, nearest anchor within 0.15 s, tiled identically across strings — a *fret-region* cue, not a string cue, `:69-70`), `apply_position_window_priors` (≤1 nat cap, `position_window_prior.py:35`), `apply_contact_priors` (≤2 nat cap, causal read at onset−0.03 s, only for pitches with >1 candidate, `contact_prior.py:23-27,64,74`) — all at `pipeline.py:446-486`.
- **Protective gating layer — eval-only:** `fusion/vision_evidence.py` (`choose_orientation`, `combine_fingerings`, `gate_fingering_to_audio`) is imported only by `scripts/eval/*` and tests — **zero hits in `pipeline.py` or `cli.py`**. `docs/DECISIONS.md:5914-5956` records this explicitly: "The shipped default matched no reported metric" → resolved by making audio-only the default.
- **Confidence/ranking:** decode is a single Viterbi path; `TabEvent.confidence` = string-flip margin (§4.5); K-best and per-note candidate rankings exist on the eval/assist paths only.

### 6.3 Timestamp synchronization (exists, and is good)

- The demux **frame clock** re-bases video `best_effort_timestamp_time` onto the decoded-audio start time so both streams share one zero-based timeline (`demux/__init__.py:181-256`).
- Fusion matches by **nearest-neighbour frame lookup at each note onset** (v1: `playability.py:156-177`; legacy: `fusion_engine.py:1731-1752` with explicit 0.1 s tolerance).
- Beat-grid onset snapping was measured net-negative and is **deliberately not applied** (`audio/beats.py:1-7`).
- **Limitation:** v1 has no max-gap guard — a note with no nearby frame still receives the nearest frame's evidence, weighted only by homography confidence.

### 6.4 Visual→musical coordinate conversion (exists)

Homography inverse → canonical [0,1]² unit square (x along neck with nut=0, y across strings with high-E=0) → uniform or rule-of-18 fret cells + uniform string cells → Gaussian distance logits → per-finger softmax → marginal over fingers (`fingertip_to_fret.py:135-175,196-235`; `calibrate.py:73-100`). Backend equivalent (v0): `map_finger_to_position()` with basis-vector projection and a weighted position confidence (`tabvision-server/app/fretboard_detection.py:929-1095`). **Neither is reachable from the active product path.**

### 6.5 Measured status of fusion (from existing eval docs — no new results)

| Finding | Source |
|---|---|
| Ungated legacy video: **−0.15 to −0.20 aggregate Tab F1**; worst clip −0.6624 | `tabvision/pipeline.py:9-13`; `DECISIONS.md:5937-5940,5417-5418` |
| Gated video: **exactly +0.0000** (coverage 0.48–0.52 never clears the 0.71 threshold) | `DECISIONS.md:5944` |
| Video is **anti-complementary**: P(video right \| audio wrong) = 0.285 < marginal 0.574; oracle-router ceiling **+0.058** | `EVAL_REPORTS/a14_video_complementarity_2026-07-06.md:7,32-33` |
| Deployable video string accuracy **0.689** < audio prior **0.778**; best end-to-end video delta **+0.000836** (CI lower bound 0) | `DECISIONS.md:5946-5949` |
| 2026-07-28 negatives: learned string resolver **FAIL** (0.2919 vs 0.45 bar); learned fret keypoints **FAIL** (0.6305 vs 0.7195 OBB fit); wire-sparse gate **FAIL** | `HANDOFF-2026-07-28-video-evidence-closeout.md` |
| Position prior (not vision) carries the string decision: `none` condition collapses to top-1 0.4153 / Tab F1 0.3617 vs baseline 0.6126 | `EVAL_REPORTS/string_assignment_phase0_2026-07-27.md` (condition table) |

**Conclusion:** fusion is implemented and well engineered, but its vision inputs are (a) not invoked by the product, (b) measured to hurt when ungated, and (c) measured to be neutral when gated. The correct statement is: *"audio-vision fusion machinery exists in scratch and is production-quality; the active product runs audio-only; every published accuracy number is audio-only."*

---

## 7. String/Fret Ambiguity: Technical Analysis

### 7.1 The concrete problem (E4, standard tuning)

`DEFAULT_TUNING_MIDI = (40, 45, 50, 55, 59, 64)` = E2 A2 D3 G3 B3 E4 (`types.py:17-18`). E4 = MIDI 64 is playable at **six positions**, all of which `candidate_positions()` will enumerate (`fusion/candidates.py:25-45`):

| # | String (idx) | Open MIDI | Fret | Notes |
|---|---|---|---|---|
| 1 | 6 / high E (5) | 64 | **0** | open string — no finger on the board at all |
| 2 | 5 / B (4) | 59 | **5** | |
| 3 | 4 / G (3) | 55 | **9** | |
| 4 | 3 / D (2) | 50 | **14** | |
| 5 | 2 / A (1) | 45 | **19** | |
| 6 | 1 / low E (0) | 40 | **24** | edge of `max_fret=24` |

Audio can say "MIDI 64 at t=3.42 s" with high confidence. It **cannot** say which of these six was played. Same-pitch wrong-string rate on the ambiguous subset is **0.3230** (top-1 correct 0.6770; top-3 0.9986 — the right answer is almost always in the lattice, the ranking is what fails) (`EVAL_REPORTS/string_assignment_phase0_2026-07-27.md:22`).

### 7.2 What information would resolve it — availability audit

| Signal | Needed for | Currently available? |
|---|---|---|
| Audio pitch + onset time | Candidate generation, matching anchor | **Yes** — `AudioEvent` with ms-level onsets (`types.py:44-53`) |
| Tuning + playable-fret constraints | Candidate enumeration, capo handling | **Yes** — `GuitarConfig`, `candidates.py:25-45` (auto priors standard-tuning-only) |
| Corpus/physics priors (current heuristic) | Ranking candidates | **Yes** — position prior + inharmonicity (audio-derived, §4.5) |
| Detected fretboard quad (frame coords) | Coordinate frame | **Yes, opt-in** — backend per-frame (`vision_analysis.py:183-222`); scratch on `--video` |
| String-line coordinates in rectified space | Mapping y → string index | **Yes, geometric only** (`detect_strings` `:514-575`) — but **string pitch identity undetermined** (no nut/orientation) |
| Fret-wire coordinates + fret **numbers** | Mapping x → fret index | Positions **yes** (`:419-475`); **numbering no** (no nut, no rule-of-18 in backend) |
| Finger/tip location | Contact estimation | **Scratch only, experimental** (MediaPipe, default-off, weights absent); **missing in backend** |
| Finger-to-string contact estimate | The actual observation | **Experimental/quarantined** (fingertip posterior; FretCam `FingerContact`) |
| Temporal consistency across frames | Smoothing, motion gating | **Not wired** (backend per-frame; scratch EMA trackers test-only; FretCam optical flow quarantined) |
| Confidence-based fusion | Accept/abstain per note | **Machinery exists** (`λ_vision`, margins, gates) — but the gate never fires (coverage < threshold) and the vision half is inert |

### 7.3 The critical insight

The ambiguity is **not** a pitch problem — it is a *physical placement* problem. To resolve it, vision must produce, at the note's onset time, a **(string, fret) observation with a calibrated confidence**, which the existing decoder can consume as a capped prior (`playability.py:208-212`) or as a hard constraint on the eval path. Today the chain breaks at three points:
1. **Geometry is not musical** — without nut/fret numbers/string orientation, a fingertip pixel cannot be converted to a trustworthy fret number in the active backend.
2. **No contact observation exists in the active path** — nothing detects which finger touches which string.
3. **No alignment substrate crosses the process boundary** — the backend only receives ASCII text, so note onsets/confidences/candidates never reach the place where vision results live.

---

## 8. Proposed Multimodal Architecture

Design principle: **reuse what is measured-correct (audio decode, geometry, sync clock, fusion costs), replace only what is measured-wrong (ungated per-frame fingerings), and gate every new evidence source with a pre-registered no-regression test.** Stages below map to the 10-stage plan in the brief; each lists existing code to reuse, what's missing, the recommended algorithm, I/O, and the main challenge.

**Stage 1 — Extract synchronized video frames and audio**
- Reuse: `tabvision/demux/__init__.py:28-62` (mono 22.05 kHz wav + frame clock re-based to audio, `:181-256`); backend `VideoProcessor.extract` for the product path.
- Missing: the product extracts at **1 fps** (`config.py:68-73`) — far too sparse for contact/alignment; backend frames are also downscaled to 1280 px (`config.py:74-77`).
- Recommend: for fusion runs, use TabVision's own frame iterator with `--video-stride` (default 3) at full fps; for the product, add a configurable higher-rate extraction (e.g. 15–30 fps, stride-limited) without breaking existing limits (`max_extracted_frames=600`).
- Challenge: storage/CPU limits vs. temporal resolution; keep audio clock as the single time base.

**Stage 2 — Audio transcription → timestamped note events**
- Reuse: entire §4 pipeline (`highres`/`highres-ensemble`, filters, `AudioEvent[]`).
- Missing: backend consumption of structured output.
- Recommend: pass `--json` and/or `--editor-output` (`cli.py:210-217,748-775`) from `run_tabvision()` and persist note events (onset, offset, pitch, confidence, `fret_prior`, candidate list) in the job sidecar.
- Challenge: schema stability, job size, backward compatibility with `analysis.tablature`.

**Stage 3 — Fretboard localization + rectification**
- Reuse: backend hybrid detector (`hybrid_detector.py:78-146`) and rectification (`vision_analysis.py:136-235`) — already implemented and tested.
- Missing: temporal smoothing (quad flicker), nut-end orientation.
- Recommend: keep hybrid detection; add a lightweight quad/homography EMA (scratch already has `smooth_homography_track`, `video/fretboard/tracker.py:16-65`) and PCA/spacing-decay nut disambiguation (port `calibrate.py:103-127`).
- Challenge: orientation pathologies on foreshortened footage (documented: ~half the fitted maps come out end-for-end reversed on clip `118_VD1wc`, `HANDOFF-2026-07-28-video-evidence-closeout.md` §3) — orientation must be a *gated* decision with an abstain state, never a guess.

**Stage 4 — String and fret geometry (musically identified)**
- Reuse: `detect_strings()` `:514-575`, `detect_fret_wires()` `:419-475`; scratch rule-of-18 fit + nut class (`calibrate.py:150-229`, `yolo_backend.py:43-49`).
- Missing: nut detection in backend; fret numbering (fret = count of wires from nut + 1, with rule-of-18 consistency check); string pitch identity (needs orientation + standard-tuning assumption).
- Recommend: classical nut-end detection (strong vertical edge + spacing-decay signature), fit fret positions against `x_k = x0 + b(1 − r^k)`, `r = 2^(−1/12)` (rule of 18), reject fits with high residual; then assign string indices using orientation + tuning.
- Challenge: partial views (frets 1–5 visible only), capo (capo bar looks like a nut), left-handed/mirrored footage.

**Stage 5 — Hand/finger detection relative to the fretboard**
- Reuse: `video/hand/mediapipe_backend.py` (21 landmarks, curl ratio, fretting-hand selection) — implemented, but default-off and weights not installed in this environment.
- Missing: presence in the active backend; installation/pinning of `hand_landmarker.task`; robustness to motion blur and partial hands.
- Recommend: MediaPipe HandLandmarker first (easy win, no training); consider a fine-tuned detector only if MediaPipe fails on your footage domain.
- Challenge: MediaPipe's z is wrist-relative and unreliable for press depth; mirror conventions (left- vs right-handed players).

**Stage 6 — Convert visual contact into candidate (string, fret) observations**
- Reuse: `fingertip_to_fret.compute_fingering()` (`:95-220`) — homography + Gaussian cell kernel + curl/press priors + marginalization; FretCam's `FingerContact` semantics as the reference design (`fretcam/detection.py:507-524,1338-1398`).
- Missing: accuracy. Measured deployable video string accuracy 0.689 < audio prior 0.778 (`DECISIONS.md:5946-5949`); learned resolver failed its gate (0.2919 vs 0.45).
- Recommend: keep the *posterior* formulation (it is the right interface), improve inputs — fret-numbered geometry from Stage 4, normalized fingertip position relative to nut/fret lines rather than a uniform [0,1] grid, and an explicit **open-string** state (open strings are invisible to fingertip logic today, `playability.py:39-43`).
- Challenge: this is the core research problem — a fingertip near a fret line does not prove which string it presses; barre chords and muting break the one-finger-one-string assumption.

**Stage 7 — Match visual observations to audio note events by timestamp**
- Reuse: frame clock (`demux`), `find_fingering_at` (`playability.py:156-177`), causal prior application at onset−0.03 s (`contact_prior.py:23-27`), legacy's tolerance pattern (`fusion_engine.py:1731-1752`).
- Missing: a max-gap/tolerance guard in v1 (add `|Δt| ≤ ~0.12 s` else abstain); exposure of vision observations with timestamps through the backend job record.
- Recommend: nearest-frame-within-tolerance + temporal smoothing over ±k frames; abstain (do not vote) when coverage is low — "seeing nothing is safe; seeing a little is not."
- Challenge: frame rate vs. onset precision; camera/A-V clock drift (measure and correct per clip).

**Stage 8 — Validate candidates with pitch, tuning and geometry**
- Reuse: `candidates.py` (pitch→positions), `playability.py` costs, `string_physics.py`/`inharmonicity.py` (audio physics), Stage-4 geometry as a hard feasibility mask (fret ≤ max visible fret, string within detected rows).
- Missing: nothing fundamental — this is composition work.
- Challenge: conflicting evidence (physics says string A, vision says string B) — resolve via capped weights, never hard overrides, until vision is proven.

**Stage 9 — Resolve ambiguity with confidence-based ranking**
- Reuse: cluster Viterbi (`viterbi.py:185-299`), string-flip margin confidence (`:302-318`), `vision_evidence.py` gating (currently eval-only — **promote it into the runtime path before any vision is enabled**), `segment_decoder` K-best for analysis.
- Missing: a gate that actually fires (today's 0.71 coverage threshold is never met); a calibrated fusion weight.
- Recommend: pre-register a gate per §12; enable vision per-note only when (coverage ≥ threshold) AND (vision posterior margin ≥ threshold) AND (geometry orientation locked); otherwise fall back to audio-only for that note.
- Challenge: avoiding the measured failure mode where partial vision degrades more notes than it fixes.

**Stage 10 — Generate improved tablature**
- Reuse: all renderers (`render/ascii.py`, `gp5.py`, `musicxml.py`, `midi.py`); backend ASCII contract for compatibility.
- Missing: rhythm/timing in ASCII (available in `TabEvent` but not rendered); backend rendering of confidence.
- Recommend: keep ASCII as the compatibility surface; expose structured notes (Stage 2) so the frontend can show per-note confidence, candidates, and low-confidence flags (`--json` already provides `low_confidence_flags`).

---

## 9. Recommended Models and Techniques

### 9.1 Easy wins (days, no training, high confidence)

1. **Structured note-event contract** — pass `--json`/`--editor-output` in `processing.py:316`, persist to the job sidecar, surface tuning/note-count/confidence the frontend already expects (`tab-service.ts:82-83`). Unlocks every later stage and fixes a live UX gap.
2. **Nut end + fret numbering + string orientation** in `backend/app/cv/vision_analysis.py` — port the rule-of-18 fit and spacing-decay nut disambiguation from `tabvision/video/fretboard/calibrate.py:103-127,150-229` (already written and unit-tested in scratch).
3. **Vision response timestamps** — add `timestamp_seconds` to `VisionAnalysisResponse` (`schemas/vision.py:51-52`) from frame metadata (`processing.py:171-187`).
4. **Install/pin vision weights** — `hand_landmarker.task` and `yolo11n-obb.pt` are referenced but absent in this environment; without them any `--video` run fails before doing anything.
5. **Add a max-gap tolerance to `find_fingering_at`** (`playability.py:156-177`) — one-line parity with the legacy engine's 0.1 s tolerance; prevents stale-frame evidence.
6. **Promote `vision_evidence.py` gating into the runtime path** *before* any vision enablement — it exists, is tested, and is currently eval-only.

### 9.2 Substantial research (weeks–months, measurable risk)

1. **Fingertip → string/fret contact accuracy** (the central problem). Options: (a) improve the geometric posterior (Stage 6 inputs), (b) keypoint detection for contact points — note the learned fret-keypoint route already **failed** its gate (0.6305 vs 0.7195 OBB fit, `HANDOFF-2026-07-28`), (c) optical-flow/temporal smoothing from FretCam (quarantined, needs resurrection + eval), (d) a contact-specific detector trained on newly annotated data (§11). Do **not** re-run the failed learned string resolver without a new data regime.
2. **Temporal tracking** — homography EMA exists (`fretboard/tracker.py`) but is test-only; wire it with confidence decay and evaluate orientation-stability, which is the documented pathology.
3. **Fusion gating that fires** — today's coverage-based gate never triggers; design a per-note gate (coverage × posterior margin × orientation lock) with a pre-registered no-regression test.
4. **Complementary routing** — the A14 result says naive routing has ≤+0.058 headroom; only pursue if Stage 6 raises video accuracy above the audio prior (0.778).

### 9.3 Explicitly do NOT replace (no compelling reason)

- The audio transcription stack (Basic Pitch / highres / ensemble) — measured, gated, production-quality.
- The Viterbi decoder and its cost structure — well-tested; the problem is missing *evidence*, not missing machinery.
- The hybrid fretboard detector — F1 0.95 on its test set; improve its *outputs* (nut, numbering), not its architecture.
- ASCII rendering as the compatibility surface.

---

## 10. Phased Development Roadmap

### Phase 1 — Fretboard geometry & string/fret localization (vision-first, as requested)
- **Files/modules likely to change:** `backend/app/cv/vision_analysis.py` (nut detection, fret numbering, string orientation, timestamps), `backend/app/schemas/vision.py` (new fields), `backend/app/api/routes/vision.py`, tests in `backend/tests/test_vision.py`, possibly `backend/app/cv/hybrid_detector.py` (quad smoothing).
- **Data/annotations:** existing `data/extracted_fretboard/` (boxes only — insufficient); need per-frame **nut box/corner, fret-wire indices, string-line y-positions** labels. Start with synthetic boards (tests already generate them: `tests/test_vision.py:120-232`) + a few dozen real frames labeled with the existing annotate tooling pattern (`scratch/tab_vision/tabvision/scripts/annotate/`).
- **Metrics:** fretboard IoU/mAP (existing harness `backend/scripts/evaluate_real_footage.py`), nut-end accuracy (% frames with correct orientation), fret-numbering accuracy (exact & ±1), string-order accuracy ( Kendall-τ of row order vs pitch order), coverage/abstain rate.
- **Definition of done:** for every detected board, the API returns `{nut_end, frets:[{index(1-based), x, confidence}], strings:[{pitch_name, y, confidence}]}` with orientation abstaining honestly when uncertain; unit + real-footage tests green; no regression in existing detection tests.
- **Risks:** foreshortened/partial views (orientation pathologies documented in `HANDOFF-2026-07-28`); capo mistaken for nut; left-handed/mirrored footage; synthetic→real gap.

### Phase 2 — Hand/finger positions relative to the fretboard
- **Files:** new `backend/app/cv/hand_analysis.py` (or first enable `tabvision/video/hand/*` behind a flag), `vision.py` routes, schemas; install/pin MediaPipe model.
- **Data:** frames with hand/fingertip keypoint labels (21 MediaPipe landmarks are pseudo-labelable; verify a sample manually).
- **Metrics:** fingertip PCK (normalized by fret spacing), fretting-hand selection accuracy, per-frame latency, detection coverage (% frames with a usable hand).
- **DoD:** for ≥X% of frames with a visible fretting hand, fingertip positions are returned with confidence and timestamps, evaluated on a held-out real-footage set.
- **Risks:** MediaPipe failure modes (blur, occlusion by guitar body, two hands), mirror conventions, weights/licensing pinning.

### Phase 3 — Estimate string/fret contact positions
- **Files:** port/adapt `tabvision/video/hand/fingertip_to_fret.py` to consume Phase 1 geometry (fret-numbered, oriented); add an explicit open-string/muted state; optionally resurrect FretCam contact semantics as reference.
- **Data:** the critical new dataset — frames with gold **(string, fret) per pressing finger** (see §11). This does not exist in the repo today.
- **Metrics:** string accuracy (exact / ±1), fret accuracy (exact / ±1), posterior calibration (ECE), abstain quality (accuracy when it abstains vs votes).
- **DoD:** contact posterior beats *random* and approaches the audio prior on ambiguous notes; calibrated confidences; documented failure modes.
- **Risks:** this is the measured hard part (0.689 vs 0.778); barre/mute ambiguity; fingertip≠contact-point offset; open strings invisible to fingertip logic.

### Phase 4 — Align visual positions with audio note events
- **Files:** `processing.py` (structured `--json`/`--editor-output` ingestion), job sidecar schema, a new `backend/app/services/fusion_alignment.py` (or TabVision-side `--video` enablement with tolerance fix in `playability.py:156-177`), `schemas/vision.py`/`video.py`.
- **Data:** clips where both audio notes and vision frames exist (any video; alignment quality needs A/V sync check per clip).
- **Metrics:** onset↔observation matching rate within ±50/±100/±150 ms, abstain rate, per-note evidence coverage.
- **DoD:** every emitted note either has a matched vision observation (with Δt recorded) or an explicit "no evidence" marker; no stale-frame matches (tolerance enforced).
- **Risks:** 1 fps product frames vs ms onsets (must raise rate for fusion runs); clock drift; chord clusters sharing frames.

### Phase 5 — Multimodal fusion → improved tablature
- **Files:** `tabvision/fusion/*` (enable gated path: promote `vision_evidence.py` into runtime), `pipeline.py` (video flags), `processing.py` (pass `--video` behind a config flag), frontend (confidence/candidate display).
- **Data:** evaluation corpora already present in TabVision (§11) + gold string/fret labels for the ambiguous subset.
- **Metrics:** **primary — Tab F1 and ambiguous top-1 string accuracy vs audio-only** (§12), with per-clip no-regression; secondary — calibration, abstain rate, latency.
- **DoD:** pre-registered gate passed (§12): fused ≥ audio-only overall with CI excluding meaningful harm, and strict no-regression per clip; feature behind a default-off flag until then.
- **Risks:** the entire measured history (−0.20 ungated, +0.0000 gated, anti-complementary); coverage thresholds that never fire; regression on clean audio-only cases.

---

## 11. Datasets and Annotation Requirements

**Already present:**
- `data/extracted_fretboard/` — COCO fretboard boxes, 355 images (250 train / 105 test) + `annotations/{train,test}.json`. Supports detection only; **no strings, frets, nut, hands**.
- TabVision corpora (referenced by `tabvision/eval/parsers/` and `fusion/priors/*.manifest.json`): **GuitarSet** (CC-BY-4.0; audio + string/fret annotations used to build `guitarset-v1` position priors), **GAPS** (MusicXML tab with string/fret; `eval/parsers/gaps_musicxml_tab.py`), **PDMX**, **GuitarTechs** (MIDI), **UT Austin tablature (npy)**, **EGSet12**, plus a **SynthTab** blend. These give gold (pitch, string, fret, onset) for *audio-side* string-assignment evaluation — the harness already uses them (`scripts/eval/string_assignment_phase*.py`).
- Eval manifests with pre-registered gates: `fusion/priors/*.manifest.json` (e.g. `guitarset_v1` gate `mean_delta 0.1692 passed`; `acoustic_physics_v1` held-out `+0.1006`).

**Missing (must be annotated for Phases 1–3):**
1. **Geometry labels:** per-frame nut (corner/box), fret-wire x-positions with fret indices, string-line y-positions with pitch identity — a few hundred real frames across orientations/zooms/capos/left-handed players. Label with an extension of the existing annotate tooling (`tabvision/scripts/annotate/frames.py`, `label_clips.py`).
2. **Contact labels (the bottleneck):** per-frame pressing (string, fret) per finger — this is what no existing dataset in the repo provides at scale for in-the-wild video. Options: (a) controlled capture with known played notes (a "gold session" workflow already exists: `scripts/train/ingest_gold_session.py`, `personal/gold_tab.py`), (b) synthetic render augmentation (`scripts/augment/video.py`), (c) assisted labeling where audio-derived candidates pre-fill and a human corrects (the assisted-editor candidate machinery `assist/candidates.py` is designed for exactly this).
3. **Alignment labels:** note onset ↔ frame timestamp pairs with verified A/V sync (needed for Stage 7 metrics).

**Licensing:** GuitarSet CC-BY-4.0 is already handled via manifests; keep the hash-verified artifact discipline (`artifact_registry.py:82-96`) for anything new.

---

## 12. Evaluation and Benchmarking Plan

All metrics below are **proposed**; existing measured numbers are cited from current reports. Do not report any number that has not been produced by a run of the harness.

### 12.1 Component metrics

| Component | Metric | Protocol |
|---|---|---|
| Fretboard localization | IoU, AP@0.5 (box), quad-corner error (normalized by board length) | Existing `backend/scripts/evaluate_real_footage.py` + COCO test split (baseline: F1 0.95, mIoU 0.7154, `MODEL_EVALUATION_REPORT.md:29`) |
| String detection & ordering | Row detection P/R (match within ±0.5 row), ordering accuracy vs pitch-ordered ground truth, honest-abstain rate (≠6 reported) | Synthetic suite (`tests/test_vision.py:120-156`) + labeled real frames |
| Fret-wire detection | Wire P/R (±0.5 wire), fret-numbering exact/±1 accuracy (after Phase 1), rule-of-18 fit residual | Labeled real frames |
| Nut/orientation | Orientation accuracy %, abstain rate, flip-error rate (the documented pathology) | Labeled real frames |
| Fingertip/contact localization | PCK normalized by fret spacing; contact (string, fret) exact & ±1 accuracy; ECE of the posterior | Held-out gold-session clips |
| String assignment (ambiguous notes) | Top-1 / top-3 accuracy on pitch-ambiguous notes; same-pitch wrong rate | Existing harness: `scripts/eval/string_assignment_phase*.py`, `eval/string_assignment.py` (baseline 0.6770 / 0.9986 / 0.3230, `string_assignment_phase0_2026-07-27.md:22`) |
| Pitch accuracy | Pitch P/R/F1 (onset ±50 ms window) | `eval/guitarset_audio.py`, `eval/metrics.py` |
| Note-event timing | Onset F1 (±50 ms), offset error | Same (README acceptance: onset 0.94, pitch 0.93) |
| Final tablature | **Tab F1** (existing definition), solo/comp decomposition | `eval/composite.py`, `eval/runner.py`, `scripts/eval/q6_fusion_eval.py` |

### 12.2 Does vision actually improve audio-only tab? — the A/B experiment

**Design (pre-register before running):**
- **Corpora:** GAPS clean-12 (primary; the corpus where ungated video was measured at −0.2006) + GuitarSet player-05 held-out + at least one in-the-wild private set (the anti-complementary finding was measured on real footage — it must be re-checked, not assumed).
- **Arm A (control):** `tabvision transcribe <clip> --no-video --format ascii` — bit-identical to today's production invocation (`processing.py:316`).
- **Arm B (treatment):** same + `--video` with the Phase 1–4 stack (oriented/nut-anchored geometry, tolerance-guarded alignment, gated priors), `--fusion-lambda-vision` swept over a small pre-declared grid.
- **Arm C (oracle sanity):** vision with gold orientation/contact where available — measures the *ceiling* of the fusion layer independently of perception quality.
- **Primary endpoints:** aggregate Tab F1 (B − A with bootstrap CI); ambiguous top-1 string accuracy; same-pitch wrong rate.
- **Secondary:** per-clip deltas (no-regression requirement: no clip worse than −0.02), calibration (ECE), coverage/abstain rate, notes affected by video, latency.
- **Decision rule (mirrors existing gate discipline):** ship only if mean ΔTab F1 > 0 with 95% CI excluding ≤ −0.01 **and** per-clip no-regression holds — otherwise keep default-off and record the negative result, as the project already does (`DECISIONS.md`).

**Honesty constraints:** reuse the existing eval harness rather than writing a new one; report all arms including failures; never compare against numbers from a different corpus/condition (the A14 and phase-0 tables above are the reference points).

---

## 13. Risks and Technical Limitations

1. **Measured anti-fusion history.** Vision has already been shown to hurt (−0.20 Tab F1 ungated) and to be anti-complementary where audio fails (0.285 < 0.574). Any plan that assumes "adding vision helps" contradicts the evidence. Mitigation: gates, abstention, oracle arms.
2. **The gate that never fires.** Coverage-based gating measured 0.48–0.52 vs a 0.71 threshold → "vision" that does nothing (`DECISIONS.md:5944`). New gates must be calibrated on measured coverage, not aspirations.
3. **Product frame rate (1 fps).** `frame_sample_interval_seconds=1.0` (`config.py:68-73`) cannot support onset-level alignment; raising it collides with `max_extracted_frames=600` and storage/CPU.
4. **Lossy process boundary.** Only ASCII crosses TabVision→backend (`processing.py:316,322-328`); note events, confidences, candidates and `videoEnabled` metadata never arrive.
5. **Hard-coded, un-timeouted subprocess.** `processing.py:303-315` — machine-specific path, Windows-only, no timeout while the frontend gives up at 180 s (`tab-service.ts:6`); silent `analysis=null` on failure.
6. **Missing weights in this environment.** YOLO-OBB and MediaPipe model files are absent at default paths → `--video` would fail immediately.
7. **Orientation/pathology risk.** Documented end-for-end reversed homographies on some clips; open strings invisible to fingertip logic (`playability.py:39-43`); capo vs nut confusion.
8. **Stale self-description.** `cv/pipeline.py` stage flags, `capabilities.py` NOTES, README, and `JobResponse` docstrings under-report reality — misleading for anyone planning against them.
9. **Data gap.** No in-repo dataset of gold fingertip→(string,fret) contact for in-the-wild video; Phase 3 cannot be validated without building one.
10. **Prior art is quarantined, not dead.** FretCam, `fusion_engine.py`, `vision_evidence.py`, EMA trackers and the rule-of-18 fit all exist — the risk is either forgetting them (rebuilding) or enabling them unmeasured (regressing).

---

## 14. Source File and Function Reference

**Active backend**
| Path | Key symbols |
|---|---|
| `backend/app/main.py:93-97` | router registration (incl. `vision_router`) |
| `backend/app/api/routes/videos.py:24-67,70-90` | upload; job get |
| `backend/app/api/routes/frames.py:47-68,71-90,93-127,150-261` | process; frame list/serve; fretboard JSON/debug |
| `backend/app/api/routes/vision.py:168-255` | vision JSON / annotated / rectified (opt-in only) |
| `backend/app/services/uploads.py:73-157` | `save_upload`, `update_job`, `get_job` |
| `backend/app/services/processing.py:97-254,299-334,337-409` | `VideoProcessor.extract`, `run_tabvision`, `process` |
| `backend/app/services/storage.py:23-24,49-85,124-213` | upload/processed layout, atomic commit |
| `backend/app/cv/hybrid_detector.py:34-47,78-146,212-222` | thresholds, `detect()`, singleton |
| `backend/app/cv/ml_detector.py:35-40,159-187,479-510` | Faster R-CNN factory, weights, top-1 box→polygon |
| `backend/app/cv/fretboard_detector.py:47-66,269-405,572-741` | classical corridor, fret verification, confidence |
| `backend/app/cv/vision_analysis.py:136-235,419-475,514-575,583,701-704` | `order_quad`, `rectify_fretboard`, `detect_fret_wires`, `detect_strings`, `analyze_frame`, honesty note |
| `backend/app/cv/pipeline.py:15-89` | stage flags (stale), `run_pipeline` stub |
| `backend/app/schemas/{video,vision,fretboard,common}.py` | API contracts |
| `backend/app/core/config.py:36-113` | paths, 1 fps sampling, CORS |
| `backend/scripts/train_fretboard.py`, `evaluate_real_footage.py` | training/eval entry points |
| `backend/tests/test_vision.py:252,373` | "no note claims" and "vision never automatic" tests |

**TabVision audio + fusion (`scratch/tab_vision/tabvision/tabvision/`)**
| Path | Key symbols |
|---|---|
| `pipeline.py:190-517,520-571,693-709` | `run_pipeline_with_artifacts`, backend routing |
| `cli.py:60-76,179-567,606-778` | subcommands, `transcribe` options (`--json`, `--video`, `--fusion-lambda-vision`) |
| `types.py:17-18,25-53,127-153` | tuning, `GuitarConfig`, `AudioEvent`, `FrameFingering`, `TabEvent` |
| `demux/__init__.py:28-62,118-142,181-256,307-350` | demux, audio extract, frame clock |
| `audio/{basicpitch,highres,highres_ensemble,checkpoint_ensemble,filters,beats}.py` | models, ensembling, filters |
| `fusion/candidates.py:25-45` | pitch → all (string, fret) |
| `fusion/playability.py:113-123,156-177,180-218,235-277` | margin confidence, frame lookup, emission/transition costs |
| `fusion/viterbi.py:99-182,185-299,302-318` | decoder selection, DP, string-flip margin |
| `fusion/{position_prior,inharmonicity,string_physics,evidence,chord,chord_shapes}.py` | priors and evidence |
| `fusion/{neck_prior,position_window_prior,contact_prior}.py` | vision-derived priors (video-gated) |
| `fusion/vision_evidence.py` | orientation/gating layer (**eval-only**) |
| `fusion/inference_policy.py:41-199,304-365` | domain gates, decoder resolution (`context-v1` blocked) |
| `render/{ascii,midi,musicxml,gp5}.py` | output formats |
| `video/hand/{mediapipe_backend,fingertip_to_fret,neck_anchor,learned_string}.py` | hands, contact posterior (default-off) |
| `video/fretboard/{keypoint,calibrate,tracker}.py` | canonical frame, rule-of-18, EMA |
| `assist/{document,candidates}.py` | editor JSON, per-note candidates |

**Scratch legacy / prototypes**
| Path | Role |
|---|---|
| `scratch/tab_vision/tabvision-server/app/fusion_engine.py:575,1731-1752,1806` | v0 `fuse_audio_only` / video matching / `fuse_audio_video` (not production) |
| `scratch/tab_vision/tabvision-server/app/{fretboard_detection,video_pipeline,hand_anchor}.py` | v0 vision + `map_finger_to_position` |
| `scratch/tab_vision/fretcam/src/fretcam/{detection,hand_tracking,tracking}.py` | quarantined contact prototype |
| `scratch/tab_vision/docs/{DECISIONS.md, VIDEO_CHAIN_AUDIT_2026-07-28.md, HANDOFF-2026-07-28-video-evidence-closeout.md, EVAL_REPORTS/*}` | measured history and gates |

**Frontend (active)**
| Path | Role |
|---|---|
| `guitartab-lovable/src/routes/index.tsx:45-58,103-118` | state machine, results/frames render |
| `guitartab-lovable/src/lib/tab-service.ts:52-117` | upload (XHR), blocking process (180 s), unused `overlayUrl` |
| `guitartab-lovable/src/lib/vision-service.ts:121-146` | `annotatedUrl` used; `analyzeFrame`/`rectifiedUrl` dead |
| `guitartab-lovable/src/components/gt/{Results,Frames,Upload}.tsx` | UI |

---

## 15. Final Recommendations: Highest-Priority Next Steps

**Do first (in order):**

1. **Structured note-event contract (small, unblocks everything).** Change `run_tabvision()` (`processing.py:299-334`) to also pass `--json` (and/or `--editor-output`), persist note events + candidates + confidences + `videoEnabled` metadata to the job sidecar, and return tuning/note-count/low-confidence flags the frontend already expects (`tab-service.ts:82-83`). No model risk; makes alignment, evaluation and UX work possible.
2. **Phase 1 vision geometry: nut end + fret numbers + string orientation** in `backend/app/cv/vision_analysis.py` (port `calibrate.py:103-127,150-229` from scratch), with timestamps in `VisionAnalysisResponse`. This converts existing, working geometry into *musically identified* coordinates — the precondition for any contact→(string,fret) mapping — and is independently evaluable (orientation accuracy, fret-numbering ±1).
3. **Install and pin vision weights** (MediaPipe `hand_landmarker.task`, `yolo11n-obb.pt`) and add the missing **max-gap tolerance** to `find_fingering_at` (`playability.py:156-177`) before any `--video` experiment is run.
4. **Build the contact dataset** (gold (string,fret) per pressing finger on real clips) — Phase 3 is impossible without it; use the existing gold-session/annotate tooling as the base.
5. **Only then** run the pre-registered A/B (§12) with the gated fusion path (`vision_evidence.py` promoted to runtime), default-off until the gate passes.

**Do not:** re-enable `--video` in production on the strength of the existing stack (measured −0.20 ungated / +0.0000 gated); re-train the failed learned string resolver without new data; replace the audio stack or the Viterbi decoder; treat FretCam/`fusion_engine.py` as dead code to delete — they are reference implementations to mine.

---

## Closing answers

**What does the project genuinely do today?**
Upload a guitar video → extract frames at 1 fps → run audio-only TabVision in a subprocess → return ASCII tablature that the frontend renders, plus an opt-in gallery of per-frame fretboard-geometry overlays. The audio→tab path is real, tested and measured (Tab F1 ≈ 0.61 baseline); the vision path is real but geometry-only, per-frame, never invoked during transcription.

**Does audio currently identify the played string reliably?**
Partially. Audio never predicts the string — a decoder infers it from pitch via all playable positions, corpus priors, acoustic inharmonicity physics and playability costs. On ambiguous pitches it gets the right string **67.7%** top-1 (**99.9%** top-3), i.e. it is usually *close but ranked wrong*; ~32% of ambiguous notes are assigned the wrong string (`string_assignment_phase0_2026-07-27.md:22`). It is the strongest string signal available today (deployable video 0.689 < audio prior 0.778).

**Does vision currently identify finger-to-string contact?**
Not in the product. The active backend has no hand/finger detection at all. In scratch there is an experimental MediaPipe-based fingertip→(string,fret) *posterior* (default-off, weights not installed, never measured above the audio prior) and a quarantined FretCam contact prototype. No component in the shipped path identifies which string or which fret is being pressed.

**Is audio-vision fusion already implemented?**
Yes — comprehensively, in `scratch/tab_vision/` (modern `tabvision/fusion/` package used by `fuse()`, plus the legacy `fusion_engine.py`), including timestamp alignment, pitch→candidate lattices, vision emission terms, capped priors, and confidence margins. But it is **not active in the product**: the backend never passes `--video`, `video_enabled` defaults to `False`, and the protective gating layer is eval-only. Measured: ungated vision hurts (−0.15…−0.20 Tab F1), gated vision does nothing (+0.0000), video is anti-complementary where audio fails.

**What is the smallest useful improvement we should implement first?**
Consume TabVision's structured `--json`/`--editor-output` note events in the backend (`processing.py:299-334`) — it is a small, mechanical change that replaces the lossy ASCII-only boundary with timestamped notes, confidences and candidate lattices, which every subsequent alignment/evaluation/fusion stage requires, and it fixes the already-broken tuning/note-count display. As the first *vision* counterpart (your stated Phase 1), add **nut-end detection + fret numbering + string orientation** to `backend/app/cv/vision_analysis.py`, because without musically identified coordinates no fingertip observation can ever be converted into a trustworthy (string, fret).

**What should the final multimodal system look like?**
A single time-base pipeline: demux (audio clock + full-rate frames) → audio transcription → `AudioEvent[]` with priors → fretboard localization/rectification with **nut-anchored, fret-numbered, string-oriented** geometry → MediaPipe (or better) hands → fingertip→contact *posterior* with an explicit open-string state → timestamp-matched (±tolerance) to each note onset → validated against pitch/tuning/geometry → injected as a **capped, abstain-capable prior** into the existing cluster-Viterbi decoder → rendered tab, where every note carries a string-assignment confidence and the system only lets vision overrule audio when a pre-registered gate says it is right. Audio stays the backbone; vision becomes a per-note, calibrated, honestly-abstaining second opinion — not a replacement.
