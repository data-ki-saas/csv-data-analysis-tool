import type { ChartBlock } from "@/lib/api";
import { renderStaticChart } from "@/lib/staticChart";

// No PDF library, no server round-trip -- same "browser print" mechanism the
// presentation builder's "Export as PDF" button already uses (see
// dashboard/[datasetId]/presentation/page.tsx), just scoped to a single
// chart instead of the whole document. A dedicated popup window (rather than
// printing the current Reports page) keeps this independent of whatever
// else is on screen -- no print-only CSS to coordinate across every other
// chart card on the page.

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function printChartAsPdf(block: ChartBlock, width = 720, height = 400): void {
  const svg = renderStaticChart(block, width, height);

  const printWindow = window.open("", "_blank", "width=800,height=600");
  if (!printWindow) {
    throw new Error("Couldn't open the print window -- check your browser's popup blocker.");
  }

  printWindow.document.write(`<!doctype html>
<html>
  <head>
    <title>${escapeHtml(block.title)}</title>
    <style>
      body { font-family: Arial, Helvetica, sans-serif; margin: 32px; text-align: center; }
      h1 { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
      svg { max-width: 100%; height: auto; }
    </style>
  </head>
  <body>
    <h1>${escapeHtml(block.title)}</h1>
    ${svg}
  </body>
</html>`);
  printWindow.document.close();

  printWindow.onafterprint = () => printWindow.close();
  printWindow.focus();
  // Give the popup a tick to lay out the SVG before invoking print -- calling
  // print() synchronously right after document.write() can race the layout
  // pass in some browsers and produce a blank first page.
  setTimeout(() => printWindow.print(), 150);
}
