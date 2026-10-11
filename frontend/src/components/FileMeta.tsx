import { X } from "lucide-react";
import { useVideoMetadata } from "../hooks/useVideoMetadata";
import { formatBytes } from "../services/validation";

interface FileMetaProps {
  file: File;
  onRemove: () => void;
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return minutes > 0 ? `${minutes}:${secs.toString().padStart(2, "0")}` : `${secs}s`;
}

/**
 * Metadata card for the selected local file. Duration/resolution come from
 * real `<video>` metadata reads (when the browser supports them); size and
 * type are read directly from the File object.
 */
export function FileMeta({ file, onRemove }: FileMetaProps) {
  const meta = useVideoMetadata(file);
  const rows = [
    ["Size", formatBytes(file.size)],
    ["Type", file.type || "unknown"],
    ["Format", fileExtensionLabel(file.name)],
    [
      "Duration",
      meta.durationSeconds !== null ? formatDuration(meta.durationSeconds) : "reading…",
    ],
    [
      "Resolution",
      meta.width && meta.height ? `${meta.width} × ${meta.height}` : "—",
    ],
  ];

  return (
    <div className="flex w-full flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="t-body-sm truncate font-semibold" title={file.name}>
          {file.name}
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1.5 sm:grid-cols-3">
          {rows.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="t-mono-sm text-ink-50">{label}</dt>
              <dd className="t-mono truncate text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <button
        type="button"
        className="btn btn-ghost shrink-0"
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
      >
        <X aria-hidden="true" size={14} />
        Remove
      </button>
    </div>
  );
}

function fileExtensionLabel(name: string): string {
  const match = /\.[^.\\/]+$/.exec(name);
  return match ? match[0].toLowerCase().slice(1).toUpperCase() : "—";
}