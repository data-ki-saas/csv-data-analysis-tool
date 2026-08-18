import type { Metadata } from "next";
import { DashboardSidebar } from "@/components/DashboardSidebar";

// Requires auth (see src/proxy.ts) — noindex since crawlers would just hit a redirect.
export const metadata: Metadata = {
  title: "Settings",
  description: "Configure light/dark mode and colour theme for the CSV Data Analysis Tool.",
  robots: { index: false, follow: false },
};

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <DashboardSidebar />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
