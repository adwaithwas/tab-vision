import { useEffect, useState } from "react";
import type { FramePreviewItem } from "../services/api";
import { getFrameCvDebugUrl, getFrameUrl, listFrames } from "../services/api";

interface AnnotatedPreviewProps {
  jobId?: string | null;
}

/**
 * Computer-Vision Inspection Preview.
 *
 * Demonstrates real frame extraction and OpenCV fretboard localization overlays.
 * Clearly separates raw video frames from CV diagnostics and labels uncertain or
 * failed detections transparently.
 */
export function AnnotatedPreview({ jobId }: AnnotatedPreviewProps) {
  const [frames, setFrames] = useState<FramePreviewItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number>(0);
  const [showCvOverlay, setShowCvOverlay] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setFrames([]);
      setSelectedIndex(0);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    listFrames(jobId)
      .then((res) => {
        if (!active) return;
        setFrames(res.frames || []);
        if (res.frames && res.frames.length > 0) {
          setSelectedIndex(0);
        }
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load frames.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [jobId]);

  if (!jobId) {
    return (
      <div
        className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-ink-20 bg-lift/40 px-6 text-center"
        role="img"
        aria-label="Awaiting video upload for frame inspection"
      >
        <span className="t-eyebrow">CV Frame Analysis</span>
        <span className="t-body-sm max-w-[34ch] text-ink-50">
          Upload and process a video above to inspect extracted frames and OpenCV fretboard
          localization overlays.
        </span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="card flex aspect-video w-full items-center justify-center p-6">
        <span className="t-body-sm text-ink-50">Loading extracted video frames…</span>
      </div>
    );
  }

  if (error || frames.length === 0) {
    return (
      <div className="card flex aspect-video w-full items-center justify-center p-6 text-center">
        <span className="t-body-sm text-ink-50">
          {error || "No extracted frames found for this job."}
        </span>
      </div>
    );
  }

  const currentFrame = frames[selectedIndex] ?? frames[0];
  if (!currentFrame) {
    return null;
  }

  const imageUrl = showCvOverlay
    ? getFrameCvDebugUrl(jobId, currentFrame.index)
    : getFrameUrl(jobId, currentFrame.index);

  return (
    <div className="card flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-divider pb-3">
        <div className="flex items-center gap-2">
          <span className="t-mono-sm font-semibold text-ink">
            Frame {currentFrame.index + 1} of {frames.length}
          </span>
          <span className="t-mono-sm text-ink-50">
            ({currentFrame.timestamp_seconds.toFixed(2)}s)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowCvOverlay(!showCvOverlay)}
            className={`btn-secondary t-mono-sm px-3 py-1 text-xs ${
              showCvOverlay ? "border-accent text-accent font-semibold" : ""
            }`}
          >
            {showCvOverlay ? "CV Diagnostics: ON" : "Raw Frame: ON"}
          </button>
        </div>
      </div>

      <div className="relative aspect-video w-full overflow-hidden rounded-md bg-black">
        <img
          key={`${imageUrl}`}
          src={imageUrl}
          alt={`Frame ${currentFrame.index} analysis`}
          className="h-full w-full object-contain"
        />
      </div>

      <div className="flex flex-col gap-2 pt-1">
        <span className="t-mono-sm text-xs text-ink-50">Select frame to inspect:</span>
        <div className="flex flex-wrap gap-1.5">
          {frames.map((f, i) => (
            <button
              key={f.index}
              type="button"
              onClick={() => setSelectedIndex(i)}
              className={`rounded px-2.5 py-1 t-mono-sm text-xs transition-colors ${
                i === selectedIndex
                  ? "bg-ink text-paper font-semibold"
                  : "bg-surface text-ink-50 hover:bg-lift"
              }`}
            >
              #{f.index} ({f.timestamp_seconds.toFixed(1)}s)
            </button>
          ))}
        </div>
      </div>

      <p className="t-body-sm text-xs text-ink-50 border-t border-divider pt-2">
        <span className="font-semibold text-ink">Computer Vision Note:</span> Classical OpenCV
        boundary localization &amp; fret density detector. Overlays clearly label detected vs.
        unconfirmed regions. Tablature is synthesized independently from the audio stream.
      </p>
    </div>
  );
}