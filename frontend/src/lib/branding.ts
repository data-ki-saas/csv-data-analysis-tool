import type { FooterPreset, HeaderPreset } from "@/lib/api";

// Shared across every export/share surface (standalone HTML, presentation
// print, per-chart PDF/JPG, the public share page) so "what does branding
// look like" is defined once. Footer HTML is already sanitized server-side
// at save time (src/settings/service.py) -- never re-escaped or re-sanitized
// here, it's meant to be rendered as real markup.

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Standalone exports (HTML file, PDF popup, JPG rasterization) are separate
// documents that never load this app's globals.css, so they can't just
// reference var(--color-accent) and expect it to resolve -- this reads the
// *current* theme's resolved accent color from the live page (where the
// variable is defined) and inlines the literal value instead, so the
// exported/shared document still carries the active color theme's brand
// color wherever it ends up being viewed. Falls back to the default
// "winter" theme's accent for any non-browser render path (there isn't one
// today, but this keeps the function safe to call from anywhere).
const DEFAULT_ACCENT = "#2563eb";

function currentAccentColor(): string {
  if (typeof document === "undefined") return DEFAULT_ACCENT;
  const value = getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim();
  return value || DEFAULT_ACCENT;
}

/** Renders the active header as an HTML fragment (logo + title), or a plain
 * `fallbackTitle` heading when no header preset is enabled -- so a user who
 * hasn't set up branding sees no regression from today's plain title.
 * Styled in the active colour theme's accent colour either way. */
export function renderBrandedHeaderHtml(
  preset: HeaderPreset | null | undefined,
  fallbackTitle: string
): string {
  const accent = currentAccentColor();
  const headingStyle = `color:${accent};border-bottom:2px solid ${accent};padding-bottom:0.5rem;margin-bottom:0.5rem;`;
  if (!preset) return `<h1 style="${headingStyle}">${escapeHtml(fallbackTitle)}</h1>`;
  const logoImg = preset.logo
    ? `<img src="${preset.logo}" alt="" style="height:40px;display:block;margin:0 auto 0.5rem;" />`
    : "";
  return `${logoImg}<h1 style="${headingStyle}">${escapeHtml(preset.title || fallbackTitle)}</h1>`;
}

/** Renders the active footer's already-sanitized HTML, or a plain
 * `fallbackText` line when no footer preset is enabled. Wrapped in an
 * accent-coloured top border either way, matching the header's treatment. */
export function renderBrandedFooterHtml(
  preset: FooterPreset | null | undefined,
  fallbackText: string
): string {
  const accent = currentAccentColor();
  const wrapperStyle = `border-top:2px solid ${accent};padding-top:0.5rem;margin-top:0.5rem;`;
  if (!preset) return `<p style="${wrapperStyle}color:${accent};">${escapeHtml(fallbackText)}</p>`;
  return `<div style="${wrapperStyle}">${preset.html}</div>`;
}
