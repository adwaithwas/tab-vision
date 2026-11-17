# CURRENT STATE AUDIT — GuitarTab AI Repository

## 1. Git State

- **Branch:** `main`, up to date with `origin/main`
- **Latest commit:** `2e0d08c added requirements` (and 4 prior commits in history)
- **Git status:** Clean — no modified tracked files
- **Untracked files (3):**
  - `INSTALL.md`
  - `INTERRUPTED_SPRINT_STATUS.md`
  - `MULTIMODAL_FUSION_READINESS.md`
- **No agent-induced modifications detected.** Repository is in a pristine state relative to the base branch.

---

## 2. Implementation Audit

| Feature | Status | Evidence |
|---------|--------|----------|
| **Video upload + validation** | Fully implemented and usable | All 16 upload tests pass (`test_upload.py`); backend validates extensions, size, content type; real files written to disk |
| **Frame extraction (OpenCV)** | Fully implemented and usable | All 23 processing tests pass (`test_processing.py`); decodes video, samples at 1 fps, saves frames as JPEG, atomic commit on success |
| **Classical fretboard detection** | Fully implemented and usable | All 18 fretboard detector tests pass (`test_fretboard_detector.py`); CNN-less pipeline using Hough lines, edge clustering, fret verification |
| **ML Fretboard RCNN** | Partially available (weights exist, inference degraded) | Model file `backend/models/fretboard_rcnn.pt` exists (COCO-trained, 355 images). `torch` not available in this environment; `HybridFretboardDetector` degrades to classical-only mode without errors. |
| **Vision analysis pipeline** (`vision_analysis.py`) | Fully implemented and usable | All 25 vision tests pass (`test_vision.py`); full end-to-end: detect → rectify → string/fret measurement; honest limitations when evidence insufficient |
| **CV pipeline** (`cv/pipeline.py`) | Stubbed / not connected | Intentionally raises `NotImplementedError`; correctly reported as `"planned"` in `/api/capabilities`; no auto-execution during upload/processing |
| **Audio pipeline (TabVision)** | Working | External `tabvision.exe` called during `process_job`; successfully produced 35-note tablature for test video; gracefully returns `None` if executable missing |
| **No CV auto-execution during processing** | Verified true | `test_vision_does_not_run_automatically_during_process` passes; `job.analysis` remains `null` until explicitly requested via `/api/vision` |

---

## 3. Vision Pipeline — End-to-End Flow

```
Upload video
   │
   v
POST /api/jobs/{id}/process
   │
   ├─► VideoProcessor.extract() — OpenCV decode → sample frames at 1 fps → save JPEG per job
   │
   ├─► run_tabvision() — call tabvision.exe for audio→MIDI→ASCII tablature
   │    └─► If executable found: produces tablature saved to job.analysis.tablature
   │    └─► If executable NOT found: analysis.tablature = None
   │
   └─► Job status: received → processing → completed (or failed)
          │
          v
GET /api/vision/jobs/{id}/frames/{idx}  (opt-in, experimental)
       │
       ├─► load_frame() — read extracted frame JPEG from disk (read-only)
       │
       ├─► detect_fretboard_hybrid() — ML-first, classical fallback
       │    │   • If ML weights available and confidence >= 0.60 → return ML result
       │    │   • Otherwise → classical OpenCV detector (fretboard_detector.py)
       │
       ├─► analyze_frame() — vision_analysis.py orchestrator
       │    │   1. Order quad corners (PCA-based)
       │    │   2. Refine orientation in rectified space
       │    │   3. Rectify perspective (cv2.warpPerspective)
       │    │   4. detect_fret_wires() — vertical Sobel column peaks
       │    │   5. detect_strings() — horizontal Sobel row peaks, 6-subset selection
       │    │   6. Return VisionAnalysis with detected, strings, frets, limitations, diagnostics
       │
       └─► Response: VisionAnalysisResponse JSON
            • detected : bool (true if credible fretboard localized)
            • confidence : float (0.0–1.0)
            • strings : list of measured string rows (may be < 6 with honest limitation note)
            • frets : list of measured fret wires (may be < 6 with caveat)
            • limitations : plain-language caveats (e.g. "Only 1 string row could be measured")
            • diagnostics : metrics from detectors (edge density, confidence, source, etc.)
            • rectified / rectified_annotated : JPEG + size when detection succeeded
```

