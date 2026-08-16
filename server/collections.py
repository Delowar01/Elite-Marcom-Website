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
     "hint": "Used by links like /services#branding. Leave alone unless you know why."},
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



# ---------------- shared renderers (one shape used by several pages) ----------------
# A stat row, a marquee, a process ladder and a set of assurance cards appear on
# more than one page with identical markup. One render/parse pair each, pointed
# at by several schemas, so the four copies can never drift apart.

# A product page and a rental item page are not in the menu; they belong to
# the section they were opened from, and that is the link that should read as
# the current one.
NAV_PARENT = {"product": "giveaways", "rental-item": "rental"}


def page_href(page: str) -> str:
    """The address a page is reached at — what a menu link must match to be
    marked as the current one. The slug *is* the address: public pages are
    served without the .html the file still carries."""
    page = NAV_PARENT.get(page, page)
    if not page or page in GLOBAL_PAGES:
        return ""
    return "/" if page == "index" else "/" + page


def _is_current(link: str, page: str) -> str:
    here = page_href(page)
    return ' aria-current="page"' if here and (link or "/") == here else ""


def _render_nav_link(v: dict, i: int, page: str = "") -> str:
    href = v.get("link") or "/"
    return (f'<li><a href="{esc(href)}"{_is_current(href, page)}>'
            f'{esc(v.get("label", ""))}</a></li>')


def _render_footer_link(v: dict, i: int) -> str:
    return f'<li><a href="{esc(v.get("link") or "/")}">{esc(v.get("label", ""))}</a></li>'


def _parse_nav_link(raw: str) -> dict:
    return {"label": tag_text(raw, "a"), "link": tag_attr(raw, "a", "href")}


_NAV_FIELDS = [
    {"key": "label", "label": "Label", "type": "text", "max": 60, "required": True},
    {"key": "link", "label": "Link", "type": "link", "max": 300, "required": True},
]


def _render_menu_link(v: dict, i: int, page: str = "") -> str:
    """The slide-in panel: same links, numbered, and the numbering is ours."""
    href = v.get("link") or "/"
    return (f'<li><a href="{esc(href)}"{_is_current(href, page)}>'
            f'<span class="num">{i + 1:02d}</span>{esc(v.get("label", ""))}</a></li>')


def _parse_menu_link(raw: str) -> dict:
    label = inner_text(re.sub(r'<span class="num">.*?</span>', "", raw, flags=re.S))
    return {"label": label, "link": tag_attr(raw, "a", "href")}


def _render_stat(v: dict, i: int) -> str:
    return (f'<div class="stat"><dt class="stat__num">{esc(v.get("value", ""))}</dt>'
            f'<dd class="stat__label">{esc(v.get("label", ""))}</dd></div>')


def _parse_stat(raw: str) -> dict:
    return {"value": text_of(raw, "stat__num"), "label": text_of(raw, "stat__label")}


_STAT_FIELDS = [
    {"key": "value", "label": "Figure", "type": "text", "max": 40, "required": True,
     "hint": "The large line — 360°, KSA + UAE, 1 team."},
    {"key": "label", "label": "What it means", "type": "text", "max": 90},
]


def _render_marquee_item(v: dict, i: int) -> str:
    return f'<span class="marquee__item">{esc(v.get("text", ""))}</span>'


def _parse_marquee_item(raw: str) -> dict:
    return {"text": inner_text(raw)}


_MARQUEE_FIELDS = [
    {"key": "text", "label": "Word", "type": "text", "max": 60, "required": True},
]


def _render_process_step(v: dict, i: int) -> str:
    return (f'<li class="process__step"><span class="process__dot" aria-hidden="true"></span>'
            f'<span class="process__num">{esc(v.get("num", ""))}</span>'
            f'<h3>{esc(v.get("title", ""))}</h3>'
            f'<p>{esc(v.get("text", ""))}</p></li>')


def _parse_process_step(raw: str) -> dict:
    return {"num": text_of(raw, "process__num"), "title": tag_text(raw, "h3"),
            "text": tag_text(raw, "p")}


