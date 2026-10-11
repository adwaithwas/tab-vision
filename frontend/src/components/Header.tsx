import { ConnectionStatus } from "./ConnectionStatus";
import type { BackendStatusState } from "../hooks/useBackendStatus";

interface HeaderProps {
  backend: BackendStatusState;
}

/**
 * Header: wordmark, one-line descriptor, minimal single-page navigation and
 * a live backend status indicator.
 */
export function Header({ backend }: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-hairline bg-surface/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1120px] items-center justify-between gap-6 px-5 py-4 sm:px-8">
        <a
          href="#top"
          className="group flex min-w-0 items-baseline gap-3 no-underline"
          aria-label="GuitarTab AI — back to top"
        >
          <span className="truncate font-display text-[1.3125rem] font-semibold leading-none tracking-tight">
            GuitarTab AI
          </span>
          <span className="hidden t-eyebrow sm:inline">
            Video&nbsp;→&nbsp;guitar tablature
          </span>
        </a>

        <div className="flex items-center gap-5 sm:gap-8">
          <nav aria-label="Page sections" className="hidden items-center gap-6 t-eyebrow md:flex">
            <a href="#upload" className="no-underline hover:text-ink hover:underline underline-offset-4">
              Upload
            </a>
            <a href="#pipeline" className="no-underline hover:text-ink hover:underline underline-offset-4">
              Pipeline
            </a>
            <a href="#results" className="no-underline hover:text-ink hover:underline underline-offset-4">
              Results
            </a>
          </nav>
          <ConnectionStatus status={backend.status} version={backend.info?.version} />
        </div>
      </div>
    </header>
  );
}