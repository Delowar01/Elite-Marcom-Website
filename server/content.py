"""Elite Marcom admin — content model, bake pipeline, publish & rollback.

Editable regions are marked in the git-tracked HTML with data-em attributes.
Draft values live in admin.db per language (en now, ar stored for later).
Publishing bakes the originals + drafts into runtime/published/site/, which
the static server checks before public/ — git always keeps the clean design
source, and rollback just re-bakes an earlier snapshot.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path

from . import config

PUBLISHED_DIR = config.RUNTIME_DIR / "published" / "site"

SITE_ORIGIN = "https://www.elitemarcom.com"

# ---------------- schema ----------------

# The menu labels used to live here as eight fixed keys, which could rename a
# link but never add, remove or reorder one. They are a managed list now
# (Sections & items -> Header), so the menu has one owner rather than a text
# field here and a list there disagreeing about what a link says.
GLOBAL_REGIONS = [
    {"key": "header.cities", "label": "Header — cities line", "kind": "text"},
    {"key": "header.cta", "label": "Header — button (main pages)", "kind": "text"},
    {"key": "footer.about", "label": "Footer — about paragraph", "kind": "multiline"},
    {"key": "footer.cities", "label": "Footer — cities line", "kind": "text"},
    {"key": "footer.email", "label": "Footer — email address", "kind": "text"},
    {"key": "footer.phone", "label": "Footer — phone number", "kind": "text"},
]

_HERO = [
    {"key": "hero.eyebrow", "label": "Hero — eyebrow line", "kind": "text"},
    {"key": "hero.title1", "label": "Hero — title line 1", "kind": "text"},
    {"key": "hero.title2", "label": "Hero — title line 2", "kind": "text"},
    {"key": "hero.lead", "label": "Hero — lead paragraph", "kind": "multiline"},
]

PAGES: dict[str, dict] = {
    "index": {"label": "Home", "file": "index.html",
              "regions": _HERO + [
                  {"key": "hero.cta1", "label": "Hero — primary button", "kind": "text"},
                  {"key": "hero.cta2", "label": "Hero — secondary button", "kind": "text"}]},
    "about": {"label": "About", "file": "about.html", "regions": _HERO},
    "services": {"label": "Services", "file": "services.html", "regions": _HERO},
    "projects": {"label": "Projects", "file": "projects.html", "regions": _HERO},
    "giveaways": {"label": "Corporate Gifts", "file": "giveaways.html", "regions": _HERO},
    "rental": {"label": "Rental", "file": "rental.html", "regions": _HERO},
    "careers": {"label": "Careers", "file": "careers.html", "regions": _HERO},
    "contact": {"label": "Contact", "file": "contact.html", "regions": _HERO},
    "privacy": {"label": "Privacy", "file": "privacy.html",
                "regions": [{"key": "hero.eyebrow", "label": "Hero — eyebrow line", "kind": "text"},
                            {"key": "hero.title1", "label": "Page title", "kind": "text"},
                            {"key": "hero.lead", "label": "Lead paragraph", "kind": "multiline"}]},
    # The service detail pages. Each is an ordinary page with a flat slug;
    # `PAGE_ADDRESS` below is what puts them under /services/.
    "services-exhibition-stands": {"label": "Services — Exhibition stands", "file": "services-exhibition-stands.html", "regions": _HERO},
    "services-fit-out-interior": {"label": "Services — Fit-out & interiors", "file": "services-fit-out-interior.html", "regions": _HERO},
    "services-corporate-events": {"label": "Services — Corporate events", "file": "services-corporate-events.html", "regions": _HERO},
    "services-outdoor-activities": {"label": "Services — Outdoor activities", "file": "services-outdoor-activities.html", "regions": _HERO},
    "services-branding": {"label": "Services — Branding", "file": "services-branding.html", "regions": _HERO},
    "services-corporate-gifts": {"label": "Services — Corporate gifts", "file": "services-corporate-gifts.html", "regions": _HERO},
    "services-event-equipment-rental": {"label": "Services — Event equipment rental", "file": "services-event-equipment-rental.html", "regions": _HERO},
    "services-photo-videography": {"label": "Services — Photo & videography", "file": "services-photo-videography.html", "regions": _HERO},
    "services-staffing": {"label": "Services — Staffing", "file": "services-staffing.html", "regions": _HERO},
    "services-digital-marketing": {"label": "Services — Digital marketing", "file": "services-digital-marketing.html", "regions": _HERO},
    "product": {"label": "Gift product page", "file": "product.html", "regions": []},
    "rental-item": {"label": "Rental item page", "file": "rental-item.html", "regions": []},
}

# A page created in the admin panel starts from the shell in blocks.py, which
# gives it these three keyed regions plus whatever the editor adds by path.
CUSTOM_REGIONS = [
    {"key": "hero.eyebrow", "label": "Hero — eyebrow line", "kind": "text"},
    {"key": "hero.title1", "label": "Hero — page title", "kind": "text"},
    {"key": "hero.lead", "label": "Hero — lead paragraph", "kind": "multiline"},
]

SEO_FIELDS = [
    {"key": "seo.title", "label": "Browser & search title", "kind": "text", "max": 200},
    {"key": "seo.description", "label": "Meta description", "kind": "multiline", "max": 400},
    {"key": "seo.ogImage", "label": "Share image (path, e.g. /assets/… or /media/…)",
     "kind": "text", "max": 300},
]

LANGS = ("en", "ar")

# keys whose <a href> is rewritten alongside the text
_HREF_RULES = {
    "footer.email": lambda v: "mailto:" + v.strip(),
    "footer.phone": lambda v: "tel:" + re.sub(r"[^+0-9]", "", v),
}


# ---------------- pages created in the admin panel ----------------

_PAGE_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
# names that belong to the app, an asset directory or a built-in page
_SLUG_RESERVED = set(PAGES) | {
    "admin", "api", "ar", "assets", "media", "js", "data", "vendor", "css",
    "sitemap", "robots", "styles", "home", "pages", "theme-custom", "static",
}


def custom_pages() -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT slug, label, title, description, nav, created_at, created_by "
        "FROM custom_pages ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def _custom_slugs() -> set[str]:
    from . import adminauth as aa

    return {r["slug"] for r in aa._connect().execute("SELECT slug FROM custom_pages")}


def is_public_page(slug: str) -> bool:
    """Is `slug` the address of a page this website serves?

    The clean-URL rewrite asks this before turning /about into about.html. A
    slug it does not recognise is left exactly as it arrived, which is what
    keeps /admin, /api/..., every asset and every typo out of the rewrite —
    and, because nothing unknown is ever rewritten, what makes a redirect
    loop impossible.
    """
    if slug in PAGES:
        return True
    return bool(_PAGE_SLUG_RE.match(slug)) and slug in _custom_slugs()


# The service detail pages read as /services/<name> but are ordinary flat
# files. A slug with a slash in it would have to be handled again in the
# published-file lookup, the reserved-name check, the admin routes and every
# layer keyed on a page name; one lookup table instead keeps the slug flat
# and moves the nesting into the address, which is the only place it shows.
PAGE_ADDRESS = {slug: "services/" + slug[len("services-"):]
                for slug in PAGES if slug.startswith("services-")}
PAGE_ADDRESS["index"] = ""
_ADDRESS_PAGE = {addr: slug for slug, addr in PAGE_ADDRESS.items() if addr}


def page_address(page: str) -> str:
    """The public address of a page, with no leading slash and no extension.
    "" is the home page."""
    return PAGE_ADDRESS.get(page, page)


def page_for_address(address: str) -> str | None:
    """The page a public address names, or None if it names no page at all.

    Accepts a page's own slug as well as its address, so that the one form
    that is not canonical — /services-branding, the file's own name — is
    recognised and can be sent to the canonical one rather than becoming a
    second indexable address for the same page.
    """
    address = address.strip("/")
    if address in _ADDRESS_PAGE:
        return _ADDRESS_PAGE[address]
    if "/" in address:
        return None
    return address if is_public_page(address) else None


def all_pages() -> dict[str, dict]:
    """Built-in pages plus everything created in the admin panel."""
    pages: dict[str, dict] = {key: {**cfg, "custom": False} for key, cfg in PAGES.items()}
    for row in custom_pages():
        pages[row["slug"]] = {"label": row["label"], "file": f"{row['slug']}.html",
                              "regions": CUSTOM_REGIONS, "custom": True,
                              "nav": bool(row["nav"]), "title": row["title"],
                              "description": row["description"]}
    return pages


def page_config(page: str) -> dict | None:
    if page in PAGES:
        return {**PAGES[page], "custom": False}
    return all_pages().get(page)


def page_source(page: str) -> str:
    """The design source for a page: the git-tracked file for a built-in one,
    and a shell built from a live page for one created in the admin."""
    from . import blocks

    cfg = page_config(page)
    if cfg is None:
        raise ValueError("unknown page")
    if not cfg.get("custom"):
        return (config.PUBLIC_DIR / cfg["file"]).read_text(encoding="utf-8")
    return blocks.page_shell(page, cfg.get("title") or cfg["label"],
                             cfg.get("description") or "", cfg["label"],
                             cfg.get("description") or "")


def page_create(slug: str, label: str, title: str, description: str,
                nav: bool, by: str) -> dict:
    from . import adminauth as aa

    slug = str(slug or "").strip().lower()
    if not _PAGE_SLUG_RE.match(slug):
        raise ValueError("The address must be lowercase letters, digits and dashes "
                         "(for example team or our-process).")
    if slug in _SLUG_RESERVED or (config.PUBLIC_DIR / f"{slug}.html").exists():
        raise ValueError("That address is already used by the site.")
    if slug in _custom_slugs():
        raise ValueError("A page with that address already exists.")
    label = re.sub(r"\s+", " ", str(label or "")).strip()[:60]
    if not label:
        raise ValueError("Give the page a name.")
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:200] or f"{label} — Elite Marcom"
    description = re.sub(r"\s+", " ", str(description or "")).strip()[:300]
    with aa._lock:
        conn = aa._connect()
        conn.execute("INSERT INTO custom_pages (slug, label, title, description, nav, "
                     "created_at, created_by) VALUES (?,?,?,?,?,?,?)",
                     (slug, label, title, description, 1 if nav else 0,
                      int(time.time()), by[:200]))
        conn.commit()
    return {"slug": slug, "label": label, "title": title,
            "description": description, "nav": bool(nav)}


def page_update(slug: str, label: str | None, title: str | None,
                description: str | None, nav: bool | None) -> dict:
    from . import adminauth as aa

    current = next((p for p in custom_pages() if p["slug"] == slug), None)
    if current is None:
        raise ValueError("unknown page")
    label = re.sub(r"\s+", " ", str(label)).strip()[:60] if label is not None else current["label"]
    if not label:
        raise ValueError("Give the page a name.")
    title = (re.sub(r"\s+", " ", str(title)).strip()[:200] if title is not None
             else current["title"]) or f"{label} — Elite Marcom"
    description = (re.sub(r"\s+", " ", str(description)).strip()[:300]
                   if description is not None else current["description"])
    nav_value = current["nav"] if nav is None else (1 if nav else 0)
    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE custom_pages SET label=?, title=?, description=?, nav=? WHERE slug=?",
                     (label, title, description, nav_value, slug))
        conn.commit()
    return {"slug": slug, "label": label, "title": title,
            "description": description, "nav": bool(nav_value)}


def page_delete(slug: str) -> bool:
    """Remove the page, its drafts and its design — and the published copy,
    so a deleted page stops answering before the next publish."""
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        cur = conn.execute("DELETE FROM custom_pages WHERE slug=?", (slug,))
        if cur.rowcount:
            conn.execute("DELETE FROM content WHERE page=?", (slug,))
            conn.execute("DELETE FROM designs WHERE page=?", (slug,))
        conn.commit()
    if not cur.rowcount:
        return False
    for path in (PUBLISHED_DIR / f"{slug}.html", PUBLISHED_DIR / "ar" / f"{slug}.html"):
        path.unlink(missing_ok=True)
    return True


def _valid_keys(page: str) -> set[str]:
    if page == "_global":
        return {r["key"] for r in GLOBAL_REGIONS}
    cfg = page_config(page)
    if cfg is None:
        raise ValueError("unknown page")
    return {r["key"] for r in cfg["regions"]} | {f["key"] for f in SEO_FIELDS}


# ---------------- draft store (admin.db) ----------------

def get_values(page: str, lang: str = "en") -> dict[str, str]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT key, value FROM content WHERE page=? AND lang=?", (page, lang)).fetchall()
    return {r["key"]: r["value"] for r in rows}


# --- limited rich text (bold/italic/links/lists/line breaks) ---

_RICH_TAGS = {"strong", "em", "b", "i", "u", "br", "ul", "ol", "li", "a"}
_RICH_HREF = re.compile(r"^(https://|http://|mailto:|tel:|/|#)[^\s\"'<>]*$")


class _RichSanitizer(HTMLParser):
    """Rebuild input keeping only whitelisted inline tags; everything else is
    reduced to its text content. Attributes are dropped except a[href]."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _RICH_TAGS:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag == "a":
            href = next((v for k, v in attrs if k == "href"), "") or ""
            if not _RICH_HREF.match(href):
                return
            self.out.append(f'<a href="{html_mod.escape(href, quote=True)}">')
            self._open.append("a")
            return
        self.out.append(f"<{tag}>")
        self._open.append(tag)

    def handle_endtag(self, tag):
        if tag in _RICH_TAGS and tag in self._open:
            while self._open:
                open_tag = self._open.pop()
                self.out.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data):
        self.out.append(html_mod.escape(data))

    def result(self) -> str:
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