_PROCESS_FIELDS = [
    {"key": "num", "label": "Stage label", "type": "text", "max": 24, "required": True,
     "hint": "Written out, so it can read 01 or STAGE 01."},
    {"key": "title", "label": "Title", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "What happens", "type": "textarea", "max": 400},
]


def _render_assurance(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 80}"' if i else ""
    num = v.get("num") or f"{i + 1:02d}"
    return (f'<article class="assure reveal" data-reveal="fade-up"{delay}>'
            f'<span class="assure__num">{esc(num)}</span>'
            f'<h3>{esc(v.get("title", ""))}</h3>'
            f'<p>{esc(v.get("text", ""))}</p></article>')


def _parse_assurance(raw: str) -> dict:
    return {"num": text_of(raw, "assure__num"), "title": tag_text(raw, "h3"),
            "text": tag_text(raw, "p")}


_ASSURE_FIELDS = [
    {"key": "num", "label": "Step number", "type": "text", "max": 8,
     "hint": "Leave empty to number automatically."},
    {"key": "title", "label": "Title", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "Description", "type": "textarea", "max": 400},
]


def _chip_class(tone: str) -> str:
    tone = tone if tone in _CHIP_TONES else "chip"
    return "chip" if tone == "chip" else f"chip {tone}"


_CHIP_TONE_FIELD = {
    "key": "tone", "label": "Colour", "type": "select", "max": 20,
    "options": [{"value": "chip", "label": "Neutral"},
                {"value": "chip--orange", "label": "Orange"},
                {"value": "chip--violet", "label": "Violet"}],
}


def _render_chip(v: dict, i: int) -> str:
    """A plain badge, or a link when one is given."""
    cls = _chip_class(v.get("tone", ""))
    if v.get("link"):
        return f'<li><a class="{esc(cls)}" href="{esc(v["link"])}">{esc(v.get("label", ""))}</a></li>'
    return f'<span class="{esc(cls)}">{esc(v.get("label", ""))}</span>'


def _parse_chip(raw: str) -> dict:
    node = _first(raw, "chip")
    tone = "chip"
    if node:
        for cls in (node["attrs"].get("class") or "").split():
            if cls in _CHIP_TONES and cls != "chip":
                tone = cls
    return {"label": inner_text(node["html"]) if node else inner_text(raw),
            "link": tag_attr(raw, "a", "href"), "tone": tone}


_CHIP_FIELDS = [
    {"key": "label", "label": "Label", "type": "text", "max": 60, "required": True},
    {"key": "link", "label": "Link", "type": "link", "max": 300,
     "hint": "Leave empty for a badge that is not clickable."},
    _CHIP_TONE_FIELD,
]


def _render_work_card(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 70}"' if i else ""
    tall = " work-card--tall" if v.get("tall") == "yes" else ""
    img = v.get("image") or ""
    media = (f'\n            <figure class="media-frame media-frame--sheen" data-parallax="0.05">'
             f'\n              <img src="{esc(img)}" alt="{esc(v.get("imageAlt") or v.get("title", ""))}" '
             f'{_dims(v)}loading="lazy">\n            </figure>' if img else "")
    chip = (f'\n              <span class="{esc(_chip_class(v.get("tone", "")))}">{esc(v["chip"])}</span>'
            if v.get("chip") else "")
    return (f'<a class="work-card{tall} reveal" data-reveal="zoom-up"{delay} '
            f'href="{esc(v.get("link") or "#")}">{media}'
            f'\n            <div class="work-card__meta">{chip}'
            f'\n              <h3>{esc(v.get("title", ""))}</h3>'
            f'\n              <p>{esc(v.get("text", ""))}</p>'
            f"\n            </div>\n          </a>")


def _dims(v: dict, w: str = "width", h: str = "height") -> str:
    """The picture's own width and height when the page had them — a fixed pair
    would put every image in the wrong aspect box."""
    out = ""
    if str(v.get(w) or "").isdigit():
        out += f'width="{esc(str(v[w]))}" '
    if str(v.get(h) or "").isdigit():
        out += f'height="{esc(str(v[h]))}" '
    return out


