"""Cache-busting guard.

Production serves CSS/JS by path, not by hashed filename, so a changed asset
only reaches returning visitors when its `?v=` query changes on EVERY page that
references it. These tests fail the moment a reference is missed, which is the
failure that would otherwise ship silently: one page pinned to the old version.
"""
from __future__ import annotations

import collections
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent.parent
HTML_DIRS = (BASE / "public", BASE / "server" / "adminui")

# Server-rendered stylesheets sent with Cache-Control: no-cache — they carry no
# version because there is no cached copy to bust.
DYNAMIC = {"/theme-custom.css"}

# Only real references count: a rel="preload"/"modulepreload" hint has to byte-
# match the request the browser will make anyway (for modules, the bare import
# specifier), so adding a ?v= there would stop the preload being used at all.
PRELOAD = re.compile(r'rel="(?:module)?preload"')
REF = re.compile(r'<(?:link|script)[^>]*?(?:href|src)="(/[^"?]+\.(?:css|js))(\?v=([^"]*))?"[^>]*>')


def html_files() -> list[pathlib.Path]:
    files = [p for d in HTML_DIRS for p in sorted(d.glob("*.html"))]
    assert files, "no HTML pages found to check"
    return files


def references() -> list[tuple[pathlib.Path, str, str | None]]:
    found = []
    for page in html_files():
        for tag in re.finditer(r"<(?:link|script)\b[^>]*>", page.read_text(encoding="utf-8")):
            if PRELOAD.search(tag.group(0)):
                continue
            m = REF.match(tag.group(0))
            if m:
                found.append((page, m.group(1), m.group(3) if m.group(2) else None))
    return found


def test_every_local_css_and_js_reference_is_versioned():
    missing = [f"{page.name} → {path}"
               for page, path, version in references()
               if path not in DYNAMIC and version is None]
    assert not missing, (
        "these references have no ?v= cache-busting query, so a changed file "
        "would never reach returning visitors: " + ", ".join(missing))


def test_one_version_per_asset_across_every_page():
    seen: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for page, path, version in references():
        if version is not None:
            seen[path][version].append(page.name)

    stale = {path: dict(versions) for path, versions in seen.items() if len(versions) > 1}
    assert not stale, (
        "the same asset is referenced at different ?v= values — the pages on the "
        "older value will keep serving a cached copy: " + repr(stale))


def test_referenced_assets_exist_on_disk():
    roots = {BASE / "public": "", BASE / "server" / "adminui": "/admin"}
    missing = []
    for _, path, _ in references():
        if path in DYNAMIC:
            continue
        for root, prefix in roots.items():
            rel = path[len(prefix):] if prefix and path.startswith(prefix) else path
            if (root / rel.lstrip("/")).is_file():
                break
        else:
            missing.append(path)
    assert not missing, f"referenced but not found on disk: {sorted(set(missing))}"
