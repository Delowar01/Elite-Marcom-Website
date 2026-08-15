"""Elite Marcom admin — visual-editor design overrides (element styles, media,
responsive breakpoints, sections, animations).

A page's design document is JSON describing overrides addressed by stable
CSS-selector paths (anchored to section ids stamped at bake time, or to the
header/footer). Baking applies it in layers on the git-tracked HTML:
section operations → attribute operations → an emitted <style> block.
Everything is whitelist-validated server-side; values can never break out
of the style block or the tag they target.
"""
from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser

# ---------------- schema & validation ----------------

BREAKPOINTS = ("base", "tablet", "mobile")  # base = desktop / all
# styles cascade downward (desktop → smaller unless overridden) …
_BP_MEDIA = {"tablet": "@media (max-width: 1024px)", "mobile": "@media (max-width: 640px)"}
# … but visibility is a per-device toggle, so it uses exclusive ranges
_BP_HIDE = {"base": "@media (min-width: 1025px)",
            "tablet": "@media (min-width: 641px) and (max-width: 1024px)",
            "mobile": "@media (max-width: 640px)"}

ANIMATIONS = ("fade-up", "fade-in", "slide-left", "slide-right", "zoom",
              "zoom-up", "mask-title", "blur-in", "rise")

_LEN = r"-?\d+(\.\d+)?(px|rem|em|%|vw|vh)"
_LEN_RE = re.compile(rf"^({_LEN}|0|auto)$")
_LEN4_RE = re.compile(rf"^({_LEN}|0|auto)( ({_LEN}|0|auto)){{0,3}}$")
_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}(\s*,\s*\d{1,3}){2}(\s*,\s*(0|1|0?\.\d+))?\s*\)"
    r"|var\(--[\w-]+\)|transparent|currentColor)$")
_SHADOW_RE = re.compile(r"^(none|[\d.\spx%,()#a-fA-F-]+|rgba?\([\d.,\s]+\)[\d.\spx-]+)$")
_URL_RE = re.compile(r"^/(assets|media)/(?!.*\.\.)[\w./-]+$")

STYLE_PROPS: dict[str, re.Pattern | tuple] = {
    "font-size": _LEN_RE,
    "font-weight": re.compile(r"^([1-9]00|bold|normal)$"),
    "line-height": re.compile(rf"^({_LEN}|\d+(\.\d+)?|normal)$"),
    "letter-spacing": re.compile(rf"^({_LEN}|normal|0)$"),
    "text-align": ("left", "center", "right", "justify"),
    "text-transform": ("none", "uppercase", "lowercase", "capitalize"),
    "color": _COLOR_RE,
    "background-color": _COLOR_RE,
    "padding": _LEN4_RE,
    "margin": _LEN4_RE,
    "width": _LEN_RE,
    "max-width": _LEN_RE,
    "height": _LEN_RE,
    "border-radius": _LEN4_RE,
    "border-width": _LEN_RE,
    "border-style": ("none", "solid", "dashed", "dotted"),
    "border-color": _COLOR_RE,
    "box-shadow": _SHADOW_RE,
    "opacity": re.compile(r"^(0|1|0?\.\d{1,3})$"),
    "gap": _LEN_RE,
    # layout and alignment, so a container can be arranged without code
    "min-height": _LEN_RE,
    "align-items": ("flex-start", "center", "flex-end", "stretch", "baseline"),
    "justify-content": ("flex-start", "center", "flex-end", "space-between",
                        "space-around", "space-evenly"),
    "flex-direction": ("row", "row-reverse", "column", "column-reverse"),
    "display": ("block", "flex", "grid", "inline-block", "inline-flex", "none"),
    "grid-template-columns": re.compile(
        rf"^(repeat\(\d{{1,2}},\s*(minmax\(0,\s*1fr\)|1fr|{_LEN})\)"
        rf"|((minmax\(0,\s*1fr\)|1fr|auto|{_LEN})\s*){{1,6}})$"),
    # how a chosen background picture is painted
    "background-size": ("cover", "contain", "auto"),
    "background-position": ("center", "top", "bottom", "left", "right",
                            "center top", "center bottom", "left center", "right center"),
    "background-repeat": ("no-repeat", "repeat", "repeat-x", "repeat-y"),
    "object-fit": ("cover", "contain", "fill", "none", "scale-down"),
    "aspect-ratio": re.compile(r"^(auto|\d{1,2}\s*/\s*\d{1,2})$"),
}

