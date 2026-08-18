import type { ChartBlock } from "@/lib/api";
import { renderStaticChart } from "@/lib/staticChart";

// Reuses the same dependency-free static SVG renderer the standalone-HTML
// export and print path already use (see staticChart.ts) -- rasterizing that
// self-contained SVG via canvas is the whole trick here, no chart library
// screenshot API or server round-trip needed.

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "chart";
}

export async function downloadChartAsJpg(block: ChartBlock, width = 960, height = 480): Promise<void> {
  const svg = renderStaticChart(block, width, height);
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
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas rendering is not supported in this browser");

    // JPG has no transparency -- paint a white background first, matching the
    // light surface the SVG's colors/strokes are tuned to sit on.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0, width, height);

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
