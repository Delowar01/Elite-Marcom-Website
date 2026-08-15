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
  (`JASANI_SCHEDULE`): products at 00:00, **price at 01:00**, stock at 08:00 and
  18:00 local. Each slot is exactly one call and runs once per local day, marked
  in the budget file whether it succeeded or failed — a failing hour must not
  retry all day. Four slots is exactly `SUPPLIER_AUTO_BUDGET`: adding one
  without raising that spends the reserved manual call.
  `get_catalog` never triggers a refresh; it serves the snapshot so a page load
  never waits on the supplier.
- **Price is its own primary call.** `list_price` is *not* in the Product API
  (reference §12 lists no price field); it comes from the **Price API**,
  `GET https://{host}/products/price/{token}` (§22), with `id`, `default_code`,
  `currency`, `list_price`, `retail_price`. Join on **`id` only** — the two
  markets share product codes but never share ids, so matching on
  `default_code` is how a KSA price lands on a UAE product; the code is kept
  for mismatch reporting and nothing else. Never try to read the price off the
  products feed again: that is how 1,778 KSA and 2,573 UAE products sat at zero
  prices through any number of syncs.
- **One price, called Price.** `list_price` — our own supplier price, excluding
  VAT — is the only price the panel keeps, stored as `internal[id]["price"]`.
  The supplier's `retail_price` is a *suggested selling* price, not ours, and is
  deliberately dropped at `normalize_price`: it is not stored, not exported, not
  shown, and `_lift_internal` strips it (`_DEAD_INTERNAL_KEYS`) from snapshots
  that still carry it. Do not reintroduce it as a second column — a figure that
  is not ours sitting beside one that is only invites the wrong number into a
  quote. `_price_of` reads a pre-rename snapshot's `wholesale` key so a live
  cache keeps working until its next write.
- Manual sync targets (`force_refresh`, `REFRESH_COST`): `products`, `prices`,
  `stock` — one call each — and `full` = all three. A multi-call target checks
  `_budget_left` **before the first request**, so a full sync never spends one
  call and then dies half-applied. A products refresh carries forward cached
  stock, and a failed price leg leaves the last-known-good prices in place —
  `_lift_internal` merges each write into the stored map rather than replacing
  it.
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
- **Internal-only supplier fields.** `blocked_qty` and `list_price` are
  captured but never ride on a product: the stock and price merges park them
  under `_INT_KEY`, and `_write_cache` — the single choke point that
  persists a snapshot — lifts them into a sibling `internal` map keyed by
  product id. A caller that hands the product list to a public response
  therefore cannot leak what the list never holds. Read them with
  `internal_map(market)`; they reach the admin only behind `jasani.prices`
  (owner/admin), and never a customer document — the product-sheet PDF is
  asserted price-free in the tests.
- **What the website shows** is decided in `get_catalog`, the one function every
  public path already goes through, so the catalogue, stock feed, product page,
  request validation and the notify-me flow can never disagree. Two switches,
  both behind `jasani.visibility`: a per-market `jasani.hideZeroStock.<market>`
  setting, and the `jasani_hidden` table for items taken off by hand. The
  zero-stock rule ships **off** — turning it on removes items from the live site,
  so it is an explicit decision, and it also removes the page a customer would
  use to ask for a back-in-stock notification.
- Low stock is `EM_LOW_STOCK_THRESHOLD` (default 20) — the same figure
  `public/js/giveaways.js` uses. Two thresholds would disagree in public.
- Printing manuals: `parent_id` is only a CANDIDATE manual id for the supplier's
  `/preview_product?product_id=...` PDF. Candidates are validated server-side
  (signature, page count, 10 MB cap) and cached 24h — valid and failed verdicts
  alike — in `runtime/cache/manuals/`. Customers download only via the
  `/api/giveaways/manual` proxy; never link to a Jasani URL. Full guide:
  `docs/jasani-printing-manual-guide.md` (drawing tools, custom PDFs and
  branding-price enrichment are future phases from that guide).
- **Product videos come from the supplier's PUBLIC page, not the API**
  (`server/supplier_video.py`). The Product API returns `videos: []` for items
  that plainly have one — ITGL 1291 is id 24246 / `parentId` 29453, and
  `https://www.jasani.ae/shop/…-29453` embeds `youtube.com/embed/lFhAiGLjoMo`.
  `parentId` **is** that public page id. Reading a webpage is not an API call:
  no token, no primary endpoint, nothing charged to the five-a-day budget — do
  not route it through `_fetch`. It is lazy (only a product page a customer
  opened, only after that page has rendered — the catalogue never asks), paced
  (`VIDEO_CONCURRENCY`, `VIDEO_MIN_INTERVAL_S`) and cached per **template**,
  positive *and* negative: without the negative cache every video-less product
  would be re-fetched on every visit, which is the crawl this must never
  become. Only a validated 11-character YouTube id leaves the module; supplier
  HTML is parsed and discarded.
- **A video's poster is a gallery photograph too.** Odoo keeps it as a
  `product.image` record, so the feed sends it as an ordinary picture and the
  same frame appears twice — once playable, once not. The two URLs
  (`/web/image/product.image/8803/…` and `i.ytimg.com/vi/{id}/…`) share
  nothing, so they are matched by **supplier record id**, never by URL and
  never by gallery position: the page's own markup pairs a record with the
  embed (smallest element containing both), or, failing that, one video plus
  exactly one of our records the page never shows as a photograph. Anything
  less certain leaves every image in place — `supplierPoster` stays empty and
  the browser removes nothing. Showing one picture twice is a blemish;
  deleting the wrong one loses a product photo.

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
