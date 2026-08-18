import type { MetadataRoute } from "next";

const SITE_URL = "https://csv-data-analysis-tool-one.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // /dashboard and /settings require auth (see src/proxy.ts) — an
      // unauthenticated crawler would just be bounced to /login anyway.
      // /share is public and reachable, but it's arbitrary user-generated
      // content, not canonical marketing content, so it's kept out of the
      // index too (see share/[token]/layout.tsx's matching noindex).
      disallow: ["/dashboard", "/settings", "/share"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
