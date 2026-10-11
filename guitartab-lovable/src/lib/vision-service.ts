// Typed client for the isolated, experimental vision endpoints.
// Separate from tab-service.ts on purpose: the audio pipeline is frozen and
// must never depend on vision. Vision is opt-in and only runs when a frame is
// explicitly analysed from the UI.

import { API_BASE, ApiError, getFrames, type FrameInfo } from "./tab-service";

export type { FrameInfo };

const api = (path: string) => `${API_BASE}/${path.replace(/^\/+/, "")}`;

export type VisionPoint = { x: number; y: number };

export type VisionString = {
  position: number;
  y_in_rectified: number;
  strength: number;
  start: VisionPoint;
  end: VisionPoint;
};

export type VisionFret = {
  index: number;
  x_in_rectified: number;
  strength: number;
  start: VisionPoint;
  end: VisionPoint;
};

export type RectifiedSize = { width: number; height: number };

export type VisionAnalysis = {
  jobId: string;
  frameIndex: number;
  detected: boolean;
  confidence: number;
  detectionSource?: string | undefined;
  polygon?: VisionPoint[] | undefined;
  rectified?: RectifiedSize | undefined;
  strings: VisionString[];
  stringsDetected: number;
  frets: VisionFret[];
  fretsDetected: number;
  failureReason?: string | undefined;
  limitations: string[];
  images: { annotated?: string | undefined; rectified?: string | undefined };
};

const parse = (t: string) => {
  try {
    return JSON.parse(t) as Record<string, unknown> | null;
  } catch {
    return null;
  }
};

const num = (o: Record<string, unknown>, k: string, d = 0) =>
  typeof o[k] === "number" ? (o[k] as number) : d;

const str = (o: Record<string, unknown>, k: string) =>
  typeof o[k] === "string" ? (o[k] as string) : undefined;

const point = (v: unknown): VisionPoint | undefined => {
  const o = (v ?? {}) as Record<string, unknown>;
  if (typeof o.x === "number" && typeof o.y === "number")
    return { x: o.x as number, y: o.y as number };
  return undefined;
};

function mapAnalysis(body: Record<string, unknown>, jobId: string, frameIndex: number): VisionAnalysis {
  const poly = Array.isArray(body.polygon)
    ? (body.polygon as unknown[]).map(point).filter((p): p is VisionPoint => !!p)
    : undefined;
  const rect = (body.rectified ?? null) as Record<string, unknown> | null;
  const images = (body.images ?? {}) as Record<string, unknown>;

  return {
    jobId: str(body, "job_id") ?? jobId,
    frameIndex: num(body, "frame_index", frameIndex),
    detected: body.detected === true,
    confidence: num(body, "confidence", 0),
    detectionSource: str(body, "detection_source"),
    polygon: poly && poly.length ? poly : undefined,
    rectified:
      rect && typeof rect.width === "number" && typeof rect.height === "number"
        ? { width: rect.width as number, height: rect.height as number }
        : undefined,
    strings: (Array.isArray(body.strings) ? body.strings : []).map((s) => {
      const o = (s ?? {}) as Record<string, unknown>;
      return {
        position: num(o, "position"),
        y_in_rectified: num(o, "y_in_rectified"),
        strength: num(o, "strength"),
        start: point(o.start) ?? { x: 0, y: 0 },
        end: point(o.end) ?? { x: 0, y: 0 },
      };
    }),
    stringsDetected: num(body, "strings_detected", 0),
    frets: (Array.isArray(body.frets) ? body.frets : []).map((f) => {
      const o = (f ?? {}) as Record<string, unknown>;
      return {
        index: num(o, "index"),
        x_in_rectified: num(o, "x_in_rectified"),
        strength: num(o, "strength"),
        start: point(o.start) ?? { x: 0, y: 0 },
        end: point(o.end) ?? { x: 0, y: 0 },
      };
    }),
    fretsDetected: num(body, "frets_detected", 0),
    failureReason: str(body, "failure_reason"),
    limitations: Array.isArray(body.limitations)
      ? (body.limitations as unknown[]).filter((x): x is string => typeof x === "string")
      : [],
    images: {
      annotated: str(images, "annotated"),
      rectified: str(images, "rectified"),
    },
  };
}

/** Explicitly run the isolated vision analysis on one extracted frame. */
export async function analyzeFrame(jobId: string, frameIndex: number): Promise<VisionAnalysis> {
  const res = await fetch(
    api(`/api/vision/jobs/${encodeURIComponent(jobId)}/frames/${frameIndex}`)
  );
  const text = await res.text();
  const body = parse(text);
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    const msg =
      typeof detail === "object" && detail && typeof (detail as { message?: unknown }).message === "string"
        ? ((detail as { message: string }).message)
        : "";
    throw new ApiError(msg || "The vision analyzer could not process this frame.", res.status >= 500);
  }
  if (!body) throw new ApiError("The vision analyzer returned an unreadable response.", true);
  return mapAnalysis(body, jobId, frameIndex);
}

/** URL for the annotated overlay JPEG (safe to fail independently). */
export const annotatedUrl = (jobId: string, frameIndex: number) =>
  api(`/api/vision/jobs/${encodeURIComponent(jobId)}/frames/${frameIndex}/annotated`);

/** URL for the rectified crop JPEG (404s when no fretboard was detected). */
export const rectifiedUrl = (jobId: string, frameIndex: number) =>
  api(`/api/vision/jobs/${encodeURIComponent(jobId)}/frames/${frameIndex}/rectified`);

export { getFrames };