# background-image is emitted from a validated path, never raw CSS
_BG_KEY = "background-image"

# A path is anchored to a section (or the header/footer) and then walks down by
# tag and position. An element placed in a blank section gets its own
# [data-em-el=…] anchor as well: reordering the elements around it would shift
# every nth-of-type below it, and a style must not jump to a different element
# because something above it moved.
_PATH_RE = re.compile(
    r"^(\[data-em-sec=[sa]\d{1,3}\]|header\.site-header|footer\.site-footer|main|body)"
    r"( \[data-em-el=e\d{1,3}\])?"
    r"(>[a-z][a-z0-9]{0,15}(:nth-of-type\(\d{1,3}\))?){0,12}$")

# The element anchor is joined with a SPACE, not ">". A placed element sits
# inside the blank template's .container > .em-stack, so a child combinator
# would match nothing — and these paths are emitted verbatim as CSS selectors
# by build_css and used as querySelector arguments by the editor bridge. The
# server's own resolver searches descendants either way, which is exactly how
# a style could look saved and applied while doing nothing at all.
_EL_JOIN_RE = re.compile(r">(\[data-em-el=e\d{1,3}\])")

# s… = a section that was already in the page, a… = one the editor added
_SEC_ID_RE = re.compile(r"^[sa]\d{1,3}$")
_ADDED_ID_RE = re.compile(r"^a\d{1,3}$")
# e… = an element placed inside a blank section from the element library
_EL_ID_RE = re.compile(r"^e\d{1,3}$")

# An element's replacement text is limited rich text (bold/italic/link/list),
# sanitized on the way in by content.sanitize_rich.
MAX_TEXT = 4000

# The only third-party frame the editor may point at: our own privacy host and
# a validated 11-character video id, the same shape server/supplier_video.py
# enforces. Nothing else, and never a raw embed pasted by an admin.
_YT_EMBED_RE = re.compile(r"^https://www\.youtube-nocookie\.com/embed/[A-Za-z0-9_-]{11}"
                          r"(\?rel=0(&amp;playsinline=1)?)?$")

ATTRS = {
    "src": lambda v: len(v) <= 300 and bool(_URL_RE.match(v) or _YT_EMBED_RE.match(v)),
    "alt": lambda v: len(v) <= 300 and not re.search(r'[<>"]', v),
    "href": lambda v: (len(v) <= 300 and not re.search(r'[<>"\s]', v)
                       and bool(re.match(r"^(https://|http://|mailto:|tel:|/|#)", v))),
}


class DesignError(Exception):
    """User-facing validation error."""


