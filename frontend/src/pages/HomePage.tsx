import { useCallback, useState } from "react";
import { AnalyzePanel } from "../components/AnalyzePanel";
import { Header } from "../components/Header";
import { PipelineSection } from "../components/PipelineSection";
import { ResultsSection } from "../components/ResultsSection";
import { UploadZone } from "../components/UploadZone";
import { useBackendStatus } from "../hooks/useBackendStatus";
import { useCapabilities } from "../hooks/useCapabilities";
import { useUpload } from "../hooks/useUpload";
import { validateVideoFile, DEFAULT_ALLOWED_EXTENSIONS } from "../services/validation";

export function HomePage() {
  const backend = useBackendStatus();
  const capabilities = useCapabilities();
  const upload = useUpload();

  const maxSizeMb = capabilities.data?.video_upload.max_file_size_mb ?? 100;
  const allowedExtensions =
    capabilities.data?.video_upload.allowed_extensions ?? DEFAULT_ALLOWED_EXTENSIONS;

  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const handleSelect = useCallback(
    (next: File | null) => {
      upload.reset();
      if (!next) {
        setFile(null);
        setFileError(null);
        return;
      }
      const problem = validateVideoFile(next, {
        maxBytes: maxSizeMb * 1024 * 1024,
        allowedExtensions,
      });
      if (problem) {
        setFile(null);
        setFileError(problem);
        return;
      }
      setFileError(null);
      setFile(next);
    },
    [maxSizeMb, allowedExtensions, upload],
  );

  const handleAnalyze = () => {
    if (!file || fileError !== null || upload.inFlight || backend.status !== "online") return;
    upload.start(file);
  };

  const canAnalyze =
    file !== null && fileError === null && !upload.inFlight && backend.status === "online";

  return (
    <div id="top" className="flex min-h-screen flex-col">
      <Header backend={backend} />

      <main className="mx-auto w-full max-w-[1120px] flex-1 px-5 sm:px-8">
        {/* 01 — Introduction */}
        <section className="flex flex-col gap-8 py-12 sm:py-16">
          <div className="max-w-[640px]">
            <span className="t-eyebrow">CVDV · Computer Vision &amp; Digital Vision — 2026</span>
            <h1 className="t-h1 mt-4">Turn a performance into tablature.</h1>
            <p className="t-body mt-6 text-ink-50">
              GuitarTab&nbsp;AI is a research prototype that will read a short video of
              six-string guitar playing and produce six-string tablature. This
              foundation milestone implements video upload and validation for real; the
              note-reading computer-vision pipeline is the next stage of the research.
            </p>
          </div>
        </section>

        {/* 02 — Source video / upload */}
        <section id="upload" aria-labelledby="upload-title" className="flex scroll-mt-24 flex-col gap-6">
          <header className="flex flex-col gap-2">
            <span className="t-eyebrow">01 — Source</span>
            <h2 id="upload-title" className="t-h2">
              Upload a clip
            </h2>
            <p className="t-body-sm max-w-[62ch] text-ink-50">
              Accepted formats are MP4, MOV and WebM up to {maxSizeMb}&nbsp;MB. The clip
              is uploaded as-is and validated on both this page and the server. It is
              not analyzed in this milestone.
            </p>
          </header>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
            <UploadZone
              file={file}
              error={fileError}
              onSelect={handleSelect}
              disabled={upload.inFlight}
              formatsLabel="MP4, MOV, WebM"
              maxSizeLabel={`${maxSizeMb} MB`}
            />
            <aside className="card flex flex-col justify-between gap-6 p-6">
              <AnalyzePanel
                canAnalyze={canAnalyze}
                uploading={upload.inFlight}
                offline={backend.status !== "online"}
                progress={upload.progress}
                onAnalyze={handleAnalyze}
                onCancel={upload.cancel}
              />
            </aside>
          </div>
        </section>

        <hr className="my-16 border-divider" />

        {/* 03 — Pipeline / capabilities */}
        <div id="pipeline" className="scroll-mt-24">
          <PipelineSection
            data={capabilities.data}
            loading={capabilities.loading}
            error={capabilities.error}
          />
        </div>

        <hr className="my-16 border-divider" />

        {/* 04 — Results */}
        <div id="results" className="scroll-mt-24">
          <ResultsSection
            hasFile={file !== null}
            uploadState={upload.state}
            jobResult={
              upload.result
                ? {
                    jobId: upload.result.job_id,
                    originalName: upload.result.original_name,
                    sizeBytes: upload.result.size_bytes,
                    extension: upload.result.extension,
                    uploadedAt: upload.result.uploaded_at,
                    retentionNote: upload.result.retention_note,
                  }
                : null
            }
            uploadError={upload.error}
            analysis={upload.result?.analysis ?? null}
          />
        </div>
      </main>

      <footer className="mt-20 border-t border-hairline">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-3 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span className="t-eyebrow">GuitarTab AI — research prototype</span>
          <span className="t-mono-sm text-ink-50">
            Foundation milestone · uploads live · CV pipeline planned
          </span>
        </div>
      </footer>
    </div>
  );
}