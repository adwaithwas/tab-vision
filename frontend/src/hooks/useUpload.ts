import { useCallback, useRef, useState } from "react";
import { ApiError } from "../services/api";
import type { UploadHandle, UploadProgress } from "../services/upload";
import { uploadVideo } from "../services/upload";
import type { UploadResponse } from "../types/api";

export type UploadState = "idle" | "uploading" | "success" | "cancelled" | "error";

export interface UseUploadResult {
  state: UploadState;
  progress: UploadProgress | null;
  result: UploadResponse | null;
  error: string | null;
  /** True while an upload is in flight — guards against duplicate submissions. */
  inFlight: boolean;
  start: (file: File) => void;
  cancel: () => void;
  reset: () => void;
}

/**
 * Drives the real multipart upload and its honest lifecycle:
 * idle → uploading (progress) → success | cancelled | error.
 *
 * The in-flight guard lives in a ref (not derived state) so a fast double
 * click can never start two concurrent uploads, and no side effects run
 * inside state updaters.
 */
export function useUpload(): UseUploadResult {
  const [state, setState] = useState<UploadState>("idle");
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const handleRef = useRef<UploadHandle | null>(null);
  const inFlightRef = useRef(false);

  const start = useCallback((file: File) => {
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    setState("uploading");
    setProgress(null);
    setResult(null);
    setError(null);

    const handle = uploadVideo(file, {
      onProgress: (p) => setProgress(p),
    });
    handleRef.current = handle;

    handle.promise.then(
      async (response) => {
        let job = response as any;
        try {
          const { processJob } = await import("../services/api");
          // This call will block until TabVision finishes (~60s)
          job = await processJob(job.job_id);
        } catch (e) {
          console.error("Processing failed", e);
        }

        setResult(job);
        if (job.status === 'failed') {
          setError(job.error || "Job processing failed.");
          setState("error");
        } else {
          setState("success");
        }
      },
      (cause: unknown) => {
        if (cause instanceof ApiError && cause.code === "cancelled") {
          setState("cancelled");
          setError(null);
        } else {
          setError(
            cause instanceof ApiError
              ? cause.message
              : "An unexpected error occurred while uploading.",
          );
          setState("error");
        }
      },
    ).finally(() => {
      inFlightRef.current = false;
      handleRef.current = null;
    });
  }, []);

  const cancel = useCallback(() => {
    handleRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    handleRef.current?.abort();
    handleRef.current = null;
    inFlightRef.current = false;
    setState("idle");
    setProgress(null);
    setResult(null);
    setError(null);
  }, []);

  return {
    state,
    progress,
    result,
    error,
    inFlight: state === "uploading",
    start,
    cancel,
    reset,
  };
}