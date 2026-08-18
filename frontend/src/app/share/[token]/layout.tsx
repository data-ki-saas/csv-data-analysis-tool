import type { Metadata } from "next";
import { getPublicChartShareServer } from "@/lib/api";

// Public (no auth) but not canonical marketing content -- an arbitrary
// user-generated chart snapshot, not something worth indexing. noindex here
// plus /share in robots.ts's disallow list. That only tells search crawlers
// not to *index* it -- link-preview scrapers (Slack, iMessage, Twitter/X,
// Discord) don't obey robots.txt, so title/description/image still need to
// be real per-share metadata for the preview to look right when a link is
// pasted somewhere. Per the share page's own visual hierarchy (dataset name
// above the chart's own title), og:title mirrors the dataset name and
// og:description mirrors the chart's title -- the thumbnail comes from the
// sibling opengraph-image.tsx route, which Next wires up automatically for
// this same route segment.
export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const share = await getPublicChartShareServer(token);

  const name = share?.dataset_name ?? "Shared Chart";
  const description = share?.title ?? "A chart shared from CSV Data Analysis Tool.";

  return {
    title: name,
    description,
    robots: { index: false, follow: false },
    openGraph: {
      title: name,
      description,
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: name,
      description,
    },
  };
}

export default function SharedChartLayout({ children }: { children: React.ReactNode }) {
  return children;
}
