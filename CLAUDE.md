# Elite Marcom Website — working notes

Static multi-page site (`public/` webroot, vanilla JS namespaced under `window.EM`)
plus a FastAPI backend (`server/`). Tests: `python -m pytest tests/` (must stay green).
Local run: `START WEBSITE.bat` (Windows) / `uvicorn server.main:app --port 8847`.
Secrets live only in the git-ignored `.env` (see `.env.example`) — never commit them.

## Jasani supplier integration — read this first

**Before changing anything under `server/jasani.py` or the Corporate Gifts pages,
review `docs/jasani-api-reference.md`** (the complete Jasani API technical
documentation). Non-negotiable rules from it:

- At most **5 primary GET calls per day** (products / price / stock), measured in
  **UAE time**. Branding endpoints are outside the limit. The budget counter is
  persisted in `runtime/cache/supplier-budget.json`; never retry a 403.
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

- Bump the `?v=` query on any changed CSS/JS asset in every referencing HTML page.
- Corporate Gifts UI: catalog + product page share variant grouping via
  `EM.giftKey` (`public/js/site.js`); request lists live in localStorage
  (`em-giveaway-request`, per market, max 50 items).
- Workflow: develop on `claude/markdown-file-instructions-y9jr50`, push, and
  fast-forward `main` (the user pulls from `main` to test locally).