def validate_doc(doc: dict, global_scope: bool = False) -> dict:
    """Return a cleaned copy; raise DesignError on anything out of policy."""
    if not isinstance(doc, dict):
        raise DesignError("Invalid design document.")
    clean: dict = {"elements": {}, "sections": {}}
    elements = doc.get("elements") or {}
    if not isinstance(elements, dict) or len(elements) > 200:
        raise DesignError("Too many styled elements.")
    for path, spec in elements.items():
        if isinstance(path, str):
            path = _EL_JOIN_RE.sub(r" \1", path, count=1)
        if not isinstance(path, str) or len(path) > 300 or not _PATH_RE.match(path):
            raise DesignError(f"Invalid element path: {str(path)[:80]}")
        if global_scope and not path.startswith(("header.site-header", "footer.site-footer")):
            raise DesignError("Site-wide design overrides may only target the header or footer.")
        if not isinstance(spec, dict):
            raise DesignError("Invalid element override.")
        out: dict = {}
        styles = spec.get("styles") or {}
        clean_styles: dict = {}
        for bp, props in styles.items():
            if bp not in BREAKPOINTS or not isinstance(props, dict):
                raise DesignError("Unknown breakpoint.")
            clean_props = {}
            for prop, value in props.items():
                value = str(value).strip()
                if not value:
                    continue
                if prop == _BG_KEY:
                    if not _URL_RE.match(value):
                        raise DesignError("Background images must be /assets/… or /media/… paths.")
                    clean_props[prop] = value
                    continue
                rule = STYLE_PROPS.get(prop)
                if rule is None:
                    raise DesignError(f"Style property not allowed: {str(prop)[:40]}")
                ok = value in rule if isinstance(rule, tuple) else bool(rule.match(value))
                if not ok or len(value) > 120:
                    raise DesignError(f"Invalid value for {prop}.")
                clean_props[prop] = value
            if clean_props:
                clean_styles[bp] = clean_props
        if clean_styles:
            out["styles"] = clean_styles
        attrs = spec.get("attrs") or {}
        clean_attrs = {}
        for name, value in attrs.items():
            if name not in ATTRS:
                raise DesignError(f"Attribute not allowed: {str(name)[:30]}")
            value = str(value).strip()
            if value and not ATTRS[name](value):
                raise DesignError(f"Invalid {name} value.")
            if value:
                clean_attrs[name] = value
        if clean_attrs:
            out["attrs"] = clean_attrs
        text = spec.get("text")
        if text is not None:
            from . import content

            text = str(text)
            if len(text) > MAX_TEXT * 2:
                raise DesignError("That text is too long to save.")
            # the same whitelist the keyed regions use: bold, italic, links,
            # lists, line breaks — everything else becomes plain text
            text = content.sanitize_rich(text)[:MAX_TEXT]
            if text.strip():
                out["text"] = text
        hidden = spec.get("hidden") or {}
        clean_hidden = {bp: True for bp in BREAKPOINTS if hidden.get(bp) is True}
        if clean_hidden:
            out["hidden"] = clean_hidden
        anim = spec.get("anim")
        if isinstance(anim, dict) and anim.get("type"):
            a_type = str(anim["type"])
            if a_type != "none" and a_type not in ANIMATIONS:
                raise DesignError("Unknown animation.")
            try:
                delay = max(0, min(420, int(anim.get("delay") or 0)))
            except (TypeError, ValueError):
                delay = 0
            out["anim"] = {"type": a_type, "delay": delay}
        if out:
            clean["elements"][path] = out
    sections = doc.get("sections") or {}
    if not global_scope and isinstance(sections, dict):
        from . import blocks

        clean_sec: dict = {}
        added = sections.get("added") or []
        if not isinstance(added, list) or len(added) > 30:
            raise DesignError("Too many added sections on one page.")
        clean_added, seen_ids = [], set()
        for item in added:
            if not isinstance(item, dict):
                raise DesignError("Invalid added section.")
            sid = str(item.get("id") or "")
            if not _ADDED_ID_RE.match(sid) or sid in seen_ids:
                raise DesignError("Invalid added-section id.")
            seen_ids.add(sid)
            source = item.get("from")
            if isinstance(source, dict):
                # a section copied from a page of ours: the markup still comes
                # from git, never from the panel — we only remember which one
                from . import content

                src_page = str(source.get("page") or "")
                src_sec = str(source.get("sec") or "")
                if src_page not in content.all_pages():
                    raise DesignError("That page is not one of ours.")
                if not _SEC_ID_RE.match(src_sec):
                    raise DesignError("Invalid copied-section id.")
                refusal = copy_refusal(src_page, src_sec)
                if refusal:
                    raise DesignError(refusal)
                clean_added.append({"id": sid, "from": {"page": src_page, "sec": src_sec}})
                continue
            template = str(item.get("template") or "")
            if template not in blocks.TEMPLATES:
                raise DesignError(f"Unknown section block: {template[:40]}")
            entry = {"id": sid, "template": template}
            children = item.get("children") or []
            if children and 'data-em-slot="1"' not in blocks.TEMPLATES[template]["html"]:
                raise DesignError(
                    "Only a Blank section can hold elements from the library. "
                    "Add a Blank section for them.")
            if not isinstance(children, list) or len(children) > 40:
                raise DesignError("Too many elements in one section.")
            clean_children, seen_els = [], set()
            for child in children:
                if not isinstance(child, dict):
                    raise DesignError("Invalid element.")
                eid = str(child.get("id") or "")
                etpl = str(child.get("template") or "")
                if not _EL_ID_RE.match(eid) or eid in seen_els:
                    raise DesignError("Invalid element id.")
                if etpl not in blocks.ELEMENTS:
                    raise DesignError(f"Unknown element: {etpl[:40]}")
                seen_els.add(eid)
                clean_children.append({"id": eid, "template": etpl})
            if clean_children:
                entry["children"] = clean_children
            clean_added.append(entry)
        if clean_added:
            clean_sec["added"] = clean_added
        for field in ("order", "removed", "duplicated"):
            values = sections.get(field) or []
            if not isinstance(values, list) or len(values) > 80 or \
                    not all(isinstance(v, str) and _SEC_ID_RE.match(v) for v in values):
                if values:
                    raise DesignError("Invalid section list.")
                values = []
            if values:
                clean_sec[field] = values
        if clean_sec:
            clean["sections"] = clean_sec
    return clean


