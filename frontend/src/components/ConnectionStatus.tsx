import type { BackendStatus } from "../hooks/useBackendStatus";

interface ConnectionStatusProps {
  status: BackendStatus;
  version?: string | null;
}

const DOT_CLASS: Record<BackendStatus, string> = {
  online: "bg-ink",
  offline: "bg-error",
  checking: "bg-transparent border border-ink-20",
};

const LABEL: Record<BackendStatus, string> = {
  online: "Backend online",
  offline: "Backend offline",
  checking: "Checking server",
};

/**
 * Reflects the actual backend connection state (polled health endpoint).
 * The dot uses palette tokens only: filled ink = online, hollow = checking,
 * error red = offline.
 */
export function ConnectionStatus({ status, version }: ConnectionStatusProps) {
  const title =
    status === "online" && version ? `GuitarTab AI backend v${version}` : LABEL[status];

  return (
    <span
      className="inline-flex items-center gap-2"
      title={title}
      aria-live="polite"
      aria-atomic="true"
    >
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${DOT_CLASS[status]}`}
      />
      <span className="t-eyebrow">
        {LABEL[status]}
        {status === "online" && version ? ` · v${version}` : ""}
      </span>
    </span>
  );
}