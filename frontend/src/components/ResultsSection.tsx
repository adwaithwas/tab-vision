import type { ReactNode } from "react";
import { AnnotatedPreview } from "./AnnotatedPreview";
import { TablatureArea } from "./TablatureArea";

interface ResultsSectionProps {
  /** True once a valid file is selected. */
  hasFile: boolean;
  /** Upload lifecycle backed by real backend responses. */
  uploadState: "idle" | "uploading" | "success" | "cancelled" | "error";
  jobResult: {
    jobId: string;
    originalName: string;
    sizeBytes: number;
    extension: string;
    uploadedAt: string;
    retentionNote: string;
  } | null;
  uploadError: string | null;
  /** Analysis output — always null in this milestone. */
  analysis: unknown;
}

/**
 * Results experience, built to stay empty and honest until the CV pipeline
 * produces real data. The reserved areas (preview + tablature) and the
 * event-confidence panel are all wired to *actual* results only.
 */
export function ResultsSection({
  hasFile,
  uploadState,
  jobResult,
  uploadError,
  analysis,
}: ResultsSectionProps) {
  return (
    <section aria-labelledby="results-title" className="flex flex-col gap-10">
      <header className="flex flex-col gap-2">
        <span className="t-eyebrow">03 — Output</span>
        <h2 id="results-title" className="t-h2">
          Results
        </h2>
      </header>

      <StatusPane
        hasFile={hasFile}
        uploadState={uploadState}
        jobResult={jobResult}
        uploadError={uploadError}
      />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <article className="flex flex-col gap-3">
          <h3 className="t-eyebrow">Visual Analysis (CV-based)</h3>
          <AnnotatedPreview jobId={uploadState === "success" && jobResult ? jobResult.jobId : null} />
        </article>

        <article className="flex flex-col gap-3">
          <h3 className="t-eyebrow">Six-string tablature (Audio-based)</h3>
          <div className="card p-6">
            <TablatureArea tabText={(analysis as any)?.tablature} />
          </div>
        </article>
      </div>

      <ConfidencePanel analysis={analysis} />
    </section>
  );
}

function StatusPane({
  hasFile,
  uploadState,
  jobResult,
  uploadError,
}: Pick<ResultsSectionProps, "hasFile" | "uploadState" | "jobResult" | "uploadError">) {
  if (uploadState === "uploading") {
    return <Banner>Receiving your video… the upload progress is shown above.</Banner>;
  }

  if (uploadState === "cancelled") {
    return <Banner variant="neutral">Upload cancelled. No file was submitted to the server.</Banner>;
  }

  if (uploadState === "error" && uploadError) {
    return <Banner variant="error">{uploadError}</Banner>;
  }

  if (jobResult && uploadState === "success") {
    return <JobRecord jobResult={jobResult} />;
  }

  return (
    <Banner variant="neutral">
      {hasFile
        ? "Your video is ready on this device. Press “Analyze Video” to upload it."
        : "No analysis yet. Choose a short, well-lit clip of six-string playing to begin — this build uploads and runs audio transcription."}
    </Banner>
  );
}

function Banner({
  variant = "info",
  children,
}: {
  variant?: "info" | "neutral" | "error";
  children: ReactNode;
}) {
  return (
    <div
      role="status"
      className={`t-body-sm max-w-[62ch] border-l pl-4 ${
        variant === "error" ? "border-error text-error" : "border-ink text-ink-50"
      }`}
    >
      {children}
    </div>
  );
}

function JobRecord({
  jobResult,
}: {
  jobResult: NonNullable<ResultsSectionProps["jobResult"]>;
}) {
  const receivedAt = new Date(jobResult.uploadedAt);
  const rows: Array<[string, string]> = [
    ["Job", jobResult.jobId],
    ["File", jobResult.originalName],
    ["Size", formatBytes(jobResult.sizeBytes)],
    ["Format", jobResult.extension.toUpperCase()],
    ["Status", "received"],
    ["Received", receivedAt.toLocaleString()],
  ];

  return (
    <div className="card p-6">
      <div className="flex flex-col gap-4">
        <div>
          <p className="t-body-sm font-semibold">Video received and registered</p>
          <p className="t-body-sm mt-1 max-w-[62ch] text-ink-50">
            The file was stored and registered as an analysis job. The audio track was
            transcribed using TabVision, producing the tablature below. (Visual processing
            is not yet active).
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-3">
          {rows.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="t-mono-sm text-ink-50">{label}</dt>
              <dd className="t-mono break-all text-ink">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="t-mono-sm text-ink-50">{jobResult.retentionNote}</p>
      </div>
    </div>
  );
}

/**
 * Event-level confidence and evaluation panel.
 *
 * Rendered only when real analysis data exists. The type check below keeps
 * fabricated or placeholder data out: with no events, nothing is shown.
 */
function ConfidencePanel({ analysis }: { analysis: unknown }) {
  if (!isAnalysisResultWithEvents(analysis)) return null;
  const events = analysis.events;

  return (
    <article className="flex flex-col gap-3">
      <h3 className="t-eyebrow">Event confidence</h3>
      <div className="card overflow-x-auto p-6">
        <table className="w-full text-left">
          <thead>
            <tr className="t-mono-sm text-ink-50">
              <th className="pr-6">Start</th>
              <th className="pr-6">End</th>
              <th className="pr-6">String</th>
              <th className="pr-6">Fret</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event, index) => (
              // eslint-disable-next-line react/no-array-index-key
              <tr key={index} className="t-mono border-t border-hairline">
                <td className="py-2 pr-6">{event.start_s.toFixed(2)}s</td>
                <td className="py-2 pr-6">{event.end_s.toFixed(2)}s</td>
                <td className="py-2 pr-6">{event.string}</td>
                <td className="py-2 pr-6">{event.fret}</td>
                <td className="py-2">{event.confidence?.toFixed(2) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function isAnalysisResultWithEvents(value: unknown): value is {
  events: Array<{ start_s: number; end_s: number; string: number; fret: number; confidence: number | null }>;
} {
  return Boolean(
    value &&
      typeof value === "object" &&
      Array.isArray((value as { events?: unknown }).events) &&
      ((value as { events: unknown[] }).events.length > 0),
  );
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  const decimals = value >= 10 || exponent === 0 ? 0 : 1;
  return `${value.toFixed(decimals)} ${units[exponent]}`;
}