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

GLOBAL_REGIONS = [
    {"key": "nav.home", "label": "Menu — Home", "kind": "text"},
    {"key": "nav.about", "label": "Menu — About", "kind": "text"},
    {"key": "nav.services", "label": "Menu — Services", "kind": "text"},
    {"key": "nav.projects", "label": "Menu — Projects", "kind": "text"},
    {"key": "nav.gifts", "label": "Menu — Corporate Gifts", "kind": "text"},
    {"key": "nav.rental", "label": "Menu — Rental", "kind": "text"},
    {"key": "nav.careers", "label": "Menu — Careers", "kind": "text"},
    {"key": "nav.contact", "label": "Menu — Contact", "kind": "text"},
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
    "product": {"label": "Gift product page", "file": "product.html", "regions": []},
    "rental-item": {"label": "Rental item page", "file": "rental-item.html", "regions": []},
}

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


def _valid_keys(page: str) -> set[str]:
    if page == "_global":
        return {r["key"] for r in GLOBAL_REGIONS}
    cfg = PAGES.get(page)
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
    raw = (config.PUBLIC_DIR / PAGES[page]["file"]).read_text(encoding="utf-8")
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
    from . import design

    cfg = PAGES[page]
    raw = (config.PUBLIC_DIR / cfg["file"]).read_text(encoding="utf-8")
    raw = design.apply_to_page(raw, page)
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


# ---------------- publish, history, rollback ----------------

def _sitemap_xml() -> str:
    today = time.strftime("%Y-%m-%d")
    urls = []
    for page, cfg in PAGES.items():
        loc = SITE_ORIGIN + ("/" if page == "index" else f"/{cfg['file']}")
        urls.append(f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def publish_all(by: str, note: str = "") -> dict:
    from . import adminauth as aa

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for page, cfg in PAGES.items():
        baked = bake_page(page, "en")
        tmp = PUBLISHED_DIR / (cfg["file"] + ".tmp")
        tmp.write_text(baked, encoding="utf-8")
        tmp.replace(PUBLISHED_DIR / cfg["file"])
        count += 1
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
    for f in PUBLISHED_DIR.glob("*"):
        f.unlink(missing_ok=True)
    return True


_PUBLISHABLE = {cfg["file"] for cfg in PAGES.values()} | {"sitemap.xml"}


def published_file(path: str) -> Path | None:
    """Called by the static server; must stay cheap and traversal-safe."""
    name = "index.html" if path in ("", ".", "/") else path
    if name not in _PUBLISHABLE:
        return None
    p = PUBLISHED_DIR / name
    return p if p.is_file() else None


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
