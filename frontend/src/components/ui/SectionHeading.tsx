import type { ReactNode } from "react";

interface SectionHeadingProps {
  index: string;
  eyebrow: string;
  title: string;
  children?: ReactNode;
}

/** Editorial section header: numbered mono eyebrow + serif title + optional lead. */
export function SectionHeading({ index, eyebrow, title, children }: SectionHeadingProps) {
  return (
    <header className="mb-6 flex flex-col gap-2">
      <span className="t-eyebrow">
        {index} — {eyebrow}
      </span>
      <h2 className="t-h2">{title}</h2>
      {children && <p className="t-body-sm max-w-[62ch] text-ink-50">{children}</p>}
    </header>
  );
}