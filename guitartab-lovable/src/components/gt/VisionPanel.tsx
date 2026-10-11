import { useEffect, useState } from "react";
import { ScanLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { frameUrl } from "@/lib/tab-service";
import {
  analyzeFrame,
  annotatedUrl,
  getFrames,
  rectifiedUrl,
  type FrameInfo,
  type VisionAnalysis,
} from "@/lib/vision-service";

const fmt = (t?: number) =>
  t == null ? "—" : `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

/**
 * Experimental fretboard-vision panel.
 *
 * Runs only when the user explicitly asks ("Run vision analysis") — it is
 * never triggered by upload or transcription, so the audio pipeline cannot be
 * slowed or broken by vision. All vision failures are caught and rendered
 * inline without touching the tablature result above.
 */
export function VisionPanel({ jobId }: { jobId: string }) {
  const [frames, setFrames] = useState<FrameInfo[] | null>(null);
  const [sel, setSel] = useState(0);
  const [analysis, setAnalysis] = useState<VisionAnalysis | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setFrames(null);
    setAnalysis(null);
    setError(null);
    setSel(0);
    getFrames(jobId)
      .then((f) => live && setFrames(f))
      .catch(() => live && setFrames([]));
    return () => {
      live = false;
    };
  }, [jobId]);

  const cur = frames?.[sel];
  const busy = running;

  const run = async () => {
    if (!cur || busy) return;
    setRunning(true);
    setError(null);
    try {
      setAnalysis(await analyzeFrame(jobId, cur.index));
    } catch (e) {
      setAnalysis(null);
      setError((e as Error).message || "The vision analyzer could not process this frame.");
    } finally {
      setRunning(false);
    }
  };

  if (!frames || frames.length === 0) return null;

  return (
    <section className="mt-28" aria-labelledby="vision-h">
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-t border-rule pt-6">
        <div>
          <p className="eyebrow">Experimental · Computer vision</p>
          <h3 id="vision-h" className="mt-2 font-display text-2xl font-medium tracking-tight">
            Fretboard geometry
          </h3>
        </div>
        <button
          onClick={run}
          disabled={!cur || busy}
          className="group inline-flex h-10 items-center gap-2 border border-rule px-4 text-sm transition-colors hover:bg-foreground hover:text-background disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ScanLine className={cn("h-4 w-4", busy && "animate-pulse")} />
          {busy ? "Analyzing…" : "Run vision analysis"}
        </button>
      </div>

      <p className="mt-3 max-w-2xl text-sm text-ink-soft">
        Runs an isolated detector on one extracted frame: it localizes the fretboard,
        straightens it, then measures string rows and fret wires from real pixels.
        It never runs during transcription, and it identifies no notes.
      </p>

      <ul className="mt-5 flex gap-3 overflow-x-auto md:grid md:grid-cols-4 md:content-start">
        {frames.map((f, i) => (
          <li key={f.index} className="shrink-0">
            <button
              onClick={() => setSel(i)}
              aria-label={`Select frame at ${fmt(f.timestamp)}`}
              aria-current={sel === i}
              className={cn(
                "block w-24 border-b-2 pb-1 text-left transition-opacity md:w-full",
                sel === i ? "border-primary" : "border-transparent opacity-60 hover:opacity-100"
              )}
            >
              <img
                src={frameUrl(jobId, f.index)}
                alt=""
                loading="lazy"
                className="aspect-video w-full bg-surface object-cover"
                onError={(e) => {
                  e.currentTarget.style.visibility = "hidden";
                }}
              />
              <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
                {fmt(f.timestamp)}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {error && (
        <p role="alert" className="mt-6 border-t border-destructive pt-4 text-sm text-destructive">
          {error} Your tablature above is unaffected.
        </p>
      )}

      {!analysis && !error && (
        <p className="mt-6 font-mono text-xs text-muted-foreground">
          {busy ? "Analyzing frame…" : "No analysis yet for this recording. Pick a frame and run the analysis."}
        </p>
      )}

      {analysis && (
        <div className="mt-6">
          <dl className="grid grid-cols-2 gap-x-8 gap-y-1 font-mono text-xs text-muted-foreground sm:grid-cols-4">
            <div>
              <dt>Status</dt>
              <dd className={analysis.detected ? "text-foreground" : "text-destructive"}>
                {analysis.detected ? "Fretboard localized" : "Not detected"}
              </dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd className="text-foreground">{analysis.confidence.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Strings</dt>
              <dd className="text-foreground">
                {analysis.stringsDetected === 6
                  ? "6 / 6 resolved"
                  : `${analysis.stringsDetected} row${analysis.stringsDetected === 1 ? "" : "s"}`}
              </dd>
            </div>
            <div>
              <dt>Fret wires</dt>
              <dd className="text-foreground">{analysis.fretsDetected} measured</dd>
            </div>
          </dl>
          {analysis.detectionSource && (
            <p className="mt-2 font-mono text-xs text-muted-foreground">
              Source: {analysis.detectionSource}
              {analysis.failureReason ? ` · ${analysis.failureReason}` : ""}
            </p>
          )}

          <div className="mt-6 grid gap-6 md:grid-cols-3">
            <figure>
              <div className="relative overflow-hidden bg-surface">
                <img
                  src={frameUrl(jobId, cur?.index ?? 0)}
                  alt={`Original frame at ${fmt(cur?.timestamp)}`}
                  className="block aspect-video w-full object-contain"
                  onError={(e) => {
                    e.currentTarget.style.opacity = "0.15";
                  }}
                />
                <figcaption className="absolute bottom-0 left-0 bg-background px-2 py-1 font-mono text-xs">
                  Original
                </figcaption>
              </div>
            </figure>

            <figure>
              <div className="relative overflow-hidden bg-surface">
                <img
                  src={annotatedUrl(jobId, cur?.index ?? 0)}
                  alt="Detection overlay with measured strings and frets"
                  className="block aspect-video w-full object-contain"
                  onError={(e) => {
                    e.currentTarget.style.opacity = "0.15";
                  }}
                />
                <figcaption className="absolute bottom-0 left-0 bg-background px-2 py-1 font-mono text-xs">
                  Overlay · strings blue · frets yellow
                </figcaption>
              </div>
            </figure>

            <figure>
              <div className="relative overflow-hidden bg-surface">
                {analysis.rectified ? (
                  <img
                    src={rectifiedUrl(jobId, cur?.index ?? 0)}
                    alt="Rectified fretboard crop"
                    className="block max-h-64 w-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.opacity = "0.15";
                    }}
                  />
                ) : (
                  <div className="flex aspect-video w-full items-center justify-center px-4 text-center text-sm text-ink-soft">
                    No rectified crop — no fretboard was localized in this frame.
                  </div>
                )}
                <figcaption className="absolute bottom-0 left-0 bg-background px-2 py-1 font-mono text-xs">
                  Rectified crop
                </figcaption>
              </div>
            </figure>
          </div>

          {analysis.limitations.length > 0 && (
            <ul className="mt-6 space-y-1 border-t border-border pt-4 text-sm text-ink-soft">
              {analysis.limitations.map((l, i) => (
                <li key={i}>· {l}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
