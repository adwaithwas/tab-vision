# GuitarTab AI

**Video to guitar tablature.** GuitarTab AI is a Computer Vision (CVDV) research
prototype that will read a short video of six-string guitar playing and produce
six-string tablature.

> **Milestone status — foundation only.** This repository currently implements a
> polished, fully working **application foundation**: a React/TypeScript
> interface, a FastAPI backend, and a real video upload + validation pipeline.
> The **computer-vision pipeline is not implemented yet**. No note detection,
> prediction, accuracy or tablature output is produced, and the application
> never fakes any. The results surface is built and waiting for real data.

---

## 1. What works today vs. what is planned

| Capability | Status |
|---|---|
| FastAPI backend (health, capabilities, upload, job lookup) | **Implemented** |
| Real multipart video upload with validation and safe storage | **Implemented** |
| Live backend connection indicator in the UI | **Implemented** |
| Video selection, metadata, client-side validation, drag & drop | **Implemented** |
| Upload progress (real bytes) and cancellation | **Implemented** |
| Annotated-video preview, tablature staff, event-confidence panel | **Structure only** (empty by design) |
| Fretboard detection, string/fret mapping, hand detection | **Planned** |
| Temporal note tracking, note-event extraction | **Planned** |
| Tablature inference / generation | **Planned** |

Planned stages are reported by `GET /api/capabilities` and rendered in the
“Pipeline” section of the UI. Nothing there is marked as implemented.

---

## 2. Architecture and request flow

```
                 ┌──────────────────────────────┐
                 │  React + Vite + TS (frontend) │
                 │  pages → components → hooks   │
                 │  services/api · services/upload│
                 └───────────────┬──────────────┘
                                 │ fetch /api/health, /api/capabilities
                                 │ XHR multipart  POST /api/videos/upload
                                 ▼
                 ┌──────────────────────────────┐
                 │  FastAPI (backend/app)        │
                 │  api/routes → services → cv    │
                 │  schemas · core (config/log)   │
                 └───────────────┬──────────────┘
                                 │ validate + stream to disk
                                 ▼
                 ┌──────────────────────────────┐
                 │  data/uploads/                │
                 │  {job_id}.{ext} + {job_id}.json│
                 └──────────────────────────────┘

  cv/pipeline.py — declared but raises NotImplementedError (no inference yet)
```

- All computer-vision and ML logic lives in Python under `backend/app/cv/`.
  React components never contain CV logic.
- The frontend talks to the backend through a single typed client
  (`frontend/src/services/api.ts`), so the CV pipeline can be added later
  without rewriting the UI.

See [`docs/architecture.md`](docs/architecture.md) for the planned CV pipeline
and [`docs/api.md`](docs/api.md) for the API contract.

---

## 3. Repository structure

```
frontend/                React + Vite + TypeScript + Tailwind app
  src/
    components/          UI components (Header, UploadZone, Results…)
    pages/               HomePage
    services/            api client, upload transport, validation
    hooks/               useBackendStatus, useCapabilities, useUpload, useVideoMetadata
    types/               shared API types (mirrors docs/api.md)
    styles/              design tokens + component recipes (Tailwind v4)
    test/                vitest setup
backend/                 FastAPI service
  app/
    main.py              app factory (CORS, logging, routers)
    api/routes/          health, capabilities, videos
    schemas/             Pydantic request/response models
    services/            upload validation + storage
    cv/                  CV pipeline (stub — not implemented)
    core/                settings + logging
  tests/                 pytest suite
  requirements.txt
data/
  raw/  processed/  annotations/   reserved for datasets/artifacts
  uploads/                         uploads + job metadata (gitignored)
scripts/
  cleanup_uploads.py               retention cleanup
docs/
  architecture.md  api.md
DESIGN.md                          visual design system used by the frontend
```

---

## 4. Prerequisites

- **Python** 3.11 or newer (developed on 3.13) with `venv`.
- **Node.js** 20+ and **npm** 10+ (developed on Node 22 / npm 10).
- A modern browser.

---

## 5. Installation

From the repository root:

### Backend

```powershell
# create and activate a virtual environment
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1            # Windows PowerShell
# source backend/.venv/bin/activate           # macOS / Linux

pip install -r backend\requirements.txt
```
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

### Frontend

```powershell
cd frontend
npm install
```

### Environment configuration

Both sides read optional `.env` files. Copy the examples:

```powershell
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
```

