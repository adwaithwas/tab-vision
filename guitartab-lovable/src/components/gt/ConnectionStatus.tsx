import { useCallback, useEffect, useState } from "react";
import { API_BASE, checkHealth } from "@/lib/tab-service";
import { cn } from "@/lib/utils";

type Status = "checking" | "online" | "offline";

const label: Record<Status, string> = { checking: "Checking server", online: "Server connected", offline: "Server unreachable" };

export function ConnectionStatus({ refreshKey = 0 }: { refreshKey?: number }) {
  const [status, setStatus] = useState<Status>("checking");
  const [open, setOpen] = useState(false);

  const check = useCallback(async () => {
    setStatus("checking");
    setOpen(false);
    setStatus((await checkHealth()) ? "online" : "offline");
  }, []);

  useEffect(() => { void check(); }, [check]);
  useEffect(() => { if (refreshKey > 0) void check(); }, [refreshKey, check]);

  return (
    <span className="relative hidden items-center sm:inline-flex">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        title="Connection to the transcription server"
        className="inline-flex items-center gap-2 font-mono text-xs text-ink-soft transition-colors hover:text-foreground"
      >
        <span className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "online" && "bg-primary",
          status === "checking" && "bg-muted-foreground animate-pulse",
          status === "offline" && "bg-destructive",
        )} />
        <span aria-live="polite">{label[status]}</span>
      </button>

      {open && (
        <div role="dialog" aria-label="Server connection details" className="animate-rise absolute top-full right-0 z-50 mt-3 w-72 border border-rule bg-background p-5 text-left shadow-lg">
          <p className="font-mono text-xs text-muted-foreground">{label[status]}</p>
          {status === "offline" ? (
            <>
              <p className="mt-3 text-sm text-ink-soft">
                Tab Vision can't reach the transcription server, so uploading won't work yet. To fix it:
              </p>
              <ol className="mt-3 space-y-2 text-sm text-ink-soft">
                <li className="grid grid-cols-[1.25rem_1fr] gap-2">
                  <span className="font-mono text-xs text-primary">1.</span>
                  <span>Running locally? Start the backend on port 8000 and allow this site's address in its CORS settings.</span>
                </li>
                <li className="grid grid-cols-[1.25rem_1fr] gap-2">
                  <span className="font-mono text-xs text-primary">2.</span>
                  <span>On a published site? The backend must be hosted on an HTTPS address, with that address set as the API URL.</span>
                </li>
              </ol>
            </>
          ) : status === "checking" ? (
            <p className="mt-3 text-sm text-ink-soft">Testing the connection…</p>
          ) : (
            <p className="mt-3 text-sm text-ink-soft">The transcription server is reachable and ready for uploads.</p>
          )}
          <p className="mt-3 truncate font-mono text-xs text-muted-foreground">{API_BASE}</p>
          <button onClick={check} className="mt-4 inline-flex items-center gap-2 border border-rule px-3 py-1.5 text-xs hover:bg-foreground hover:text-background">
            Recheck connection
          </button>
        </div>
      )}
    </span>
  );
}
