import type { MetadataRoute } from "next";

const SITE_URL = "https://csv-data-analysis-tool-one.vercel.app";

// Only public, indexable routes belong here — /dashboard and /settings
// require auth and are excluded from robots.ts too.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE_URL, changeFrequency: "monthly", priority: 1 },
    { url: `${SITE_URL}/login`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/signup`, changeFrequency: "yearly", priority: 0.5 },
  ];
}
