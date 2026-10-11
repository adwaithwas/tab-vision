import { useId, useRef, useState } from "react";
import type { DragEvent } from "react";
import { UploadCloud } from "lucide-react";
import { FileMeta } from "./FileMeta";

export interface UploadZoneProps {
  file: File | null;
  error: string | null;
  onSelect: (file: File | null) => void;
  disabled?: boolean;
  /** Display strings, e.g. "MP4, MOV, WebM" and "100 MB". */
  formatsLabel?: string;
  maxSizeLabel?: string;
  accept?: string;
}

/**
 * Large drag-and-drop upload area.
 *
 * - Click / drag anywhere to choose a video.
 * - Keyboard accessible through the native file input (visible focus ring).
 * - Displays the selected file's real metadata and allows replacement or
 *   removal.
 * - Never submits an invalid file: the parent validates before selecting.
 */
export function UploadZone({
  file,
  error,
  onSelect,
  disabled = false,
  formatsLabel = "MP4, MOV, WebM",
  maxSizeLabel = "100 MB",
  accept = "video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm",
}: UploadZoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pickFile = (list: FileList | null) => {
    const next = list && list.length > 0 ? list[0] ?? null : null;
    if (file === next) return;
    onSelect(next);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    pickFile(event.dataTransfer.files);
  };

  const zoneClass = [
    "card -mx-px flex min-h-[14rem] cursor-pointer flex-col items-center justify-center gap-5 p-8 text-center",
    "transition-colors duration-200",
    dragging && !disabled ? "border-ink" : "border-hairline",
    disabled ? "pointer-events-none opacity-60" : "hover:border-ink/35",
    "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ink has-[:focus-visible]:outline-offset-4",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div>
      <label
        htmlFor={inputId}
        className={zoneClass}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={accept}
          disabled={disabled}
          className="sr-only"
          onChange={(event) => pickFile(event.target.files)}
        />

        {file ? (
          <FileMeta file={file} onRemove={() => onSelect(null)} />
        ) : (
          <>
            <UploadCloud aria-hidden="true" size={28} strokeWidth={1.5} className="text-ink-50" />
            <div>
              <p className="t-h2">Drop a video here</p>
              <p className="t-body-sm mt-1 text-ink-50">
                or click to browse your computer
              </p>
            </div>
            <div className="t-eyebrow">{formatsLabel} · up to {maxSizeLabel}</div>
          </>
        )}
      </label>

      {error && (
        <p role="alert" className="t-mono mt-3 border-l border-error pl-3 text-error">
          {error}
        </p>
      )}
    </div>
  );
}