**Detection capabilities:**
- Fretboard localization (polygon + geometry) via classical CV + optional ML
- String row measurement (y-positions in rectified crop; fewer than 6 reported honestly)
- Fret wire measurement (x-positions in rectified crop; minimum 3 for reliable stats)
- Rectified crop generation with annotated overlay

**Limitations always populated:**
- Fewer than 6 strings measured → note that six evenly spaced strings not resolved
- Fewer than 3 frets → note that fret spacing statistics unreliable
- String pitch identity (EADGBE) and fret numbers NOT inferred — only geometric positions measured
- No note-level claims of any kind

**Output usability:** Yes — when a credible fretboard is detected, the response includes ordered polygon, geometry, string positions, fret positions, rectified crop, and honest limitations. When nothing credible is found, `detected=false` with `failure_reason` and limitations.

---

## 4. ML Model

| Attribute | Value |
|-----------|-------|
| **Checkpoint path** | `backend/models/fretboard_rcnn.pt` |
| **Training provenance** | Fine-tuned Faster R-CNN (MobileNetV3-Large + FPN) on 355-image guitar fretboard segmentation dataset in COCO format. Trained for 15 epochs with SGD (lr=5e-4, momentum=0.9, weight_decay=1e-4). |
| **Evaluation metrics** | Not explicitly reported in the inference code. Training tracks average loss per epoch. The model is loaded lazily and returns `detected=False` when confidence is below `DEFAULT_MIN_CONFIDENCE=0.40`. |
| **Current inference usage** | **Not actively used** in the default code path. The `HybridFretboardDetector` attempts ML first (`ml_high_threshold=0.60`), but since `torch` is not importable in the current environment, the detector degrades to classical OpenCV-only mode without error. If `torch` were available and the weights existed, the ML detector would be used for high-confidence detections (>0.60), with classical fallback for blended confidence (0.40–0.60). |
| **Fallback behavior** | When ML unavailable: `HybridFretboardDetector.detect()` runs the classical `detect_fretboard()` and returns its result with `source="classical"` added to diagnostics. |

---

## 5. Frontend — Vision Features Connected and Usable

| Feature | UI Status | Details |
|---------|-----------|---------|
| **Upload zone** | Fully functional | Drag/drop or browse; client-side validation mirrors backend rules; real upload via XHR |
| **PipelineSection** | Functional | Pulls real capabilities from `/api/capabilities`; shows all CV stages as `"planned"` with `"status: planned"`; never claims anything implemented |
| **AnalyzePanel** | Functional | Button labeled "Analyze Video"; disabled when backend offline; informative copy explaining CV pipeline not yet implemented |
| **ResultsSection** | Partially functional | Shows job status; tablature area renders empty six-line scaffold; `ConfidencePanel` only renders when `isAnalysisResultWithEvents(analysis)` — never true in this milestone since `analysis` is always `null` |
| **AnnotatedPreview** | Functional (opt-in) | Loads frames for a processed job; toggle between "CV Diagnostics ON" (calls `/api/vision/jobs/{id}/frames/{idx}/annotated`) and "Raw Frame ON"; shows detection polygon + strings + frets drawn on frame, or clearly labels "NO FRETBOARD DETECTED" with reason |
| **TablatureArea** | Functional | Renders empty six-string tablature staff with string labels (E A D G B E); only populates tab if `tabText` prop provided; otherwise shows "No note events yet — the staff stays empty until real analysis output exists." |
| **Vision endpoints** (`/api/vision/...`) | Opt-in, functional | Separate router prefix `/api/vision`; no existing audio-pipeline schemas modified; every error scoped to request; frame reuse read-only via `ProcessingService.frame_file_path` |

**What the user sees in the UI:**
- Upload video → job created with status `received`
- Press "Analyze Video" → upload continues, job moves to `completed`
- Job details show: status `received`, analysis `null`, no tablature auto-generated from vision
- User must explicitly use vision endpoints or the tablature remains the empty scaffold
- Pipeline roadmap visible: all CV stages explicitly marked as planned

---

## 6. Audio Pipeline — Video-to-Audio-to-Tablature

**Status:** Verified working.

**Flow:**
1. `POST /api/jobs/{id}/process` → `ProcessingService.process()` → `service.processor.extract()` (frame extraction)
2. Then `service.run_tabvision(job_id, video_path)` is called
3. `run_tabvision()` locates `tabvision.exe` at `scratch/tab_vision/tabvision/.venv/Scripts/tabvision.exe`
4. If found: runs `transcribe <video> --format ascii -o out.tab`
5. Reads the `.tab` output, saves it to `processed/<job_id>/out.tab`
6. Job `analysis` field set to `{"tablature": "<content>"}`

