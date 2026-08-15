"""Product videos read from the supplier's PUBLIC product pages.

The Product API does not carry a usable video link for most items. The
confirmed example: ITGL 1291 NAPIER — MagCase Phone Cardholder — Grey comes
back as id 24246 / parent_id 29453 with ``videos: []``, while the supplier's
own public page

    https://www.jasani.ae/shop/itgl-1291-napier-magcase-phone-cardholder-grey-29453

embeds ``https://www.youtube.com/embed/lFhAiGLjoMo``. The trailing number in
that URL is the template id we already store as ``parentId``, so the page can
be reached from data we hold without asking the supplier anything.

Three rules this module exists to keep:

* **Nothing here is an API call.** No token, no primary endpoint, no daily
  budget — ``jasani._budget_ok`` is never consulted and never spent. It is an
  ordinary request for a public webpage, and it is deliberately slow: at most
  ``VIDEO_CONCURRENCY`` in flight and never two closer together than
  ``VIDEO_MIN_INTERVAL_S``.
* **Every verdict is cached, including "no video".** Without the negative
  cache the pages with nothing on them would be fetched again on every visit,
  which is exactly the crawl we must not create. The cache is keyed by
  template, so all colour variants of one product share a single lookup.
* **Discovery is on demand only.** The catalogue never triggers it — only a
  product page a customer actually opened, and only after that page has
  already rendered from the cached snapshot.

Only a validated 11-character YouTube id ever leaves this module. Supplier
HTML is parsed and discarded; none of it is stored.
"""
from __future__ import annotations

import asyncio
import html as html_mod
import json
import re
import time
import urllib.parse
from pathlib import Path

import httpx

from . import config
from .jasani import _safe_supplier_url

_CACHE_DIR = config.RUNTIME_DIR / "cache" / "videos"

_UA = "EliteMarcomBot/1.0 (+https://elitemarcom.com)"

# A YouTube id is exactly 11 characters. The feed parser in jasani.py is
# deliberately looser because the supplier hand-types those fields; a whole
# webpage is a different input, and anything but an exact id here is a
# mis-parse waiting to become the wrong video on a product page.
_ID = r"([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
# The host is matched from the "//" of the URL, not wherever the string
# "youtube.com" happens to appear — https://elsewhere.example/youtube.com/embed/…
# is a path on somebody else's server, not a video.
_HOST = r"(?:https?:)?//(?:www\.|m\.)?"
_YT_RE = re.compile(
    _HOST + r"youtube(?:-nocookie)?\.com/(?:embed|v|e|shorts|live)/" + _ID
    + r"|" + _HOST + r"youtube(?:-nocookie)?\.com/watch\?(?:[^\s\"'<>]*?[&?])?v=" + _ID
    + r"|" + _HOST + r"youtu\.be/" + _ID,
    re.I)
_THUMB_RE = re.compile(
    r"https?://i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/([A-Za-z0-9_]+\.jpg)", re.I)

MAX_VIDEOS = 4

# Odoo shops repeat other products at the bottom of a product page (alternative
# products, accessories, recently viewed). A video embedded down there belongs
# to a different item, so the scan is narrowed to the product region when the
# page marks one — and falls back to the whole document when it does not.
_REGION_START = ('id="product_detail"', "id='product_detail'",
                 'id="wrap"', "oe_website_sale")
_REGION_END = ("alternative_products", "accessory_products",
               "o_wsale_product_page_reviews", "recently_viewed", "<footer")


def _region(page: str) -> str:
    start = -1
    for marker in _REGION_START:
        start = page.find(marker)
        if start >= 0:
            break
    if start < 0:
        return page
    end = len(page)
    for marker in _REGION_END:
        at = page.find(marker, start)
        if at >= 0:
            end = min(end, at)
    return page[start:end]