def sanitize_rich(text: str) -> str:
    s = _RichSanitizer()
    s.feed(text)
    s.close()
    return s.result()


_RICH_MARKER = re.compile(r"<(strong|em|b|i|u|br|ul|ol|li|a)\b", re.IGNORECASE)


def set_values(page: str, values: dict, lang: str, by: str) -> list[str]:
    from . import adminauth as aa

    if lang not in LANGS:
        raise ValueError("unknown language")
    allowed = _valid_keys(page)
    saved = []
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        for key, value in values.items():
            if key not in allowed:
                raise ValueError(f"unknown field: {key[:60]}")
            value = str(value or "").strip()[:2000]
            if "<" in value and not key.startswith("seo."):
                value = sanitize_rich(value)[:4000]
            if value:
                conn.execute(
                    "INSERT INTO content (page, key, lang, value, updated_at, updated_by) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(page, key, lang) DO UPDATE SET "
                    "value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                    (page, key, lang, value, now, by[:200]))
            else:
                # empty = back to the original design text
                conn.execute("DELETE FROM content WHERE page=? AND key=? AND lang=?",
                             (page, key, lang))
            saved.append(key)
        conn.commit()
    return saved


def _all_content_rows() -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT page, key, lang, value FROM content ORDER BY page, key, lang").fetchall()
    return [dict(r) for r in rows]


def last_edit_ts(page: str) -> int:
    from . import adminauth as aa

    row = aa._connect().execute(
        "SELECT MAX(updated_at) AS m FROM content WHERE page IN (?, '_global')", (page,)).fetchone()
    return row["m"] or 0


# ---------------- region locator (stdlib HTML parser) ----------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "source", "track", "wbr"}


class _Locator(HTMLParser):
    """Byte-offset locations of every data-em element's start tag and content."""

    def __init__(self, raw: str):
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self._lines = [0]
        for line in raw.splitlines(keepends=True):
            self._lines.append(self._lines[-1] + len(line))
        self.stack: list[tuple[str, str | None, int, int]] = []
        self.regions: list[dict] = []

    def _off(self) -> int:
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        start = self._off()
        gt = self.raw.find(">", start)
        self.stack.append((tag, dict(attrs).get("data-em"), start, gt + 1))

    def handle_startendtag(self, tag, attrs):  # <tag/> — never a region
        pass

    def handle_endtag(self, tag):
        while self.stack:
            t, key, tag_start, content_start = self.stack.pop()
            if t == tag:
                if key:
                    self.regions.append({"key": key, "tagStart": tag_start,
                                         "contentStart": content_start,
                                         "contentEnd": self._off()})
                break


def _locate(raw: str) -> list[dict]:
    loc = _Locator(raw)
    loc.feed(raw)
    return sorted(loc.regions, key=lambda r: r["contentStart"])


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def original_values(page: str) -> dict[str, str]:
    """Current design text for placeholders in the editor."""
    raw = page_source(page)
    out = {r["key"]: _strip_tags(raw[r["contentStart"]:r["contentEnd"]]) for r in _locate(raw)}
    m = re.search(r"<title>(.*?)</title>", raw, flags=re.S)
    if m:
        out["seo.title"] = _strip_tags(m.group(1))
    m = re.search(r'<meta name="description" content="([^"]*)"', raw)
    if m:
        out["seo.description"] = html_mod.unescape(m.group(1))
    m = re.search(r'<meta property="og:image" content="([^"]*)"', raw)
    if m:
        out["seo.ogImage"] = m.group(1).replace(SITE_ORIGIN, "")
    return out


# ---------------- bake ----------------

def _escaped(value: str) -> str:
    if _RICH_MARKER.search(value):
        # sanitized at save time — whitelist tags only, text already escaped
        return value.replace("\r", "").replace("\n", "<br>")
    return html_mod.escape(value).replace("\r", "").replace("\n", "<br>")


def bake_page(page: str, lang: str = "en") -> str:
    from . import collections as collections_mod
    from . import design

    raw = page_source(page)
    # repeatable lists sit between the section layer and the element overrides:
    # a section the editor duplicated brings its container with it, one it
    # removed takes its list away, and an override on a card inside a list is
    # applied after the list is built rather than being rebuilt away
    raw = design.apply_to_page(raw, page,
                               between=lambda r: collections_mod.apply_to_page(r, page))
    raw = _inject_nav(raw, page)
    raw = _inject_social(raw)
    raw = _stamp_default_theme(raw)
    values = get_values("_global", lang) | get_values(page, lang)
    if values:
        regions = [r for r in _locate(raw) if values.get(r["key"])]
        for r in sorted(regions, key=lambda x: x["tagStart"], reverse=True):
            value = values[r["key"]]
            start_tag = raw[r["tagStart"]:r["contentStart"]]
            if r["key"] in _HREF_RULES:
                start_tag = re.sub(r'href="[^"]*"',
                                   f'href="{html_mod.escape(_HREF_RULES[r["key"]](value), quote=True)}"',
                                   start_tag, count=1)
            raw = raw[:r["tagStart"]] + start_tag + _escaped(value) + raw[r["contentEnd"]:]
    # --- SEO head fields ---
    title = values.get("seo.title")
    if title:
        safe = html_mod.escape(title)
        raw = re.sub(r"<title>.*?</title>", f"<title>{safe}</title>", raw, count=1, flags=re.S)
        raw = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
                     rf"\g<1>{html_mod.escape(title, quote=True)}\g<2>", raw, count=1)
    desc = values.get("seo.description")
    if desc:
        safe = html_mod.escape(re.sub(r"\s+", " ", desc), quote=True)
        raw = re.sub(r'(<meta name="description" content=")[^"]*(")',
                     rf"\g<1>{safe}\g<2>", raw, count=1)
        raw = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
                     rf"\g<1>{safe}\g<2>", raw, count=1)
    og = values.get("seo.ogImage")
    if og:
        og = og.strip()
        if og.startswith("/"):
            og = SITE_ORIGIN + og
        if re.match(r"^https://[\w./-]+$", og):
            raw = re.sub(r'(<meta property="og:image" content=")[^"]*(")',
                         rf"\g<1>{og}\g<2>", raw, count=1)
    return raw


