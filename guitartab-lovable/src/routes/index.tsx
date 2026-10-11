import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { UploadZone } from "@/components/gt/Upload";
import { Processing, Results } from "@/components/gt/Results";
import { Frames } from "@/components/gt/Frames";
import { VisionPanel } from "@/components/gt/VisionPanel";
import { ConnectionStatus } from "@/components/gt/ConnectionStatus";
import { generateTablature, type Stage, type TabResult } from "@/lib/tab-service";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Tab Vision — From performance to tablature" },
      { name: "description", content: "Turn your guitar videos into playable six-string tabs." },
      { property: "og:title", content: "Tab Vision — From performance to tablature" },
      { property: "og:description", content: "Turn your guitar videos into playable six-string tabs." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

type State =
  | { k: "idle" }
  | { k: "processing"; stage: Stage }
  | { k: "done"; result: TabResult }
  | { k: "error"; message: string };

function Wordmark() {
  return <span className="font-display text-lg font-semibold tracking-tight">Tab Vision<span className="text-primary">.</span></span>;
}

function Index() {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<State>({ k: "idle" });
  const abort = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [failCount, setFailCount] = useState(0);
  const busy = state.k === "processing";

  useEffect(() => () => abort.current?.abort(), []);

  const run = async () => {
    if (!file || busy) return;
    abort.current = new AbortController();
    setState({ k: "processing", stage: "uploading" });
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    try {
      const result = await generateTablature(file, (stage) => setState({ k: "processing", stage }), abort.current.signal);
      setState({ k: "done", result });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setFailCount((n) => n + 1);
      setState({ k: "error", message: (e as Error).message || "Something went wrong." });
    }
  };

  const onFile = (f: File | null) => { setFile(f); setState({ k: "idle" }); };
  const status = busy ? "Processing" : state.k === "done" ? "Ready" : state.k === "error" ? "Attention" : null;

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6 sm:px-10">
        <a href="#top" aria-label="Tab Vision home"><Wordmark /></a>
        <nav className="flex items-center gap-6 text-sm text-ink-soft">
          <a href="#studio" className="hover:text-foreground">Studio</a>
          <a href="#about" className="hidden hover:text-foreground sm:inline">About</a>
          <ConnectionStatus refreshKey={failCount} />
          {status && (
            <span className="hidden items-center gap-2 font-mono text-xs sm:inline-flex" aria-live="polite">
              <span className={cn("h-1.5 w-1.5 rounded-full", state.k === "error" ? "bg-destructive" : "bg-primary", busy && "animate-pulse")} />
              {status}
            </span>
          )}
        </nav>
      </header>

      <main id="top" className="mx-auto max-w-6xl px-6 sm:px-10">
        <section id="studio" className="grid gap-12 border-t border-rule pt-16 pb-24 md:grid-cols-12 md:pt-24 lg:gap-16">
          <div className="min-w-0 md:col-span-6">
            <p className="eyebrow">Studio · Six-string transcription</p>
            <h1 className="mt-6 break-words font-display text-[clamp(3rem,6vw,5rem)] font-medium leading-[0.94] tracking-[-0.035em]">
              From performance to tablature<span className="text-primary">.</span>
            </h1>
            <p className="mt-8 max-w-sm text-lg text-ink-soft">Turn your guitar videos into playable six-string tabs.</p>
          </div>
          <div className="min-w-0 md:col-span-6 md:pt-24">
            <UploadZone file={file} onFile={onFile} disabled={busy} />
            <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
              <p className="font-mono text-xs text-muted-foreground">{file ? "Ready when you are." : "Select a recording to begin."}</p>
              <button onClick={run} disabled={!file || busy}
                className="group inline-flex h-12 shrink-0 items-center gap-3 bg-primary px-6 text-sm font-medium text-primary-foreground transition-all hover:gap-4 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground">
                {busy ? "Generating…" : "Generate tablature"} <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </section>

        <div ref={resultsRef} className="scroll-mt-8">
          {state.k === "processing" && file && <div className="pb-24"><Processing stage={state.stage} fileName={file.name} /></div>}
          {state.k === "error" && (
            <div role="alert" className="animate-rise mb-24 border-t border-destructive pt-8">
              <p className="eyebrow text-destructive">Transcription failed</p>
              <p className="mt-3 font-display text-2xl">{state.message}</p>
              <p className="mt-2 text-sm text-ink-soft">Try a clearer, well-lit recording with the fretboard in view.</p>
              <button onClick={run} className="mt-6 inline-flex items-center gap-2 border border-rule px-4 py-2 text-sm hover:bg-foreground hover:text-background">
                <RotateCcw className="h-4 w-4" /> Try again
              </button>
            </div>
          )}
          {state.k === "done" && file && (
            <div className="border-t border-rule pt-10 pb-28">
              <Results result={state.result} file={file} />
              <Frames jobId={state.result.jobId} />
              <VisionPanel jobId={state.result.jobId} />
            </div>
          )}
        </div>
      </main>

      <footer id="about" className="border-t border-rule">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-12 sm:flex-row sm:items-baseline sm:justify-between sm:px-10">
          <Wordmark />
          <p className="max-w-sm text-sm text-ink-soft">A project exploring computer vision and audio-based guitar transcription.</p>
        </div>
      </footer>
    </div>
  );
}
