# Elite One Desk

A premium corporate website and admin CMS for **Elite One Desk** — travel,
business setup, company formation, residency, licensing and government-related
support, presented as one desk rather than six.

Built as a production system: Next.js App Router, TypeScript, Tailwind CSS v4,
PostgreSQL with Drizzle ORM, and a role-based admin panel that controls every
public word, picture and link on the site.

---

## Table of contents

- [What is here](#what-is-here)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Commands](#commands)
- [How the site is put together](#how-the-site-is-put-together)
- [The admin panel](#the-admin-panel)
- [Content model](#content-model)
- [Bilingual content](#bilingual-content)
- [Security](#security)
- [Performance](#performance)
- [Brand assets](#brand-assets)
- [Deployment](#deployment)

---

## What is here

```
elite-one-desk/
├── brand-source/        Logo masters (EPS + SVG) and the scripts that derive
│                        every shipped brand asset from them
├── deploy/              nginx, systemd, PM2, backup and release scripts
├── drizzle/             Generated SQL migrations — committed, never edited
├── public/
│   ├── brand/           Logo, favicons and the default share image
│   └── fonts/           Self-hosted Inter, Plus Jakarta Sans, IBM Plex Sans Arabic
├── scripts/             migrate / seed / reset, plus the seed content itself
└── src/
    ├── app/
    │   ├── (public)/    The website, under /[lang]
    │   ├── (backoffice)/ The admin panel, under /admin
    │   ├── api/         The public enquiry endpoint and the admin CSV export
    │   └── media/       Serves uploaded files from UPLOAD_DIR
    ├── components/      site/ · admin/ · ui/
    ├── lib/             auth, cms, db, i18n, media, queries, settings, seo
    └── styles/          One stylesheet: tokens, base, components, utilities
```

## Requirements

| | |
|---|---|
| Node.js | 20.9 or newer (22 LTS recommended) |
| PostgreSQL | 14 or newer |
| Disk | ~600 MB for the app, plus whatever the media library grows to |

## Local setup

```bash
# 1. Dependencies
npm install

# 2. Environment
cp .env.example .env
#    Set DATABASE_URL, then generate a secret:
#      openssl rand -base64 48     → AUTH_SECRET
#    Set UPLOAD_DIR (.data/uploads is fine locally)
#    Set SEED_OWNER_EMAIL / SEED_OWNER_PASSWORD for the first account

# 3. Database
createdb elite_one_desk
npm run db:migrate
npm run db:seed          # catalogue, pages, navigation, FAQs, packages, artwork

# 4. Run it
npm run dev              # http://localhost:3000 · admin at /admin
```

The seed is **idempotent**. Running it again adds anything new and overwrites
nothing you have edited, which is also how a release picks up new starting
content without touching the site's own.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Development server |
| `npm run build` | Production build (`output: standalone`) |
| `npm start` | Run the production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run verify` | lint → typecheck → build. Run this before pushing |
| `npm run db:generate` | Generate a migration after changing `schema.ts` |
| `npm run db:migrate` | Apply pending migrations |
| `npm run db:seed` | Add missing starting content (safe to re-run) |
| `npm run db:reset` | Drop every table and re-migrate — **destroys all data** |

## How the site is put together

**Language routing.** English is served from the root (`/about`) and Arabic from
`/ar/about`. Internally both are the same `[lang]` route: middleware rewrites
`/about` onto `/en/about`, and `/en/...` is a 301 back to the clean form so one
page never has two indexable addresses.

**Pages are stacks of sections.** A page is a row in `pages` and an ordered list
of rows in `page_sections`. Each section names a block type from a fixed registry
(`src/lib/cms/blocks.ts`) and carries a `jsonb` payload of that block's declared
fields. One registry drives the admin form, the validation on save and the
renderer's field lookups, so adding a block type is one registry entry plus one
component — and the three can never drift apart.

**Nothing from the panel is rendered as markup.** Rich-text fields go through a
tag whitelist on the way in (`src/lib/cms/sanitize.ts`); everything else is
escaped by React. Icons are keys into an in-code set. Section templates are ours.

**Caching.** Pages render per request — the CSP nonce makes them dynamic — so the
caching lives one level down: every data loader is cached and tagged, and
publishing drops the tag. The result behaves like a static site that updates the
instant someone presses Publish, with no build step in between.

## The admin panel

`/admin`, deliberately not linked from the public site.

| Screen | |
|---|---|
| Dashboard | Unread and open enquiries, most-requested services, unpublished edits, recent activity |
| Enquiries | Search, filter, status, assignment, internal notes, CSV export |
| Pages & sections | Add, reorder, duplicate, hide and delete sections; draft → preview → publish |
| Service categories | The six columns, their groups and their order |
| Services | The full service-page template — benefits, audience, requirements, process, timeline, notes |
| Travel packages | Egypt and international programmes |
| Videos | Paste a YouTube address; the id and still are worked out for you |
| Testimonials | Unpublished until someone actively publishes them |
| FAQs | Global, per category or per service; published as structured data |
| Media library | Upload, re-encode, replace, delete — with a check for where each picture is placed |
| Navigation & footer | All four menus, one level of sub-links in the header |
| Site settings | Brand, contact, WhatsApp, social, disclaimers, feature switches |
| SEO | Per-page title, description, share card, canonical, noindex |
| Analytics | GA4, Tag Manager and Meta Pixel ids — nothing loads until one is entered |
| Users & roles | Accounts, role assignment, password resets, the permission matrix |
| Activity log | Who changed what, and when |

**Draft, preview, publish.** Editing a section writes a draft; the live site keeps
showing the published version. Preview renders the *real* public page with
`?preview=1` — same layout, fonts and scripts, reading drafts instead — at three
widths and in both languages. Publishing copies the draft over and drops the
cache tag.

**Roles.** Owner (everything), Admin (everything except rewriting role
permissions, and cannot touch owner accounts), Editor (content, media, SEO; reads
enquiries), Viewer (read-only). Every mutation names the permission it needs and
checks it on the server — hiding a button is never the control.

## Content model

| Table | |
|---|---|
| `users` `roles` `permissions` `role_permissions` `sessions` `login_attempts` | Identity and access |
| `pages` `page_sections` | The section-based CMS, with a draft column per section |
| `service_categories` `service_subcategories` `services` | The catalogue |
| `travel_packages` `videos` `testimonials` `faqs` | Repeatable content |
| `media` | The library; files live in `UPLOAD_DIR`, never in the build output |
| `enquiries` `enquiry_notes` | Lead management |
| `navigation_items` `site_settings` `seo_metadata` `social_links` | Site chrome |
| `activity_logs` | Audit trail |

## Bilingual content

Localised text is a pair of columns (`titleEn` / `titleAr`) rather than a
translations table: every localisable field is known at build time, so a column
pair keeps the types honest and a page render to one query.

**Arabic is optional everywhere.** An empty Arabic field falls back to English at
read time, which is what lets the Arabic edition go live before translation is
finished. The interface itself (`src/lib/i18n/dictionary.ts`) is fully
translated, including plural forms, which Arabic gets wrong in an audible way if
you use the English two-form rule.

The seeded catalogue ships with Arabic **names** for every category, group and
service — a visitor who switches language has to be able to navigate — and leaves
the long body copy in English, deliberately, rather than shipping a machine
translation. Fill those in under Services and Pages when a translator is
available.

RTL is handled with logical CSS properties throughout (`padding-inline`,
`inset-inline-start`, `text-start`), so the layout mirrors without a second
stylesheet. Decorative glyphs that imply direction carry `.flip-rtl`.

## Security

- **Passwords** — scrypt (N=2¹⁵, r=8, p=1) from Node's standard library. No
  native module, so a VPS build never turns into a compiler problem.
- **Sessions** — an opaque id plus a secret; only a SHA-256 of the secret is
  stored. httpOnly, SameSite=Lax, Secure in production, 12-hour sliding expiry.
- **Login throttling** — counted in the database, not in memory, so a restart
  does not reset an attacker's budget. Six failures per address, twenty per
  network, per fifteen minutes.
- **CSRF** — a synchroniser token bound to the session row, rendered into every
  admin form and compared with `timingSafeEqual` on submit.
- **Authorisation** — checked server-side in every action and on every page.
- **CSP** — per-request nonce with `strict-dynamic`, set in middleware.
- **Uploads** — the real format is read from the file's own bytes, then the image
  is decoded and re-encoded by sharp, so the stored file is one this application
  produced. SVG cannot be re-encoded, so it goes through an element whitelist and
  is served under `default-src 'none'; sandbox`.
- **Enquiry spam** — a honeypot field and a minimum time-on-form, both answering
  200 so a bot learns nothing, plus a per-address rate limit.
- **CSV export** — values beginning `=`, `+`, `-` or `@` are prefixed, because a
  spreadsheet will otherwise execute a visitor's text as a formula.

## Performance

- Self-hosted fonts, subset per script, `font-display: swap`.
- Uploads are re-encoded to WebP with three derivative widths at upload time and
  served with `srcset`; stored dimensions reserve the box before the bytes
  arrive, so images never shift the layout.
- The video showcase requests nothing from YouTube until someone presses play.
- Third-party tags are `afterInteractive` and only load when an id is configured.
- Scroll reveals are CSS classes toggled by one IntersectionObserver, not a
  motion library. The resting state is the visible state, so a visitor with no
  JavaScript — or a crawler — sees the finished page.
- `prefers-reduced-motion` disables every animation, including the hero.

## Brand assets

`brand-source/` holds the logo masters and the two scripts that derive
everything in `public/brand/` from them. The lockup ships as pre-sized WebP
rather than SVG because the artwork carries a 700-path Riyadh skyline inside the
monitor — 63 KB gzipped as vector, and invisible below about 200 px.

The nine illustrations in the media library are generated geometry, not stock
photography: licence-clean, in the same visual language as the hero, and
replaceable from the Media library without touching code. `scripts/seed/assets/`
holds the source images and the generator.

## Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for the Hostinger VPS walkthrough:
server preparation, PostgreSQL, the first release, nginx, HTTPS, the process
manager, backups and the update procedure.