def merge_docs(global_doc: dict, page_doc: dict) -> dict:
    """Global (header/footer) overrides + page overrides; page wins per detail."""
    merged: dict = {"elements": {}, "sections": page_doc.get("sections") or {}}
    for source in (global_doc, page_doc):
        for path, spec in (source.get("elements") or {}).items():
            target = merged["elements"].setdefault(path, {})
            for bp, props in (spec.get("styles") or {}).items():
                target.setdefault("styles", {}).setdefault(bp, {}).update(props)
            if spec.get("attrs"):
                target.setdefault("attrs", {}).update(spec["attrs"])
            if spec.get("text"):
                target["text"] = spec["text"]
            if spec.get("hidden"):
                target.setdefault("hidden", {}).update(spec["hidden"])
            if spec.get("anim"):
                target["anim"] = spec["anim"]
    return merged


# ---------------- storage (admin.db) ----------------

def get_doc(page: str) -> dict:
    from . import adminauth as aa

    row = aa._connect().execute("SELECT doc FROM designs WHERE page=?", (page,)).fetchone()
    if row is None:
        return {"elements": {}, "sections": {}}
    try:
        return json.loads(row["doc"])
    except ValueError:
        return {"elements": {}, "sections": {}}


def set_doc(page: str, doc: dict, by: str) -> dict:
    from . import adminauth as aa

    clean = validate_doc(doc, global_scope=(page == "_global"))
    with aa._lock:
        conn = aa._connect()
        if clean["elements"] or clean.get("sections"):
            conn.execute(
                "INSERT INTO designs (page, doc, updated_at, updated_by) VALUES (?,?,?,?) "
                "ON CONFLICT(page) DO UPDATE SET doc=excluded.doc, "
                "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (page, json.dumps(clean, ensure_ascii=False), int(time.time()), by[:200]))
        else:
            conn.execute("DELETE FROM designs WHERE page=?", (page,))
        conn.commit()
    return clean


def hidden_index() -> list[dict]:
    """Everything currently hidden across the site, with enough detail to
    put it back.

    Hiding is set per element and per breakpoint deep inside the visual
    editor's inspector, and per section in its section list, which means a
    thing switched off months ago on one page at one width is effectively
    lost — nobody remembers where to look. This is the one list that answers
    "what is turned off right now"."""
    from . import content

    known = set(content.PAGES) | {"_global"}
    out: list[dict] = []
    for row in all_docs():
        page = str(row.get("page") or "")
        if page not in known:
            continue
        doc = row.get("doc") or {}
        if isinstance(doc, str):       # all_docs() hands back the stored JSON
            try:
                doc = json.loads(doc)
            except ValueError:
                continue
        for path, spec in (doc.get("elements") or {}).items():
            breakpoints = [bp for bp in BREAKPOINTS if (spec.get("hidden") or {}).get(bp) is True]
            if breakpoints:
                out.append({"page": page, "kind": "element", "path": path,
                            "label": path, "breakpoints": breakpoints})
        # a section is hidden by having its id in the section 'removed' list
        for sid in ((doc.get("sections") or {}).get("removed") or []):
            out.append({"page": page, "kind": "section", "path": sid,
                        "label": f"Section {sid}", "breakpoints": list(BREAKPOINTS)})
    out.sort(key=lambda o: (o["page"], o["kind"], o["path"]))
    return out


def unhide(page: str, kind: str, path: str, by: str) -> bool:
    """Put one hidden element or section back on every breakpoint."""
    doc = get_doc(page)
    if kind == "section":
        sections = doc.get("sections") or {}
        removed = list(sections.get("removed") or [])
        if path not in removed:
            return False
        sections["removed"] = [s for s in removed if s != path]
        if not sections["removed"]:
            sections.pop("removed", None)
        doc["sections"] = sections
    else:
        spec = (doc.get("elements") or {}).get(path)
        if not spec or not (spec.get("hidden") or {}):
            return False
        spec.pop("hidden", None)
        if not spec:
            doc["elements"].pop(path, None)
    set_doc(page, doc, by)
    return True


def all_docs() -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute("SELECT page, doc FROM designs").fetchall()
    return [{"page": r["page"], "doc": r["doc"]} for r in rows]


def restore_docs(rows: list[dict]) -> None:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM designs")
        for r in rows or []:
            conn.execute("INSERT INTO designs (page, doc, updated_at, updated_by) VALUES (?,?,?,?)",
                         (r["page"], r["doc"], int(time.time()), "rollback"))
        conn.commit()


def last_design_edit(page: str) -> int:
    from . import adminauth as aa

    row = aa._connect().execute(
        "SELECT MAX(updated_at) AS m FROM designs WHERE page IN (?, '_global')", (page,)).fetchone()
    return row["m"] or 0


# ---------------- element tree (stdlib parser) ----------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "source", "track", "wbr"}


class _Node:
    __slots__ = ("tag", "attrs", "parent", "children", "tag_start", "content_start",
                 "content_end", "end")

    def __init__(self, tag, attrs, parent, tag_start, content_start):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[_Node] = []
        self.tag_start = tag_start
        self.content_start = content_start
        self.content_end = content_start
        self.end = content_start


class _Tree(HTMLParser):
    def __init__(self, raw: str):
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self._lines = [0]
        for line in raw.splitlines(keepends=True):
            self._lines.append(self._lines[-1] + len(line))
        self.root = _Node("#root", {}, None, 0, 0)
        self.root.content_end = self.root.end = len(raw)
        self._stack = [self.root]
        self.feed(raw)

    def _off(self):
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._off()
        gt = self.raw.find(">", start)
        node = _Node(tag, dict(attrs), self._stack[-1], start, gt + 1)
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)
        else:
            node.content_end = node.end = gt + 1

    def handle_startendtag(self, tag, attrs):
        start = self._off()
        gt = self.raw.find(">", start)
        node = _Node(tag, dict(attrs), self._stack[-1], start, gt + 1)
        node.content_end = node.end = gt + 1
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                node = self._stack[i]
                node.content_end = self._off()
                node.end = self.raw.find(">", node.content_end) + 1
                del self._stack[i:]
                break


