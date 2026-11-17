# INSTALL

Setup and run instructions for **GuitarTab AI**. The project has two parts:

| Part | Folder | Stack |
|---|---|---|
| Backend | `backend/` | Python + FastAPI + PyTorch (fretboard detection) |
| Frontend (main) | `frontend/` | React + Vite + TypeScript + Tailwind |
| Frontend (Lovable) | `guitartab-lovable/` | React + TanStack Start + Vite |

Only one frontend is needed. `frontend/` is the hand-written app; the
`guitartab-lovable/` folder is an alternative UI built with Lovable.

---

## 1. Required versions

| Tool | Required version | Notes |
|---|---|---|
| **Python** | **3.11, 3.12 or 3.13 (64-bit)** | 3.12 recommended. **Do NOT use 3.14+** — `torch==2.6.0` has no wheels for it, pip falls back to a source build, and installation "does not compile". 32-bit Python is not supported. |
| **Node.js** | **22 LTS** or 24 LTS | Vite requires `^20.19.0 || >=22.12.0`. Avoid Node 20 (end-of-life). npm 10/11 ships with Node. |
| **npm** | bundled with Node | 10+ |
| Browser | modern Chrome/Edge/Firefox | |

All Python packages are pinned in `backend/requirements.lock.txt` and ship
prebuilt wheels — **no C/C++ compiler is required**.

---

## 2. Install Python (Windows)

Option A — winget:
```powershell
winget install Python.Python.3.12
```

Option B — official installer: download from <https://www.python.org/downloads/>
and **tick "Add python.exe to PATH"**.

Verify (open a new terminal):
```powershell
python --version          # Python 3.12.x
python -c "import platform; print(platform.architecture())"   # 64bit
```

macOS / Linux: `brew install python@3.12` or your package manager, then
`python3 --version`.

---

## 3. Install Node.js (Windows)

Option A — winget (simplest):
```powershell
winget install OpenJS.NodeJS.LTS
```

Option B — nvm-windows (switch versions easily):
```powershell
winget install CoreyButler.NVMforWindows
# open a NEW terminal so nvm is on PATH
nvm install 22
nvm use 22
```

Option C — from a specific `.nvmrc` (if one exists): `nvm use`.

Verify (new terminal):
```powershell
node --version            # v22.x (>= 22.12) or v24.x
npm --version             # 10+ / 11+
```

macOS / Linux: `nvm install 22` or `brew install node@22`.

---

## 4. Backend (`backend/`)

Run all commands from the repository root.

### 4.1 First-time setup
```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
```

> The default `torch`/`torchvision` wheels are **CPU-only** and run on any
> machine. For an NVIDIA GPU, replace that install step with:
> ```powershell
> backend\.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
> ```

### 4.2 Run
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Health check: <http://127.0.0.1:8000/api/health> → `{"status":"ok",...}`
- Interactive API docs: <http://127.0.0.1:8000/docs>

### 4.3 Tests
```powershell
cd backend
.venv\Scripts\python.exe -m pytest
```

Backend configuration is read from `backend/.env` (copy `backend/.env.example`):
```powershell
copy backend\.env.example backend\.env
```

---

## 5. Frontend — main app (`frontend/`)

```powershell
cd frontend
npm install
npm run dev
```
- App: <http://localhost:5173> (Vite default; it will print the used port)

Other scripts:
```powershell
npm run typecheck     # tsc --noEmit
npm test              # vitest run
npm run build         # production build
```

Configuration — copy `frontend/.env.example` to `frontend/.env`:
```
VITE_API_BASE_URL=http://localhost:8000
```

---

## 6. Frontend — Lovable app (`guitartab-lovable/`)

```powershell
cd guitartab-lovable
npm install
npm run dev
```
- App: the URL Vite prints (default <http://localhost:5173>)

Other scripts: `npm run build`, `npm run lint`, `npm test`.

Configuration lives in `guitartab-lovable/.env.local`:
```
VITE_API_BASE_URL=http://localhost:8000
```

> This folder was originally built with **bun** (`bun.lock` + `bunfig.toml`),
> but `package-lock.json` is present so `npm` works too. To match the original
> toolchain instead: `npm install -g bun`, then `bun install` / `bun run dev`.

---

## 7. Running the backend + a frontend together

Two terminals, both from the repository root:

**Terminal 1 — backend**
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend (pick one)**
```powershell
# main app
cd frontend; npm run dev

# OR the Lovable app
cd guitartab-lovable; npm run dev
```

The header shows a live connection status driven by `GET /api/health`.

---

## 8. Environment variables

| Variable | Side | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000` | Backend base URL |
| `GUITARTAB_ENVIRONMENT` | backend | `development` | Environment label |
| `GUITARTAB_UPLOAD_DIR` | backend | `<repo>/data/uploads` | Where uploads are stored |
| `GUITARTAB_MAX_UPLOAD_SIZE_MB` | backend | `100` | Maximum upload size |
| `GUITARTAB_KEEP_UPLOADS_DAYS` | backend | `30` | Upload retention |
| `GUITARTAB_CORS_ORIGINS` | backend | `http://localhost:5173,...` | Allowed browser origins |

---

## 9. Maintenance

Remove expired uploads:
```powershell
backend\.venv\Scripts\python.exe scripts\cleanup_uploads.py --dry-run
backend\.venv\Scripts\python.exe scripts\cleanup_uploads.py
```

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pip install` tries to **build torch from source** ("does not compile") | Python is 3.14+ or 32-bit. Install 64-bit Python **3.11–3.13** and recreate `backend\.venv`. |
| `ImportError` / `RuntimeError` when importing `torchvision` | `torch` and `torchvision` versions don't match. Use the pinned pairs (`torch 2.6.0` ↔ `torchvision 0.21.0`). |
| `module compiled against API version ... numpy` error | Mismatched NumPy/OpenCV. Install `backend/requirements.lock.txt`, which pins compatible versions. |
| `uvicorn` "not recognized" | The venv is missing/broken. Re-run section 4.1 and always call `backend\.venv\Scripts\python.exe -m uvicorn`. |
| Backend starts, frontend shows "Backend offline" | Backend not running, wrong `VITE_API_BASE_URL`, or origin not in `GUITARTAB_CORS_ORIGINS`. |
| `npm run dev` errors about Node version | Node is older than 20.19 / 22.12. Install Node 22 LTS (section 3). |
| `EADDRINUSE` / port busy | Another process uses the port; free it or pass a different `--port` / Vite `--port`. |
| The header status stays offline but backend is up | Browser blocks `http` API from an `https` page; use matching schemes or host the backend over HTTPS. |
