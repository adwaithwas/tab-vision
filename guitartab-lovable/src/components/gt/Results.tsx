import { useEffect, useState } from "react";
import { Check, Copy, Download } from "lucide-react";
import type { TabResult } from "@/lib/tab-service";
import { formatBytes } from "./Upload";
import { cn } from "@/lib/utils";

export function Processing({ stage, fileName }: { stage: "uploading" | "transcribing"; fileName: string }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 4000); return () => clearTimeout(t); }, []);
  const stages = [["uploading", "Uploading recording"], ["transcribing", "Transcribing notes"]] as const;
  const idx = stages.findIndex(([k]) => k === stage);
  return (
    <div className="animate-rise border-t border-rule pt-10" aria-live="polite">
      <p className="eyebrow">In progress · {fileName}</p>
      <h2 className="mt-3 font-display text-4xl font-medium tracking-tight">Analyzing your performance</h2>
      <div className="scan-bar mt-8 h-px bg-border" />
      <ol className="mt-8 grid gap-4 sm:grid-cols-2">
        {stages.map(([k, label], i) => (
          <li key={k} className={cn("flex items-baseline gap-4 border-t pt-4", i <= idx ? "border-rule" : "border-border")}>
            <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
            <span className={cn("text-base", i < idx ? "text-muted-foreground line-through decoration-1" : i === idx ? "text-foreground" : "text-muted-foreground")}>{label}</span>
            {i === idx && <span className="ml-auto h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />}
            {i < idx && <Check className="ml-auto h-4 w-4 text-primary" />}
          </li>
        ))}
      </ol>
      {slow && <p className="mt-8 max-w-md text-sm text-ink-soft">Longer recordings take a little more time. You can keep this tab open — nothing will be lost.</p>}
    </div>
  );
}

export function Results({ result, file }: { result: TabResult; file: File }) {
  const [copy, setCopy] = useState<"idle" | "done" | "error">("idle");
  const [dl, setDl] = useState(false);

  const doCopy = async () => {
    try { await navigator.clipboard.writeText(result.tablature); setCopy("done"); }
    catch { setCopy("error"); }
    setTimeout(() => setCopy("idle"), 2000);
  };
  const doDownload = () => {
    setDl(true);
    const url = URL.createObjectURL(new Blob([result.tablature], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url; a.download = file.name.replace(/\.[^.]+$/, "") + "-tab.txt"; a.click();
    URL.revokeObjectURL(url);
    setTimeout(() => setDl(false), 1200);
  };

  const meta: [string, string][] = [["Source", file.name], ["Size", formatBytes(file.size)]];
  if (result.tuning) meta.push(["Tuning", result.tuning]);
  if (result.noteCount != null) meta.push(["Notes", String(result.noteCount)]);

  return (
    <section className="animate-rise" aria-labelledby="tab-h">
      <div className="flex items-center gap-2 text-sm text-primary"><Check className="h-4 w-4" /> Transcription complete</div>
      <dl className="mt-6 grid grid-cols-2 border-y border-rule sm:grid-cols-4">
        {meta.map(([k, v]) => (
          <div key={k} className="border-r border-border px-0 py-4 last:border-r-0 sm:px-4 sm:first:pl-0">
            <dt className="eyebrow">{k}</dt>
            <dd className="mt-1 truncate font-mono text-sm">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-16 flex flex-wrap items-end justify-between gap-6">
        <h2 id="tab-h" className="font-display text-5xl font-medium tracking-tight sm:text-6xl">Your tablature</h2>
        <div className="flex gap-2">
          <button onClick={doCopy} className="inline-flex h-10 items-center gap-2 border border-rule px-4 text-sm transition-colors hover:bg-foreground hover:text-background">
            {copy === "done" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copy === "done" ? "Copied" : copy === "error" ? "Copy failed" : "Copy"}
          </button>
          <button onClick={doDownload} className="inline-flex h-10 items-center gap-2 bg-foreground px-4 text-sm text-background transition-colors hover:bg-primary">
            <Download className="h-4 w-4" /> {dl ? "Downloading…" : "Download .txt"}
          </button>
        </div>
      </div>

      <div className="mt-8 overflow-x-auto border-y border-rule bg-card" tabIndex={0} aria-label="Tablature, scroll horizontally">
        <pre className="px-6 py-8 font-mono text-[13px] leading-[1.7] whitespace-pre sm:px-10 sm:text-sm">
          {result.tablature.split("\n").map((line, i) => (
            <div key={i} className={cn(line === "" && "my-3 h-px bg-border")}>
              {line && <><span className="text-primary">{line.slice(0, 2)}</span>{line.slice(2)}</>}
            </div>
          ))}
        </pre>
      </div>
    </section>
  );
}
