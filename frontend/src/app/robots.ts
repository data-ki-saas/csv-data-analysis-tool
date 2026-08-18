import type { MetadataRoute } from "next";

const SITE_URL = "https://csv-data-analysis-tool-one.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Everything past these requires auth (see src/proxy.ts) — an
      // unauthenticated crawler would just be bounced to /login anyway.
      disallow: ["/dashboard", "/settings"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
