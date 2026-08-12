# Elite Marcom — Admin Panel Master Plan

**Status:** Approved plan, pre-implementation
**Owner:** Elite Marcom
**Scope:** One admin panel controlling the complete website
**Guiding rule:** The public site stays fast, static-feeling and secure. The admin panel
edits *content and settings*; it never turns the public site into a heavy CMS frontend.

---

## 1. Architecture at a glance

```
┌─────────────────────────────  Same FastAPI app  ─────────────────────────────┐
│                                                                              │
│  /admin (login-only SPA shell)      /api/admin/*  (authenticated APIs)       │
│      │                                   │                                   │
│      ▼                                   ▼                                   │
│  Visual editor ──── edits ────►  Content store (drafts + versions)           │
│                                      │ publish (atomic, roll-backable)      │
│                                      ▼                                       │
│  Public pages  ◄── published snapshot (baked HTML + theme.css + assets)      │
└──────────────────────────────────────────────────────────────────────────────┘
```

Key decisions:

1. **Same backend, new surface.** The admin panel lives in the existing FastAPI app
   under `/admin` + `/api/admin/*`. No second server, no new hosting requirement,
   `START WEBSITE.bat` keeps working.
2. **Content lives in structured JSON, not in the HTML.** Every editable region of
   every page gets a stable content key (`home.hero.title`, `footer.tagline`,
   `about.values[2].text`…). The current HTML becomes the *layout template*;
   an on-publish "bake" step writes final HTML snapshots to `runtime/published/`
   which the server serves. Editing can never corrupt the design source in git.
3. **Publish is atomic and versioned.** Draft → Preview → Publish. Every publish is a
   numbered snapshot (content + theme + affected assets) with one-click rollback.
4. **Style control = design tokens, not free CSS.** Colors, fonts, sizes, spacing,
   radii, animation durations are edited as tokens compiled to one
   `theme-custom.css` (CSS variables) loaded after `styles.css`. Layout positions are
   controlled through *section presets* (order, alignment, spacing, visibility,
   image/text side) rather than free pixel dragging — this keeps every page
   responsive and on-brand no matter who edits it.
5. **Admin UI technology:** same convention as the site — dependency-free modular
   vanilla JS + the existing design system (dark/light, tokens), served by FastAPI.
   No build step, no CDN, works under the strict CSP. (If we later want richer
   interactions we can vendor Preact the way Three.js is vendored.)
6. **Database:** the existing SQLite grows new tables:
   `admin_users, admin_sessions, roles, permissions, audit_log, content_versions,
   media, media_usage, redirects, seo_meta, analytics_events, settings`.

---

## 2. Modules

### 2.1 Dashboard
- Today at a glance: new requests, low-stock rentals, Jasani budget gauge,
  visitors today, last publish, failed logins.
- Shortcuts to the most common tasks; pending-review queue (branding preferences).

### 2.2 Visual Editor (desktop / tablet / mobile)
- The real site rendered in an iframe with an **edit overlay**; viewport toolbar
  switches 1440 / 834 / 390 widths (plus free resize).
- Click any editable region → side panel opens with its controls:
  - **Text:** inline rich-lite editing (bold/italic/links only), character guards.
  - **Images:** swap from Media Library, alt text, focal point.
  - **Buttons/links:** label + target with link picker (internal pages validated).
  - **Sections:** reorder by drag, show/hide, spacing presets, background variant,
    text/image side, column count where the design allows.
  - **Animations:** per-section reveal preset (fade-up / mask / zoom / none),
    delay and duration within safe ranges; global reduced-motion respect stays.
- Style tab per selection exposes only the tokens that apply (e.g. heading size
  scale, accent color choice) — every change previews live in all three viewports.
- Draft autosave, undo/redo, "who else is editing" lock indicator.

### 2.3 Pages
- One management screen per page (Home, About, Services, Projects, Corporate Gifts,
  Rental, Careers, Contact, Privacy, Product/Item templates) **plus Header and
  Footer as global "pages"** (nav labels/order, CTA button, cities line, footer
  columns, contact details, social links).
- Structured form view of the same content the visual editor edits (fast bulk edits).
- Add content from a **section library** (hero variants, text+media, stats row,
  FAQ, gallery, CTA strip, testimonial) — sections are pre-designed and
  responsive; adding one never requires design work.
- Per-page: publish state, scheduled publish (go live at a date/time), duplicate,
  version history with visual diff.
- Careers roles and Projects case studies become editable lists here (they are
  static JSON/HTML today).

