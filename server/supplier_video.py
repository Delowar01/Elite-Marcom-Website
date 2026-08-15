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
from html.parser import HTMLParser
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


# Odoo serves every gallery picture from a product.image record, and the record
# id is in the URL: /web/image/product.image/8801/image_1024. That id is the
# only reliable identity shared between the public page and the API feed, which
# hands us the same URLs — the two never agree on anything else. The poster of
# a video is a product.image record like any other, which is why it arrives in
# the feed as an ordinary photo and shows up twice in the gallery.
_IMG_RE = re.compile(r"/web/image/product\.image/(\d{1,12})", re.I)

# Elements that never wrap anything, so they never open a scope.
_VOID = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input",
                   "link", "meta", "param", "source", "track", "wbr"))

# Odoo's own marker on the indicator cell of a video slide. Its presence is
# what makes the slide-index association a fact rather than an inference, so it
# is required, not merely preferred.
VIDEO_THUMB_MARKER = "o_product_video_thumb"

# An indicator cell is a thumbnail, not a document. A span longer than this
# means the element was never closed and we are looking at the rest of the
# page, where any image id we found would belong to something else.
_INDICATOR_MAX = 4000


class _Nodes(HTMLParser):
    """Every element in the page with its span, class, slide index and parent.

    Enough structure to answer two different questions from one pass: which
    element contains both a video and an image, and which carousel slide a
    video is — the second being the one the shop states outright.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.nodes: list[dict] = []
        self._stack: list[int] = []
        self._lines: list[int] = []

    def _at(self) -> int:
        line, col = self.getpos()
        return (self._lines[line - 1] if 0 < line <= len(self._lines) else 0) + col

    def parse(self, text: str) -> list[dict]:
        offset = 0
        for chunk in text.split("\n"):
            self._lines.append(offset)
            offset += len(chunk) + 1
        try:
            self.feed(text)
            self.close()
        except Exception:
            pass  # a half-parsed page still yields usable structure
        for node in self.nodes:
            if node["end"] < 0:
                node["end"] = len(text)
        return self.nodes

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        idx = len(self.nodes)
        self.nodes.append({
            "tag": tag,
            "cls": (at.get("class") or "").split(),
            "slide": at.get("data-bs-slide-to") or at.get("data-slide-to") or "",
            "start": self._at(),
            "end": self._at() if tag in _VOID else -1,
            "parent": self._stack[-1] if self._stack else -1,
        })
        if tag not in _VOID:
            self._stack.append(idx)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self.nodes[self._stack[i]]["tag"] == tag:
                close = self._at() + len(tag) + 3
                # everything opened inside an element closes with it
                for k in self._stack[i:]:
                    if self.nodes[k]["end"] < 0:
                        self.nodes[k]["end"] = close
                del self._stack[i:]
                return


def slide_posters(text: str, nodes: list[dict]) -> dict[int, str]:
    """{offset of a video → product.image id} from Odoo's own slide numbering.

    The shop states the relationship outright and we read it, rather than
    inferring anything:

        <div class="carousel-item">…<iframe src="…/embed/lFhAiGLjoMo">…</div>
                       ↑ tenth carousel item of its carousel, so slide 9
        <li data-bs-slide-to="9" class="… o_product_video_thumb">
            <img src="/web/image/product.image/20045/image_128">

    The indicator must carry Odoo's video marker: without it the cell is an
    ordinary photograph and the numbers lining up would mean nothing. Slides
    are counted within their own carousel, so a second carousel on the page
    cannot shift the numbering of the first.
    """
    indicators: dict[int, str] = {}
    for node in nodes:
        idx = node["slide"]
        if not idx.isdigit() or node["end"] <= node["start"]:
            continue
        seg = text[node["start"]:node["end"]]
        if len(seg) > _INDICATOR_MAX or VIDEO_THUMB_MARKER not in seg:
            continue
        m = _IMG_RE.search(seg)
        if m:
            indicators.setdefault(int(idx), m.group(1))
    if not indicators:
        return {}

    groups: dict[int, list[dict]] = {}
    for node in nodes:
        if "carousel-item" in node["cls"]:
            groups.setdefault(node["parent"], []).append(node)

    out: dict[int, str] = {}
    for items in groups.values():
        items.sort(key=lambda n: n["start"])
        for i, item in enumerate(items):
            iid = indicators.get(i)
            if not iid:
                continue
            for m in _YT_RE.finditer(text[item["start"]:item["end"]]):
                out[item["start"] + m.start()] = iid
    return out


def _paired_ids(nodes: list[dict], at: int, imgs: list[tuple[int, str]]) -> set[str]:
    """product.image ids in the smallest element that holds BOTH this video and
    at least one image — the supplier's own pairing, or {} when there is none.

    The fallback for shops that put the poster in the same cell as the embed
    instead of numbering their slides.
    """
    if not imgs:
        return set()
    spans = sorted(((n["start"], n["end"]) for n in nodes if n["start"] <= at < n["end"]),
                   key=lambda s: s[1] - s[0])
    for lo, hi in spans:
        near = {iid for pos, iid in imgs if lo <= pos < hi}
        if near:
            return near
    return set()


def parse_page(page: str) -> dict:
    """What the supplier's public product page says about videos.

    Returns ``{"videos": [...], "imageIds": [...]}`` where ``imageIds`` are the
    product.image records the page shows as ORDINARY photographs — the second
    half of the identification, since a record our feed has and the page never
    shows as a photograph is the video's poster.

    ``supplierImageId`` is filled by the first method that answers:

    1. **Odoo's slide numbering** — the video is carousel slide N and the
       indicator ``data-bs-slide-to="N"`` carries ``o_product_video_thumb``
       and a product.image id. The shop states the pairing; we read it.
    2. **Containment** — one image record in the smallest element that also
       holds the embed, for shops that keep the two together.

    Two candidates and neither method answers: the field stays empty and every
    photograph stays in the gallery.
    """
    if not page:
        return {"videos": [], "imageIds": []}
    # escaped slashes in inline JSON (https:\/\/…) and &amp; in href attributes
    # both hide a URL from the pattern. Neither substitution can disturb the
    # markup, so element offsets stay aligned with the text being searched —
    # a full HTML unescape could turn &lt;div&gt; in a description into a tag.
    text = _region(page.replace("\\/", "/").replace("&amp;", "&"))
    thumbs: dict[str, str] = {}
    for m in _THUMB_RE.finditer(text):
        thumbs.setdefault(m.group(1), m.group(0))
    imgs = [(m.start(), m.group(1)) for m in _IMG_RE.finditer(text)]
    nodes = _Nodes().parse(text) if _YT_RE.search(text) else []
    by_slide = slide_posters(text, nodes)

    videos: list[dict] = []
    seen: set[str] = set()
    paired: set[str] = set()
    for m in _YT_RE.finditer(text):
        vid = m.group(1) or m.group(2) or m.group(3)
        if not vid or vid in seen:
            continue
        seen.add(vid)
        pair = by_slide.get(m.start(), "")
        if not pair:
            near = _paired_ids(nodes, m.start(), imgs)
            pair = near.pop() if len(near) == 1 else ""
        if pair:
            paired.add(pair)
        videos.append({
            "youtubeId": vid,
            "thumbnail": thumbs.get(vid, f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
            "supplierImageId": pair,
        })
        if len(videos) >= MAX_VIDEOS:
            break

    ordinary: list[str] = []
    for _pos, iid in imgs:
        if iid not in paired and iid not in ordinary:
            ordinary.append(iid)
    return {"videos": videos, "imageIds": ordinary}


def parse_videos(page: str) -> list[dict]:
    """Validated YouTube entries in document order — supplier HTML in, ids out."""
    return parse_page(page)["videos"]


def image_ids(urls) -> list[str]:
    """product.image record ids from gallery URLs, in order, de-duplicated."""
    out: list[str] = []
    for url in urls or []:
        m = _IMG_RE.search(str(url))
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def associate_posters(product: dict, videos: list[dict], page_image_ids: list[str]) -> list[dict]:
    """Point each video at the product.image record the feed sent us as a photo.

    Two ways in, both from supplier data and neither from gallery position:

    1. the page paired an id with the embed (``supplierImageId``);
    2. otherwise, the set difference — one video, and exactly one of our image
       records missing from the page's ordinary photographs. That missing
       record is the poster, because the page accounts for every other one.

    Anything less certain than that leaves the video without a poster and the
    gallery untouched: deleting the wrong photograph is far worse than showing
    one image twice.
    """
    mine = image_ids(product.get("images") or [])
    by_id = {}
    for url in product.get("images") or []:
        m = _IMG_RE.search(str(url))
        if m:
            by_id.setdefault(m.group(1), str(url))

    out = [dict(v) for v in videos]
    known = {v.get("supplierImageId") for v in out if v.get("supplierImageId")}
    if len(out) == 1 and not out[0].get("supplierImageId") and page_image_ids:
        missing = [i for i in mine if i not in set(page_image_ids) | known]
        if len(missing) == 1:
            out[0]["supplierImageId"] = missing[0]

    for v in out:
        iid = v.get("supplierImageId") or ""
        # an id we do not actually hold identifies nothing to remove
        v["supplierPoster"] = by_id.get(iid, "")
        if not v["supplierPoster"]:
            v["supplierImageId"] = iid if iid in by_id else ""
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

# Bump whenever a parser change means a stored verdict could be improved on.
# An entry written under an older number is treated as absent: it is discovered
# again from the public page and rewritten. Schema 1 predates supplierImageId
# and imageIds, so every one of those entries holds a video whose poster was
# never identified — exactly the duplicate this is meant to remove. Nobody
# should ever have to delete cache files by hand for a parser fix to land.
CACHE_SCHEMA = 2


def _cache_path(market: str, tid: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]", "", str(tid))[:40]
    return _CACHE_DIR / f"{market}-{safe}.json"


def _read_cache(market: str, tid: str) -> dict | None:
    """The stored verdict for one template, or None when it has expired."""
    try:
        meta = json.loads(_cache_path(market, tid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    try:
        written_with = int(meta.get("schemaVersion") or 0)
    except (TypeError, ValueError):
        written_with = 0
    if written_with < CACHE_SCHEMA:
        return None  # written by an older parser — rediscover, do not trust
    videos = [v for v in meta.get("videos") or [] if isinstance(v, dict) and v.get("youtubeId")]
    if not meta.get("ok", True):
        ttl = config.VIDEO_ERROR_CACHE_HOURS * 3600
    elif videos:
        ttl = config.VIDEO_CACHE_DAYS * 86400
    else:
        ttl = config.VIDEO_MISS_CACHE_DAYS * 86400
    if time.time() - float(meta.get("checkedAt") or 0) > ttl:
        return None
    ids = [str(i) for i in meta.get("imageIds") or [] if str(i).isdigit()]
    return {"videos": videos, "imageIds": ids}


def _write_cache(market: str, tid: str, found: dict, ok: bool) -> None:
    """Persist the verdict, the page's own poster pairing and the ids it showed
    as ordinary photographs — so a later visit needs no second page read to
    work out which gallery image the video already is."""
    try:
        _cache_path(market, tid).write_text(json.dumps({
            "schemaVersion": CACHE_SCHEMA,
            "checkedAt": int(time.time()), "ok": ok,
            "videos": found.get("videos") or [],
            "imageIds": found.get("imageIds") or []}), encoding="utf-8")
    except OSError:
        pass  # a cache we cannot write is a slower answer, never a failed one


async def _discover(market: str, product: dict, tid: str) -> tuple[dict, bool]:
    """(page findings, reached) — reached=False means the supplier page never
    loaded, which is a retry-sooner verdict rather than 'this has no video'."""
    for url in page_urls(market, product):
        page = await fetch_page(url)
        if page is not None:
            return parse_page(page), True
    listing = await fetch_page(search_url(market, product))
    if listing is not None:
        link = link_for_template(listing, market, tid)
        if link:
            page = await fetch_page(link)
            if page is not None:
                return parse_page(page), True
    return {"videos": [], "imageIds": []}, False


async def videos_for(market: str, product: dict) -> list[dict]:
    """Videos for one catalogue product, from the API feed if it carried any,
    else from the supplier's public page — cached either way.

    Each entry may carry ``supplierImageId`` / ``supplierPoster``: the gallery
    photograph that IS this video's poster, so the page can drop it instead of
    showing the same frame twice, once playable and once not. The pairing is
    resolved against this product's own image list on every call, so a variant
    with a different gallery gets its own answer from one cached page read.
    """
    existing = [{"youtubeId": v["youtubeId"], "thumbnail": v.get("thumbnail") or "",
                 "supplierImageId": "", "supplierPoster": ""}
                for v in (product.get("videos") or [])
                if isinstance(v, dict) and v.get("youtubeId")]
    if existing:
        # a feed-supplied video already keeps its poster out of images
        return existing
    tid = template_id(product)
    if not tid:
        return []
    cached = _read_cache(market, tid)
    if cached is not None:
        return associate_posters(product, cached["videos"], cached["imageIds"])
    st = _state()
    key = f"{market}:{tid}"
    lock = st["keys"].get(key)
    if lock is None:
        lock = st["keys"].setdefault(key, asyncio.Lock())
    async with lock:
        # a concurrent request for the same template may have just filled it
        cached = _read_cache(market, tid)
        if cached is not None:
            return associate_posters(product, cached["videos"], cached["imageIds"])
        found, reached = await _discover(market, product, tid)
        _write_cache(market, tid, found, reached)
        if len(st["keys"]) > 500:
            st["keys"].clear()
        return associate_posters(product, found["videos"], found["imageIds"])


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
        if int(meta.get("schemaVersion") or 0) < CACHE_SCHEMA:
            continue  # awaiting rediscovery — not a verdict yet
        if meta.get("videos"):
            hits += 1
        else:
            misses += 1
    return {"withVideo": hits, "withoutVideo": misses, "entries": hits + misses}
