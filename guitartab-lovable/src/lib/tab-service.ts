// Typed client for the Tab Vision FastAPI backend.
// Base URL comes from VITE_API_BASE_URL (default http://localhost:8000).

export const ACCEPTED_EXT = ["mp4", "mov", "webm"] as const;
export const MAX_BYTES = 100 * 1024 * 1024;
const PROCESS_TIMEOUT_MS = 180_000;

export const API_BASE = String(import.meta.env['VITE_API_BASE_URL'] ?? "http://localhost:8000").replace(/\/+$/, "");
const api = (path: string) => `${API_BASE}/${path.replace(/^\/+/, "")}`;

export type TabResult = {
  jobId: string;
  tablature: string;
  tuning?: string | undefined;
  noteCount?: number | undefined;
};

export type FrameInfo = { index: number; timestamp?: number | undefined; width?: number | undefined; height?: number | undefined };

export type Stage = "uploading" | "transcribing";

export class ApiError extends Error {
  constructor(message: string, public retryable = true) { super(message); this.name = "ApiError"; }
}

export function validateFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!(ACCEPTED_EXT as readonly string[]).includes(ext))
    return "Unsupported format. Please choose an MP4, MOV or WEBM file.";
  if (file.size > MAX_BYTES) return "This file is larger than 100 MB.";
  if (file.size === 0) return "This file appears to be empty.";
  return null;
}

// Turn a backend error body into a short, user-safe message (no stack traces / paths).
function friendly(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  let msg = "";
  if (typeof detail === "string") msg = detail;
  else if (Array.isArray(detail) && typeof detail[0]?.msg === "string") msg = detail[0].msg;
  const safe = msg && msg.length < 160 && !/traceback|\/|\\|File "/i.test(msg) ? msg : "";
  if (status === 413) return "This file is larger than 100 MB.";
  if (status === 415) return "Unsupported format. Please choose an MP4, MOV or WEBM file.";
  if (status === 409) return safe || "This recording is already being processed. Please wait a moment.";
  if (status === 404) return "We couldn't find this job on the server. Please upload again.";
  if (status === 400 || status === 422) return safe || "The server couldn't accept this file.";
  return safe || "The transcription service ran into a problem. Please try again.";
}

const parse = (t: string) => { try { return JSON.parse(t); } catch { return null; } };

export function uploadVideo(file: File, onProgress?: (p: number) => void, signal?: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", api("/api/videos/upload"));
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      const body = parse(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300 && body?.job_id) return resolve(String(body.job_id));
      reject(new ApiError(friendly(xhr.status, body), xhr.status >= 500));
    };
    xhr.onerror = () => reject(new ApiError("Couldn't reach the transcription server. Check that it's running and try again."));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

export async function processJob(jobId: string, signal?: AbortSignal): Promise<TabResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort("timeout"), PROCESS_TIMEOUT_MS);
  signal?.addEventListener("abort", () => ctrl.abort());
  try {
    const res = await fetch(api(`/api/jobs/${encodeURIComponent(jobId)}/process`), { method: "POST", signal: ctrl.signal });
    const body = parse(await res.text());
    if (!res.ok) throw new ApiError(friendly(res.status, body), res.status !== 404);
    const a = body?.analysis ?? {};
    const tab = a.tablature;
    if (typeof tab !== "string" || !tab.trim()) throw new ApiError("No tablature could be produced from this recording.", false);
    const tuning = typeof a.tuning === "string" ? a.tuning : Array.isArray(a.tuning) ? a.tuning.join(" ") : undefined;
    const notes = Array.isArray(a.notes) ? a.notes.length : typeof a.note_count === "number" ? a.note_count : undefined;
    return { jobId, tablature: tab, tuning, noteCount: notes };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (ctrl.signal.aborted) throw new ApiError("Transcription took too long. Please try again.");
    throw new ApiError("Couldn't reach the transcription server. Check that it's running and try again.");
  } finally { clearTimeout(timer); }
}

export async function getFrames(jobId: string): Promise<FrameInfo[]> {
  const res = await fetch(api(`/api/jobs/${encodeURIComponent(jobId)}/frames`));
  if (!res.ok) throw new ApiError(friendly(res.status, null));
  const body = await res.json();
  const list: unknown[] = Array.isArray(body) ? body : body?.frames ?? [];
  return list.map((f, i) => {
    const o = (f ?? {}) as Record<string, unknown>;
    const num = (k: string[]) => { for (const x of k) if (typeof o[x] === "number") return o[x] as number; return undefined; };
    return { index: num(["frame_index", "index"]) ?? i, timestamp: num(["timestamp", "timestamp_s", "time"]), width: num(["width"]), height: num(["height"]) };
  });
}

export const frameUrl = (jobId: string, i: number) => api(`/api/jobs/${encodeURIComponent(jobId)}/frames/${i}`);
export const overlayUrl = (jobId: string, i: number) => api(`/api/jobs/${encodeURIComponent(jobId)}/frames/${i}/fretboard-debug`);

export async function checkHealth(): Promise<boolean> {
  try { return (await fetch(api("/api/health"), { signal: AbortSignal.timeout(4000) })).ok; } catch { return false; }
}

export async function generateTablature(file: File, onStage: (s: Stage) => void, signal?: AbortSignal): Promise<TabResult> {
  onStage("uploading");
  const jobId = await uploadVideo(file, undefined, signal);
  onStage("transcribing");
  return processJob(jobId, signal);
}
