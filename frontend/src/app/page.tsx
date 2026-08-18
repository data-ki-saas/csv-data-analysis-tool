import type { Metadata } from "next";
import Link from "next/link";

// Generated with backend/scripts/generate_seo.py --route /
export const metadata: Metadata = {
  title: "CSV Data Analysis Tool — Business Intelligence from CSV Files",
  description:
    "Turn any CSV into business intelligence in seconds. Upload a file, get an instant schema and row-count preview, run SQL, and turn your csv to charts — interactive charts, no data warehouse required.",
  alternates: { canonical: "/" },
};

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
];

const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "CSV Data Analysis Tool",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "Upload a CSV to get instant business intelligence: schema preview, SQL querying, and interactive charts.",
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
            Turn any CSV into business intelligence
          </h1>
          <p className="mx-auto max-w-2xl text-lg opacity-80">
            Upload a CSV, get an instant schema and row-count preview, run SQL against it,
            and turn the results into interactive charts — all without standing up a data
            warehouse.
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
