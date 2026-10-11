import { Button } from "./ui/Button";
import type { UploadProgress } from "../services/upload";
import { formatBytes } from "../services/validation";

export interface AnalyzePanelProps {
  canAnalyze: boolean;
  uploading: boolean;
  offline: boolean;
  progress: UploadProgress | null;
  onAnalyze: () => void;
  onCancel: () => void;
}

function ProgressBar({ progress }: { progress: UploadProgress | null }) {
  if (!progress) {
    return (
      <div
        className="h-1 w-full animate-pulse bg-ink-8"
        role="progressbar"
        aria-label="Uploading"
      />
    );
  }
  const { percent, loaded, total } = progress;
  return (
    <div className="w-full">
      <div
        className="h-1 w-full bg-ink-8"
        role="progressbar"
        aria-label="Upload progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
      >
        <div
          className="h-1 bg-ink transition-[width] duration-200"
          style={{ width: percent !== null ? `${percent}%` : "100%" }}
        />
      </div>
      <div className="mt-2 flex justify-between t-mono-sm text-ink-50">
        <span>{percent !== null ? `${percent}%` : "uploading"}</span>
        <span>
          {formatBytes(loaded)}
          {total > 0 ? ` / ${formatBytes(total)}` : ""}
        </span>
      </div>
    </div>
  );
}

/**
 * Analysis controls. In this milestone "Analyze Video" performs the real,
 * validated upload; it does not fabricate analysis. The note states exactly
 * what happens so the control is never a dead or misleading button.
 */
export function AnalyzePanel({
  canAnalyze,
  uploading,
  offline,
  progress,
  onAnalyze,
  onCancel,
}: AnalyzePanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          onClick={onAnalyze}
          disabled={!canAnalyze || offline}
          isBusy={uploading}
          busyLabel="Uploading…"
          title={offline ? "The backend is offline" : undefined}
        >
          Analyze Video
        </Button>

        {uploading && (
          <Button variant="outline" onClick={onCancel}>
            Cancel upload
          </Button>
        )}
      </div>

      {uploading && <ProgressBar progress={progress} />}

      <p className="t-mono-sm max-w-[52ch] leading-relaxed text-ink-50">
        This build uploads and validates your clip, then registers it as an analysis
        job. Note extraction and tablature generation are part of the computer-vision
        pipeline, which is not implemented yet — no results are produced at this stage.
      </p>

      {offline && (
        <p role="status" className="t-mono border-l border-error pl-3 text-error">
          The backend is offline, so the video cannot be uploaded right now. Start the
          FastAPI server, then try again.
        </p>
      )}
    </div>
  );
}