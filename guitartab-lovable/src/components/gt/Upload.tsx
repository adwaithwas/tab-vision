import { useRef, useState } from "react";
import { X, RefreshCw, AlertCircle } from "lucide-react";
import { validateFile } from "@/lib/tab-service";
import { cn } from "@/lib/utils";

export function formatBytes(n: number) {
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function StringsGlyph({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 120 60" className="h-14 w-28" aria-hidden>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line key={i} x1="0" x2="120" y1={6 + i * 9.6} y2={6 + i * 9.6}
          className={cn("transition-colors duration-300", active ? "stroke-primary" : "stroke-foreground")} strokeWidth={0.5 + i * 0.25} />
      ))}
      {[30, 60, 90].map((x) => <line key={x} x1={x} x2={x} y1="2" y2="58" className="stroke-border" strokeWidth="1" />)}
      <circle cx="45" cy="24.8" r="4" className="fill-primary" />
      <circle cx="75" cy="44" r="4" className="fill-foreground" />
    </svg>
  );
}

export function UploadZone({ file, onFile, disabled }: { file: File | null; onFile: (f: File | null) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const take = (f?: File) => {
    if (!f) return;
    const err = validateFile(f);
    setError(err);
    onFile(err ? null : f);
  };

  return (
    <div>
      <input ref={input} type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" className="sr-only" tabIndex={-1}
        onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} disabled={disabled} />

      {file ? (
        <div className="flex items-center gap-6 border border-rule bg-card px-6 py-6 sm:px-8">
          <span className="font-mono text-xs text-primary">●</span>
          <div className="min-w-0 flex-1">
            <p className="eyebrow">Selected recording</p>
            <p className="mt-1 truncate font-display text-xl font-medium">{file.name}</p>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">{formatBytes(file.size)}</p>
          </div>
          <button type="button" disabled={disabled} onClick={() => input.current?.click()}
            className="inline-flex items-center gap-1.5 text-sm text-ink-soft underline-offset-4 hover:text-foreground hover:underline disabled:opacity-40">
            <RefreshCw className="h-3.5 w-3.5" /> Replace
          </button>
          <button type="button" disabled={disabled} onClick={() => { onFile(null); setError(null); }} aria-label="Remove file"
            className="p-1 text-ink-soft hover:text-destructive disabled:opacity-40">
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button type="button" disabled={disabled}
          onClick={() => input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files?.[0]); }}
          className={cn(
            "group flex w-full flex-col items-start gap-10 border bg-card px-6 py-10 text-left transition-colors sm:flex-row sm:items-end sm:justify-between sm:px-10 sm:py-14",
            "disabled:cursor-not-allowed disabled:opacity-50",
            drag ? "border-primary bg-accent" : error ? "border-destructive" : "border-dashed border-foreground/40 hover:border-foreground",
          )}>
          <div>
            <StringsGlyph active={drag} />
            <p className="mt-8 font-display text-2xl font-medium tracking-tight sm:text-3xl">
              {drag ? "Release to add your video" : <>Drop a video, or <span className="underline decoration-1 underline-offset-[6px] group-hover:text-primary">browse</span></>}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-1 font-mono text-xs text-muted-foreground">
            <dt>Formats</dt><dd className="text-foreground">MP4 · MOV · WEBM</dd>
            <dt>Max size</dt><dd className="text-foreground">100 MB</dd>
          </dl>
        </button>
      )}
      {error && (
        <p role="alert" className="mt-3 flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error}
        </p>
      )}
    </div>
  );
}
