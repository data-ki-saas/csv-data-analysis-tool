import type { ReactNode } from "react";

// Hand-rolled, dependency-free icons (straight lines/basic shapes only, no
// complex path data) -- consistent with this codebase's established pattern
// of avoiding new npm dependencies for presentational concerns (see
// staticChart.ts's SVG rendering, exportChartImage.ts/exportChartPdf.ts).

const ICON_PROPS = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function InsightsIcon() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="12" cy="9" r="6" />
      <line x1="9" y1="18" x2="15" y2="18" />
      <line x1="10" y1="21" x2="14" y2="21" />
    </svg>
  );
}

export function PinIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M6 3h12v18l-6-4-6 4V3Z" />
    </svg>
  );
}

export function JpgIcon() {
  return (
    <svg {...ICON_PROPS}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <path d="M21 16l-5-5-4 4-3-3-6 6" />
    </svg>
  );
}

export function PdfIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M6 2h8l4 4v16H6z" />
      <path d="M14 2v4h4" />
      <line x1="9" y1="13" x2="15" y2="13" />
      <line x1="9" y1="17" x2="15" y2="17" />
    </svg>
  );
}

export function ShareIcon() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="18" cy="18" r="2.5" />
      <line x1="8.2" y1="10.8" x2="15.8" y2="7.2" />
      <line x1="8.2" y1="13.2" x2="15.8" y2="16.8" />
    </svg>
  );
}

export function CopyIcon() {
  return (
    <svg {...ICON_PROPS}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <rect x="3" y="3" width="12" height="12" rx="2" />
    </svg>
  );
}

export function RevokeIcon() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="12" cy="12" r="9" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  );
}

export function ArrowUpIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="6 12 12 6 18 12" />
      <line x1="12" y1="6" x2="12" y2="18" />
    </svg>
  );
}

export function ArrowDownIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="6 12 12 18 18 12" />
      <line x1="12" y1="6" x2="12" y2="18" />
    </svg>
  );
}

export function TrashIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M4 7h16" />
      <path d="M9 7V4h6v3" />
      <path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  );
}

export function MaximizeIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="8 3 4 3 4 8" />
      <polyline points="16 3 20 3 20 8" />
      <polyline points="20 16 20 20 16 20" />
      <polyline points="4 16 4 20 8 20" />
    </svg>
  );
}

export function MinimizeIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="4 8 4 4 8 4" />
      <polyline points="16 4 20 4 20 8" />
      <polyline points="20 16 20 20 16 20" />
      <polyline points="8 20 4 20 4 16" />
    </svg>
  );
}

// Dual-colour, unlike every other icon here -- a site "home" mark benefits
// from a bit of brand colour in a header that's otherwise plain currentColor
// outlines, so the roof is filled with the accent colour while the body
// stays an outline in the current text colour.
export function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11.5 12 4l9 7.5" fill="none" stroke="var(--color-accent)" />
      <path d="M5.5 10v9.5a1 1 0 0 0 1 1H17.5a1 1 0 0 0 1-1V10" fill="none" stroke="currentColor" />
      <path d="M9.5 20.5v-6h5v6" fill="none" stroke="currentColor" />
    </svg>
  );
}

// A folded-corner document (same silhouette as PdfIcon) with a row/column
// grid instead of text lines -- reads as a spreadsheet/CSV file rather than
// a generic document.
export function CsvIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M6 2h8l4 4v16H6z" />
      <path d="M14 2v4h4" />
      <line x1="6" y1="11" x2="18" y2="11" />
      <line x1="6" y1="15" x2="18" y2="15" />
      <line x1="10" y1="8" x2="10" y2="20" />
      <line x1="14" y1="8" x2="14" y2="20" />
    </svg>
  );
}

interface IconButtonProps {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
}

/** An icon-only button with an accessible label and a small hover tooltip
 * showing that label -- pure Tailwind, no tooltip library. */
export function IconButton({ label, onClick, disabled, children }: IconButtonProps) {
  return (
    <span className="group/tooltip relative inline-flex">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        className="rounded p-1.5 opacity-70 transition-opacity hover:bg-accent/10 hover:opacity-100 disabled:opacity-30 [&_svg]:h-4 [&_svg]:w-4"
      >
        {children}
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute -top-8 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded bg-foreground px-2 py-1 text-xs text-background opacity-0 transition-opacity group-hover/tooltip:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}