def _stamp_default_theme(raw: str) -> str:
    """Write the admin's chosen default onto <html>, for `theme-init.js` to read.

    It goes in the markup rather than into a stylesheet or a fetch because the
    theme has to be decided before the first paint, and anything that needs a
    round trip first would either flash the wrong theme or put a request in
    front of every page load. An admin changing this reaches the live site at
    the next publish, which is the same contract as every other page change —
    and the preview shows it straight away.

    "auto" writes nothing: an unstamped page follows the visitor's device, so
    the shipped files and the admin panel behave exactly as they always have.
    """
    from . import media

    try:
        theme = media.get_brand_tokens().get("theme") or media.DEFAULT_THEME
    except Exception:
        return raw
    m = re.search(r"<html\b[^>]*>", raw, re.I)
    if not m:
        return raw
    tag = re.sub(r'\s+data-default-theme="[^"]*"', "", m.group(0))
    if theme in ("dark", "light"):
        tag = re.sub(r"(/?)>$", f' data-default-theme="{theme}"' + r"\1>", tag, count=1)
    return raw[:m.start()] + tag + raw[m.end():]


# ---------------- navigation & social (baked into every page) ----------------

def _insert_before_close(raw: str, open_marker: str, close_tag: str, markup: str) -> str:
    """Append list items just before the closing tag of one specific list."""
    start = raw.find(open_marker)
    if start == -1:
        return raw
    end = raw.find(close_tag, start)
    if end == -1:
        return raw
    return raw[:end] + markup + raw[end:]


