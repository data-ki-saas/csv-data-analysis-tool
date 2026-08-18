import type { Presentation, PresentationBlock } from "@/lib/api";
import { renderStaticChart } from "@/lib/staticChart";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderBlockHtml(block: PresentationBlock): string {
  if (block.type === "chart") {
    return `<div class="block chart-block"><h3>${escapeHtml(block.title)}</h3>${renderStaticChart(block)}</div>`;
  }
  if (block.type === "insights") {
    return (
      `<div class="block insights-block"><h4>Key insights — ${escapeHtml(block.chart_title)}</h4>` +
      `<ul>${block.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul></div>`
    );
  }
  return `<div class="block text-block"><p>${escapeHtml(block.text)}</p></div>`;
}

/** A fully self-contained HTML document -- inline CSS, inline SVG charts, no
 * external requests and no JS framework -- so it opens correctly in any
 * browser long after this app (or the dataset) is gone. */
export function buildStandaloneHtml(presentation: Presentation): string {
  const pagesHtml = presentation.pages
    .map(
      (page, i) =>
        `<section class="page"><h2>${escapeHtml(page.title || `Page ${i + 1}`)}</h2>` +
        `<div class="blocks">${page.blocks.map(renderBlockHtml).join("")}</div></section>`
    )
    .join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeHtml(presentation.title)}</title>
<style>
  :root { color-scheme: light; }
  body { font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; background: #f8fafc; color: #0f172a; }
  header { padding: 2rem 1.5rem 1rem; text-align: center; }
  header h1 { margin: 0; font-size: 1.75rem; }
  .page { max-width: 900px; margin: 0 auto 2rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
          padding: 1.5rem 2rem 2rem; page-break-after: always; }
  .page h2 { margin-top: 0; font-size: 1.25rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5rem; }
  .blocks { display: flex; flex-direction: column; gap: 1.5rem; }
  .chart-block h3 { margin: 0 0 0.5rem; font-size: 1rem; }
  .chart-block svg { width: 100%; height: auto; max-width: 640px; display: block; }
  .insights-block { background: #eff6ff; border-radius: 6px; padding: 0.75rem 1rem; }
  .insights-block h4 { margin: 0 0 0.5rem; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em;
                        color: #1d4ed8; }
  .insights-block ul { margin: 0; padding-left: 1.25rem; font-size: 0.9rem; }
  .text-block p { font-size: 0.95rem; line-height: 1.5; white-space: pre-wrap; }
  footer { text-align: center; font-size: 0.75rem; color: #64748b; padding: 1rem; }
  @media print { body { background: #fff; } .page { border: none; } }
</style>
</head>
<body>
<header><h1>${escapeHtml(presentation.title)}</h1></header>
${pagesHtml}
<footer>Exported from CSV Data Analysis Tool</footer>
</body>
</html>`;
}

export function downloadStandaloneHtml(presentation: Presentation): void {
  const html = buildStandaloneHtml(presentation);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const safeName = presentation.title.replace(/[^a-z0-9-_]+/gi, "-").replace(/^-+|-+$/g, "") || "presentation";
  link.download = `${safeName}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
