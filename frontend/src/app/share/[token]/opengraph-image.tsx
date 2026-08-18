import { ImageResponse } from "next/og";
import { getPublicChartShareServer, type ChartBlock } from "@/lib/api";
import { renderStaticChart } from "@/lib/staticChart";

export const alt = "Shared chart";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Renders the actual shared chart as the thumbnail rather than a generic
// card -- reuses staticChart.ts's dependency-free SVG renderer (the same one
// behind the standalone-HTML export and the per-chart JPG/PDF download,
// see CLAUDE.md) since it's already a pure string-generating function with
// no DOM dependency, so it works here in a server-rendered image route the
// same way it does client-side. The SVG is embedded as an <img> data URI --
// satori (which ImageResponse uses under the hood) rasterizes an
// image/svg+xml data URI directly, so this needed no extra conversion step.
export default async function Image({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const share = await getPublicChartShareServer(token);

  if (!share) {
    return new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#0f172a",
            color: "#fff",
            fontSize: 48,
            fontFamily: "Arial, Helvetica, sans-serif",
          }}
        >
          Shared Chart
        </div>
      ),
      size
    );
  }

  const block: ChartBlock = {
    type: "chart",
    id: token,
    title: share.title,
    chart_type: share.chart_type,
    partition_type: share.partition_type,
    column: share.column,
    result: share.result,
  };
  const chartSvg = renderStaticChart(block, 1000, 420);
  const chartDataUri = `data:image/svg+xml;base64,${Buffer.from(chartSvg).toString("base64")}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: "#ffffff",
          padding: "48px",
          fontFamily: "Arial, Helvetica, sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 22, color: "#64748b" }}>CSV Data Analysis Tool</div>
        <div
          style={{
            display: "flex",
            fontSize: 44,
            fontWeight: 700,
            color: "#0f172a",
            marginTop: 8,
            maxWidth: "100%",
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          }}
        >
          {share.dataset_name ?? "Shared Chart"}
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 26,
            color: "#334155",
            marginTop: 6,
            maxWidth: "100%",
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          }}
        >
          {share.title}
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", marginTop: 16 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={chartDataUri} width={1000} height={420} alt="" />
        </div>
      </div>
    ),
    size
  );
}
