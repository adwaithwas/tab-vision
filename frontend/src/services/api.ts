import type { CapabilitiesResponse, HealthResponse } from "../types/api";

/**
 * Base URL of the FastAPI backend.
 *
 * Configured with `VITE_API_BASE_URL` (see `frontend/.env.example`).
 * Always trimmed so callers can concatenate endpoints safely.
 */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

/** Default request timeout for read-only calls. */
const REQUEST_TIMEOUT_MS = 120_000;

/**
 * A structured, user-presentable API error.
 *
 * The message is always safe to display — never a stack trace or server path.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | undefined;

  constructor(code: string, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

interface BackendErrorDetail {
  code?: string;
  message?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Normalise any non-2xx response body into an `ApiError`.
 *
 * Handles the three shapes the backend can produce: the structured
 * `{detail: {code, message}}` envelope, a plain `{detail: "..."}` string
 * (FastAPI validation errors), and non-JSON bodies.
 */
export function errorFromResponse(status: number, body: unknown): ApiError {
  if (isRecord(body) && "detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") {
      return new ApiError("bad_request", detail, status);
    }
    if (isRecord(detail)) {
      const typed = detail as BackendErrorDetail;
      return new ApiError(
        typed.code ?? "error",
        typed.message ?? "The server rejected the request.",
        status,
      );
    }
    if (Array.isArray(detail)) {
      const first = detail[0];
      const message = isRecord(first) && typeof first.msg === "string"
        ? first.msg
        : "The request was rejected by the server.";
      return new ApiError("validation_error", message, status);
    }
  }
  return new ApiError("http_error", `Request failed with status ${status}.`, status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError(
      "network_error",
      "Could not reach the backend server. Check that it is running and that the API base URL is correct.",
    );
  } finally {
    window.clearTimeout(timer);
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw errorFromResponse(response.status, payload);
  }
  return payload as T;
}

/** GET /api/health — real service health. */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", signal ? { signal } : undefined);
}

/** GET /api/capabilities — implemented vs. planned functionality. */
export function getCapabilities(signal?: AbortSignal): Promise<CapabilitiesResponse> {
  return request<CapabilitiesResponse>("/api/capabilities", signal ? { signal } : undefined);
}

/** POST /api/jobs/{jobId}/process — start frame extraction and TabVision. */
export function processJob(jobId: string, signal?: AbortSignal): Promise<any> {
  return request<any>(`/api/jobs/${jobId}/process`, { method: "POST", signal });
}

/** GET /api/jobs/{jobId} — poll job status. */
export function getJob(jobId: string, signal?: AbortSignal): Promise<any> {
  return request<any>(`/api/jobs/${jobId}`, { signal });
}

export interface FramePreviewItem {
  index: number;
  timestamp_seconds: number;
  url: string;
  width: number;
  height: number;
}

export interface FrameListResponse {
  job_id: string;
  total_frames: number;
  count: number;
  truncated: boolean;
  sample_interval_seconds: number;
  frames: FramePreviewItem[];
}

/** GET /api/jobs/{jobId}/frames — list extracted frames. */
export function listFrames(jobId: string, limit = 24, signal?: AbortSignal): Promise<FrameListResponse> {
  return request<FrameListResponse>(`/api/jobs/${jobId}/frames?limit=${limit}`, { signal });
}

/** URL for a raw extracted frame JPEG. */
export function getFrameUrl(jobId: string, frameIndex: number): string {
  return `${API_BASE_URL}/api/jobs/${jobId}/frames/${frameIndex}`;
}

/** URL for the computer-vision debug overlay JPEG. */
export function getFrameCvDebugUrl(jobId: string, frameIndex: number): string {
  return `${API_BASE_URL}/api/jobs/${jobId}/frames/${frameIndex}/fretboard-debug`;
}