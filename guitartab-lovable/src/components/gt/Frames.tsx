import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { frameUrl, getFrames, type FrameInfo } from "@/lib/tab-service";
import { annotatedUrl } from "@/lib/vision-service";

const fmt = (t?: number) => t == null ? "—" : `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

export function Frames({ jobId }: { jobId: string }) {
  const [frames, setFrames] = useState<FrameInfo[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [sel, setSel] = useState(0);
  const [overlay, setOverlay] = useState(false);
  const [imgErr, setImgErr] = useState(false);

  useEffect(() => {
    let live = true;
    setFrames(null); setFailed(false); setSel(0);
    getFrames(jobId).then((f) => live && setFrames(f)).catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [jobId]);

  useEffect(() => setImgErr(false), [sel, overlay]);
  const cur = frames?.[sel];

  return (
    <section className="mt-28" aria-labelledby="frames-h">
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-t border-rule pt-6">
        <h3 id="frames-h" className="font-display text-2xl font-medium tracking-tight">Performance frames</h3>
        <div role="group" aria-label="Frame view" className="flex font-mono text-xs">
          {(["Original", "Analysis"] as const).map((l, i) => (
            <button key={l} aria-pressed={overlay === (i === 1)} onClick={() => setOverlay(i === 1)}
              className={cn("border px-3 py-1.5 transition-colors -ml-px", overlay === (i === 1) ? "border-rule bg-foreground text-background" : "border-border text-ink-soft hover:text-foreground")}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {failed && <p className="mt-6 text-sm text-ink-soft">Frames couldn't be loaded for this recording. Your tablature above is unaffected.</p>}
      {!failed && !frames && <div className="mt-6 aspect-video w-full animate-pulse bg-surface md:w-2/3" />}
      {frames && frames.length === 0 && <p className="mt-6 text-sm text-ink-soft">No frames were extracted from this recording.</p>}
      {cur && (
        <div className="mt-6 grid gap-6 md:grid-cols-[2fr_1fr]">
          <figure className="relative overflow-hidden bg-surface" style={cur.width && cur.height ? { aspectRatio: `${cur.width}/${cur.height}` } : undefined}>
            {imgErr ? (
              <div className="flex aspect-video w-full items-center justify-center text-sm text-ink-soft">
                {overlay ? "Analysis view isn't available for this frame." : "This frame couldn't be loaded."}
              </div>
            ) : (
              <img src={overlay ? annotatedUrl(jobId, cur.index) : frameUrl(jobId, cur.index)} alt={`Frame at ${fmt(cur.timestamp)}`}
                onError={() => setImgErr(true)} className="block h-full w-full object-contain" />
            )}
            <figcaption className="absolute bottom-0 left-0 bg-background px-2 py-1 font-mono text-xs">{fmt(cur.timestamp)}</figcaption>
          </figure>
          <ul className="flex gap-3 overflow-x-auto md:grid md:grid-cols-2 md:content-start">
            {frames!.map((f, i) => (
              <li key={f.index} className="shrink-0">
                <button onClick={() => setSel(i)} aria-label={`Show frame at ${fmt(f.timestamp)}`} aria-current={sel === i}
                  className={cn("block w-32 border-b-2 pb-1 text-left transition-opacity md:w-full", sel === i ? "border-primary" : "border-transparent opacity-60 hover:opacity-100")}>
                  <img src={frameUrl(jobId, f.index)} alt="" loading="lazy" className="aspect-video w-full bg-surface object-cover"
                    onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
                  <span className="mt-1 block font-mono text-[11px] text-muted-foreground">{fmt(f.timestamp)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
