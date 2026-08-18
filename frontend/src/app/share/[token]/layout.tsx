import type { Metadata } from "next";

// Public (no auth) but not canonical marketing content -- an arbitrary
// user-generated chart snapshot, not something worth indexing. noindex here
// plus /share in robots.ts's disallow list.
export const metadata: Metadata = {
  title: "Shared Chart",
  description: "A chart shared from CSV Data Analysis Tool.",
  robots: { index: false, follow: false },
};

export default function SharedChartLayout({ children }: { children: React.ReactNode }) {
  return children;
}