def _inject_nav(raw: str, page: str) -> str:
    """Put admin-created pages into the three menus every page carries: the
    header bar, the slide-in panel and the footer's second column."""
    extras = [row for row in custom_pages() if row["nav"]]
    if not extras:
        return raw
    links = []
    for row in extras:
        href = f"/{row['slug']}"
        current = ' aria-current="page"' if row["slug"] == page else ""
        links.append((href, html_mod.escape(row["label"]), current))
    header = "".join(f'\n        <li><a href="{h}"{c}>{lbl}</a></li>' for h, lbl, c in links)
    raw = _insert_before_close(raw, '<nav class="site-nav"', "</ul>", header)
    footer = "".join(f'\n          <li><a href="{h}">{lbl}</a></li>' for h, lbl, _ in links)
    raw = _insert_before_close(raw, '<nav aria-label="Footer — more"', "</ul>", footer)
    panel_start = raw.find('<aside class="menu-panel"')
    if panel_start != -1:
        already = raw.count("<li>", panel_start, raw.find("</ol>", panel_start))
        panel = "".join(
            f'\n      <li><a href="{h}"{c}><span class="num">{already + i + 1:02d}</span>{lbl}</a></li>'
            for i, (h, lbl, c) in enumerate(links))
        raw = _insert_before_close(raw, '<aside class="menu-panel"', "</ol>", panel)
    return raw