Documented, non-secret values:

| Variable | Side | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000` | Backend base URL |
| `GUITARTAB_ENVIRONMENT` | backend | `development` | Environment label |
| `GUITARTAB_UPLOAD_DIR` | backend | `<repo>/data/uploads` | Where uploads are stored |
| `GUITARTAB_MAX_UPLOAD_SIZE_MB` | backend | `100` | Maximum upload size |
| `GUITARTAB_KEEP_UPLOADS_DAYS` | backend | `30` | Retention window |
| `GUITARTAB_CORS_ORIGINS` | backend | `http://localhost:5173,…` | Allowed browser origins |

---

## 6. Running the application

Two terminals, both from the repository root.

**Terminal 1 — backend:**

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API root: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>

**Terminal 2 — frontend:**

```powershell
cd frontend
npm run dev
```

- App: <http://localhost:5173>

The header shows a **live** status indicator driven by `GET /api/health`. When
the backend is stopped the indicator turns to “Backend offline” and the
**Analyze Video** button is disabled.

---

## 7. Uploading and validating a video

1. Drag a video onto the upload area, or click to browse.
2. Accepted formats: **MP4, MOV, WebM**; maximum size **100 MB** (configurable).
3. The interface shows the file name, size, type, and — when the browser can
   read them — duration and resolution. You can remove or replace the file.
4. Invalid files (wrong extension/type, empty, oversized) are rejected **before**
   any request with an actionable message.
5. **Analyze Video** performs the real upload with a progress indicator. You can
   cancel an in-flight upload.
6. On success the app shows the real **job id** and confirms the video was
   received and stored. It explicitly states that **no analysis is performed** —
   the job remains in the `received` state until the CV pipeline exists.

### Where uploads are stored and how they are cleaned up

- Uploads are written to `data/uploads/` as a server-generated
  `{job_id}.{ext}` file plus a `{job_id}.json` metadata sidecar.
- Filenames are generated server-side (UUID); user-supplied names are used only
  as metadata and never as filesystem paths.
- The directory is git-ignored. Retention defaults to **30 days**
  (`GUITARTAB_KEEP_UPLOADS_DAYS`). Remove old uploads at any time:

  ```powershell
  backend\.venv\Scripts\python.exe scripts\cleanup_uploads.py --dry-run
  backend\.venv\Scripts\python.exe scripts\cleanup_uploads.py
  ```

---

## 8. Tests, build and type-checking

### Backend

```powershell
cd backend
.venv\Scripts\python.exe -m pytest
```

Covers health, capabilities, CORS, valid/invalid uploads, empty and oversized
files, safe filename handling, the job round-trip, and error responses.

### Frontend

```powershell
cd frontend
npm run typecheck   # tsc --noEmit
npm test            # vitest run
npm run build       # production build
```

Frontend tests cover rendering, the live backend status, file validation,
upload success/error/cancel, disabled/loading states, and accessibility basics.

---
Backend:
```powershell
cd "d:\code\PROJECTS\tab creator\backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
$ Verify it is running: Open http://127.0.0.1:8000/api/health in your browser. It should respond with {"status":"ok",...}.

Frontend:
```poweshell
cd "d:\code\PROJECTS\tab creator\frontend"
npm run dev

```
$ Access the App: Open http://localhost:5173 in your browser. The header indicator will display ONLINE when connected to the backend.
---

## 9. API summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Real service health |
| `GET` | `/api/capabilities` | Implemented vs. planned capabilities |
| `POST` | `/api/videos/upload` | Validate + store a video (multipart field `file`) |
| `GET` | `/api/jobs/{job_id}` | Fetch stored job metadata |

Full contract: [`docs/api.md`](docs/api.md).

---

## 10. Design

The interface follows the **Thesis Quarterly** design system in
[`DESIGN.md`](DESIGN.md): warm cream surfaces, ink text, Source Serif 4 for
running text, IBM Plex Mono for labels/numerals/buttons, and a single cobalt
accent reserved for links and highlights. Tokens are declared once in
`frontend/src/styles/index.css` and referenced everywhere downstream.

---

## 11. Known limitations

- No computer-vision inference exists yet; jobs stay in the `received` state.
- Video validation checks extension, declared content type, size and
  non-emptiness. It does not decode the container or verify playability.
- Uploads are stored on local disk; there is no database (none is needed yet).
- The frontend status poll runs every 15 seconds.
