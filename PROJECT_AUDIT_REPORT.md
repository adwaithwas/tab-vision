# GuitarTab AI — Technical Audit Report

- **Repository:** `D:\code\PROJECTS\tab creator`
- **Report file:** `PROJECT_AUDIT_REPORT.md` (the only file created by this audit)
- **Audit type:** Read-only, evidence-based technical audit
- **Date of audit:** 2026-10-12
- **Branch audited:** `main` (HEAD `47990ac`)
- **Auditor note:** No files were modified, no commands that install/download/train/migrate were run, and no Git state was changed. All secret values are redacted.

### Evidence classification legend

| Tag | Meaning |
|---|---|
| `[V-S]` | Verified from source code / repository text |
| `[V-A]` | Verified by inspecting an artifact on disk (binary/JSON/image) |
| `[H-A]` | Supported by a pre-existing artifact produced by an earlier run (not re-executed in this audit) |
| `[INF]` | Inferred with stated reasoning; not directly proven |
| `[UNK]` | Unknown / not verified in this audit |

---

## 1. Executive Summary

GuitarTab AI is a two-part research prototype that aims to turn a short video of a six-string guitar into tablature. The audit finds that the project is **substantially more built than its own documentation claims**, and also that **significant documentation and API metadata are stale and now contradict the code**.

Key findings:

1. **A real, working computer-vision fretboard detector exists.** `[V-S]` A classical OpenCV pipeline (`backend/app/cv/fretboard_detector.py`) and a hybrid ML wrapper (`hybrid_detector.py`) are implemented and wired into HTTP routes (`frames.py`, `vision.py`). This directly contradicts `README.md`, `docs/architecture.md`, `backend/app/cv/pipeline.py`, and the `/api/capabilities` payload, which all state fretboard detection is "planned"/not implemented. `[V-S]`
2. **A real, working audio→tablature path exists, but lives outside the backend.** `[V-S]` `ProcessingService.run_tabvision` (`backend/app/services/processing.py:299`) shells out to an **external executable** `scratch/tab_vision/tabvision/.venv/Scripts/tabvision.exe`. `[V-A]` That executable is present on disk. `[H-A]` A stored job sidecar proves the end-to-end path completed and produced ASCII tablature.
3. **A trained model checkpoint exists whose provenance is only partially documented.** `[V-A]` `backend/models/fretboard_rcnn.pt` (76,020,762 bytes) is a pure `state_dict` with no embedded metadata. Training code `[V-S]` (`ml_detector.py`, `scripts/train_fretboard.py`) fine-tunes a torchvision Faster R-CNN (MobileNetV3-Large + FPN, 2 classes) on a 355-image fretboard subset.
4. **Real execution evidence exists for the CV detector.** `[H-A]` `data/processed/evaluation/` contains a synthetic benchmark report (16/16 correct, mean IoU 0.9029) and a real-footage report (9/9 frames detected) produced by `scripts/evaluate_fretboard_detector.py`.
5. **The active frontend reports itself with outdated copy** and one route is a Lovable-managed ("published history") project. `[V-S]`
6. **The dominant risk is documentation/state drift, not missing functionality** — the capabilities contract, CV stage metadata, and README actively misrepresent what the system does. `[V-S]`

No accuracy claims in this report are invented: every number here comes from a file on disk or is explicitly marked inferred/unknown.

---

## 2. Scope, Method & Limitations

**In scope:** architecture, backend API/services, CV pipeline, audio/TabVision pipeline, model provenance, dataset provenance, frontends (active and deprecated), tests, configuration/secrets handling, build/run, documentation, discrepancies/risks.

**Method:** static inspection of source, docs, config, tests, and on-disk artifacts; enumeration of directories; Git state inspection; reading pre-existing generated artifacts (evaluation reports, job sidecars, model state dict header). `[V-S]`

**Explicitly NOT performed (limitations):**