def _find_main_sections(tree: _Tree) -> tuple[_Node | None, list[_Node]]:
    def walk(node):
        for child in node.children:
            if child.tag == "main":
                return child
            found = walk(child)
            if found is not None:
                return found
        return None

    main = walk(tree.root)
    if main is None:
        return None, []
    return main, [c for c in main.children if c.tag == "section"]


def _resolve_path(tree: _Tree, path: str) -> _Node | None:
    segments = path.split(">")
    anchor = segments[0]
    el_anchor = ""
    if " " in anchor:
        anchor, el_anchor = anchor.split(" ", 1)
        el_anchor = el_anchor.strip()
    node: _Node | None = None
    if anchor.startswith("[data-em-sec="):
        sec_id = anchor[len("[data-em-sec="):-1]
        _, sections = _find_main_sections(tree)
        for s in sections:
            if s.attrs.get("data-em-sec") == sec_id:
                node = s
                break
    else:
        want_tag = anchor.split(".")[0]
        want_cls = anchor.split(".")[1] if "." in anchor else None

        def walk(n):
            for child in n.children:
                if child.tag == want_tag and (
                        want_cls is None or want_cls in (child.attrs.get("class") or "").split()):
                    return child
                found = walk(child)
                if found is not None:
                    return found
            return None

        node = walk(tree.root)
    if node is None:
        return None
    if el_anchor.startswith("[data-em-el="):
        el_id = el_anchor[len("[data-em-el="):-1]

        def find_el(n):
            for child in n.children:
                if child.attrs.get("data-em-el") == el_id:
                    return child
                found = find_el(child)
                if found is not None:
                    return found
            return None

        node = find_el(node)
        if node is None:
            return None
    for seg in segments[1:]:
        m = re.match(r"^([a-z][a-z0-9]*)(?::nth-of-type\((\d+)\))?$", seg)
        if not m:
            return None
        tag, nth = m.group(1), int(m.group(2) or 1)
        count = 0
        nxt = None
        for child in node.children:
            if child.tag == tag:
                count += 1
                if count == nth:
                    nxt = child
                    break
        if nxt is None:
            return None
        node = nxt
    return node


