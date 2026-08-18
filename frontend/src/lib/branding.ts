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

/** Renders the active header as an HTML fragment (logo + title), or a plain
 * `fallbackTitle` heading when no header preset is enabled -- so a user who
 * hasn't set up branding sees no regression from today's plain title. */
export function renderBrandedHeaderHtml(
  preset: HeaderPreset | null | undefined,
  fallbackTitle: string
): string {
  if (!preset) return `<h1>${escapeHtml(fallbackTitle)}</h1>`;
  const logoImg = preset.logo
    ? `<img src="${preset.logo}" alt="" style="height:40px;display:block;margin:0 auto 0.5rem;" />`
    : "";
  return `${logoImg}<h1>${escapeHtml(preset.title || fallbackTitle)}</h1>`;
}

/** Renders the active footer's already-sanitized HTML, or a plain
 * `fallbackText` line when no footer preset is enabled. */
export function renderBrandedFooterHtml(
  preset: FooterPreset | null | undefined,
  fallbackText: string
): string {
  if (!preset) return `<p>${escapeHtml(fallbackText)}</p>`;
  return preset.html;
}