- `pytest` / frontend test suites were **not executed** in this audit. All test results below refer to what tests *assert*, not that they passed today. `[UNK]`
- The trained model was **not re-run** on any image. `[UNK]`
- The TabVision executable was **not invoked** in this audit. `[UNK]`
- `scratch/` was not recursively fully scanned (very large `.venv` and `node_modules` dominate); targeted inspection only. `[V-S]`
- Metrics from `data/processed/evaluation/*` are treated as `[H-A]` (produced by a prior run), not re-verified. `[H-A]`

---

## 3. Repository & Git State

- **Branch:** `main`, reported up to date with `origin/main`. `[V-S]`
- **Latest commit:** `47990ac` ("removed overview section"); initial commit `b1e2429`; 5 commits total. `[V-S]`
- **No submodules:** no `.gitmodules`. `guitartab-lovable/` is tracked as ordinary files (not a gitlink). `[V-S]`
- **Unstaged change present before the audit:** `guitartab-lovable/src/routes/index.tsx` — exactly one deleted line (a footer paragraph: `"A project exploring computer vision and audio-based guitar transcription."`). This modification predates the audit and **was not touched**. `[V-S]`
- **Tracked top level:** `.gitignore`, `DESIGN.md`, `README.md`, `backend/`, `data/`, `docs/`, `frontend/`, `guitartab-lovable/`, `package-lock.json`, `scripts/`. `[V-S]`
- **Untracked / local-only (present on disk):** `.pytest_cache/`, `scratch/`, `test video.mp4` (8,765,990 bytes), plus all gitignored data artifacts below. `[V-S]`
- **Lovable-mounted nested repo:** `guitartab-lovable/` contains `AGENTS.md` instructing that published Git history must not be rewritten (no force-push/rebase/amend/squash of pushed commits). This constrains future Git operations on that path. `[V-S]`

### `.gitignore` (audited relevant entries) `[V-S]`