def social_values() -> dict[str, str]:
    from . import adminauth as aa
    from . import blocks

    return {key: str(aa.setting_get(f"social.{key}", "") or "") for key in blocks.SOCIAL_KEYS}


def _inject_social(raw: str) -> str:
    from . import blocks

    markup = blocks.render_social(social_values())
    if not markup:
        return raw
    anchor = '<div class="site-footer__meta">'
    if anchor not in raw:
        return raw
    return raw.replace(anchor, markup + "\n    " + anchor, 1)


# ---------------- publish, history, rollback ----------------

# /product and /rental-item are the templates a catalogue item is rendered
# into. On their own — which is the only form an address without an id takes —
# they are empty shells, so they are pages the site serves but not pages worth
# offering a search engine.
SITEMAP_SKIP = {"product", "rental-item"}


def _sitemap_english_only(page: str) -> bool:
    """Pages whose Arabic edition exists but is not worth offering yet.

    `collection_items` has no language dimension, so a service page's Arabic
    edition currently carries the English body. The page still works and is
    still reachable — a visitor who follows the language switch gets it — but
    listing it in the sitemap would be inviting Google to index a page in the
    wrong language. Drop this rule (and add hreflang) the moment the service
    pages have real Arabic text.
    """
    return page.startswith("services-")


