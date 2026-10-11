# API contract

Base URL (development): `http://localhost:8000`. Interactive docs at `/docs`.

All error responses use FastAPI’s `detail` envelope. For our own validation
errors `detail` is an object; for request-schema errors (HTTP 422) FastAPI
returns `detail` as a list, which the frontend client also handles.

```json
{
  "detail": {
    "code": "unsupported_extension",
    "message": "Unsupported file type '.txt'. Accepted extensions: mp4, mov, webm.",
    "field": null
  }
}
```

These shapes are mirrored in `frontend/src/types/api.ts`.

---

## `GET /api/health`

Real service health. Used by the header status indicator.

**200**

```json
{
  "status": "ok",
  "service": "GuitarTab AI",
  "version": "0.1.0",
  "environment": "development",
  "time": "2026-10-10T03:44:10.932284Z"
}
```

---

## `GET /api/capabilities`

Reports what is implemented and what is planned. The UI renders this verbatim;
it never assumes a capability.

**200**

```json
{
  "service": "GuitarTab AI",
  "version": "0.1.0",
  "video_upload": {
    "supported": true,
    "max_file_size_mb": 100,
    "allowed_extensions": [".mp4", ".mov", ".webm"],
    "allowed_content_types": ["video/mp4", "video/quicktime", "video/webm", "application/octet-stream"]
  },
  "cv_pipeline": {
    "implemented": false,
    "stages": [
      {
        "key": "fretboard_detection",
        "label": "Fretboard detection",
        "implemented": false,
        "status": "planned",
        "description": "Locate the fretboard and frets in the camera frame."
      }
    ]
  },
  "notes": ["..."]
}
```

`status` is one of `implemented`, `in_progress`, `planned`.

---

## `POST /api/videos/upload`

`multipart/form-data` with a single field named **`file`**.

```bash
curl -X POST http://localhost:8000/api/videos/upload \
  -F "file=@clip.mp4;type=video/mp4"
```

Validation (server-side):

1. Field present and named `file`.
2. Extension in `.mp4`, `.mov`, `.webm`.
3. Declared content type is a known video type or `application/octet-stream`.
4. Declared `Content-Length` (when present) under the limit.
5. Streamed to disk in 1 MiB chunks; aborts and removes partial files if the
   limit is exceeded.
6. File is non-empty.

Stored as `data/uploads/{job_id}.{ext}` with a `{job_id}.json` metadata sidecar.
The response **does not** include server paths.

**201**

```json
{
  "job_id": "0433f1ccc6d6484d84ee26dac4aa632a",
  "status": "received",
  "original_name": "clip.mp4",
  "extension": "mp4",
  "size_bytes": 62914560,
  "content_type": "video/mp4",
  "uploaded_at": "2026-10-10T03:44:10.932284Z",
  "retention_note": "Uploads are retained for up to 30 days and can be removed manually with scripts/cleanup_uploads.py at any time."
}
```

**Errors**

| Status | `detail.code` | Meaning |
|---|---|---|
| 400 | `missing_file` | No usable filename provided |
| 400 | `missing_extension` | File has no extension |
| 400 | `unsupported_extension` | Extension not in the allow-list |
| 400 | `unsupported_content_type` | Declared type is not a video type |
| 400 | `empty_file` | Zero-byte upload |
| 413 | `file_too_large` | Over the configured limit |
| 422 | *(list)* | Multipart field `file` missing |
| 500 | `storage_error` | Could not persist the file |

---

## `GET /api/jobs/{job_id}`

Returns persisted job metadata.

**200**

```json
{
  "job_id": "0433f1ccc6d6484d84ee26dac4aa632a",
  "status": "received",
  "original_name": "clip.mp4",
  "extension": "mp4",
  "size_bytes": 62914560,
  "content_type": "video/mp4",
  "created_at": "2026-10-10T03:44:10.932284Z",
  "updated_at": "2026-10-10T03:44:10.932284Z",
  "analysis": null,
  "error": null
}
```

`status` is one of `received`, `queued`, `analyzing`, `completed`, `failed`.
`analysis` is **always `null`** in this milestone and will become
`{ "events": [ { "string": 3, "fret": 5, "start_s": 1.2, "end_s": 1.5, "confidence": 0.91 } ] }`
when the CV pipeline lands.

**404**

```json
{ "detail": { "code": "job_not_found", "message": "No job found for id 'xyz'.", "field": null } }
```

---

---

## `GET /api/jobs/{job_id}/frames/{frame_index}/fretboard`

Runs classical OpenCV fretboard localization on an extracted frame.

**200**

```json
{
  "job_id": "0433f1ccc6d6484d84ee26dac4aa632a",
  "frame_index": 0,
  "detected": true,
  "confidence": 0.9882,
  "polygon": [
    {"x": 130.0, "y": 217.0},
    {"x": 510.0, "y": 217.0},
    {"x": 510.0, "y": 263.0},
    {"x": 130.0, "y": 263.0}
  ],
  "geometry": {
    "orientation_deg": 0.0,
    "estimated_length": 380.0,
    "estimated_width": 46.0,
    "aspect_ratio": 8.26,
    "fret_count_estimate": 12,
    "transverse_edge_density": 0.5332
  },
  "failure_reason": null,
  "diagnostics": {
    "image_size": [640, 480],
    "candidates_evaluated": 12,
    "pairs_evaluated": 48
  }
}
```

When no credible fretboard exists, returns `detected: false`, `polygon: null`, and a descriptive `failure_reason` (e.g. `insufficient_transverse_frets`, `insufficient_edge_detail`, `excessive_image_noise`).

---

## `GET /api/jobs/{job_id}/frames/{frame_index}/fretboard-debug`

Returns an annotated JPEG image with the detected fretboard polygon overlay, corner markers, central longitudinal axis, and diagnostic HUD banner.

**200** — `image/jpeg`

---

## CORS

Local development origins are allowed via `GUITARTAB_CORS_ORIGINS`
(default `http://localhost:5173`, `http://127.0.0.1:5173`). Allowed methods:
`GET`, `POST`, `OPTIONS`.

