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
_URL_RE = re.compile(r"^/(assets|media)/[\w./-]+$")

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
}

# background-image is emitted from a validated path, never raw CSS
_BG_KEY = "background-image"

_PATH_RE = re.compile(
    r"^(\[data-em-sec=s\d{1,3}\]|header\.site-header|footer\.site-footer|main|body)"
    r"(>[a-z][a-z0-9]{0,15}(:nth-of-type\(\d{1,3}\))?){0,12}$")

ATTRS = {
    "src": lambda v: bool(_URL_RE.match(v)) and len(v) <= 300,
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
        sec_id = re.compile(r"^s\d{1,3}$")
        clean_sec: dict = {}
        for field in ("order", "removed", "duplicated"):
            values = sections.get(field) or []
            if not isinstance(values, list) or len(values) > 50 or \
                    not all(isinstance(v, str) and sec_id.match(v) for v in values):
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
            tag_text = re.sub(r"(/?)>$", insert + r"\1>", tag_text, count=1)
    return tag_text


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
    ids = [sid for sid, _ in stamped]
    by_id = dict(stamped)
    order = [sid for sid in (sections_spec.get("order") or ids) if sid in by_id]
    for sid in ids:  # anything missing from a stale order list keeps its place
        if sid not in order:
            order.append(sid)
    removed = set(sections_spec.get("removed") or [])
    duplicated = set(sections_spec.get("duplicated") or [])
    parts = []
    for sid in order:
        if sid in removed:
            continue
        parts.append(by_id[sid])
        if sid in duplicated:
            copy = by_id[sid]
            copy = re.sub(r'\s(data-em|data-em-sec|id|aria-labelledby)="[^"]*"', "", copy)
            parts.append(copy)
    prefix = raw[main.content_start:sections[0].tag_start]
    suffix = raw[sections[-1].end:main.content_end]
    rebuilt = prefix + "\n\n".join(parts) + suffix
    return raw[:main.content_start] + rebuilt + raw[main.content_end:]


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


def apply_to_page(raw: str, page: str) -> str:
    """Full design layer for one page: sections → attributes → style block.
    Sections are stamped even with no overrides so editor paths stay stable."""
    merged = merge_docs(get_doc("_global"), get_doc(page))
    raw = _apply_sections(raw, merged.get("sections") or {})
    if merged["elements"]:
        raw = _apply_attr_ops(raw, merged["elements"])
        css = build_css(merged["elements"])
        if css:
            block = f'<style id="em-design">\n{css}\n</style>\n</head>'
            raw = raw.replace("</head>", block, 1)
    return raw