### 2.4 Website & Brand (design system)
- **Colors:** brand palette editor (orange/violet/ink + dark & light palettes)
  with automatic contrast checking (WCAG warnings before save).
- **Typography:** font choices (self-hosted uploads — WOFF2, served locally to keep
  the no-third-party CSP), size scale, heading weights, letter-spacing.
- **Look:** corner radius scale, border/glass intensity, shadow level.
- **Motion:** global animation on/off, speed multiplier, marquee speed, cursor
  effects toggle.
- **Identity:** logo (dark + light variants), favicon set, PDF logo (printing
  manuals pick this up automatically), default OG image.
- **3D Hero (GLB) manager:** upload a new `.glb` (size cap, Draco validation,
  malware scan), live preview inside the panel with the same renderer, camera
  sliders (zoom / height / FOV — writes the existing `data-camz/camy/fov`),
  autorotate speed, fallback poster image, and a version list to switch back.

### 2.5 Media Library
- Drag-drop upload → automatic WebP conversion + responsive size variants,
  EXIF stripped, signature-validated, malware-scanned (existing pipeline reused).
- Folders + tags, search, alt-text management, usage tracking ("used on Home,
  About") and **replace-in-place** (swap the file, every usage updates).
- Safe delete (blocked while in use), storage usage meter.
- Videos: YouTube references managed here for the Films section.

### 2.6 SEO
- Per page: title, meta description with pixel-width preview, canonical, robots,
  OG/Twitter image + text, **live Google/WhatsApp/X result previews**.
- Auto-regenerated `sitemap.xml` + `robots.txt` editor.
- Structured data: Organization, LocalBusiness (Riyadh/Dubai), Product markup for
  catalog pages — generated, with validation.
- **Redirects manager** (301/302 table) and broken-link checker (scheduled crawl
  of internal links).
- Readiness checks per page: missing alts, duplicate titles, heading order,
  image weight budget — scored checklist, not just raw data.

### 2.7 Jasani Integration console
- Connection status per market (KSA/UAE), last product/stock sync, snapshot ages.
- **Daily budget gauge** (5 primary calls, UAE-day reset) with per-call log;
  a "refresh now" button that *spends the documented reserve call* and is
  disabled when the budget is gone — the panel makes the limit visible instead
  of letting anyone burn it.
- Cache browser: view the normalized snapshot, search a product, see its raw
  mapped fields; clear/rebuild cache buttons.
- Printing-manual monitor: generated vs supplier-fallback counts, failed
  candidates list, regenerate button.
- Branding-data cache status; future Branding-Prices sync switch (internal-only
  costing, per the API docs).
- Token health: masked, never displayed; rotation checklist; alerts on repeated 403.
- Preview-fallback indicator so "the site is showing demo data" is diagnosable
  at a glance.

### 2.8 Requests Inbox
- Every submission in one queue: **gift enquiries** (with branding preferences +
  uploaded logos), **rental enquiries** (with per-item days and event dates),
  contact messages, career applications (CVs), availability notifications.
- Decrypt-on-view (records stay AES-GCM encrypted at rest; every view is audited).
- Status workflow: New → In progress → Quoted → Won/Lost/Closed, assignee,
  internal notes, color labels.
- Branding preferences surface as **Pending technical review** with approve /
  needs-changes actions (feeds the printing-manual customer PDF phase).
- One-click reply templates (opens mail client pre-filled), CSV export,
  retention countdown per record (existing retention rules visualized).
- **New-request notifications:** email and/or WhatsApp ping to staff (configurable).

### 2.9 Site Insights
- **Privacy-first, first-party analytics** — no cookies, no third parties
  (fits the CSP and the region's privacy expectations): a tiny beacon records
  pageviews with daily-salted IP hashing.
- Dashboards: visitors/pageviews over time, top pages, referrers, countries,
  device/viewport split, entry/exit pages.
- Catalog intelligence: most-viewed products (gifts & rental), catalog search
  terms, filter usage, add-to-request and enquiry **conversion funnel**,
  manual downloads.
- Performance: Core Web Vitals collected from real visitors, slow-page list.
- Alerts: traffic spike/drop, error-rate rise, form-failure rise.
- Optional later: one-click GA4/Plausible forwarding if external reporting is
  ever wanted — off by default.

### 2.10 Users & Roles
- Admin accounts: Argon2 password hashing, **mandatory TOTP 2FA**, session list
  with remote sign-out, login rate-limiting + lockout, optional IP allowlist.
- Roles (editable permission matrix):
  - **Owner** — everything, including users and secrets.
  - **Admin** — everything except user/secret management.
  - **Editor** — pages, media, brand, SEO; cannot publish settings or view requests.
  - **Catalog Manager** — rental inventory, Jasani console (read + refresh).
  - **Sales** — Requests Inbox only.
  - **Analyst** — read-only Insights + logs.
- Per-user activity view; invitation flow with forced 2FA setup on first login.

### 2.11 Activity Log
- Append-only audit of every admin action: who, what, when, from where, and a
  **before/after diff** for content and settings changes.
- Hash-chained entries (tamper-evident), filter by user/module/date, CSV export.
- Sensitive events highlighted: logins/failures, permission changes, secret
  rotations, record decryptions, publishes and rollbacks.

### 2.12 Suggested additions (recommended)
- **Backups & restore:** nightly snapshot of content + media + settings, one-click
  restore, downloadable zip; publish history doubles as content backup.
- **Arabic + RTL readiness:** the content model stores per-language values from
  day one (`en` now, `ar` later) — a KSA/UAE site will want Arabic; retrofitting
  is far more expensive than planning it.
- **Announcement manager:** site-wide bar or popup (Ramadan collection, event
  presence) with schedule windows.
- **Maintenance mode** with allowlisted preview access.
- **Security center:** secret-age reminders (rotate Jasani token, data keys),
  failed-login map, dependency update notes.
- **Rental inventory manager** (the admin side promised earlier): CRUD for rental
  items — images from Media Library, specs, per-market stock, categories,
  featured flags — writing the same `rental-inventory.json` schema the site
  already reads, so the public site needs zero changes.

---

## 3. How editing actually reaches the public site

1. Every page template gets `data-em` attributes marking editable regions
   (one-time instrumentation of the existing HTML).
2. Admin edits write to the **draft** content store.
3. **Preview** renders the draft through the same bake pipeline to a private URL.
4. **Publish** bakes final HTML (template + published content + theme tokens) into
   `runtime/published/` and atomically switches the server to it. Public visitors
   always get plain fast HTML — no client-side content fetching, no SEO penalty.
5. Rollback = point the server at a previous snapshot.

This gives CMS convenience with static-site speed, and git always holds the
clean design source.

---

## 4. Security posture (extends the existing rules)

- Admin reachable only over HTTPS; separate session cookie (`Secure, HttpOnly,
  SameSite=Strict`), CSRF tokens on every mutation, strict CSP (self-only).
- All uploads run the existing validation pipeline (signature, size, malware scan).
- Jasani token and data keys never render in any admin response.
- Public/admin data boundary: supplier prices and `blocked_qty` stay internal
  even inside the panel except for authorized roles (per the Jasani docs).
- Fail-closed production config extends to admin secrets (refuse to start
  without strong `EM_ADMIN_*` secrets).
- Rate limits on login, uploads, publish, and analytics ingestion.

---

## 5. Build order (phases)

| Phase | Delivers | Why this order |
|---|---|---|
| **0. Foundations** | Auth + 2FA, roles, sessions, audit log, admin shell UI, settings store | Everything else hangs off it |
| **1. Requests Inbox + Jasani console** | Immediate daily business value from data that already exists | No content-model work needed |
| **2. Media Library + Website & Brand** | Uploads pipeline, theme tokens → `theme-custom.css`, logo/favicon, **GLB manager** | Prerequisite for page editing |
| **3. Pages + SEO** | Content model, per-page structured editors incl. header/footer, bake/publish/rollback, SEO module, rental inventory manager | The core CMS |
| **4. Visual Editor** | Iframe overlay editing on top of Phase 3's content bindings, 3-viewport preview, section library | Needs the content model to exist first |
| **5. Site Insights** | First-party analytics beacon + dashboards + Web Vitals | Independent; benefits from panel maturity |
| **6. Polish** | Backups/restore, scheduled publishing, announcements, security center, Arabic/RTL content entry | Completes the platform |

Each phase ships usable on its own, keeps all existing tests green, and follows
the established workflow (feature branch → renders/review → merge to `main`).
Relative size: Phase 0 and 1 are the fastest wins; Phases 3–4 are the largest.

---

## 6. Decisions to confirm before Phase 0

1. **Access:** admin at `/admin` on the same domain (recommended) or a separate
   subdomain?
2. **2FA mandatory for all users** (recommended) or Owner/Admin only?
3. **Analytics:** first-party self-hosted only (recommended), or also forward to
   GA4?
4. **Languages:** confirm Arabic is wanted so the content model is bilingual from
   day one (strongly recommended for KSA/UAE even if Arabic content comes later).
5. **Staff notifications** for new requests: email, WhatsApp, or both?
