# Elite Marcom — Corporate Website

Production-ready, ultra-premium corporate website for **Elite Marcom** — a global
experiential marketing, exhibitions, events, production, branding and
creative-solutions company operating from **Riyadh** and **Dubai** with
worldwide delivery.

Eight public pages + Privacy Notice, dark/light themes, an interactive 3D
exhibition-stand hero (Three.js + supplied GLB), a live Giveaways catalog with a
secure supplier integration, a Rental request workflow, Careers with encrypted
CV applications, and a hardened FastAPI backend. A private admin panel at
`/admin` (password + mandatory 2FA) edits the site, but the git-tracked design
in `public/` always stays the source of truth.

## Quick start (local)

```bash
./install.sh          # one-time: creates .venv and installs pinned dependencies
./start-local.sh      # starts http://127.0.0.1:8847/
```

Windows: run `INSTALL DEPENDENCIES.bat` once, then `START WEBSITE.bat`.

Installation and startup are separate on purpose — the start scripts reuse the
existing environment and never reinstall dependencies.

## Project layout

```
public/                  strict public webroot (the only directory ever served)
  index/about/services/projects/giveaways/rental/careers/contact/privacy.html
                                       served at /about, /services, … — the
                                       `clean_urls` middleware in server/main.py
                                       maps a slug onto its file and 301s the
                                       old .html address to the new one
  styles.css home.css pages.css        design system + page styles
  js/                                  site, hero-3d, forms, page scripts
  vendor/three/                        Three.js 0.167.1 + GLTFLoader (vendored)
  assets/                              logo, WebP imagery, GLB, career posters
  data/                                preview/fallback catalogs (non-canonical)
server/                  FastAPI backend (config, security, storage, jasani, main)
server/data/             canonical rental inventory + career jobs seed
runtime/                 private storage (SQLite, encrypted CVs, caches) — never served
tests/                   API / security / parser tests (pytest)
.env.example             placeholders only — copy to .env and fill
```

## Backend

Python 3.11+ / FastAPI / Pydantic v2 / httpx / defusedxml / cryptography.

Public endpoints only: `/healthz`, `/api/security/*`, `/api/careers/*`,
`/api/contact/enquiries`, `/api/rentals/*`, `/api/giveaways/*`. Swagger/ReDoc
are disabled in production.

Security highlights:

- exact Origin validation + explicit CORS allowlist for state-changing requests
- short-lived, one-time, HMAC-signed form challenges bound to form + visitor
- zero-size honeypot field, per-endpoint rate limits, global concurrency cap
- Cloudflare Turnstile verification (required in production, optional locally)
- IP addresses stored only as keyed hashes (dedicated secret), never plaintext
- submissions and CVs encrypted at rest with AES-GCM; distinct secrets for
  data encryption, token signing and IP hashing
- CV rules enforced in UI **and** backend: PDF only, ≤5 MB, valid signature and
  EOF, unencrypted, 1–100 pages; clamd malware scanning is mandatory in
  production and fails closed
- daily retention cleanup: contact/giveaway/rental 180 days, careers/CVs
  90 days, catalog cache 30 days
- strict CSP, HSTS (production), nosniff, frame-ancestors 'none', minimal
  Permissions-Policy
- production **fails closed** if secrets, https origins, Turnstile or a
  writable private runtime path are missing

### Giveaways supplier (Jasani)

The supplier is contacted **only from the backend** using `JASANI_API_TOKEN`.
Allowed hosts are exactly `www.giftsksa.com` (KSA) and `www.jasani.ae` (UAE);
no redirects, no environment proxies, 5 MB response cap, hardened XML/JSON
parsing, per-day request budget, 60-minute product/stock cache and 24-hour
capped branding cache under `runtime/cache/`. If neither live nor cached data
exists the API returns a controlled `503` and the frontend falls back to the
local preview catalog, clearly labelled **Preview data**. The token never
appears in HTML, JS, URLs sent to the browser, logs or errors.

## Production notes

Run behind a maintained HTTPS reverse proxy (Caddy/Nginx). Bind the app
privately (`EM_HOST=127.0.0.1`), set `EM_TRUSTED_PROXIES` to the proxy's IP so
forwarded client IPs are honoured only from it, and keep `runtime/` on a
private persistent volume. Set `EM_ENV=production` — startup aborts unless all
required configuration is present. Back up `runtime/` (encrypted data) and the
encryption keys separately.

