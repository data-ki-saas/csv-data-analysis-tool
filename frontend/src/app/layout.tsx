import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_URL = "https://csv-data-analysis-tool-one.vercel.app";

// Site-wide defaults. Route-specific overrides live in each route's layout.tsx
// (hand-written directly per route -- see CLAUDE.md's SEO section). Keywords/
// descriptions here target three audiences deliberately, not just "business
// intelligence": YouTube/content creators (animated charts, video export),
// businesses wanting data intelligence (SQL, dashboards), and users embedding
// data analysis into presentations/PPT decks (white-labelled exports).
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "CSV Data Analysis Tool — Business Intelligence from CSV Files",
    template: "%s — CSV Data Analysis Tool",
  },
  description:
    "Turn any CSV into business intelligence, presentation-ready charts, and animated YouTube-ready chart " +
    "videos. Upload a file, run SQL, and export interactive line graphs and dashboards — no data warehouse required.",
  keywords: [
    "data intelligence",
    "business intelligence",
    "csv to charts",
    "interactive charts",
    "csv data analysis",
    "sql query tool",
    "data visualization",
    "youtube chart maker",
    "animated charts for youtube",
    "embed charts in powerpoint",
    "presentation ready charts",
  ],
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "CSV Data Analysis Tool",
    title: "CSV Data Analysis Tool — Business Intelligence from CSV Files",
    description:
      "Turn any CSV into business intelligence, animated YouTube-ready chart videos, and presentation-ready dashboards.",
  },
  twitter: {
    card: "summary",
    title: "CSV Data Analysis Tool — Business Intelligence from CSV Files",
    description:
      "Turn any CSV into business intelligence, animated YouTube-ready chart videos, and presentation-ready dashboards.",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies the saved theme before paint, so there's no flash of the
            default theme. Keep the storage key/shape in sync with
            src/lib/theme.ts and theme-provider.tsx. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var raw=localStorage.getItem("csv-tool-theme");var mode="system",colorTheme="winter";if(raw){var parsed=JSON.parse(raw);mode=parsed.mode||mode;colorTheme=parsed.colorTheme||colorTheme;}var dark=mode==="dark"||(mode!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);var root=document.documentElement;root.dataset.colorTheme=colorTheme;root.classList.toggle("dark",dark);}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