def _sitemap_xml() -> str:
    today = time.strftime("%Y-%m-%d")
    urls = []
    prefixes = [""] + (["ar/"] if "ar" in languages() else [])
    pages = {k: v for k, v in all_pages().items() if k not in SITEMAP_SKIP}
    for prefix in prefixes:
        for page, cfg in pages.items():
            if prefix == "ar/" and _sitemap_english_only(page):
                continue
            # the address, not the file: a page is served without its
            # extension, and a service page under /services/
            tail = f"{prefix}{page_address(page)}"
            urls.append(f"  <url><loc>{SITE_ORIGIN}/{tail}</loc>"
                        f"<lastmod>{today}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def languages() -> list[str]:
    from . import adminauth as aa

    langs = aa.setting_get("site.languages") or ["en"]
    return [l for l in langs if l in LANGS] or ["en"]


_AR_SWITCH = ('<a class="lang-switch" href="{href}" hreflang="{lang}" lang="{lang}">{label}</a>')


def localize(raw: str, lang: str) -> str:
    """Turn a baked page into its Arabic edition: RTL document, /ar/ links,
    and a language switch in the header. English pages get the switch too."""
    enabled = languages()
    switch = ""
    if len(enabled) > 1:
        switch = (_AR_SWITCH.format(href="/", lang="en", label="English") if lang == "ar"
                  else _AR_SWITCH.format(href="/ar/", lang="ar", label="العربية"))
    if lang == "ar":
        raw = raw.replace('<html lang="en"', '<html lang="ar" dir="rtl"', 1)
        # keep internal navigation inside the Arabic edition. One path
        # segment only, so /assets/… and /js/… are left where they are, and a
        # lookahead rather than a closing quote so /services#branding keeps
        # its fragment.
        raw = re.sub(r'href="/([a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)?)(?=["#?])',
                     r'href="/ar/\1', raw)
        raw = re.sub(r'href="/"(\s|>)', r'href="/ar/"\1', raw)
        raw = raw.replace('<link rel="canonical" href="https://www.elitemarcom.com/',
                          '<link rel="canonical" href="https://www.elitemarcom.com/ar/')
    if switch:
        raw = raw.replace('<button class="icon-btn theme-toggle"',
                          switch + '\n      <button class="icon-btn theme-toggle"', 1)
    return raw


def publish_all(by: str, note: str = "") -> dict:
    from . import adminauth as aa

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    langs = languages()
    pages = all_pages()
    live = {cfg["file"] for cfg in pages.values()}
    for page, cfg in pages.items():
        baked = localize(bake_page(page, "en"), "en")
        tmp = PUBLISHED_DIR / (cfg["file"] + ".tmp")
        tmp.write_text(baked, encoding="utf-8")
        tmp.replace(PUBLISHED_DIR / cfg["file"])
        count += 1
    # a page deleted in the admin panel must stop answering, not linger as a
    # published file nothing links to any more
    for stale in PUBLISHED_DIR.glob("*.html"):
        if stale.name not in live:
            stale.unlink(missing_ok=True)
    if "ar" in langs:
        ar_dir = PUBLISHED_DIR / "ar"
        ar_dir.mkdir(parents=True, exist_ok=True)
        for stale in ar_dir.glob("*.html"):
            if stale.name not in live:
                stale.unlink(missing_ok=True)
        for page, cfg in pages.items():
            baked = localize(bake_page(page, "ar"), "ar")
            tmp = ar_dir / (cfg["file"] + ".tmp")
            tmp.write_text(baked, encoding="utf-8")
            tmp.replace(ar_dir / cfg["file"])
            count += 1
    else:
        for stale in (PUBLISHED_DIR / "ar").glob("*.html"):
            stale.unlink(missing_ok=True)
    (PUBLISHED_DIR / "sitemap.xml").write_text(_sitemap_xml(), encoding="utf-8")
    from . import design

    snapshot = json.dumps({"note": note, "content": _all_content_rows(),
                           "designs": design.all_docs()}, ensure_ascii=False)
    with aa._lock:
        conn = aa._connect()
        cur = conn.execute("INSERT INTO publishes (ts, by, pages, snapshot) VALUES (?,?,?,?)",
                           (int(time.time()), by[:200], count, snapshot))
        conn.commit()
    return {"pages": count, "id": int(cur.lastrowid)}


def publish_history(limit: int = 15) -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT id, ts, by, pages FROM publishes ORDER BY id DESC LIMIT ?",
        (max(1, min(50, limit)),)).fetchall()
    return [dict(r) for r in rows]


