"""Elite Marcom admin — repeatable content: the lists a page is made of.

The design layer already lets an admin add, duplicate, reorder, hide and
delete whole SECTIONS. This module is the other half: the ITEMS inside a
section — the ten service cards, the eight service rows on the home page, the
values, the offices. Adding an eleventh service is a form, not a deployment.

How it hangs together
---------------------
A managed list is a container in the shipped HTML carrying ``data-em-list``:

    <div class="sc-grid" data-em-list="services-spaces"> … </div>

Each such name has a schema here: the fields an item has, a ``render`` that
writes the markup, and a ``parse`` that reads an item back out of the shipped
page. Two rules follow from that pairing, and everything else is detail:

* **The markup is ours, never an admin's.** ``render`` writes every tag; the
  admin supplies text, an image path and a link, each escaped or validated on
  the way in. Nothing typed in the panel is ever parsed as HTML.
* **An untouched list is the page.** ``parse`` reads the shipped markup, so a
  list nobody has edited has no database rows at all and follows the git HTML
  as it changes. The first edit materialises the list as it currently stands,
  and from then on the panel owns it — the same "runtime copy wins" bargain
  the rental inventory makes. Reset drops the rows and the page comes back.

Baking replaces each container's contents with the visible items, in the
stored order. A hidden item is simply not rendered.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import time
from html.parser import HTMLParser

MAX_ITEMS = 60          # a page section, not a database
MAX_FIELD = 4000


class CollectionError(Exception):
    """User-facing validation error."""


# ---------------- small HTML readers (our own markup, so class-based) ----------------

_VOID_TAGS = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input",
                        "link", "meta", "param", "source", "track", "wbr"))


class _Grab(HTMLParser):
    """Spans of elements carrying a given class, plus their attributes."""

    def __init__(self, want: str) -> None:
        super().__init__(convert_charrefs=False)
        self.want = want
        self.hits: list[dict] = []
        self._stack: list[dict] = []
        self._lines: list[int] = []
        self._raw = ""

    def _at(self) -> int:
        line, col = self.getpos()
        return (self._lines[line - 1] if 0 < line <= len(self._lines) else 0) + col

    def run(self, raw: str) -> list[dict]:
        self._raw = raw
        offset = 0
        for chunk in raw.split("\n"):
            self._lines.append(offset)
            offset += len(chunk) + 1
        try:
            self.feed(raw)
            self.close()
        except Exception:
            pass
        for open_ in self._stack:
            if open_["want"]:
                open_["end"] = len(raw)
                self.hits.append(open_)
        self.hits.sort(key=lambda h: h["start"])
        return self.hits

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            return  # never opens a scope, so it must not sit on the stack
        at = dict(attrs)
        classes = (at.get("class") or "").split()
        self._stack.append({"tag": tag, "attrs": at, "want": self.want in classes,
                            "start": self._at(), "end": -1})

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]["tag"] == tag:
                close = self._at() + len(tag) + 3
                for node in self._stack[i:]:
                    if node["want"]:
                        node["end"] = close
                        node["html"] = self._raw[node["start"]:close]
                        self.hits.append(node)
                del self._stack[i:]
                return


def elements_with_class(raw: str, cls: str) -> list[dict]:
    return _Grab(cls).run(raw)


def _first(raw: str, cls: str) -> dict | None:
    hits = elements_with_class(raw, cls)
    return hits[0] if hits else None


def text_of(raw: str, cls: str) -> str:
    """The readable text inside the first element with this class."""
    node = _first(raw, cls)
    return inner_text(node.get("html", "")) if node else ""


def inner_text(span: str) -> str:
    body = re.sub(r"^<[^>]*>", "", span)
    body = re.sub(r"</[a-zA-Z0-9]+>\s*$", "", body)
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    return html_mod.unescape(body).strip()


def attr_of(raw: str, cls: str, attr: str) -> str:
    node = _first(raw, cls)
    return (node["attrs"].get(attr) or "") if node else ""


def tag_attr(raw: str, tag: str, attr: str) -> str:
    m = re.search(rf"<{tag}\b[^>]*\s{attr}=\"([^\"]*)\"", raw, re.I)
    return html_mod.unescape(m.group(1)) if m else ""


def tag_text(raw: str, tag: str, nth: int = 0) -> str:
    found = re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", raw, re.I | re.S)
    return inner_text(found[nth]) if len(found) > nth else ""


def list_items(raw: str) -> list[str]:
    return [inner_text(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", raw, re.I | re.S)]


# ---------------- field values in, safe markup out ----------------

_IMG_RE = re.compile(r"^/(assets|media)/[\w./-]{1,240}$")
_HREF_RE = re.compile(r"^(https://|http://|mailto:|tel:|/|#)[^\s\"'<>]{0,280}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def clean_value(field: dict, value) -> str:
    """One field, validated by type. Raises CollectionError with a sentence an
    admin can act on — never a stack trace and never a silently dropped edit."""
    kind = field.get("type", "text")
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if kind in ("text", "link", "image", "slug"):
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
        text = re.sub(r"[ \t]+", " ", text)
    else:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    limit = min(int(field.get("max") or 300), MAX_FIELD)
    if len(text) > limit:
        raise CollectionError(f"{field['label']} is longer than {limit} characters.")
    if field.get("required") and not text:
        raise CollectionError(f"{field['label']} is required.")
    if text and kind == "image" and not _IMG_RE.match(text):
        raise CollectionError(f"{field['label']} must be an image from the Media library "
                              "or the site assets (a path starting /media/ or /assets/).")
    if text and kind == "link" and not _HREF_RE.match(text):
        raise CollectionError(f"{field['label']} must be a link starting https://, /, #, "
                              "mailto: or tel:.")
    if text and kind == "slug" and not _SLUG_RE.match(text):
        raise CollectionError(f"{field['label']} may use lowercase letters, numbers and "
                              "hyphens only.")
    if kind == "lines":
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()][:24]
        return "\n".join(lines)
    return text


def esc(value: str) -> str:
    return html_mod.escape(value or "", quote=True)


def _lines(value: str) -> list[str]:
    return [ln for ln in (value or "").split("\n") if ln.strip()]


# ---------------- item renderers (every tag written here, by us) ----------------

_ARROW = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
          'aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6"/></svg>')


def _render_service_card(v: dict, i: int) -> str:
    anchor = v.get("anchor") or ""
    ident = f' id="{esc(anchor)}"' if anchor else ""
    labelled = f' aria-labelledby="{esc(anchor)}-h"' if anchor else ""
    head_id = f' id="{esc(anchor)}-h"' if anchor else ""
    includes = "".join(f"\n                <li>{esc(x)}</li>" for x in _lines(v.get("includes", "")))
    spec = (f'\n              <div class="sc-card__spec"><h4>{esc(v.get("specTitle") or "What it includes")}</h4>'
            f"<ul>{includes}\n                </ul></div>" if includes else "")
    link = v.get("link") or ""
    go = (f'\n              <a class="sc-card__go" href="{esc(link)}">'
          f'{esc(v.get("linkLabel") or "Talk to us about this")} {_ARROW}</a>' if link else "")
    img = v.get("image") or ""
    media = (f'\n            <div class="sc-card__media">'
             f'\n              <img src="{esc(img)}" alt="{esc(v.get("imageAlt") or v.get("name", ""))}" '
             f'width="560" height="350" loading="lazy">'
             f'\n              <span class="sc-card__hint" aria-hidden="true"><i></i>Hover for detail</span>'
             f"\n            </div>" if img else "")
    return (f'<article class="sc-card sc-anim"{ident} style="--d:{i * 0.09:.2f}s"{labelled}>{media}'
            f'\n            <div class="sc-card__body">'
            f'\n              <p class="sc-card__eyebrow">{esc(v.get("eyebrow", ""))}</p>'
            f'\n              <h3 class="sc-card__name"{head_id}>{esc(v.get("name", ""))}</h3>'
            f'\n              <p class="sc-card__desc">{esc(v.get("description", ""))}</p>'
            f"{spec}{go}"
            f"\n            </div>\n          </article>")


def _parse_service_card(raw: str) -> dict:
    spec = _first(raw, "sc-card__spec")
    return {
        "anchor": tag_attr(raw, "article", "id"),
        "eyebrow": text_of(raw, "sc-card__eyebrow"),
        "name": text_of(raw, "sc-card__name"),
        "description": text_of(raw, "sc-card__desc"),
        "image": tag_attr(raw, "img", "src"),
        "imageAlt": tag_attr(raw, "img", "alt"),
        "specTitle": tag_text(spec["html"], "h4") if spec else "",
        "includes": "\n".join(list_items(raw)),
        "linkLabel": re.sub(r"\s+", " ", text_of(raw, "sc-card__go")).strip(),
        "link": attr_of(raw, "sc-card__go", "href"),
    }


_SERVICE_FIELDS = [
    {"key": "name", "label": "Service name", "type": "text", "max": 120, "required": True},
    {"key": "eyebrow", "label": "Chapter label", "type": "text", "max": 80,
     "hint": "The small line above the name."},
    {"key": "description", "label": "Short description", "type": "textarea", "max": 400},
    {"key": "image", "label": "Image", "type": "image", "max": 240},
    {"key": "imageAlt", "label": "Image description", "type": "text", "max": 240,
     "hint": "What the picture shows, for screen readers and search."},
    {"key": "specTitle", "label": "Detail panel heading", "type": "text", "max": 80},
    {"key": "includes", "label": "What it includes", "type": "lines", "max": 1600,
     "hint": "One line per point."},
    {"key": "linkLabel", "label": "Button label", "type": "text", "max": 80},
    {"key": "link", "label": "Button link", "type": "link", "max": 300},
    {"key": "anchor", "label": "Anchor id", "type": "slug", "max": 60,
     "hint": "Used by links like /services.html#branding. Leave alone unless you know why."},
]


def _render_service_row(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 40}"' if i else ""
    preview = f' data-preview="{esc(v["preview"])}"' if v.get("preview") else ""
    return (f'<a role="listitem" class="service-row reveal" data-reveal="fade-up"{delay} '
            f'href="{esc(v.get("link") or "#")}"{preview}>'
            f'\n            <span class="service-row__num">{i + 1:02d}</span>'
            f'<span class="service-row__name">{esc(v.get("name", ""))}</span>'
            f'\n            <span class="service-row__hint">{esc(v.get("hint", ""))}</span>'
            f'<span class="service-row__arrow" aria-hidden="true">→</span>\n          </a>')


def _parse_service_row(raw: str) -> dict:
    return {
        "name": text_of(raw, "service-row__name"),
        "hint": text_of(raw, "service-row__hint"),
        "link": tag_attr(raw, "a", "href"),
        "preview": tag_attr(raw, "a", "data-preview"),
    }


_SERVICE_ROW_FIELDS = [
    {"key": "name", "label": "Name", "type": "text", "max": 120, "required": True},
    {"key": "hint", "label": "Supporting line", "type": "text", "max": 160},
    {"key": "link", "label": "Link", "type": "link", "max": 300},
    {"key": "preview", "label": "Preview image", "type": "image", "max": 240,
     "hint": "Shown beside the list when someone hovers this row."},
]


def _render_value(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 80}"' if i else ""
    return (f'<div class="value reveal" data-reveal="fade-up"{delay}>'
            f'\n          <dt>{esc(v.get("title", ""))}</dt>'
            f'\n          <dd>{esc(v.get("text", ""))}</dd>\n        </div>')


def _parse_value(raw: str) -> dict:
    return {"title": tag_text(raw, "dt"), "text": tag_text(raw, "dd")}


_VALUE_FIELDS = [
    {"key": "title", "label": "Title", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "Description", "type": "textarea", "max": 400},
]

_CHIP_TONES = ("chip", "chip--orange", "chip--violet")


def _render_presence(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 90}"' if i else ""
    tone = v.get("tone") if v.get("tone") in _CHIP_TONES else "chip"
    tone_cls = "chip" if tone == "chip" else f"chip {tone}"
    chip = (f'\n          <span class="{esc(tone_cls)}">{esc(v["chip"])}</span>'
            if v.get("chip") else "")
    return (f'<article class="presence-card reveal" data-reveal="fade-up"{delay}>{chip}'
            f'\n          <h3>{esc(v.get("title", ""))}</h3>'
            f'\n          <p>{esc(v.get("text", ""))}</p>\n        </article>')


def _parse_presence(raw: str) -> dict:
    node = _first(raw, "chip")
    tone = "chip"
    if node:
        for cls in (node["attrs"].get("class") or "").split():
            if cls in _CHIP_TONES and cls != "chip":
                tone = cls
    return {"chip": text_of(raw, "chip"), "tone": tone,
            "title": tag_text(raw, "h3"), "text": tag_text(raw, "p")}


_PRESENCE_FIELDS = [
    {"key": "title", "label": "Place", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "Description", "type": "textarea", "max": 400},
    {"key": "chip", "label": "Badge", "type": "text", "max": 40},
    {"key": "tone", "label": "Badge colour", "type": "select", "max": 20,
     "options": [{"value": "chip", "label": "Neutral"},
                 {"value": "chip--orange", "label": "Orange"},
                 {"value": "chip--violet", "label": "Violet"}]},
]


# ---------------- the managed lists ----------------
# Adding another one is this table plus a data-em-list attribute on the page.

def _service_list(name: str, label: str, hint: str) -> dict:
    return {"label": label, "page": "services", "hint": hint,
            "itemLabel": "service", "itemClass": "sc-card", "fields": _SERVICE_FIELDS,
            "render": _render_service_card, "parse": _parse_service_card,
            "titleField": "name", "imageField": "image"}


SCHEMAS: dict[str, dict] = {
    "services-spaces": _service_list(
        "services-spaces", "Services — Spaces & fit-out",
        "The service cards in the first chapter of the Services page."),
    "services-events": _service_list(
        "services-events", "Services — Events & operations",
        "The service cards in the second chapter of the Services page."),
    "services-brand": _service_list(
        "services-brand", "Services — Brand & media",
        "The service cards in the third chapter of the Services page."),
    "home-services": {
        "label": "Home — what we do", "page": "index",
        "hint": "The numbered list of services on the home page. Numbering is automatic.",
        "itemLabel": "row", "itemClass": "service-row", "fields": _SERVICE_ROW_FIELDS,
        "render": _render_service_row, "parse": _parse_service_row,
        "titleField": "name", "imageField": "preview"},
    "about-values": {
        "label": "About — mission & values", "page": "about",
        "hint": "The values listed on the About page.",
        "itemLabel": "value", "itemClass": "value", "fields": _VALUE_FIELDS,
        "render": _render_value, "parse": _parse_value,
        "titleField": "title", "imageField": ""},
    "about-presence": {
        "label": "About — where we work", "page": "about",
        "hint": "The office / presence cards on the About page.",
        "itemLabel": "location", "itemClass": "presence-card", "fields": _PRESENCE_FIELDS,
        "render": _render_presence, "parse": _parse_presence,
        "titleField": "title", "imageField": ""},
}


def schema(name: str) -> dict:
    spec = SCHEMAS.get(name)
    if spec is None:
        raise CollectionError("That content list does not exist.")
    return spec


def page_label(page: str) -> str:
    from . import content

    cfg = content.all_pages().get(page) or {}
    return cfg.get("label") or page


def public_schema(name: str) -> dict:
    """The schema as the panel needs it — no Python callables."""
    spec = schema(name)
    return {"id": name, "label": spec["label"], "page": spec["page"],
            "pageLabel": page_label(spec["page"]),
            "hint": spec.get("hint", ""), "itemLabel": spec.get("itemLabel", "item"),
            "fields": spec["fields"], "titleField": spec.get("titleField", ""),
            "imageField": spec.get("imageField", "")}


# ---------------- reading the shipped page ----------------

def _container(raw: str, name: str) -> dict | None:
    """The span of the container carrying data-em-list="name"."""
    m = re.search(rf'<([a-z][a-z0-9]*)\b[^>]*\sdata-em-list="{re.escape(name)}"[^>]*>', raw, re.I)
    if not m:
        return None
    tag = m.group(1)
    open_re = re.compile(rf"<{tag}\b", re.I)
    close_re = re.compile(rf"</{tag}\s*>", re.I)
    depth, at = 1, m.end()
    while depth > 0 and at < len(raw):
        nxt_open = open_re.search(raw, at)
        nxt_close = close_re.search(raw, at)
        if not nxt_close:
            return None
        if nxt_open and nxt_open.start() < nxt_close.start():
            depth += 1
            at = nxt_open.end()
        else:
            depth -= 1
            at = nxt_close.end()
            if depth == 0:
                return {"start": m.start(), "contentStart": m.end(),
                        "contentEnd": nxt_close.start(), "end": at}
    return None


def shipped_items(name: str) -> list[dict]:
    """The list exactly as it stands in the git HTML — the starting point for
    a collection nobody has edited yet."""
    from . import content

    spec = schema(name)
    try:
        raw = content.page_source(spec["page"])
    except Exception:
        return []
    box = _container(raw, name)
    if box is None:
        return []
    inner = raw[box["contentStart"]:box["contentEnd"]]
    out = []
    for i, node in enumerate(elements_with_class(inner, spec["itemClass"])):
        values = spec["parse"](node.get("html", ""))
        out.append({"id": f"d{i + 1}", "hidden": False, "shipped": True, "values": values})
    return out


# ---------------- storage (admin.db) ----------------

def _rows(name: str) -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT item_id, position, hidden, data FROM collection_items "
        "WHERE collection=? ORDER BY position, id", (name,)).fetchall()
    out = []
    for r in rows:
        try:
            values = json.loads(r["data"])
        except ValueError:
            values = {}
        out.append({"id": r["item_id"], "hidden": bool(r["hidden"]),
                    "shipped": False, "values": values if isinstance(values, dict) else {}})
    return out


def is_managed(name: str) -> bool:
    from . import adminauth as aa

    row = aa._connect().execute(
        "SELECT 1 FROM collection_items WHERE collection=? LIMIT 1", (name,)).fetchone()
    return row is not None


def items(name: str) -> list[dict]:
    """The current list: the panel's copy once anything has been edited,
    otherwise whatever the shipped page says today."""
    schema(name)
    return _rows(name) if is_managed(name) else shipped_items(name)


def _write(name: str, rows: list[dict], by: str) -> None:
    from . import adminauth as aa

    if len(rows) > MAX_ITEMS:
        raise CollectionError(f"A list can hold up to {MAX_ITEMS} items.")
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM collection_items WHERE collection=?", (name,))
        conn.executemany(
            "INSERT INTO collection_items (collection, item_id, position, hidden, data, "
            "updated_at, updated_by) VALUES (?,?,?,?,?,?,?)",
            [(name, r["id"], i, 1 if r["hidden"] else 0,
              json.dumps(r["values"], ensure_ascii=False), now, by[:200])
             for i, r in enumerate(rows)])
        conn.commit()


def _materialised(name: str) -> list[dict]:
    """The list as editable rows. The first edit to an untouched collection
    copies the shipped items in, so the admin edits what they were looking at
    rather than an empty screen."""
    rows = items(name)
    for r in rows:
        r["shipped"] = False
    return rows


def _clean_values(name: str, values: dict) -> dict:
    spec = schema(name)
    if not isinstance(values, dict):
        raise CollectionError("Send the item's fields as an object.")
    out = {}
    for field in spec["fields"]:
        out[field["key"]] = clean_value(field, values.get(field["key"], ""))
    if spec.get("titleField") and not out.get(spec["titleField"]):
        raise CollectionError("Give the item a name before saving it.")
    return out


def _next_id(rows: list[dict]) -> str:
    used = {r["id"] for r in rows}
    n = 1
    while f"i{n}" in used:
        n += 1
    return f"i{n}"


def add_item(name: str, values: dict, by: str) -> dict:
    rows = _materialised(name)
    item = {"id": _next_id(rows), "hidden": False, "shipped": False,
            "values": _clean_values(name, values)}
    rows.append(item)
    _write(name, rows, by)
    return item


def update_item(name: str, item_id: str, values: dict, by: str) -> dict:
    rows = _materialised(name)
    for row in rows:
        if row["id"] == item_id:
            row["values"] = _clean_values(name, values)
            _write(name, rows, by)
            return row
    raise CollectionError("That item is no longer in the list — reload the screen.")


def duplicate_item(name: str, item_id: str, by: str) -> dict:
    """A copy placed directly after the original, so it is where the eye is."""
    spec = schema(name)
    rows = _materialised(name)
    for i, row in enumerate(rows):
        if row["id"] == item_id:
            values = dict(row["values"])
            title = spec.get("titleField")
            if title and values.get(title):
                values[title] = f"{values[title]} (copy)"[:300]
            # an anchor is an address; two items must never share one
            for field in spec["fields"]:
                if field["type"] == "slug" and values.get(field["key"]):
                    values[field["key"]] = f"{values[field['key']]}-copy"[:60]
            copy = {"id": _next_id(rows), "hidden": row["hidden"], "shipped": False,
                    "values": values}
            rows.insert(i + 1, copy)
            _write(name, rows, by)
            return copy
    raise CollectionError("That item is no longer in the list — reload the screen.")


def delete_item(name: str, item_id: str, by: str) -> bool:
    rows = _materialised(name)
    kept = [r for r in rows if r["id"] != item_id]
    if len(kept) == len(rows):
        return False
    _write(name, kept, by)
    return True


def set_hidden(name: str, item_id: str, hidden: bool, by: str) -> bool:
    rows = _materialised(name)
    for row in rows:
        if row["id"] == item_id:
            row["hidden"] = bool(hidden)
            _write(name, rows, by)
            return True
    return False


def reorder(name: str, order: list[str], by: str) -> list[dict]:
    rows = _materialised(name)
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[i] for i in order if i in by_id]
    # anything the caller did not mention keeps its place at the end, so a
    # stale screen can never delete an item by omitting it
    ordered += [r for r in rows if r["id"] not in set(order)]
    _write(name, ordered, by)
    return ordered


def reset(name: str, by: str) -> list[dict]:
    """Give the list back to the page. The rows go; the git HTML returns."""
    from . import adminauth as aa

    schema(name)
    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM collection_items WHERE collection=?", (name,))
        conn.commit()
    return shipped_items(name)


def summary() -> list[dict]:
    out = []
    for name in SCHEMAS:
        rows = items(name)
        out.append({**public_schema(name), "count": len(rows),
                    "hidden": sum(1 for r in rows if r["hidden"]),
                    "managed": is_managed(name)})
    return out


def all_rows() -> list[dict]:
    """Everything, for a backup."""
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT collection, item_id, position, hidden, data, updated_at, updated_by "
        "FROM collection_items ORDER BY collection, position").fetchall()
    return [dict(r) for r in rows]


def restore_rows(rows: list[dict]) -> None:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM collection_items")
        for r in rows or []:
            if r.get("collection") not in SCHEMAS:
                continue
            conn.execute(
                "INSERT INTO collection_items (collection, item_id, position, hidden, data, "
                "updated_at, updated_by) VALUES (?,?,?,?,?,?,?)",
                (r["collection"], str(r.get("item_id") or "")[:40], int(r.get("position") or 0),
                 1 if r.get("hidden") else 0, str(r.get("data") or "{}"),
                 int(r.get("updated_at") or 0), str(r.get("updated_by") or "")[:200]))
        conn.commit()


def last_edit_ts() -> int:
    from . import adminauth as aa

    row = aa._connect().execute("SELECT MAX(updated_at) AS t FROM collection_items").fetchone()
    return int(row["t"] or 0) if row else 0


# ---------------- bake ----------------

def render_list(name: str) -> str:
    spec = schema(name)
    visible = [r for r in items(name) if not r["hidden"]]
    return "\n          ".join(spec["render"](r["values"], i) for i, r in enumerate(visible))


def _containers(raw: str, name: str) -> list[dict]:
    """Every container for this list, in document order. A section the admin
    duplicated brings its container with it, so there can be more than one."""
    out, at = [], 0
    while len(out) < 12:
        box = _container(raw[at:], name)
        if box is None:
            break
        out.append({k: v + at for k, v in box.items()})
        at = out[-1]["end"]
    return out


def apply_to_page(raw: str, page: str) -> str:
    """Replace every managed container on this page with its current items.

    Runs after the design layer, so a section an admin duplicated carries the
    list too, and a section they removed takes its list with it. Containers are
    filled from the last one backwards: replacing the first would move every
    offset after it.
    """
    for name, spec in SCHEMAS.items():
        if spec["page"] != page:
            continue
        boxes = _containers(raw, name)
        if not boxes:
            continue
        markup = render_list(name)
        body = f"\n          {markup}\n        " if markup else ""
        for box in reversed(boxes):
            raw = raw[:box["contentStart"]] + body + raw[box["contentEnd"]:]
    return raw