# ---------------- bake application ----------------

def _set_attrs_in_tag(tag_text: str, changes: dict[str, str | None]) -> str:
    """Rewrite attributes inside one start tag; None removes the attribute."""
    for name, value in changes.items():
        pattern = re.compile(rf'\s{re.escape(name)}="[^"]*"')
        tag_text = pattern.sub("", tag_text)
        if value is not None:
            insert = f' {name}="{value}"'
            # A replacement STRING would read backslashes in the value as regex
            # escapes: an alt of "AC\DC" raised re.error and took every later
            # bake — and Publish — down with it. A function replacement is
            # literal, and cannot expand \1 into a captured group either.
            tag_text = re.sub(r"(/?)>$", lambda m, ins=insert: ins + m.group(1) + ">",
                              tag_text, count=1)
    return tag_text


_FORM_RE = re.compile(r"<form\b", re.I)
_ID_RE = re.compile(r'\sid="([^"]*)"')
# attributes that point at an id inside the same block
_REF_ATTRS = ("for", "aria-labelledby", "aria-describedby", "aria-controls", "form", "list")


def _reid_copy(body: str, prefix: str) -> str:
    """Re-prefix the ids inside a copied section and the references to them.

    Deleting them instead broke every label/field pair and every in-block
    anchor; leaving them alone would put two elements on the page claiming one
    id. A reference is only rewritten when its target is inside this copy, so a
    link to a section elsewhere on the page still goes there.
    """
    ids = {m.group(1) for m in _ID_RE.finditer(body) if m.group(1)}
    if not ids:
        return re.sub(r'\s(data-em|data-em-sec|data-em-list)="[^"]*"', "", body)
    body = _ID_RE.sub(lambda m: f' id="{prefix}-{m.group(1)}"' if m.group(1) in ids else m.group(0),
                      body)
    for attr in _REF_ATTRS:
        body = re.sub(
            rf'\s{attr}="([^"]*)"',
            lambda m, a=attr: (f' {a}="{prefix}-{m.group(1)}"' if m.group(1) in ids else m.group(0)),
            body)
    body = re.sub(
        r'\shref="#([^"]*)"',
        lambda m: (f' href="#{prefix}-{m.group(1)}"' if m.group(1) in ids else m.group(0)),
        body)
    return re.sub(r'\s(data-em|data-em-sec|data-em-list)="[^"]*"', "", body)


def copy_refusal(page: str, sec_id: str) -> str:
    """Why this section cannot be copied, or "" when it can.

    Checked when the copy is saved, so the admin hears about it there rather
    than finding a section missing from the published page.
    """
    markup = section_from_page(page, sec_id, "probe")
    if markup:
        return ""
    from . import content

    try:
        raw = content.page_source(page)
    except Exception:
        return "That page is not one of ours."
    raw = _apply_sections(raw, {})
    tree = _Tree(raw)
    _main, sections = _find_main_sections(tree)
    for node in sections:
        if node.attrs.get("data-em-sec") == sec_id:
            return ("A section containing a form cannot be copied — the copy could not be "
                    "wired up, and an unwired form would send what a visitor types into a "
                    "web address. Copy the sections around it instead.")
    return "That section is no longer on the page."


def section_from_page(page: str, sec_id: str, new_id: str) -> str:
    """One section lifted out of a page of ours, restamped under a new id.

    This is what "copy a section and paste it" means: the markup is still the
    git-tracked page's, so nothing an admin typed is ever parsed as HTML. Ids
    and keyed regions are stripped — the copy is edited independently of the
    original, and two elements must never claim the same anchor.
    """
    from . import collections as collections_mod
    from . import content

    try:
        raw = content.page_source(page)
    except Exception:
        return ""
    raw = _apply_sections(raw, {})          # stamp s… ids the same way a bake does
    # copy what the page actually shows today, items and all — a services
    # section copied after an eleventh service was added must carry eleven
    raw = collections_mod.apply_to_page(raw, page)
    tree = _Tree(raw)
    _main, sections = _find_main_sections(tree)
    for node in sections:
        if node.attrs.get("data-em-sec") != sec_id:
            continue
        span = raw[node.tag_start:node.end]
        tag_text = raw[node.tag_start:node.content_start]
        body = span[len(tag_text):]
        if _FORM_RE.search(body):
            # A form is bound by id to the page's own JavaScript. A second copy
            # cannot be wired up, and an unbound one submits natively — the
            # visitor's name, email and message would leave in a URL. Saving one
            # is refused (see copy_refusal); a doc stored before that rule
            # existed drops the section rather than breaking the page.
            return ""
        body = _reid_copy(body, new_id)
        new_tag = _set_attrs_in_tag(tag_text, {
            "data-em-sec": new_id, "id": None, "aria-labelledby": None,
            "data-em": None, "data-em-list": None})
        return new_tag + body
    return ""