def source_mtime() -> int:
    """Newest change to the git-tracked page sources (a code deploy bumps it)."""
    newest = 0
    for cfg in PAGES.values():   # only built-ins have a file a deploy can change
        try:
            newest = max(newest, int((config.PUBLIC_DIR / cfg["file"]).stat().st_mtime))
        except OSError:
            continue
    return newest


def last_publish() -> dict | None:
    hist = publish_history(1)
    return hist[0] if hist else None


def rollback(publish_id: int, by: str) -> dict:
    from . import adminauth as aa

    row = aa._connect().execute("SELECT snapshot FROM publishes WHERE id=?",
                                (publish_id,)).fetchone()
    if row is None:
        raise ValueError("unknown publish version")
    data = json.loads(row["snapshot"])
    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM content")
        for r in data.get("content", []):
            conn.execute(
                "INSERT INTO content (page, key, lang, value, updated_at, updated_by) "
                "VALUES (?,?,?,?,?,?)",
                (r["page"], r["key"], r["lang"], r["value"], int(time.time()), by[:200]))
        conn.commit()
    from . import design

    design.restore_docs(data.get("designs", []))
    return publish_all(by, note=f"rollback to #{publish_id}")


def unpublish_all() -> bool:
    """Serve the original git HTML again (drafts are kept)."""
    if not PUBLISHED_DIR.exists():
        return False
    for f in PUBLISHED_DIR.glob("*.html"):
        f.unlink(missing_ok=True)
    (PUBLISHED_DIR / "sitemap.xml").unlink(missing_ok=True)
    ar_dir = PUBLISHED_DIR / "ar"
    if ar_dir.exists():
        for f in ar_dir.glob("*.html"):
            f.unlink(missing_ok=True)
    return True


_PUBLISHABLE = {cfg["file"] for cfg in PAGES.values()} | {"sitemap.xml"}


def default_language() -> str:
    """Which edition an unprefixed URL serves. Only a published language can
    be the default, so switching to Arabic before publishing it cannot leave
    the site serving nothing."""
    try:
        from . import adminauth as aa

        lang = str(aa.setting_get("site.defaultLanguage", "en") or "en").lower()
        published = [str(x).lower() for x in (aa.setting_get("site.languages") or ["en"])]
    except Exception:
        return "en"
    return lang if lang in ("en", "ar") and lang in published else "en"


