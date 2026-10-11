import type { UploadResponse } from "../types/api";
import { ApiError, API_BASE_URL, errorFromResponse } from "./api";

export interface UploadProgress {
  loaded: number;
  total: number;
  /** 0–100, or null when the transport cannot report a total. */
  percent: number | null;
}

export interface UploadOptions {
  onProgress?: (progress: UploadProgress) => void;
  /** Abort signal to cancel the in-flight upload. */
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** A handle that lets callers await — and cancel — an upload. */
export interface UploadHandle {
  promise: Promise<UploadResponse>;
  abort: () => void;
}

const DEFAULT_TIMEOUT_MS = 300_000;

/**
 * Upload a video with `XMLHttpRequest`.
 *
 * XHR is used deliberately: it is the only browser transport that reports
 * reliable upload progress and supports true cancellation. Progress shown to
 * the user therefore reflects actual bytes sent — nothing is simulated.
 */
export function uploadVideo(file: File, options: UploadOptions = {}): UploadHandle {
  const { onProgress, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const xhr = new XMLHttpRequest();

  const promise = new Promise<UploadResponse>((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);

    xhr.open("POST", `${API_BASE_URL}/api/videos/upload`);
    xhr.responseType = "text";
    xhr.timeout = timeoutMs;

    xhr.upload.onprogress = (event) => {
      if (!onProgress) return;
      const total = event.lengthComputable ? event.total : 0;
      onProgress({
        loaded: event.loaded,
        total,
        percent: total > 0 ? Math.round((event.loaded / total) * 100) : null,
      });
    };

    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadResponse);
      } else {
        reject(errorFromResponse(xhr.status, body));
      }
    };

    xhr.onerror = () => {
      reject(
        new ApiError(
          "network_error",
          "The upload failed because the server could not be reached. Check your connection and try again.",
        ),
      );
    };

    xhr.ontimeout = () => {
      reject(
        new ApiError(
          "timeout",
          "The upload timed out. Try a smaller file or a faster connection.",
        ),
      );
    };

    xhr.onabort = () => {
      reject(new ApiError("cancelled", "Upload cancelled."));
    };

    if (signal) {
      if (signal.aborted) {
        reject(new ApiError("cancelled", "Upload cancelled."));
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.send(form);
  });

  return {
    promise,
    abort: () => xhr.abort(),
  };
}