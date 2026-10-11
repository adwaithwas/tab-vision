import type { CapabilitiesResponse } from "../types/api";
import { SectionHeading } from "./ui/SectionHeading";

interface PipelineSectionProps {
  data: CapabilitiesResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * Shows the *real* capabilities contract from the backend: upload is live,
 * every CV stage is explicitly planned. Presented as a numbered pipeline so
 * the roadmap is visible without claiming anything is implemented.
 */
export function PipelineSection({ data, loading, error }: PipelineSectionProps) {
  return (
    <section aria-labelledby="pipeline-title" className="flex flex-col gap-4">
      <SectionHeading index="02" eyebrow="Capabilities" title="Pipeline">
        What this build does today, and what the computer-vision stages will add
        in the next milestone. Values come from the backend&rsquo;s `/api/capabilities`
        endpoint — never from assumptions baked into the interface.
      </SectionHeading>

      {loading && <p className="t-mono-sm text-ink-50">Loading capabilities…</p>}
      {error && (
        <p role="status" className="t-mono border-l border-error pl-3 text-error">
          Could not load capabilities from the backend: {error}
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-5">
          <div className="card p-6">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
              <StatusChip label="Video upload" implemented={data.video_upload.supported} />
              <span className="t-mono-sm text-ink-50">
                {data.video_upload.max_file_size_mb} MB max ·{" "}
                {data.video_upload.allowed_extensions.join(" · ")}
              </span>
              <span className="t-mono-sm text-ink-50">
                {data.cv_pipeline.implemented
                  ? "CV pipeline: partially implemented"
                  : "CV pipeline: not implemented"}
              </span>
            </div>
          </div>

          <ol className="grid gap-3 sm:grid-cols-2">
            {data.cv_pipeline.stages.map((stage, index) => (
              <li key={stage.key} className="card flex flex-col gap-2 p-5">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="t-mono-sm text-ink-50">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <StatusChip label={stage.status} implemented={stage.implemented} />
                </div>
                <h3 className="t-body-sm font-semibold">{stage.label}</h3>
                <p className="t-body-sm text-ink-50">{stage.description}</p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function StatusChip({ label, implemented }: { label: string; implemented: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-sm px-2 py-0.5 t-mono-sm capitalize ${
        implemented ? "bg-ink text-surface" : "border border-ink-20 text-ink-50"
      }`}
    >
      {label}
    </span>
  );
}