Supplier calls are slow and large: the UAE products feed is about 4 MB and was
measured from the production VPS at 24.2 seconds, almost all of it before the
first byte. `EM_SUPPLIER_TIMEOUT_S` (default 60) is the read timeout for those
calls — set it well above the slowest feed, because a timeout aborts a reply
that was on its way. Nothing is charged against the daily allowance for it: a
call that never got an HTTP response is refunded.

`EM_SUPPLIER_MAX_BYTES` (default 8388608, 8 MB) is the hard ceiling on an
upstream response. The UAE products feed is about 4.17 MB today, so the cap
needs headroom for the catalogue to grow: a response over the limit is rejected
outright, which looks like a supplier failure rather than a size problem. Keep
it strict — it is what stops a hostile or broken upstream streaming without end.

### Editing the site from the admin panel

The **Visual editor** edits any text on a page, not only the fields the design
was tagged with: click a button label, a card title, a list item or a caption
and its wording is editable in the panel on the right. Text on a tagged element
is stored in the content model (and can be translated per language); text on
anything else is stored as an override against that element's stable path.
Either way the git-tracked HTML is never modified — publishing bakes drafts
into `runtime/published/site/`, and **Unpublish** puts the original design back.

**Sections** in the editor adds ready-made blocks (heading and paragraph, text
beside an image, three cards, numbered steps, a numbers row, a checklist, a
quote, a call to action, a wide image banner and a blank block), and reorders,
hides, duplicates or deletes them. The block markup ships with the site, so an
added block inherits the site's own typography, spacing and animations.

**Pages & SEO → New page** creates a page. It is generated from the live site
shell, so it carries the same header, footer, theme and scripts by
construction; give it a name and an address, and it is editable, previewable,
translatable and publishable like any built-in page, optionally listed in the
site menus. Built-in pages cannot be deleted — hide their sections instead.

Footer **social links** are set in Settings, one https:// address per network.
Empty fields render no icon at all, and the row reaches the live site at the
next publish.

### Jasani items

**Jasani items** lists everything in the cached supplier snapshot for a market —
SKU, name, brand, colour, wholesale and retail price, available, incoming and
booked stock, and whether the item is on the website. Opening it never calls
Jasani, so it costs none of the market's five daily calls. Search takes several
terms at once (press Enter or type a comma; a pasted column of SKUs becomes one
term per line) and matches any of them; filters cover stock status, brand,
colour, category, website state and a price band on either price. Every list can
be exported as PDF, Excel or CSV, either as filtered or as the whole snapshot.

Clicking a row opens the item's own page: image gallery with slide and zoom,
stock and price facts, description and full specifications. **Export as PDF**
there produces a branded one-page product sheet for a customer — deliberately
without any price, because supplier prices are internal.

Supplier prices and booked stock (`list_price`, `retail_price`, `blocked_qty`)
are internal by supplier policy. They are stored beside the catalogue rather
than on it, are visible only to roles with `jasani.prices` (owner and admin),
and never appear in a public response or a customer document.

**Jasani console → What the website shows** decides what the public Corporate
Gifts pages sell: a per-market rule that hides items with no available stock
(off by default — turning it on also removes the page customers use to ask for a
back-in-stock notification), and a search to hide or restore one item by hand.
Both need the `jasani.visibility` permission.

## Tests

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests -q
```

## Supplied-asset notes (honest inventory)

- The interactive hero uses the supplied `Elite_stand_glb.glb`, mapped to
  `public/assets/aces-exhibition.glb` as specified.
- Site imagery (portfolio, services, about, catalogs) was extracted from the
  supplied *Elite Marcom Company Profile* PDF and converted to WebP.
- The logo SVG/favicons were extracted from the supplied vector logo PDF; a
  light variant was generated for dark backgrounds.
- The three career posters referenced in the brief (2D Designer, 3D Exhibition
  Stand Designer, Sales Executive) were **not** among the supplied files, so
  branded SVG posters were generated in their place — swap in the originals at
  `public/assets/careers/` when available.
- Film-gallery thumbnails use supplied imagery mapped to the exact filenames
  required by the brief.
