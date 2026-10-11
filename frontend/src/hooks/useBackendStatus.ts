import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getHealth } from "../services/api";
import type { HealthResponse } from "../types/api";

export type BackendStatus = "checking" | "online" | "offline";

export interface BackendStatusState {
  status: BackendStatus;
  info: Pick<HealthResponse, "service" | "version"> | null;
  /** Set when the last check failed; null while online/checking. */
  lastError: string | null;
}

const HEALTH_POLL_MS = 15_000;

/**
 * Poll the backend health endpoint and reflect the *real* connection state.
 *
 * Never hard-codes "online": the indicator follows actual end-to-end
 * responses from the FastAPI service.
 */
export function useBackendStatus(pollMs: number = HEALTH_POLL_MS): BackendStatusState {
  const [status, setStatus] = useState<BackendStatus>("checking");
  const [info, setInfo] = useState<Pick<HealthResponse, "service" | "version"> | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);

  const check = useCallback(async () => {
    try {
      const health = await getHealth();
      setInfo({ service: health.service, version: health.version });
      setStatus("online");
      setLastError(null);
    } catch (cause) {
      // Cancellation (on unmount) must not flip the indicator.
      if (cause instanceof ApiError && cause.code === "network_error") {
        setStatus("offline");
        setLastError(cause.message);
      } else {
        setStatus("offline");
        setLastError("The backend returned an unexpected response.");
      }
    }
  }, []);

  useEffect(() => {
    void check();
    pollTimer.current = window.setInterval(() => void check(), pollMs);
    return () => {
      if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
    };
  }, [check, pollMs]);

  return { status, info, lastError };
}