# Elite Marcom Website — working notes

Static multi-page site (`public/` webroot, vanilla JS namespaced under `window.EM`)
plus a FastAPI backend (`server/`). Tests: `python -m pytest tests/` (must stay green).
Local run: `START WEBSITE.bat` (Windows) / `uvicorn server.main:app --port 8847`.
Secrets live only in the git-ignored `.env` (see `.env.example`) — never commit them.

## Jasani supplier integration — read this first

**Before changing anything under `server/jasani.py` or the Corporate Gifts pages,
review `docs/jasani-api-reference.md`** (the complete Jasani API technical
documentation). Non-negotiable rules from it:

- **One supplier account per market**: `JASANI_API_TOKEN` is KSA,
  `JASANI_API_TOKEN_UAE` is UAE. Never fall back from one to the other — a
  single token carrying both markets means ten calls a day on one account and a
  403 that parks it.
- At most **5 primary GET calls per market per day** (products / price / stock),
  measured in that market's **own local time** (`JASANI_UTC_OFFSET`: KSA +3,
  UAE +4). Branding endpoints are outside the limit. Per-market counters live in
  `runtime/cache/supplier-budget.json`; never retry a 403.
  Automatic work stops at `EM_SUPPLIER_AUTO_BUDGET` (default 4) so the remaining
  call stays available for a manual sync by an owner or admin —
  `_budget_ok(market, manual=True)`, reached only through `force_refresh`. A call
  that never got an HTTP response is refunded; anything the supplier served counts.
  One in-flight sync per market (`_refresh_lock`), so a double-click or a burst
  of visitors cannot spend two calls on the same work.
- The four automatic calls are **scheduled, not demand-driven**
  (`JASANI_SCHEDULE`): products at 00:00, stock at 08:00, 13:00 and 18:00 local.
  Each slot is exactly one call and runs once per local day, marked in the budget
  file whether it succeeded or failed — a failing hour must not retry all day.
  `get_catalog` never triggers a refresh; it serves the snapshot so a page load
  never waits on the supplier.
- `EM_SUPPLIER_TIMEOUT_S` (default 60) is the read timeout for supplier calls.
  The UAE products feed is ~4 MB and measured 24.2s from the production VPS, so
  a 20s timeout aborted valid replies. A timed-out call is refunded, not spent.
- `EM_SUPPLIER_MAX_BYTES` (default 8388608 = 8 MB) caps an upstream response.
  The UAE products feed is ~4.17 MB, so keep headroom above the live size — an
  over-limit response is rejected and reads as a supplier failure. Never remove
  the cap: it is what stops an endless upstream stream.
- Upstream refresh cadence: products ~daily, stock ~twice daily
  (`EM_PRODUCT_REFRESH_HOURS` / `EM_STOCK_REFRESH_HOURS`). The website reads the
  cached snapshot; serve last-known-good on any supplier failure.
- `id` = supplier variant id; `default_code` = SKU; `parent_id` = template id,
  meaningful for grouping **only when `configurable` is true**.
- Stock availability comes from **`net_available_qty` only** — never `total_qty`,
  never add `blocked_qty`. `blocked_qty` and all supplier prices are internal-only:
  keep them out of every public payload, page, and log.
- `color_options` and `alternative_products` carry **template** ids — resolve them
  against the catalog before linking; never build URLs from raw supplier ids.
- Token stays server-side (`JASANI_API_TOKEN`), never in browser code, URLs shown
  to users, or logs. Host allowlist: `www.giftsksa.com` (KSA), `www.jasani.ae` (UAE);
  never mix markets.
- No public prices, no online payment, no automatic supplier orders. The Order API
  needs separate written authorization — do not wire it to the public site.
- Printing manuals: `parent_id` is only a CANDIDATE manual id for the supplier's
  `/preview_product?product_id=...` PDF. Candidates are validated server-side
  (signature, page count, 10 MB cap) and cached 24h — valid and failed verdicts
  alike — in `runtime/cache/manuals/`. Customers download only via the
  `/api/giveaways/manual` proxy; never link to a Jasani URL. Full guide:
  `docs/jasani-printing-manual-guide.md` (drawing tools, custom PDFs and
  branding-price enrichment are future phases from that guide).

## Site conventions

