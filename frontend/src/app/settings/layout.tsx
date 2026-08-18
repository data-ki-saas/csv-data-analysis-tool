import type { Metadata } from "next";

// Requires auth (see src/proxy.ts) — noindex since crawlers would just hit a redirect.
export const metadata: Metadata = {
  title: "Settings",
  description: "Configure light/dark mode and colour theme for the CSV Data Analysis Tool.",
  robots: { index: false, follow: false },
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
