import type { Metadata } from "next";

// Requires auth (see src/proxy.ts) — noindex since crawlers would just hit a redirect.
export const metadata: Metadata = {
  title: "Dashboard",
  description: "Upload CSV files and manage your datasets in the CSV Data Analysis Tool.",
  robots: { index: false, follow: false },
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
