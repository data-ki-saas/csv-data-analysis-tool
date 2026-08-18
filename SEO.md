# SEO

Action list for search visibility, targeting three audiences deliberately, not just
generic BI terms: **YouTube/content creators** (animated charts, chart video export),
**businesses** wanting **data intelligence** (**csv to charts**, **interactive
charts**, SQL/dashboards), and users **embedding data analysis into presentations/PPT
decks** (white-labelled chart/PDF exports). See `CLAUDE.md`'s "SEO" section for how
the implementation works (metadata pattern, robots/sitemap).

## Done

- [x] Split the app so `/` is a public marketing/landing page and the authenticated
      app moved to `/dashboard` — previously everything but `/login`/`/signup`
      required auth, leaving nothing for search engines to index.
- [x] Site-wide metadata defaults in `frontend/src/app/layout.tsx` (title template,
      description, keywords, Open Graph, Twitter card, `metadataBase`).
- [x] Per-route `<title>`/description on `/`, `/login`, `/signup`, `/dashboard`,
      `/settings`.
- [x] `noindex` + `robots.ts` disallow on `/dashboard` and `/settings` (auth-gated,
      nothing for a crawler to see but a redirect).
- [x] `sitemap.ts` listing the public routes.
- [x] JSON-LD `SoftwareApplication` structured data on the marketing page.
- [x] Retargeted metadata/keywords and the marketing page's copy around three
      audiences (YouTube/content creators, businesses, PPT/presentation users) instead
      of generic "business intelligence" alone — see the home page's `AUDIENCES`
      section and updated `keywords` arrays in `page.tsx`/`layout.tsx`.
- [x] ~~`backend/scripts/generate_seo.py`~~ — removed. SEO metadata is now hand-written
      directly per route (see "To do" below) rather than LLM-drafted by a script.

## To do — recurring dev workflow

- [ ] **Every time a new frontend page is added**, write its metadata directly in
      that route's `layout.tsx` (or `page.tsx` if it's a server component with no
      page-specific interactivity) — match the style/keyword targeting already
      established in `layout.tsx`/`page.tsx`, and never claim a feature the page
      doesn't actually have. Add the route to `sitemap.ts` if public, or to
      `robots.ts`'s disallow list (plus `noindex` metadata) if it requires auth.
- [ ] Re-run Lighthouse / PageSpeed Insights against `/` after any change to the
      marketing page — it's the one page SEO performance actually depends on.

## To do — one-time / external setup (needs the user, not code)

These can't be done from the repo — they need access to accounts/consoles this
session doesn't have:

- [ ] Verify the production domain in **Google Search Console** and **Bing Webmaster
      Tools**, then submit `/sitemap.xml`.
- [ ] Decide on a custom domain — `csv-data-analysis-tool-one.vercel.app` works but a
      branded domain is stronger for SEO and trust; `metadataBase` in `layout.tsx` and
      the `SITE_URL` constants in `robots.ts`/`sitemap.ts` need updating if it changes.
- [ ] Add a real Open Graph image (`opengraph-image.png`/`.tsx` in `frontend/src/app/`)
      — link previews currently have no image. Next.js picks this up automatically
      via its file-convention.
- [ ] Set up analytics (e.g. Google Analytics, Plausible, or Vercel Analytics) to
      track organic traffic and keyword performance over time.
- [ ] Validate structured data with Google's [Rich Results
      Test](https://search.google.com/test/rich-results) once the site is live at its
      final domain.
- [ ] Content/backlinks: the site currently has exactly one indexable content page
      (`/`). Ranking for competitive terms like "business intelligence" typically
      needs more indexed content (e.g. a blog, use-case pages, comparison pages) and
      inbound links (directory listings like Product Hunt/G2, guest posts, etc.) —
      this is marketing work, not something to script.
