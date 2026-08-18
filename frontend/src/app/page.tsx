import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "CSV Data Analysis Tool — Business Intelligence from CSV Files",
  description:
    "Turn any CSV into business intelligence, presentation-ready charts, and animated YouTube-ready chart " +
    "videos. Upload a file, run SQL, and export interactive line graphs, dashboards, and PPT-ready visuals — " +
    "no data warehouse required.",
  keywords: [
    "youtube chart maker",
    "animated charts for youtube",
    "interactive line graphs",
    "data visualization for content creators",
    "business intelligence tool",
    "csv data intelligence",
    "embed charts in powerpoint",
    "presentation ready charts",
    "white label pdf export",
    "chart mp4 export",
  ],
  alternates: { canonical: "/" },
};

const AUDIENCES = [
  {
    title: "For YouTube & content creators",
    body: "Turn a spreadsheet into rich, animated charts and line diagrams your audience actually watches — export as MP4 clips ready to drop straight into your next video.",
  },
  {
    title: "For businesses seeking data intelligence",
    body: "Upload a CSV and get real business intelligence in minutes — instant schema, SQL querying, and interactive dashboards that answer the questions your spreadsheet can't.",
  },
  {
    title: "For presentations & PPT decks",
    body: "Export polished, white-labelled charts and dashboards ready to paste straight into your next PowerPoint or client deck — no screenshots, no redesigning from scratch.",
  },
];

const FEATURES = [
  {
    title: "Instant data intelligence",
    body: "Upload a CSV with thousands to millions of rows and get an instant schema, row count, and preview — no setup, no data warehouse.",
  },
  {
    title: "SQL for business intelligence",
    body: "Query your data directly with SQL, powered by DuckDB, to answer real business intelligence questions without exporting to another tool.",
  },
  {
    title: "CSV to charts, instantly",
    body: "Go from raw CSV to interactive charts in a few clicks — explore trends and outliers visually as soon as your data is uploaded.",
  },
  {
    title: "Built for your data, securely",
    body: "Every dataset is scoped to your account, backed by Supabase auth, so your data intelligence stays private to you.",
  },
  {
    title: "Chart videos for YouTube & social",
    body: "Download your charts and graphs as animated MP4 clips — ready-made b-roll and data-story visuals for YouTube, Shorts, and social content.",
  },
  {
    title: "White-labelled PDFs & dashboards",
    body: "Export polished, white-labelled PDF reports and interactive dashboards to share with clients or your team, with no third-party branding attached.",
  },
];

const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "CSV Data Analysis Tool",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "Upload a CSV to get instant business intelligence, animated chart videos for YouTube and content " +
    "creators, and white-labelled charts and PDF reports ready to embed in presentations.",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
};

export default function MarketingPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      <main className="mx-auto flex w-full max-w-4xl flex-col gap-16 px-4 py-16">
        <header className="flex items-center justify-between">
          <span className="text-lg font-semibold">CSV Data Analysis Tool</span>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/login" className="underline">
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded bg-accent px-3 py-1.5 text-accent-foreground"
            >
              Sign up free
            </Link>
          </nav>
        </header>

        <section className="flex flex-col gap-6 text-center">
          <h1 className="text-4xl font-semibold sm:text-5xl">
            Turn any CSV into charts, insights, and content
          </h1>
          <p className="mx-auto max-w-2xl text-lg opacity-80">
            Upload a CSV and get instant business intelligence, interactive charts and line
            diagrams ready to embed in your next presentation, and animated chart videos ready
            for your next YouTube upload — no data warehouse, no video editor, no redesigning
            from scratch.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/signup"
              className="rounded bg-accent px-5 py-2.5 font-medium text-accent-foreground"
            >
              Get started free
            </Link>
            <Link href="/login" className="rounded border border-border px-5 py-2.5 font-medium">
              Sign in
            </Link>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {AUDIENCES.map((audience) => (
            <div key={audience.title} className="flex flex-col gap-2 rounded border border-border bg-accent/5 p-5">
              <h2 className="font-medium">{audience.title}</h2>
              <p className="text-sm opacity-80">{audience.body}</p>
            </div>
          ))}
        </section>

        <section className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="flex flex-col gap-2 rounded border border-border p-5">
              <h2 className="font-medium">{feature.title}</h2>
              <p className="text-sm opacity-80">{feature.body}</p>
            </div>
          ))}
        </section>
      </main>
    </>
  );
}