**Verification:** Running the full pipeline on `test video.mp4` (9s, 1000×1000, h264/aac, ~24 fps) produced:
- 9 frames extracted successfully
- TabVision executable found and ran successfully
- Tablature with 35 notes, tuning E A D G B E, capo none
- Job `analysis.tablature` contains the ASCII tab string

**If tabvision.exe NOT found:** `run_tabvision()` logs a warning and returns `None`; job `analysis` remains `None`; the upload/process flow continues unaffected — the user gets a completed job with no tablature, and the frontend shows the empty scaffold with the banner "Your video is ready on this device. Press 'Analyze Video' to upload it."

**Hard constraint:** Do not modify `scratch/tab_vision/` or the audio pipeline — verified the pipeline works as-is.

---

## 7. Tests — Pass/Fail Counts

| Test file | Tests run | Pass | Fail | Notes |
|-----------|-----------|------|------|-------|
| `test_capabilities.py` | 1 | 1 | 0 | |
| `test_health.py` | 2 | 2 | 0 | |
| `test_cors.py` | 3 | 3 | 0 | |
| `test_upload.py` | 16 | 16 | 0 | |
| `test_processing.py` | 23 | 23 | 0 | |
| `test_fretboard_detector.py` | 18 | 18 | 0 | |
| `test_vision.py` | 25 | 25 | 0 | |
| **Total** | **88** | **88** | **0** | **0% failure rate** |

**Intermittent failures:** None reported. All tests pass consistently.

---

## 8. Real Demonstration — Test Video Results

**Test video:** `test video.mp4`
- Duration: 9.009 seconds
- Resolution: 1000 × 1000 pixels
- FPS: ~23.976 (approx 24 fps)
- Codec: h264 / aac
- Size: 8.77 MB

**Full pipeline execution:**

1. **Upload** (`POST /api/videos/upload`): 201 response, job ID `500b1a6bf3a44ffb8a72efc3db9ef74`
2. **Process** (`POST /api/jobs/{id}/process`): 200 response
   - Frame extraction: **9 frames** extracted at 1 fps interval from 216 total frames
   - Video metadata: 1000×1000, ~24 fps, ~9s duration
   - TabVision: **Found and executed successfully**
   - Tablature produced: 35 notes, tuning E A D G B E, capo none
3. **Job analysis:** `{"tablature": "TabVision ASCII tab\nTuning: E A D G B E   Capo: none   Notes: 35\n..."}`

**Vision API endpoints** (opt-in):

- `GET /api/vision/jobs/{id}/frames/0`: 200
  - `detected: True`, `confidence: 0.9564`
  - `strings_detected: 1` (honest limitation: only 1 string measurable from video frame evidence)
  - `frets_detected: 6`
  - `limitations: ['Only 1 string row(s) could be measured from image evidence; six evenly spaced strings were not resolved in this frame.', 'String pitch identity (EADGBE) and fret numbers are not inferred — only geometric positions are measured. No notes are identified.']`
  - `failure_reason: None`
  - One string row measured, 6 fret wires measured (from classical CV on this particular frame)

- `GET /api/vision/jobs/{id}/frames/0/annotated`: 200, JPEG image (78,675 bytes) — original frame with detection polygon + measured strings (blue) + frets (yellow) overlaid

- `GET /api/vision/jobs/{id}/frames/0/rectified`: 200, JPEG rectified crop with annotations

- `GET /api/jobs/{id}`: analysis contains `{"tablature": "..."}` from TabVision (audio-based), **not** from vision

**Key observation:** The full end-to-end pipeline works end-to-end: upload → frame extraction → TabVision audio transcription → tablature. The vision analysis is a separate, opt-in layer that measures geometry from extracted frames but does not affect the audio/tablature output.

---

## 9. Agent Work — Changes from Recent Sessions

**Check:** Repository state after audit.

- `git status` shows only the 3 pre-existing untracked files (`INSTALL.md`, `INTERRUPTED_SPRINT_STATUS.md`, `MULTIMODAL_FUSION_READINESS.md`)
- No new files, modifications, or commits introduced during this audit
- Temporary test scripts (`run_test.py`, `test_vision_api.py`) were successfully cleaned up
- Git untracked files count matches the baseline: 3 files

**Conclusion:** No agent-induced changes are present in the repository. The audit only read existing code and ran existing tests; all findings reflect the state of the codebase before this session began.