import { useEffect, useState } from "react";
import { getCapabilities, ApiError } from "../services/api";
import type { CapabilitiesResponse } from "../types/api";

export interface CapabilitiesState {
  data: CapabilitiesResponse | null;
  /** True while the capabilities have not been loaded at least once. */
  loading: boolean;
  /** Set when loading failed; the UI falls back to safe defaults. */
  error: string | null;
}

/**
 * Loads `GET /api/capabilities` once and keeps it for the session.
 *
 * The frontend treats a missing response as a graceful degradation: upload
 * validation falls back to documented defaults instead of failing.
 */
export function useCapabilities(): CapabilitiesState {
  const [data, setData] = useState<CapabilitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const caps = await getCapabilities();
        if (!cancelled) {
          setData(caps);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause.message
              : "Could not load backend capabilities.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, loading, error };
}