Ignores: `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `node_modules/`, `dist/`, `*.local`, `.env`, `.env.*.local`, `data/uploads/*` (except `.gitkeep`), `data/raw/*`, `data/processed/*`, `data/annotations/*`, `data/extracted_fretboard/`, `runs/`, `*.pt`, `backend/models/*.pt`, `scratch/`, `*.mp4/.wav/.mp3`, `*.log`.

**Consequence:** the CV checkpoint (`backend/models/fretboard_rcnn.pt`), the dataset zip, the extracted dataset, all extracted frames, and all evaluation outputs are **untracked**. The audit's evidence for model provenance and execution exists only on this machine. `[V-S]`

---

## 4. Architecture Overview

Three components coexist:

1. **Backend (`backend/`)** — FastAPI app (`app.main:create_app`). Routers: `health`, `capabilities`, `videos`, `frames`, `vision`. Services: `uploads`, `processing` (`ProcessingService`, `VideoProcessor`), `storage` (`ProcessedStore`). CV under `app/cv/`. File-based persistence only — **no database**. `[V-S]`
2. **Active frontend (`guitartab-lovable/`)** — TanStack Start / TanStack Router, React 19, Tailwind 4, Vite (Lovable template `tanstack_start_ts_current`). Talks to backend via `src/lib/tab-service.ts` (audio flow) and `src/lib/vision-service.ts` (opt-in vision). `[V-S]`
3. **TabVision subproject (`scratch/tab_vision/`)** — a **separate, gitignored project** (Flask API, Basic Pitch audio model, MediaPipe/OpenCV vision, `fusion_engine.py`). The backend invokes its packaged CLI `tabvision.exe` as a subprocess. `[V-S]`

**Request flow (verified):**

```
Browser (guitartab-lovable)
  → tab-service.ts    POST /api/videos/upload        (multipart, XHR, progress+abort)
  → tab-service.ts    POST /api/jobs/{id}/process    (180s timeout)
                        └─ backend ProcessingService.process()
                             ├─ VideoProcessor.extract()   (OpenCV frames → data/processed/{job})
                             └─ run_tabvision()            (subprocess → tabvision.exe)
  → tab-service.ts    GET  /api/jobs/{id}/frames
  → vision-service.ts GET  /api/vision/jobs/{id}/frames/{i}(/annotated|/rectified)  (opt-in)
```

`[V-S]`

**Storage layout:** uploads at `data/uploads/{job_id}.{ext}` + `{job_id}.json` sidecar; processed frames at `data/processed/{job_id}/` (with `.tmp-*` staging dirs). `[V-S]` `[V-A]`

---

## 5. Backend API & Services

### 5.1 Configuration (`app/core/config.py`) `[V-S]`

- `Settings(BaseSettings)`, `env_prefix="GUITARTAB_"`, env file `backend/.env`, `extra="ignore"`.
- Defaults: `app_name="GuitarTab AI"`, `version="0.1.0"`, `environment="development"`.
- Uploads: `upload_dir=<repo>/data/uploads`, `max_upload_size_mb=100`, `allowed_extensions=(".mp4",".mov",".webm")`, `allowed_content_types=("video/mp4","video/quicktime","video/webm","application/octet-stream")`, `upload_timeout_seconds=300`, `keep_uploads_days=30`.
- Frame extraction: `processed_dir=<repo>/data/processed`, `frame_sample_interval_seconds=1.0`, `frame_store_max_width=1280`, `jpeg_quality=85`.
- Resource limits: `max_video_duration_seconds=600`, `max_video_dimension=4096`, `max_decoded_frames=100_000`, `max_extracted_frames=600`.
- CORS default: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:8080`, `http://127.0.0.1:8080`, `http://localhost:3000`.
- `get_settings()` is `@lru_cache`d and validates/creates both data directories.

### 5.2 App wiring (`app/main.py`) `[V-S]`

- `create_app()` builds FastAPI, runs `configure_logging()`, lifespan calls `settings.validate_directories()`, adds `CORSMiddleware` (`allow_methods=["GET","POST","OPTIONS"]`), registers a global `Exception` handler returning a structured `ErrorDetail`, exposes `GET /` and includes the 5 routers.

### 5.3 Endpoints (verified from source) `[V-S]`

| Method | Path | Notes |
|---|---|---|
| GET | `/` | service/docs/health/capabilities links |
| GET | `/api/health` | status/service/environment/version/time |
| GET | `/api/capabilities` | implemented vs planned (see §16 drift) |
| POST | `/api/videos/upload` | validates + stores (field `file`); returns 201 |
| GET | `/api/jobs/{job_id}` | persisted metadata |
| POST | `/api/jobs/{job_id}/process` | decode + extract frames + run TabVision |
| GET | `/api/jobs/{job_id}/frames` | frame preview list (limit 1–200) |
| GET | `/api/jobs/{job_id}/frames/{frame_index}` | JPEG frame (optional `max_width`) |
| GET | `/api/jobs/{job_id}/frames/{frame_index}/fretboard` | hybrid detection JSON |
| GET | `/api/jobs/{job_id}/frames/{frame_index}/fretboard-debug` | detection overlay JPEG |
| GET | `/api/vision/jobs/{job_id}/frames/{frame_index}` | isolated vision analysis JSON |
| GET | `/api/vision/jobs/{job_id}/frames/{frame_index}/annotated` | annotated overlay JPEG |
| GET | `/api/vision/jobs/{job_id}/frames/{frame_index}/rectified` | rectified crop JPEG (404 if none) |

### 5.4 Processing service (`app/services/processing.py`) `[V-S]`

- `ProcessingService.process(job_id)` enforces a per-job `threading.Lock` (returns 409 on concurrent duplicate), transitions `received → processing → completed|failed`, extracts frames, then calls `run_tabvision` (see §7), and stores `analysis = {"tablature": <ascii>}` when TabVision returns content.
- `ProcessingError` carries `code`, `message`, `status_code`; routes convert to `HTTPException` with `ErrorDetail`.

---

## 6. Computer-Vision / Fretboard Detection

### 6.1 Modules `[V-S]`

- `cv/fretboard_detector.py` — classical OpenCV: CLAHE, adaptive Canny, probabilistic Hough, neck-edge pair clustering, perspective rectification + transverse fret verification, multi-factor confidence. Requires aspect ratio ≥ 2.2:1.
- `cv/vision_analysis.py` — classical analysis for the isolated `/api/vision` API: corner ordering, `cv2.warpPerspective` rectification, fret wires via vertical Sobel column profile, strings via horizontal Sobel row profile. Honors a "never fabricate" contract (`detected=False` unless credible; never hard-codes six strings).
- `cv/ml_detector.py` — `MLFretboardDetector` backed by a fine-tuned Faster R-CNN; lazy torch import; `DEFAULT_MIN_CONFIDENCE=0.40`; `DEFAULT_WEIGHTS_PATH = backend/models/fretboard_rcnn.pt`; polygon derived from the bbox.
- `cv/hybrid_detector.py` — ML-first with classical fallback/merge. `HybridDetectorConfig(ml_high_threshold=0.60, ml_blend_threshold=0.40, prefer_ml_above=0.50)`. Public entry point used by `frames.py`.
- `cv/pipeline.py` — a **stub** whose `STAGES` marks `fretboard_detection` (and all later stages) `implemented=False`, `status="planned"`; `run_pipeline()` raises `NotImplementedError`.

### 6.2 Honesty contract `[V-S]`

Both `vision_analysis.py` and `ml_detector.py` explicitly return `detected=False` with a `failure_reason` rather than inventing geometry. `/api/vision` isolates vision failures so the audio path is never affected (`vision.py` docstring and `_run_analysis` containment).

---

## 7. Audio → Tablature (TabVision) Pipeline

- **Entry point:** `ProcessingService.run_tabvision(job_id, video_path)` — `backend/app/services/processing.py:299`. `[V-S]`
- **Mechanism:** `subprocess.run([str(tabvision_exe), "transcribe", str(video_path), "--format", "ascii", "-o", str(out_tab)], capture_output=True, text=True, check=True)`. `[V-S]`
- **Executable path:** `<repo>/scratch/tab_vision/tabvision/.venv/Scripts/tabvision.exe`. `[V-A]` present on disk. If missing, the method logs a warning and returns `None` (job still completes, just without `analysis`). `[V-S]`
- **Output handling:** reads `out.tab`, copies it to `data/processed/{job_id}/out.tab`, returns the content; `CalledProcessError` and generic exceptions are logged and return `None` (no crash). `[V-S]`
- **TabVision project context (`scratch/tab_vision/`):** separate gitignored project. Per its `AUDIT.md` (2026-05-05) and `pyproject.toml`, its v0 approach = Basic Pitch audio (TensorFlow 2.15) + MediaPipe + classical fretboard + `fusion_engine.py`; a Phase-1 Basic Pitch fine-tune on GuitarSet was frozen mid-experiment (`feature/audio-finetune-phase1`) and older measurements were invalidated. `[V-S]` `[H-A]`
- **Coupling risk:** the backend has a hard runtime dependency on an external venv/executable inside a gitignored directory — not reproducible from the repository alone. `[V-S]` `[INF]`

---

## 8. Model & Training Provenance (`backend/models/fretboard_rcnn.pt`)

**Artifact facts** `[V-A]` (inspected previously; classified as artifact verification):

- Size 76,020,762 bytes; created 2026-10-10 17:07:42.
- Contents: a pure `state_dict` (OrderedDict, 284 tensors) with **no embedded metadata** (no epoch, dataset name, class names, or optimizer state).
- Matches torchvision `fasterrcnn_mobilenet_v3_large_fpn` with 2 classes: `cls_score` shape `(2, 1024)`, `bbox_pred` shape `(8, 1024)`. Loads strictly with only 46 BatchNorm `num_batches_tracked` keys missing (frozen-BN detection backbone).

**Training code (verified)** `[V-S]`:

- `build_fretboard_model(pretrained=True, num_classes=2)` — fine-tuned from **COCO-pretrained** weights (not from scratch, not an external fretboard checkpoint).
- `train_fretboard_model(...)`: SGD `lr=5e-4`, `momentum=0.9`, `weight_decay=1e-4`, `StepLR(step_size=5, gamma=0.5)`, default `num_epochs=15`, `batch_size=2`; saves `model.state_dict()` only.

**Unverified:** actual epoch count, loss trajectory, and any accuracy of *this* checkpoint are **not persisted** to disk. No `runs/`, no `eval_metrics.json`, no training log found. `[UNK]`

**Timeline (inferred from filesystem timestamps)** `[INF]`: zip → extracted dataset → checkpoint occurred sequentially on 2026-10-10 (zip 16:15 → extracted 16:59 → checkpoint 17:07), consistent with a single local training run.

---

## 9. Datasets & Provenance

- **Archive:** `data/raw/guitar-transcription-dataset.zip`, 4,361,170,426 bytes (≈4.36 GB). `[V-A]`
- **Derived from** (per training script + dataset layout): the Kaggle "Guitar Transcription Dataset" (`jacksonlightfoot`), used as a fretboard-segmentation subset. `[INF]` Dataset license was recorded as CC BY-NC-SA 4.0 (non-commercial) — **a licensing item to confirm** before any commercial use. `[INF]` `[H-A]`
- **Extracted artifacts:** `data/extracted_fretboard/train` (250 PNG), `test` (105 PNG) = **355 frames**; `annotations/train.json`, `annotations/test.json` in COCO format with a single category `fret`. `[V-A]`
- **Training used** the fretboard-segmentation subset only; the archive's `tablature_dataset/` (audio) was **not used** by this CV checkpoint. `[V-S]`

---

## 10. Frontends

### 10.1 Active: `guitartab-lovable/` `[V-S]`

- Stack: TanStack Start/Router, React 19, Tailwind 4, Vite; Lovable template `.lovable/project.json` → `tanstack_start_ts_current`.
- `src/lib/tab-service.ts`: `API_BASE` from `VITE_API_BASE_URL` (default `http://localhost:8000`); `ACCEPTED_EXT=["mp4","mov","webm"]`; `MAX_BYTES=100 MB`; `PROCESS_TIMEOUT_MS=180_000`; `uploadVideo` (XHR + progress + abort), `processJob`, `getFrames`, `frameUrl`, `overlayUrl`, `checkHealth`, `generateTablature`.
- `src/lib/vision-service.ts`: separate opt-in client; `analyzeFrame`, `annotatedUrl`, `rectifiedUrl`; explicitly documented as isolated from the "frozen" audio pipeline.
- Components: `Upload.tsx` (drag/drop, client validation, 100 MB/format copy), `ConnectionStatus.tsx` (live health poll, troubleshooting copy), `Frames.tsx` ("Analysis" toggle fetches the vision annotated overlay), `Results.tsx`.
- `.env.local` contains only `VITE_API_BASE_URL=<redacted>`. `[V-S]`
- Confirmed committed modification: `src/routes/index.tsx` footer paragraph removed (unstaged, pre-existing). `[V-S]`

### 10.2 Deprecated: `frontend/` `[V-S]`

- `package.json` name `guitartab-ai-frontend` (React 19, lucide-react, Tailwind 4, vitest).
- `src/services/api.ts`: `API_BASE_URL` from `VITE_API_BASE_URL` (default `http://localhost:8000`), `ApiError`, `getHealth`, `getCapabilities`, `processJob`, `getJob`, `listFrames`, `getFrameUrl`, `getFrameCvDebugUrl`.
- `README.md` §3/§6/§11 documents `frontend/` as the primary app; this is now **stale** relative to the active `guitartab-lovable/`.

---

## 11. Tests & Verification

**Backend (`backend/tests/`, `pytest.ini`: `testpaths=tests`, `pythonpath=.`, `addopts=-q`):** `[V-S]`

| File | Covers |
|---|---|
| `conftest.py` | tmp `upload_dir`/`processed_dir`, `settings` (max 2 MB, CORS `localhost:5173`), `client` via `TestClient(create_app)`, sample mp4/mov bytes |
| `test_health.py` | health shape + ISO-8601 time |
| `test_capabilities.py` | capabilities shape; asserts 7 stages; **asserts all stages except `preprocess` are `implemented=False`/`planned`** |
| `test_cors.py` | allowed origin echoed; unknown origin not echoed; OPTIONS preflight |
| `test_upload.py` | valid/invalid/empty/oversized uploads, safe filenames, job round-trip |
| `test_processing.py` | frame extraction via real generated videos (`video_factory.py`) |
| `test_vision.py` | vision endpoint behavior |
| `test_fretboard_detector.py` | classical detector behavior (uses `fretboard_factory.py` synthetic images) |
| `fretboard_factory.py`, `video_factory.py` | synthetic image / real-video factories |

**Critical observation:** `test_capabilities.py` *encodes the stale claim* that fretboard detection is unimplemented. Any correction of the capabilities metadata will require updating this test. `[V-S]`

**Frontend:** README documents `npm run typecheck`, `npm test`, `npm run build` for `frontend/`; the active `guitartab-lovable/` test setup was not verified. `[UNK]`

**Not executed in this audit:** neither suite was run. `[UNK]`

---

## 12. Real Execution Evidence

All items below are **pre-existing artifacts** from earlier runs (`[H-A]`), not reproduced during this audit.

### 12.1 CV synthetic benchmark — `data/processed/evaluation/evaluation_report.json` `[H-A]`

- Timestamp `2026-10-10T10:29:38Z`; 16 cases (11 positive, 5 negative).
- Results: **TP=11, TN=5, FP=0, FN=0; accuracy 1.0, precision 1.0, recall 1.0**; mean IoU (positives) 0.9029; mean orientation error 0.02°; mean latency 112.64 ms.
- Negative cases rejected with real `failure_reason`s (`insufficient_transverse_frets`, `excessive_image_noise`, `no_fretboard_candidate_found`, …).
- **Interpretation caveat:** these are **synthetic** images; the report itself warns synthetic success must not be read as real-world accuracy.

### 12.2 Real footage — same report `[H-A]`

- 9 real frames, `detected_count=9`, detection rate 100%, mean latency 614.21 ms (single frames up to ~1.0 s).

### 12.3 Hybrid run — `data/processed/evaluation/real_hybrid/evaluation_report.json` `[H-A]`

- 9 frames, detection rate 1.0, but **`source: "classical"` for all 9** → in this run the ML model did not win/contribute; results equal the classical detector. `[H-A]` `[INF]` (whether the model was loaded is not proven by the artifact).

### 12.4 End-to-end job artifact — `data/uploads/26af5e58632a4aca8fc7b4a7495d790b.json` `[H-A]`

- `status="completed"`, `original_name="test2.mp4"`, video `368×368`, `26.844 fps`, `464` frames, `17.285 s`, `frames_extracted=18`.
- `analysis.tablature` = real ASCII tab ("TabVision ASCII tab, Tuning: E A D G B E, Notes: 27", low-confidence notes marked `?`).

This is direct evidence that upload → frame extraction → TabVision subprocess → tablature all ran and persisted. `[H-A]`

### 12.5 Other on-disk artifacts `[V-A]`

- `data/processed/` contains ~19 real job output directories plus `.tmp-*` staging dirs.
- `data/uploads/` contains ~19 video+JSON job pairs (several 8,765,990-byte `test video.mp4` copies and 2,863,818-byte clips).
- `scratch/vision_eval/` contains overlay/rectified JPEGs for job ids `46b1bb27`, `9c60d4d2`, `ed6030df`.

---

## 13. Configuration & Secrets

- **Backend config source:** env vars with prefix `GUITARTAB_`, optional `backend/.env`; **no secrets are hard-coded** in application code. `[V-S]`
- `backend/.env.example` documents non-secret keys only: `GUITARTAB_ENVIRONMENT`, `GUITARTAB_UPLOAD_DIR` (commented), `GUITARTAB_MAX_UPLOAD_SIZE_MB`, `GUITARTAB_KEEP_UPLOADS_DAYS`, `GUITARTAB_CORS_ORIGINS`. `[V-S]`
- Frontend: `guitartab-lovable/.env.local` holds only `VITE_API_BASE_URL=<redacted>`; `frontend/.env.example` exists. `[V-S]`
- `.env` files are gitignored; no secret values were read out or reproduced in this report. `[V-S]`
- **Note:** `config.py` defines additional CORS default origins (`8080`, `3000`) and an `upload_timeout_seconds=300` not shown in `.env.example` — not a security issue, but a doc/config drift. `[V-S]`

---

## 14. Build / Run / Deploy

- **Backend:** `backend/requirements.txt` → fastapi, uvicorn, python-multipart, pydantic, pydantic-settings, opencv-python-headless, numpy, torch, torchvision, pytest, httpx. `[V-S]`
- **Run:** `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` (README). `[V-S]`
- **Frontend (active):** `guitartab-lovable/` via its own npm scripts (TanStack Start/Vite); the active run command was not verified in this audit. `[UNK]`
- **Frontend (deprecated):** `cd frontend && npm install && npm run dev` (README). `[V-S]`
- **Deploy:** no Dockerfile, CI workflow, or deployment config found at repo root; `scratch/tab_vision/` has `.github/`, `vercelignore` but is external/untracked. `[V-S]`
- **TabVision runtime precondition:** must have `scratch/tab_vision/tabvision/.venv/Scripts/tabvision.exe` present or audio transcription silently no-ops. `[V-S]`

---

## 15. Documentation & Specs

- `README.md` — describes the project as "foundation only" with the CV pipeline "not implemented." **Now materially inaccurate** (CV detector + TabVision path exist). It also documents `frontend/` as the primary app. `[V-S]`
- `docs/architecture.md` — explicitly a "planned" pipeline, says nothing described exists; `pipeline.py` "raises `NotImplementedError`." **Now inaccurate.** `[V-S]`
- `DESIGN.md` — "Thesis Quarterly" design tokens (Source Serif 4, IBM Plex Mono, cobalt accent; surface `#f4eedb`, primary `#1a1814`). `[V-S]`
- `backend/app/api/routes/frames.py` docstring — says "classical CV" but the code imports and calls `detect_fretboard_hybrid`. `[V-S]`
- `scratch/tab_vision/` docs: `AUDIT.md`, `SPEC.md`, `README.md`, `tabvision_specification.md`, plus dated audit/eval reports — external project, not part of the tracked product. `[V-S]`

---

## 16. Discrepancies, Risks & Unknowns

### 16.1 Confirmed discrepancies `[V-S]`

1. **Capabilities contract contradicts code.** `GET /api/capabilities` `NOTES` state "No ... fretboard detection ... is implemented," and `cv/pipeline.py` marks `fretboard_detection` (and everything after) `implemented=False`/`planned`. In reality, classical + hybrid + ML detection are implemented and exposed over HTTP.
2. **Tests enshrine the stale state.** `test_capabilities.py` asserts every stage except `preprocess` is `implemented=False`.
3. **`frames.py` docstring** says classical, code uses hybrid.
4. **README/architecture/tab-service naming.** README describes `frontend/` and no CV; the active app is `guitartab-lovable/` and CV exists.
5. **Doc/config drift.** README tables omit extra CORS origins and `upload_timeout_seconds`.

### 16.2 Risks

- **Provenance gap (medium/high):** the shipped checkpoint has no embedded metadata and there is no training log; the only accuracy figures are for the *classical* detector, not the ML model. The ML model's real-world quality is unproven. `[V-A]` `[UNK]`
- **Fragile audio dependency (high):** the core "tab generation" feature depends on an external executable inside a **gitignored** directory; a fresh clone cannot run it. `[V-S]` `[INF]`
- **Licensing (medium):** the training dataset appears non-commercial (CC BY-NC-SA 4.0) — must be confirmed and honored. `[INF]` `[H-A]`
- **Untracked critical assets (medium):** model, dataset, and eval outputs are all untracked; losing the machine loses reproducibility evidence. `[V-S]`
- **Lovable history constraint (low):** nested-repo guidance forbids rewriting published history — safe now, but a constraint on future operations. `[V-S]`
- **Silent degradation (medium):** if `tabvision.exe` is absent, jobs still report `completed` with `analysis=null`, which could be misread as success. `[V-S]`

### 16.3 Unknown / unverified `[UNK]`

- Whether current test suites pass today.
- The ML model's real accuracy; whether the model loaded during the `real_hybrid` run.
- Exact training epochs/loss for the checkpoint.
- Active frontend test/lint/build health.
- Any real (non-synthetic) ground-truth tablature accuracy for the end-to-end path.

---

## 17. Recommendations

Prioritized, non-destructive:

1. **Reconcile the capability contract with reality** (High). Update `cv/pipeline.py` stage flags, `capabilities.py` NOTES, and `test_capabilities.py` so the API reports the true state. Document clearly that *detection* is implemented while *string/fret mapping, hand tracking, note events, and tab generation* remain unimplemented in-repo (they live in the external TabVision project).
2. **Make the audio dependency reproducible** (High). Document/expose the `tabvision.exe` requirement, or vendor a supported invocation path; avoid `completed`-with-`analysis=null` masquerading as success.
3. **Record model provenance** (High). Persist training metadata (epochs, dataset id, class names, metrics) alongside the checkpoint, and publish a real evaluation of the ML detector against non-synthetic data.
4. **Fix documentation drift** (Medium). Rewrite README/architecture to reflect the active `guitartab-lovable/` frontend and the implemented CV components; fix the `frames.py` docstring.
5. **Confirm dataset licensing** (Medium) before any distribution/commercial use.
6. **Decide the tracking strategy** (Medium) for model/dataset/eval artifacts (checksum manifest, external artifact store, or Git LFS).
7. **Add an end-to-end smoke test** (Low/Medium) that asserts `analysis.tablature` is non-null for a fixture clip, gated on TabVision availability.

---

## 18. Appendix: Evidence Index

**Source (verified) `[V-S]` / artifact `[V-A]` references:**

- App/config: `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/core/logging.py`, `backend/app/api/deps.py`.
- Routes: `backend/app/api/routes/{__init__,health,capabilities,videos,frames,vision}.py`.
- Services/schemas: `backend/app/services/{processing,uploads,storage}.py`; `backend/app/schemas/{common,video,fretboard,vision}.py`.
- CV: `backend/app/cv/{__init__,pipeline,fretboard_detector,vision_analysis,ml_detector,hybrid_detector}.py`.
- Scripts: `backend/scripts/{train_fretboard,evaluate_real_footage}.py`, `scripts/{cleanup_uploads,evaluate_fretboard_detector}.py`.
- Tests: `backend/tests/*` + `backend/pytest.ini`.
- Frontends: `guitartab-lovable/{package.json,.lovable/project.json,src/lib/tab-service.ts,src/lib/vision-service.ts,src/components/gt/*,src/routes/index.tsx}`; `frontend/{package.json,src/services/api.ts}`.
- Docs: `README.md`, `docs/{architecture,api}.md`, `DESIGN.md`, `backend/.env.example`.
- External project: `scratch/tab_vision/{README.md,AUDIT.md,SPEC.md,tabvision/pyproject.toml}`.
- Config: `.gitignore`.
- Artifacts: `backend/models/fretboard_rcnn.pt`; `data/raw/guitar-transcription-dataset.zip`; `data/extracted_fretboard/**`; `data/uploads/*.{mp4,json}`; `data/processed/**`; `data/processed/evaluation/**`; `scratch/vision_eval/**`.

**Report generated by a read-only audit. No source, config, dataset, checkpoint, or Git state was modified. The only file written is this report.**