def _parse_work_card(raw: str) -> dict:
    node = _first(raw, "work-card")
    classes = (node["attrs"].get("class") or "").split() if node else []
    chip_node = _first(raw, "chip")
    tone = "chip"
    if chip_node:
        for cls in (chip_node["attrs"].get("class") or "").split():
            if cls in _CHIP_TONES and cls != "chip":
                tone = cls
    return {"title": tag_text(raw, "h3"), "text": tag_text(raw, "p"),
            "chip": text_of(raw, "chip"), "tone": tone,
            "image": tag_attr(raw, "img", "src"), "imageAlt": tag_attr(raw, "img", "alt"),
            "width": tag_attr(raw, "img", "width"), "height": tag_attr(raw, "img", "height"),
            "link": tag_attr(raw, "a", "href"),
            "tall": "yes" if "work-card--tall" in classes else "no"}


_WORK_FIELDS = [
    {"key": "title", "label": "Project name", "type": "text", "max": 90, "required": True},
    {"key": "text", "label": "One-line description", "type": "textarea", "max": 300},
    {"key": "chip", "label": "Badge", "type": "text", "max": 40},
    _CHIP_TONE_FIELD,
    {"key": "image", "label": "Image", "type": "image", "max": 240},
    {"key": "imageAlt", "label": "Image description", "type": "text", "max": 240},
    {"key": "link", "label": "Link", "type": "link", "max": 300},
    {"key": "tall", "label": "Feature this one", "type": "select", "max": 4,
     "hint": "A featured card fills two rows of the grid.",
     "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}]},
]


def _render_model_card(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 90}"' if i else ""
    return (f'<article class="model-card reveal" data-reveal="fade-up"{delay}>'
            f'\n          <span class="model-card__num">{esc(v.get("mark", ""))}</span>'
            f'\n          <h3>{esc(v.get("title", ""))}</h3>'
            f'\n          <p>{esc(v.get("text", ""))}</p>\n        </article>')


def _parse_model_card(raw: str) -> dict:
    return {"mark": text_of(raw, "model-card__num"), "title": tag_text(raw, "h3"),
            "text": tag_text(raw, "p")}


_MODEL_FIELDS = [
    {"key": "mark", "label": "Letter", "type": "text", "max": 8, "required": True},
    {"key": "title", "label": "Title", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "Description", "type": "textarea", "max": 500},
]


def _render_diff(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 70}"' if i else ""
    return (f'<div class="diff reveal" data-reveal="fade-up"{delay}>'
            f'\n            <h3>{esc(v.get("title", ""))}</h3>'
            f'\n            <p>{esc(v.get("text", ""))}</p>\n          </div>')


def _parse_diff(raw: str) -> dict:
    return {"title": tag_text(raw, "h3"), "text": tag_text(raw, "p")}


_DIFF_FIELDS = [
    {"key": "title", "label": "Title", "type": "text", "max": 80, "required": True},
    {"key": "text", "label": "Description", "type": "textarea", "max": 600},
]


def _render_office(v: dict, i: int) -> str:
    delay = f' data-reveal-delay="{i * 90}"' if i else ""
    chip = (f'\n          <span class="{esc(_chip_class(v.get("tone", "")))}">{esc(v["chip"])}</span>'
            if v.get("chip") else "")
    address = "<br>".join(esc(ln) for ln in _lines(v.get("address", "")))
    reach = []
    for line in _lines(v.get("contacts", "")):
        label, href = _split_fact(line)
        if not label or not href:
            continue
        out = f'href="{esc(href)}"'
        if href.startswith("http"):
            out += ' rel="noopener" target="_blank"'
        reach.append(f"<a {out}>{esc(label)}</a>")
    contact = (f'\n          <p style="margin-top:10px;">{"<br>".join(reach)}</p>' if reach else "")
    return (f'<article class="presence-card reveal" data-reveal="fade-up"{delay}>{chip}'
            f'\n          <h3>{esc(v.get("title", ""))}</h3>'
            f'\n          <p>{address}</p>{contact}\n        </article>')


def _parse_office(raw: str) -> dict:
    node = _first(raw, "chip")
    tone = "chip"
    if node:
        for cls in (node["attrs"].get("class") or "").split():
            if cls in _CHIP_TONES and cls != "chip":
                tone = cls
    paras = re.findall(r"<p\b[^>]*>(.*?)</p>", raw, re.S)
    address = inner_text(re.sub(r"<br\s*/?>", "\n", paras[0])) if paras else ""
    tail = paras[1] if len(paras) > 1 else ""
    links = re.findall(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', tail, re.S)
    return {"chip": text_of(raw, "chip"), "tone": tone, "title": tag_text(raw, "h3"),
            "address": "\n".join(ln.strip() for ln in address.split("\n") if ln.strip()),
            "contacts": "\n".join(f"{inner_text(lbl)} | {href}" for href, lbl in links)}


_OFFICE_FIELDS = [
    {"key": "title", "label": "City", "type": "text", "max": 80, "required": True},
    {"key": "chip", "label": "Badge", "type": "text", "max": 60},
    _CHIP_TONE_FIELD,
    {"key": "address", "label": "Address", "type": "lines", "max": 400,
     "hint": "One line per line of the address."},
    {"key": "contacts", "label": "Ways to reach this office", "type": "lines", "max": 600,
     "hint": "One per line, as “+966 59 925 5995 | tel:+966599255995”."},
]


def _render_case(v: dict, i: int) -> str:
    anchor = v.get("anchor") or f"case{i + 1}"
    hid = f"case-{anchor}-h"
    def frame(src, alt, dims, extra, reveal, delay, parallax):
        if not src:
            return ""
        cls = f"media-frame {extra}".strip()
        d = f' data-reveal-delay="{delay}"' if delay else ""
        return (f'\n            <figure class="{cls} reveal" data-reveal="{reveal}"{d} '
                f'data-parallax="{parallax}">'
                f'\n              <img src="{esc(src)}" alt="{esc(alt)}" {dims}'
                f'loading="lazy">\n            </figure>')
    media = (frame(v.get("image"), v.get("imageAlt") or v.get("title", ""), _dims(v),
                   "media-frame--sheen", "zoom-up", 0, "0.05") +
             frame(v.get("image2"), v.get("image2Alt") or v.get("title", ""),
                   _dims(v, "width2", "height2"), "case__inset",
                   v.get("inset") if v.get("inset") in ("slide-left", "slide-right")
                   else "slide-right", 140, "0.1"))
    facts = "".join(
        f"\n              <div><dt>{esc(a)}</dt><dd>{esc(b)}</dd></div>"
        for a, b in (_split_fact(ln) for ln in _lines(v.get("facts", ""))) if a)
    fact_block = (f'\n            <dl class="case__facts reveal" data-reveal="fade-up" '
                  f'data-reveal-delay="130">{facts}\n            </dl>' if facts else "")
    chip = (f'\n            <span class="{esc(_chip_class(v.get("tone", "")))} reveal" '
            f'data-reveal="fade-in">{esc(v["chip"])}</span>' if v.get("chip") else "")
    open_id = v.get("openId") or anchor
    button = (f'\n            <button class="link-arrow reveal" data-reveal="fade-up" '
              f'data-reveal-delay="180" type="button" data-open-project="{esc(open_id)}">'
              f'{esc(v.get("buttonLabel") or "View project details")}</button>'
              if v.get("buttonLabel") or open_id else "")
    return (f'<article class="case" id="{esc(anchor)}" aria-labelledby="{esc(hid)}">'
            f'\n          <div class="case__media">{media}\n          </div>'
            f"\n          <div>{chip}"
            f'\n            <h3 id="{esc(hid)}" class="service-title reveal" data-reveal="fade-up" '
            f'style="margin-top:14px;">{esc(v.get("title", ""))}</h3>'
            f'\n            <p class="reveal" data-reveal="fade-up" data-reveal-delay="70">'
            f'{esc(v.get("text", ""))}</p>{fact_block}{button}'
            f"\n          </div>\n        </article>")


def _split_fact(line: str) -> tuple[str, str]:
    left, _, right = line.partition("|")
    return left.strip(), right.strip()


def _parse_case(raw: str) -> dict:
    node = _first(raw, "chip")
    tone = "chip"
    if node:
        for cls in (node["attrs"].get("class") or "").split():
            if cls in _CHIP_TONES and cls != "chip":
                tone = cls
    imgs = re.findall(r'<img\b[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*width="(\d*)"'
                      r'[^>]*height="(\d*)"', raw)
    facts = re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", raw, re.S)
    return {
        "anchor": tag_attr(raw, "article", "id"),
        "chip": text_of(raw, "chip"), "tone": tone,
        "title": text_of(raw, "service-title"),
        "text": tag_text(raw, "p"),
        "image": imgs[0][0] if imgs else "", "imageAlt": imgs[0][1] if imgs else "",
        "width": imgs[0][2] if imgs else "", "height": imgs[0][3] if imgs else "",
        "image2": imgs[1][0] if len(imgs) > 1 else "",
        "image2Alt": imgs[1][1] if len(imgs) > 1 else "",
        "width2": imgs[1][2] if len(imgs) > 1 else "",
        "height2": imgs[1][3] if len(imgs) > 1 else "",
        "facts": "\n".join(f"{inner_text(a)} | {inner_text(b)}" for a, b in facts),
        "buttonLabel": text_of(raw, "link-arrow"),
        "openId": tag_attr(raw, "button", "data-open-project"),
        "inset": (_first(raw, "case__inset") or {}).get("attrs", {}).get("data-reveal", ""),
    }


_CASE_FIELDS = [
    {"key": "title", "label": "Project name", "type": "text", "max": 90, "required": True},
    {"key": "chip", "label": "Badge", "type": "text", "max": 60},
    _CHIP_TONE_FIELD,
    {"key": "text", "label": "Description", "type": "textarea", "max": 900},
    {"key": "image", "label": "Main image", "type": "image", "max": 240},
    {"key": "imageAlt", "label": "Main image description", "type": "text", "max": 240},
    {"key": "image2", "label": "Inset image", "type": "image", "max": 240},
    {"key": "image2Alt", "label": "Inset image description", "type": "text", "max": 240},
    {"key": "facts", "label": "Facts", "type": "lines", "max": 900,
     "hint": "One per line, as “Scope | Design · Fabrication”."},
    {"key": "buttonLabel", "label": "Button label", "type": "text", "max": 60},
    {"key": "openId", "label": "Project id it opens", "type": "slug", "max": 60,
     "hint": "Must match an id in the projects data, or the button opens nothing."},
    {"key": "anchor", "label": "Anchor id", "type": "slug", "max": 60,
     "hint": "Used by links like /projects#virgo-acp."},
]


# ---------------- the managed lists ----------------
# Adding another one is this table plus a data-em-list attribute on the page.

def _service_list(name: str, label: str, hint: str) -> dict:
    return {"label": label, "page": "services", "hint": hint,
            "itemLabel": "service", "itemClass": "sc-card", "fields": _SERVICE_FIELDS,
            "render": _render_service_card, "parse": _parse_service_card,
            "titleField": "name", "imageField": "image"}


def _shared(page: str, label: str, hint: str, kind: str, **extra) -> dict:
    """One of the shapes several pages share. `source` is where the shipped
    markup is read from — the same as `page` unless the list is global."""
    base = {
        "stat": {"itemLabel": "figure", "itemClass": "stat", "fields": _STAT_FIELDS,
                 "render": _render_stat, "parse": _parse_stat, "titleField": "value"},
        "marquee": {"itemLabel": "word", "itemClass": "marquee__item",
                    "fields": _MARQUEE_FIELDS, "render": _render_marquee_item,
                    "parse": _parse_marquee_item, "titleField": "text"},
        "process": {"itemLabel": "step", "itemClass": "process__step",
                    "fields": _PROCESS_FIELDS, "render": _render_process_step,
                    "parse": _parse_process_step, "titleField": "title"},
        "assure": {"itemLabel": "step", "itemClass": "assure", "fields": _ASSURE_FIELDS,
                   "render": _render_assurance, "parse": _parse_assurance,
                   "titleField": "title"},
        "value": {"itemLabel": "value", "itemClass": "value", "fields": _VALUE_FIELDS,
                  "render": _render_value, "parse": _parse_value, "titleField": "title"},
        "chip": {"itemLabel": "badge", "itemClass": "chip", "fields": _CHIP_FIELDS,
                 "render": _render_chip, "parse": _parse_chip, "titleField": "label"},
        "nav": {"itemLabel": "link", "itemClass": "", "fields": _NAV_FIELDS,
                "render": _render_nav_link, "parse": _parse_nav_link, "titleField": "label",
                "renderTakesPage": True},
        "footerlink": {"itemLabel": "link", "itemClass": "", "fields": _NAV_FIELDS,
                       "render": _render_footer_link, "parse": _parse_nav_link,
                       "titleField": "label"},
        "menu": {"itemLabel": "link", "itemClass": "", "fields": _NAV_FIELDS,
                 "render": _render_menu_link, "parse": _parse_menu_link, "titleField": "label",
                 "renderTakesPage": True},
    }[kind]
    return {"label": label, "page": page, "hint": hint, "imageField": "", **base, **extra}


# Header and footer are not a page — they are on every page. They are read from
# the home page's markup and baked into all of them, and they get their own
# groups on the panel because that is how an admin thinks about them.
HEADER = "_header"
FOOTER = "_footer"
GLOBAL_PAGES = {HEADER: "Header", FOOTER: "Footer"}
_GLOBAL_SOURCE = "index"

SCHEMAS: dict[str, dict] = {
    # ---- header (every page) ----
    "header-nav": _shared(HEADER, "Header — main menu",
                          "The links along the top bar of every page. Pages you add in the "
                          "panel are appended automatically.",
                          "nav", itemClass="", source=_GLOBAL_SOURCE, listTag="li"),
    "header-menu": _shared(HEADER, "Header — slide-in menu",
                           "The full-screen menu behind the ☰ button. Numbering is automatic.",
                           "menu", source=_GLOBAL_SOURCE, listTag="li"),
    # ---- footer (every page) ----
    "footer-pages": _shared(FOOTER, "Footer — Pages column",
                            "The first column of links in the footer.",
                            "footerlink", source=_GLOBAL_SOURCE, listTag="li"),
    "footer-more": _shared(FOOTER, "Footer — More column",
                           "The second column of footer links. Pages you add in the panel "
                           "are appended here automatically.",
                           "footerlink", source=_GLOBAL_SOURCE, listTag="li"),
    # ---- home ----
    "home-hero-stats": _shared("index", "Home — hero figures",
                               "The three figures under the hero headline.", "stat"),
    "home-hero-caps": _shared("index", "Home — hero badges",
                              "The row of capability badges below the hero.",
                              "chip", listTag="li"),
    "home-marquee": _shared("index", "Home — scrolling words",
                            "The band of words that scrolls across the page.", "marquee"),
    "home-about-stats": _shared("index", "Home — about figures",
                                "The figures beside the About preview.", "stat"),
    "home-services": {
        "label": "Home — what we do", "page": "index",
        "hint": "The numbered list of services on the home page. Numbering is automatic.",
        "itemLabel": "row", "itemClass": "service-row", "fields": _SERVICE_ROW_FIELDS,
        "render": _render_service_row, "parse": _parse_service_row,
        "titleField": "name", "imageField": "preview"},
    "home-work": {
        "label": "Home — selected work", "page": "index",
        "hint": "The project cards on the home page.",
        "itemLabel": "card", "itemClass": "work-card", "fields": _WORK_FIELDS,
        "render": _render_work_card, "parse": _parse_work_card,
        "titleField": "title", "imageField": "image", "carry": ("width", "height")},
    "home-process": _shared("index", "Home — how we work",
                            "The numbered stages on the home page.", "process"),
    # ---- services ----
    "services-stats": _shared("services", "Services — hero figures",
                              "The figures under the Services headline.", "stat"),
    "services-marquee": _shared("services", "Services — scrolling words",
                                "The band of words that scrolls across the page.", "marquee"),
    "services-models": {
        "label": "Services — think, build, deliver", "page": "services",
        "hint": "The three cards describing how an engagement is structured.",
        "itemLabel": "card", "itemClass": "model-card", "fields": _MODEL_FIELDS,
        "render": _render_model_card, "parse": _parse_model_card,
        "titleField": "title", "imageField": ""},
    "services-spaces": _service_list(
        "services-spaces", "Services — Spaces & fit-out",
        "The service cards in the first chapter of the Services page."),
    "services-events": _service_list(
        "services-events", "Services — Events & operations",
        "The service cards in the second chapter of the Services page."),
    "services-brand": _service_list(
        "services-brand", "Services — Brand & media",
        "The service cards in the third chapter of the Services page."),
    "services-process": _shared("services", "Services — how we work",
                                "The numbered stages on the Services page.", "process"),
    # ---- projects ----
    "projects-caps": _shared("projects", "Projects — hero badges",
                             "The badges under the Projects headline.", "chip"),
    "projects-stats": _shared("projects", "Projects — hero figures",
                              "The figures under the Projects headline.", "stat"),
    "projects-marquee": _shared("projects", "Projects — scrolling words",
                                "The band of words that scrolls across the page.", "marquee"),
    "projects-cases": {
        "label": "Projects — featured case studies", "page": "projects",
        "hint": "The long-form projects at the top of the page. The rest of the grid is "
                "the projects data file.",
        "itemLabel": "case study", "itemClass": "case", "fields": _CASE_FIELDS,
        "render": _render_case, "parse": _parse_case,
        "titleField": "title", "imageField": "image",
        "carry": ("width", "height", "width2", "height2"), "carryText": ("inset",)},
    "projects-process": _shared("projects", "Projects — how we work",
                                "The numbered stages on the Projects page.", "process"),
    # ---- about ----
    "about-values": _shared("about", "About — mission & values",
                            "The values listed on the About page.", "value"),
    "about-diff": {
        "label": "About — what sets us apart", "page": "about",
        "hint": "The four points beside the About page's difference section.",
        "itemLabel": "point", "itemClass": "diff", "fields": _DIFF_FIELDS,
        "render": _render_diff, "parse": _parse_diff,
        "titleField": "title", "imageField": ""},
    "about-presence": {
        "label": "About — where we work", "page": "about",
        "hint": "The office / presence cards on the About page.",
        "itemLabel": "location", "itemClass": "presence-card", "fields": _PRESENCE_FIELDS,
        "render": _render_presence, "parse": _parse_presence,
        "titleField": "title", "imageField": ""},
    "about-process": _shared("about", "About — how we work",
                             "The numbered stages on the About page.", "process"),
    # ---- contact ----
    "contact-offices": {
        "label": "Contact — offices", "page": "contact",
        "hint": "The address cards on the Contact page.",
        "itemLabel": "office", "itemClass": "presence-card", "fields": _OFFICE_FIELDS,
        "render": _render_office, "parse": _parse_office,
        "titleField": "title", "imageField": ""},
    # ---- corporate gifts ----
    "gifts-assurances": _shared("giveaways", "Corporate Gifts — how it works",
                                "The numbered steps on the Corporate Gifts page.", "assure"),
    # ---- rental ----
    "rental-assurances": _shared("rental", "Rental — how it works",
                                 "The numbered steps on the Rental page.", "assure"),
    # ---- careers ----
    "careers-values": _shared("careers", "Careers — how we work together",
                              "The values listed on the Careers page.", "value"),
}


def source_page(name: str) -> str:
    """Where a list's shipped markup is read from."""
    spec = schema(name)
    return spec.get("source") or spec["page"]


def pages() -> list[dict]:
    """Every page that has managed lists, in the order the panel shows them:
    the two global groups first, then the site's own pages."""
    from . import content

    order = list(GLOBAL_PAGES) + list(content.all_pages())
    seen, out = set(), []
    for page in order:
        if page in seen:
            continue
        seen.add(page)
        names = [n for n, sp in SCHEMAS.items() if sp["page"] == page]
        if names:
            out.append({"page": page, "label": page_label(page), "lists": names})
    return out


def page_groups() -> list[dict]:
    """The same grouping with the counts the page picker shows, so a screen
    that is page-first can be drawn from one request."""
    counts = {}
    for name in SCHEMAS:
        rows = items(name)
        counts[name] = (len(rows), sum(1 for r in rows if r["hidden"]),
                        is_managed(name))
    out = []
    for group in pages():
        total = sum(counts[n][0] for n in group["lists"])
        out.append({**group, "items": total,
                    "hidden": sum(counts[n][1] for n in group["lists"]),
                    "managed": any(counts[n][2] for n in group["lists"]),
                    "global": group["page"] in GLOBAL_PAGES})
    return out


def schema(name: str) -> dict:
    spec = SCHEMAS.get(name)
    if spec is None:
        raise CollectionError("That content list does not exist.")
    return spec


def page_label(page: str) -> str:
    from . import content

    if page in GLOBAL_PAGES:
        return GLOBAL_PAGES[page]
    cfg = content.all_pages().get(page) or {}
    return cfg.get("label") or page


def public_schema(name: str) -> dict:
    """The schema as the panel needs it — no Python callables."""
    spec = schema(name)
    return {"id": name, "label": spec["label"], "page": spec["page"],
            "pageLabel": page_label(spec["page"]),
            "global": spec["page"] in GLOBAL_PAGES,
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
        raw = content.page_source(source_page(name))
    except Exception:
        return []
    box = _container(raw, name)
    if box is None:
        return []
    inner = raw[box["contentStart"]:box["contentEnd"]]
    out = []
    for i, html in enumerate(_shipped_spans(inner, spec)):
        out.append({"id": f"d{i + 1}", "hidden": False, "shipped": True,
                    "values": spec["parse"](html)})
    return out


def _shipped_spans(inner: str, spec: dict) -> list[str]:
    """The markup of each item inside a container. Most lists mark their items
    with a class; a menu is bare <li>s, so those are taken by tag instead."""
    tag = spec.get("listTag")
    if tag and not spec.get("itemClass"):
        return re.findall(rf"<{tag}\b.*?</{tag}\s*>", inner, re.S | re.I)
    return [node.get("html", "") for node in elements_with_class(inner, spec["itemClass"])]


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
    for key in spec.get("carry", ()):
        out[key] = re.sub(r"[^0-9]", "", str(values.get(key) or ""))[:6]
    for key in spec.get("carryText", ()):
        out[key] = re.sub(r"[^a-z-]", "", str(values.get(key) or "").lower())[:24]
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

def render_list(name: str, page: str = "") -> str:
    """`page` is the page being baked — a menu link needs it to know whether it
    is the current one, and it is the page's own address that decides, not
    anything stored on the item."""
    spec = schema(name)
    visible = [r for r in items(name) if not r["hidden"]]
    if spec.get("renderTakesPage"):
        return "\n          ".join(spec["render"](r["values"], i, page)
                                   for i, r in enumerate(visible))
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
        if spec["page"] != page and spec["page"] not in GLOBAL_PAGES:
            continue
        boxes = _containers(raw, name)
        if not boxes:
            continue
        markup = render_list(name, page)
        body = f"\n          {markup}\n        " if markup else ""
        for box in reversed(boxes):
            raw = raw[:box["contentStart"]] + body + raw[box["contentEnd"]:]
    return raw
