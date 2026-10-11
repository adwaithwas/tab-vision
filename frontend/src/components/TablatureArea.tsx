/**
 * Empty six-string tablature scaffold.
 *
 * This renders the *structure* a tablature view needs (six lines, string
 * labels, bar lines) without inventing any note data. Note numbers only
 * appear once the CV pipeline produces real events.
 */

const STRING_LABELS = ["e", "B", "G", "D", "A", "E"] as const;

export function TablatureArea({ tabText }: { tabText?: string }) {
  if (tabText) {
    return (
      <figure className="m-0">
        <div className="overflow-x-auto">
          <pre className="font-mono text-sm whitespace-pre text-ink">
{tabText}
          </pre>
        </div>
      </figure>
    );
  }

  const lineTop = 22;
  const lineGap = 28;
  const lines = STRING_LABELS.length;
  const height = lineTop + lineGap * (lines - 1) + 22;

  return (
    <figure className="m-0">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 720 ${height}`}
          role="img"
          aria-label="Empty six-string tablature staff awaiting note events"
          className="h-auto w-full min-w-[420px]"
          preserveAspectRatio="xMidYMid meet"
        >
          {STRING_LABELS.map((label, index) => {
            const y = lineTop + lineGap * index;
            return (
              <g key={`${label}-${index}`}>
                <text
                  x={8}
                  y={y + 4}
                  className="fill-ink-50"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {label}
                </text>
                <line
                  x1={34}
                  y1={y}
                  x2={712}
                  y2={y}
                  style={{ stroke: "var(--color-ink)", strokeOpacity: 0.35, strokeWidth: 1 }}
                />
              </g>
            );
          })}

          {[190, 380, 570].map((x) => (
            <line
              key={x}
              x1={x}
              y1={lineTop - 8}
              x2={x}
              y2={lineTop + lineGap * (lines - 1) + 8}
              style={{ stroke: "var(--color-ink)", strokeOpacity: 0.14, strokeWidth: 1 }}
            />
          ))}
        </svg>
      </div>
      <figcaption className="t-mono-sm mt-3 text-ink-50">
        No note events yet — the staff stays empty until real analysis output exists.
      </figcaption>
    </figure>
  );
}