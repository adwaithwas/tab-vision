# Architecture — planned computer-vision pipeline

This document describes the *planned* CV pipeline and how it fits the existing
foundation. It is a roadmap, not an implementation: nothing described here
exists in code yet (`backend/app/cv/pipeline.py` declares the stages and raises
`NotImplementedError` when asked to run).

## 1. Target pipeline

```
guitar-playing video
        │
        ▼
Video pre-processing          frame extraction, resolution/illumination normalisation
        │
        ▼
Fretboard detection           locate neck, frets and nut in the camera frame
        │
        ▼
String / fret mapping         map observed geometry → string number + fret position
        │
        ▼
Hand / finger detection       fretting-hand position as a cue for note changes
        │
        ▼
Temporal note tracking        track note candidates across frames, dedupe events
        │
        ▼
Note-event extraction         emit discrete events (string, fret, onset, duration)
        │
        ▼
Tablature generation          render events as six-string tablature
```

## 2. Scope and assumptions (first version)

- Standard six-string guitar in standard tuning.
- Controlled camera angle and reasonable lighting.
- Single notes and simple melodies first; chords/rhythmic passages later.
- Short, locally uploaded clips.
- The job is always: video in → tablature out, with per-event confidence.

## 3. Where the code will live

- `backend/app/cv/` — all CV and ML logic (Python only).
  - `preprocess.py` — frame extraction and normalisation.
  - `fretboard.py` — geometric fretboard detection.
  - `strings.py` — string/fret mapping.
  - `hands.py` — hand/finger detection.
  - `tracking.py` — temporal note tracking.
  - `events.py` — note-event extraction.
  - `render_tab.py` — tablature rendering.
  - `pipeline.py` — orchestrates the stages (stub today).
- `backend/app/services/analysis.py` — jobs transition
  `received → queued → analyzing → completed|failed`; results are persisted in
  the job metadata sidecar and served through `GET /api/jobs/{job_id}`.

## 4. Integration contract (already in place)

- `GET /api/capabilities` reports stage status so the UI can render what is
  implemented vs. planned without hard-coding.
- `POST /api/videos/upload` returns a `job_id`; analysis consumes the stored
  `{job_id}.{ext}` file from `data/uploads/`.
- `GET /api/jobs/{job_id}` already returns an `analysis` field (null today);
  it will carry `{ events: [{ string, fret, start_s, end_s, confidence }] }`.
- The frontend already renders the annotated-preview area, an empty six-string
  tablature staff, and an event-confidence panel that only appears when real
  events exist.

## 5. Candidate techniques (to be evaluated, not assumed)

- **OpenCV** — geometric edge/line detection, Hough transforms, homography for
  fretboard localisation. Evaluated first; no heavy dependencies.
- **MediaPipe Hands** (or equivalent) — fretting-hand landmarks, subject to a
  compatibility study on the project’s Python version and Windows environment.
- Classical signal/geometry heuristics for string positions and fretting before
  resorting to learned models, to keep the pipeline explainable and cheap.

Decisions will be recorded as they are made; nothing in this document commits
the project to a library.

## 6. Data plans

- Datasets are a separate, deliberate stage. No dataset is downloaded by this
  milestone.
- Directories `data/raw/`, `data/processed/`, `data/annotations/` are reserved
  for recordings, intermediate artifacts, and manual/scripted annotations
  (e.g. JSON or ASCII-tab ground truth per clip).

## 7. Honesty rules

- No pipeline stage is reported as implemented until it actually runs and its
  behaviour is verified.
- Accuracy/confidence numbers appear in the UI only when produced by real
  evaluation against real data.
- Every analysis result carries per-event confidence when the pipeline can
  produce it; the UI hides the confidence panel until that data exists.