- **Cache busting is mandatory, not optional.** Production serves CSS/JS by
  path (no hashed filenames), so a changed asset only reaches returning
  visitors when its `?v=` changes. Every time you edit a `.css` or `.js` file,
  before the task is done:
  1. Bump `?v=` for that asset — and only that asset; assets you did not
     change keep their version.
  2. Update **every** page that references it — `public/*.html` *and*
     `server/adminui/*.html` (`app.html`, `login.html`). Shared assets like
     `styles.css`, `site.js`, `theme-init.js` and `insights.js` appear on a
     dozen pages; missing one leaves that page on the stale copy.
  3. Grep the repo for the *old* value and confirm nothing still references it.
  4. Run `python -m pytest tests/test_asset_versions.py` — it fails if one
     asset carries two different versions, if a local CSS/JS reference has no
     `?v=` at all, or if a referenced file is missing from disk.
  `runtime/published/site/` needs no hand-editing: it is baked from
  `public/` by **Publish site**, so bumping the sources and publishing carries
  the new versions through. `/theme-custom.css` is server-rendered with
  `Cache-Control: no-cache` and is exempt.
- **What the visual editor can change, and where it is stored.** Three layers,
  in this order at bake time: `design.apply_to_page` (sections → text → attrs →
  `<style id="em-design">`), then the keyed content model, then nav/social
  injection. Which layer owns an edit:
  - Text on an element **with** a `data-em` key → the content model
    (`content` table, per language, shared site-wide for `_global` keys).
  - Text on any **other** element → `design` doc, `elements[path].text`,
    sanitized with `content.sanitize_rich` (bold/italic/link/list/`<br>` only).
    The bridge offers this only for elements whose children are all inline —
    editing a wrapper must never delete the cards inside it. If a container and
    something inside it both carry text, the container wins: applying both
    would splice the inner edit into offsets the outer one already moved.
  - New blocks → `sections.added = [{id: "aN", template}]`, rendered from
    `server/blocks.py`. Ids are `s…` for sections already in the page and `a…`
    for added ones; both are valid in `order` / `removed` / `duplicated`.
    **Templates are ours, never admin input** — an admin places a block and
    edits its text, and that text goes through the same whitelist.
- **Pages created in the panel** live in the `custom_pages` table, not in git.
  Their HTML is generated by `blocks.page_shell()` from `public/about.html` at
  every bake, deliberately: a hand-kept shell would drift the first time a
  shared asset changed. They publish, localize, sitemap and back up like any
  built-in page; `published_file()` only hits the database for an `.html` miss,
  so asset requests stay allocation-cheap. Built-in pages cannot be deleted.
- Footer social icons come from `social.*` settings (https:// only, validated
  twice — on save and again in `blocks.render_social`) and are baked in, so a
  new link reaches the site at the next **Publish site**.
- Corporate Gifts UI: catalog + product page share variant grouping via
  `EM.giftKey` (`public/js/site.js`); request lists live in localStorage
  (`em-giveaway-request`, per market, max 50 items).
- After a code change that touches `public/*.html`, the admin must press
  **Publish site** once: published snapshots in `runtime/published/site/` are
  served ahead of `public/`, so a stale bake would hide new markup/scripts.
  The Pages screen detects this and says so.
- Site Insights is first-party and cookieless: no raw IP or user-agent is
  stored, visitor keys use a salt that rotates daily, and GA4 only loads when
  an admin sets a measurement id (`analytics.ga4Id`).
- Transactional email goes through Resend (`server/mailer.py`). `RESEND_API_KEY`
  is environment-only — never in the admin DB, an API response or browser code.
  Sender addresses are restricted to domains in `EM_MAIL_SENDER_DOMAINS`
  (default `mail.elitemarcom.com`). Routing, on/off switches, subjects and the
  six customer templates are edited in the admin Email screen. Sending is a
  durable outbox: the request only enqueues (unique per reference+kind), and a
  startup worker drains it with backoff — never a post-response thread.
- Backups (Operations) carry content, design, settings, rentals and media —
  never customer submissions, which stay encrypted with their own retention.
- Arabic publishes a full RTL edition under `/ar/` when `site.languages`
  includes `ar`; both editions are baked by the same publish action.
- Workflow: develop on `claude/markdown-file-instructions-y9jr50`, push, and
  fast-forward `main` (the user pulls from `main` to test locally).
