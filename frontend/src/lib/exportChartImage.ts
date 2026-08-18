import type { ChartBlock, FooterPreset, HeaderPreset } from "@/lib/api";
import { renderBrandedFooterHtml, renderBrandedHeaderHtml } from "@/lib/branding";
import { renderStaticChart } from "@/lib/staticChart";

// Reuses the same dependency-free static SVG renderer the standalone-HTML
// export and print path already use (see staticChart.ts) -- rasterizing that
// self-contained SVG via canvas is the whole trick here, no chart library
// screenshot API or server round-trip needed.

const HEADER_HEIGHT = 56;
const FOOTER_HEIGHT = 40;

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "chart";
}

/** Wraps the chart's own SVG with header/footer <foreignObject> bands inside
 * a taller combined SVG -- foreignObject can embed real (X)HTML inside SVG,
 * which canvas can then rasterize just like the chart SVG already is, so
 * branding a JPG needs no new dependency (no html2canvas) and no change to
 * the rasterize step below, just a taller/wrapped SVG going into it. */
function wrapWithBranding(
  chartSvg: string,
  width: number,
  chartHeight: number,
  header: HeaderPreset | null | undefined,
  footer: FooterPreset | null | undefined
): { svg: string; totalHeight: number } {
  const headerHeight = header ? HEADER_HEIGHT : 0;
  const footerHeight = footer ? FOOTER_HEIGHT : 0;
  const totalHeight = chartHeight + headerHeight + footerHeight;

  const headerBand = header
    ? `<foreignObject x="0" y="0" width="${width}" height="${headerHeight}">
         <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,Helvetica,sans-serif;text-align:center;">${renderBrandedHeaderHtml(header, "")}</div>
       </foreignObject>`
    : "";
  const footerBand = footer
    ? `<foreignObject x="0" y="${headerHeight + chartHeight}" width="${width}" height="${footerHeight}">
         <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial,Helvetica,sans-serif;text-align:center;font-size:11px;color:#64748b;">${renderBrandedFooterHtml(footer, "")}</div>
       </foreignObject>`
    : "";

  const svg = `<svg width="${width}" height="${totalHeight}" xmlns="http://www.w3.org/2000/svg">${headerBand}<g transform="translate(0, ${headerHeight})">${chartSvg}</g>${footerBand}</svg>`;
  return { svg, totalHeight };
}

export async function downloadChartAsJpg(
  block: ChartBlock,
  header?: HeaderPreset | null,
  footer?: FooterPreset | null,
  width = 960,
  height = 480
): Promise<void> {
  const chartSvg = renderStaticChart(block, width, height);
  const { svg, totalHeight } = wrapWithBranding(chartSvg, width, height, header, footer);
  const svgUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));

  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Failed to render chart image"));
      img.src = svgUrl;
    });

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = totalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas rendering is not supported in this browser");

    // JPG has no transparency -- paint a white background first, matching the
    // light surface the SVG's colors/strokes are tuned to sit on.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, totalHeight);
    ctx.drawImage(image, 0, 0, width, totalHeight);

    const jpgBlob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!jpgBlob) throw new Error("Failed to encode this chart as a JPG");

    const downloadUrl = URL.createObjectURL(jpgBlob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${slugify(block.title)}.jpg`;
    link.click();
    URL.revokeObjectURL(downloadUrl);
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