def published_file(path: str) -> Path | None:
    """Called by the static server; must stay cheap and traversal-safe."""
    name = "index.html" if path in ("", ".", "/") else path
    prefix = ""
    asked_for_edition = False
    if name.startswith("ar/") or name == "ar":
        name = name[3:] or "index.html"
        name = name or "index.html"
        prefix = "ar/"
        asked_for_edition = True
    elif default_language() == "ar":
        # Arabic is the site default: an unprefixed URL serves that edition,
        # and /ar/… keeps working for anyone who has the link.
        prefix = "ar/"
    if name not in _PUBLISHABLE:
        # only an .html miss is worth a database lookup — every asset request
        # comes through here too and must stay allocation-cheap
        if not (name.endswith(".html") and _PAGE_SLUG_RE.match(name[:-5])
                and name[:-5] in _custom_slugs()):
            return None
    p = PUBLISHED_DIR / prefix / name
    if p.is_file():
        return p
    if prefix and not asked_for_edition:
        # the default edition is not baked yet — serve English rather than
        # nothing. A URL that asked for /ar/ explicitly still 404s, so an
        # unpublished edition is never silently served in another language.
        p = PUBLISHED_DIR / name
        return p if p.is_file() else None
    return None


# ---------------- rental inventory (runtime copy wins) ----------------

RENTAL_RUNTIME = config.RUNTIME_DIR / "data" / "rental-inventory.json"
_RENTAL_DEFAULT = Path(__file__).parent / "data" / "rental-inventory.json"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


def rentals_load() -> tuple[list[dict], str]:
    for path, source in ((RENTAL_RUNTIME, "custom"), (_RENTAL_DEFAULT, "default")):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("products", []), source
        except (OSError, ValueError):
            continue
    return [], "default"


def _clean_rental(item: dict) -> dict:
    def s(key, maxlen, required=False):
        v = re.sub(r"\s+", " ", str(item.get(key) or "")).strip()[:maxlen]
        if required and not v:
            raise ValueError(f"{key} is required")
        return v

    rid = str(item.get("id") or "").strip().lower()
    if not _SLUG_RE.match(rid):
        raise ValueError("id must be lowercase letters, digits and dashes (e.g. rent-led-wall)")

    def path_ok(p):
        p = str(p or "").strip()
        return p if re.match(r"^/(assets|media)/[\w./-]+$", p) else ""

    images = [path_ok(p) for p in (item.get("images") or [])]
    images = [p for p in images if p][:10]
    image = path_ok(item.get("image")) or (images[0] if images else "")
    stock = item.get("stockByMarket") or {}

    def qty(market):
        try:
            return max(0, min(100000, int(stock.get(market, 0))))
        except (TypeError, ValueError):
            return 0

    return {
        "id": rid,
        "code": s("code", 40),
        "name": s("name", 160, required=True),
        "category": s("category", 80, required=True),
        "featured": bool(item.get("featured")),
        "image": image,
        "images": images or ([image] if image else []),
        "description": str(item.get("description") or "").strip()[:2000],
        "tags": [s2 for s2 in (re.sub(r"\s+", " ", str(t)).strip()[:40]
                               for t in (item.get("tags") or [])) if s2][:12],
        "specs": [s2 for s2 in (re.sub(r"\s+", " ", str(t)).strip()[:200]
                                for t in (item.get("specs") or [])) if s2][:15],
        "stockByMarket": {"ksa": qty("ksa"), "uae": qty("uae")},
    }


def rentals_save_item(item: dict) -> dict:
    clean = _clean_rental(item)
    products, _ = rentals_load()
    for i, existing in enumerate(products):
        if existing.get("id") == clean["id"]:
            products[i] = clean
            break
    else:
        products.append(clean)
    _write_rentals(products)
    return clean


def rentals_delete_item(rid: str) -> bool:
    products, _ = rentals_load()
    kept = [p for p in products if p.get("id") != rid]
    if len(kept) == len(products):
        return False
    _write_rentals(kept)
    return True


def rentals_reset() -> bool:
    try:
        RENTAL_RUNTIME.unlink()
        return True
    except OSError:
        return False


def _write_rentals(products: list[dict]) -> None:
    RENTAL_RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    tmp = RENTAL_RUNTIME.with_suffix(".tmp")
    tmp.write_text(json.dumps({"products": products}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(RENTAL_RUNTIME)