def _apply_sections(raw: str, sections_spec: dict) -> str:
    """Stamp data-em-sec ids and apply order / removed / duplicated."""
    tree = _Tree(raw)
    main, sections = _find_main_sections(tree)
    if main is None or not sections:
        return raw
    stamped = []
    for i, node in enumerate(sections):
        span = raw[node.tag_start:node.end]
        tag_text = raw[node.tag_start:node.content_start]
        if "data-em-sec" not in node.attrs:
            new_tag = _set_attrs_in_tag(tag_text, {"data-em-sec": f"s{i}"})
            span = new_tag + span[len(tag_text):]
        stamped.append((f"s{i}", span))
    from . import blocks

    ids = [sid for sid, _ in stamped]
    by_id = dict(stamped)
    # A page's <main> holds more than <section>s — a marquee band, a request
    # drawer, the services grid. Only sections are addressable, but everything
    # else has to come through the rebuild untouched: this function replaces
    # main's whole inner span, so anything it does not emit is deleted from the
    # published page. Each stray child is pinned to the section it follows.
    section_starts = {node.tag_start: sid for sid, node in zip(ids, sections)}
    leading: list[str] = []
    trailing: dict[str, list[str]] = {}
    kids = [c for c in main.children]
    kids.sort(key=lambda c: c.tag_start)
    current: str | None = None
    for child in kids:
        sid = section_starts.get(child.tag_start)
        if sid is not None:
            current = sid
            continue
        span = raw[child.tag_start:child.end]
        if current is None:
            leading.append(span)
        else:
            trailing.setdefault(current, []).append(span)
    for item in sections_spec.get("added") or []:
        if item.get("from"):
            markup = section_from_page(item["from"]["page"], item["from"]["sec"], item["id"])
        else:
            markup = blocks.render_section(item["template"], item["id"],
                                           item.get("children"))
        if markup:
            by_id[item["id"]] = markup
            ids.append(item["id"])
    order = [sid for sid in (sections_spec.get("order") or ids) if sid in by_id]
    for sid in ids:  # anything missing from a stale order list keeps its place
        if sid not in order:
            order.append(sid)
    removed = set(sections_spec.get("removed") or [])
    duplicated = set(sections_spec.get("duplicated") or [])
    parts = list(leading)
    for sid in order:
        if sid not in removed:
            parts.append(by_id[sid])
            if sid in duplicated:
                copy = by_id[sid]
                head, _, rest = copy.partition(">")
                copy = re.sub(r'\s(data-em|data-em-sec|id|aria-labelledby)="[^"]*"', "",
                              head + ">") + _reid_copy(rest, f"{sid}-copy")
                parts.append(copy)
        # emitted even when the section above it was removed: taking a section
        # off the page must not silently delete the content that sat after it
        parts.extend(trailing.get(sid, []))
    first, last = kids[0], kids[-1]
    prefix = raw[main.content_start:first.tag_start]
    suffix = raw[last.end:main.content_end]
    rebuilt = prefix + "\n\n".join(parts) + suffix
    return raw[:main.content_start] + rebuilt + raw[main.content_end:]