def parse_videos(page: str) -> list[dict]:
    """Validated YouTube entries in document order — supplier HTML in, ids out."""
    if not page:
        return []
    # escaped slashes inside inline JSON (https:\/\/…) hide the URL from the
    # pattern; the page is scanned as text, so undo that first
    text = _region(page.replace("\\/", "/"))
    text = html_mod.unescape(text)
    thumbs: dict[str, str] = {}
    for m in _THUMB_RE.finditer(text):
        thumbs.setdefault(m.group(1), m.group(0))
    out: list[dict] = []
    seen: set[str] = set()
    for m in _YT_RE.finditer(text):
        vid = m.group(1) or m.group(2) or m.group(3)
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append({"youtubeId": vid,
                    "thumbnail": thumbs.get(vid, f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")})
        if len(out) >= MAX_VIDEOS:
            break
    return out


# ---------------- public page addressing ----------------

def template_id(product: dict) -> str:
    """The supplier's public page id: parent_id, the template behind a variant."""
    raw = str(product.get("parentId") or product.get("templateId") or "").strip()
    return raw if raw.isdigit() and 0 < int(raw) < 10 ** 12 else ""


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:120]


def page_urls(market: str, product: dict) -> list[str]:
    """Candidate public product URLs, best first.

    A stored supplier URL wins when we have one. Otherwise the Odoo-style
    ``/shop/<slug>-<template id>`` address is built from the SKU and name; the
    shop resolves that by the trailing id, and a slug that has drifted only
    costs a redirect, which is followed and re-validated.
    """
    tid = template_id(product)
    if not tid:
        return []
    host = config.JASANI_HOSTS.get(market, "")
    if not host:
        return []
    out: list[str] = []
    stored = _safe_supplier_url(str(product.get("websiteUrl") or product.get("url") or ""))
    if stored and (urllib.parse.urlsplit(stored).hostname or "") == host:
        out.append(stored)
    code = str(product.get("code") or "")
    name = str(product.get("name") or "")
    words = _slug(name if _slug(code) and _slug(name).startswith(_slug(code)) else f"{code} {name}")
    out.append(f"https://{host}/shop/{words}-{tid}" if words else f"https://{host}/shop/{tid}")
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def search_url(market: str, product: dict) -> str:
    host = config.JASANI_HOSTS.get(market, "")
    term = str(product.get("code") or product.get("name") or "").strip()[:80]
    if not host or not term:
        return ""
    return f"https://{host}/shop?search={urllib.parse.quote(term, safe='')}"


def link_for_template(page: str, market: str, tid: str) -> str:
    """The canonical shop link for exactly this template id on a listing page.

    The trailing id must match: a search result for a nearby product is not
    this product, and guessing one would put someone else's video on our page.
    """
    host = config.JASANI_HOSTS.get(market, "")
    if not (page and host and tid):
        return ""
    m = re.search(r"""/shop/(?:product/)?([A-Za-z0-9._~%-]{0,140}-)?"""
                  + re.escape(tid) + r"""(?![0-9])""", page)
    if not m:
        return ""
    return f"https://{host}{m.group(0)}"


# ---------------- paced, capped fetching ----------------

# asyncio primitives are created per running loop: the test client runs each
# request on a loop of its own, and a lock that remembers a dead loop raises
# instead of guarding anything.
_loops: dict = {}


def _state() -> dict:
    loop = asyncio.get_running_loop()
    st = _loops.get(loop)
    if st is None:
        st = {"sem": asyncio.Semaphore(config.VIDEO_CONCURRENCY),
              "pace": asyncio.Lock(), "keys": {}, "last": 0.0}
        for dead in [lp for lp in _loops if lp.is_closed()]:
            _loops.pop(dead, None)
        _loops[loop] = st
    return st


async def fetch_page(url: str) -> str | None:
    """One public supplier page as text, or None if it could not be read.

    Redirects are followed by hand so every hop is re-checked against the
    supplier host allowlist — an open redirect must not turn this into a
    fetcher for arbitrary URLs. The body is streamed and cut at the byte cap:
    read first and truncated after would be no cap at all.
    """
    if not _safe_supplier_url(url):
        return None
    st = _state()
    async with st["sem"]:
        async with st["pace"]:
            wait = config.VIDEO_MIN_INTERVAL_S - (time.monotonic() - st["last"])
            if wait > 0:
                await asyncio.sleep(wait)
            st["last"] = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=config.VIDEO_PAGE_TIMEOUT_S,
                                         follow_redirects=False, trust_env=False) as client:
                target = url
                for _hop in range(4):
                    safe = _safe_supplier_url(target)
                    if not safe:
                        return None
                    async with client.stream("GET", safe, headers={
                            "User-Agent": _UA,
                            "Accept": "text/html,application/xhtml+xml"}) as res:
                        if res.status_code in (301, 302, 303, 307, 308):
                            nxt = res.headers.get("location", "")
                            target = urllib.parse.urljoin(safe, nxt) if nxt else ""
                            if not target:
                                return None
                            continue
                        if res.status_code != 200:
                            return None
                        ctype = (res.headers.get("content-type") or "").lower()
                        if ctype and "html" not in ctype:
                            return None
                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in res.aiter_bytes():
                            total += len(chunk)
                            chunks.append(chunk)
                            if total >= config.VIDEO_PAGE_MAX_BYTES:
                                break
                        body = b"".join(chunks)[:config.VIDEO_PAGE_MAX_BYTES]
                    return body.decode("utf-8", "replace")
                return None
        except Exception:
            return None


# ---------------- persistent verdict cache ----------------

def _cache_path(market: str, tid: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]", "", str(tid))[:40]
    return _CACHE_DIR / f"{market}-{safe}.json"


def _read_cache(market: str, tid: str) -> list[dict] | None:
    try:
        meta = json.loads(_cache_path(market, tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    videos = [v for v in meta.get("videos") or [] if isinstance(v, dict) and v.get("youtubeId")]
    if not meta.get("ok", True):
        ttl = config.VIDEO_ERROR_CACHE_HOURS * 3600
    elif videos:
        ttl = config.VIDEO_CACHE_DAYS * 86400
    else:
        ttl = config.VIDEO_MISS_CACHE_DAYS * 86400
    if time.time() - float(meta.get("checkedAt") or 0) > ttl:
        return None
    return videos


def _write_cache(market: str, tid: str, videos: list[dict], ok: bool) -> None:
    try:
        _cache_path(market, tid).write_text(json.dumps({
            "checkedAt": int(time.time()), "ok": ok, "videos": videos}), encoding="utf-8")
    except OSError:
        pass  # a cache we cannot write is a slower answer, never a failed one


async def _discover(market: str, product: dict, tid: str) -> tuple[list[dict], bool]:
    """(videos, reached) — reached=False means the supplier page never loaded,
    which is a retry-sooner verdict rather than 'this product has no video'."""
    for url in page_urls(market, product):
        page = await fetch_page(url)
        if page is not None:
            return parse_videos(page), True
    listing = await fetch_page(search_url(market, product))
    if listing is not None:
        link = link_for_template(listing, market, tid)
        if link:
            page = await fetch_page(link)
            if page is not None:
                return parse_videos(page), True
    return [], False


async def videos_for(market: str, product: dict) -> list[dict]:
    """Videos for one catalogue product, from the API feed if it carried any,
    else from the supplier's public page — cached either way."""
    existing = [{"youtubeId": v["youtubeId"], "thumbnail": v.get("thumbnail") or ""}
                for v in (product.get("videos") or [])
                if isinstance(v, dict) and v.get("youtubeId")]
    if existing:
        return existing
    tid = template_id(product)
    if not tid:
        return []
    cached = _read_cache(market, tid)
    if cached is not None:
        return cached
    st = _state()
    key = f"{market}:{tid}"
    lock = st["keys"].get(key)
    if lock is None:
        lock = st["keys"].setdefault(key, asyncio.Lock())
    async with lock:
        # a concurrent request for the same template may have just filled it
        cached = _read_cache(market, tid)
        if cached is not None:
            return cached
        videos, reached = await _discover(market, product, tid)
        _write_cache(market, tid, videos, reached)
        if len(st["keys"]) > 500:
            st["keys"].clear()
        return videos


def cache_status() -> dict:
    """Counts for the admin supplier console — no supplier data, just verdicts."""
    hits = misses = 0
    try:
        files = sorted(_CACHE_DIR.glob("*.json"))
    except OSError:
        files = []
    for path in files:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("videos"):
            hits += 1
        else:
            misses += 1
    return {"withVideo": hits, "withoutVideo": misses, "entries": hits + misses}