def _apply_text_ops(raw: str, elements: dict) -> str:
    """Replace the inner HTML of every element carrying a text override.

    This is what makes the parts of a page that were never given a data-em
    key — button labels, card titles, list items, captions — editable: the
    editor addresses them by the same stable path it uses for styling."""
    targets = [(path, spec["text"]) for path, spec in elements.items() if spec.get("text")]
    if not targets:
        return raw
    tree = _Tree(raw)
    spans: list[tuple[int, int, str]] = []
    for path, text in targets:
        node = _resolve_path(tree, path)
        if node is None or node.tag in _VOID:
            continue
        spans.append((node.content_start, node.content_end,
                      text.replace("\r", "").replace("\n", "<br>")))
    # If someone edited both a container and something inside it, only the
    # container's text survives — applying both would splice the inner edit
    # into offsets the outer replacement has already moved.
    spans.sort(key=lambda e: (e[0], -e[1]))
    kept: list[tuple[int, int, str]] = []
    covered = -1
    for start, end, text in spans:
        if start < covered:
            continue
        kept.append((start, end, text))
        covered = end
    for start, end, text in sorted(kept, key=lambda e: e[0], reverse=True):
        raw = raw[:start] + text + raw[end:]
    return raw


def _apply_attr_ops(raw: str, elements: dict) -> str:
    """src/alt/href replacements and animation attribute rewrites."""
    tree = _Tree(raw)
    edits: list[tuple[int, int, str]] = []
    for path, spec in elements.items():
        changes: dict[str, str | None] = {}
        for name, value in (spec.get("attrs") or {}).items():
            changes[name] = value
        anim = spec.get("anim")
        node = _resolve_path(tree, path)
        if node is None:
            continue
        if anim:
            classes = (node.attrs.get("class") or "").split()
            if anim["type"] == "none":
                changes["data-reveal"] = None
                changes["data-reveal-delay"] = None
                if "reveal" in classes:
                    classes = [c for c in classes if c != "reveal"]
                    changes["class"] = " ".join(classes) if classes else None
            else:
                changes["data-reveal"] = anim["type"]
                changes["data-reveal-delay"] = str(anim["delay"]) if anim["delay"] else None
                if "reveal" not in classes:
                    changes["class"] = " ".join(classes + ["reveal"])
        if not changes:
            continue
        tag_text = raw[node.tag_start:node.content_start]
        edits.append((node.tag_start, node.content_start, _set_attrs_in_tag(tag_text, changes)))
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    return raw


def build_css(elements: dict) -> str:
    """Emit the design <style> payload — validated values only."""
    buckets: dict[str, list[str]] = {bp: [] for bp in BREAKPOINTS}
    hide_buckets: dict[str, list[str]] = {bp: [] for bp in BREAKPOINTS}
    for path, spec in elements.items():
        for bp, props in (spec.get("styles") or {}).items():
            decls = "".join(f"{prop}:{value} !important;"
                            for prop, value in props.items() if prop != _BG_KEY)
            bg = props.get(_BG_KEY)
            if bg:
                decls += f"background-image:url('{bg}') !important;"
            if decls:
                buckets[bp].append(f"{path}{{{decls}}}")
        for bp in (spec.get("hidden") or {}):
            hide_buckets[bp].append(f"{path}{{display:none !important;}}")
    css = "\n".join(buckets["base"])
    for bp in ("tablet", "mobile"):
        if buckets[bp]:
            css += f"\n{_BP_MEDIA[bp]}{{\n" + "\n".join(buckets[bp]) + "\n}"
    for bp in BREAKPOINTS:
        if hide_buckets[bp]:
            css += f"\n{_BP_HIDE[bp]}{{\n" + "\n".join(hide_buckets[bp]) + "\n}"
    return css.strip()


def apply_to_page(raw: str, page: str, between=None) -> str:
    """Full design layer for one page: sections → attributes → style block.
    Sections are stamped even with no overrides so editor paths stay stable.

    ``between`` runs after the section layer and before the element overrides.
    Repeatable lists (server/collections.py) go there: they rebuild whole
    containers, so running them afterwards would wipe a text or style override
    an admin had put on a card inside one. Sections first, then the items
    inside them, then the per-element edits on top of both.
    """
    merged = merge_docs(get_doc("_global"), get_doc(page))
    raw = _apply_sections(raw, merged.get("sections") or {})
    if between is not None:
        raw = between(raw)
    if merged["elements"]:
        raw = _apply_text_ops(raw, merged["elements"])
        raw = _apply_attr_ops(raw, merged["elements"])
        css = build_css(merged["elements"])
        if css:
            block = f'<style id="em-design">\n{css}\n</style>\n</head>'
            raw = raw.replace("</head>", block, 1)
    return raw
