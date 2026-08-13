"""Elite Marcom website backend — giveaways supplier integration.

Backend-only Jasani client: exact host allowlist, no redirects, response
caps, hardened XML parsing, normalized private cache, daily budget.
The supplier token never reaches the browser.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import urllib.parse
from typing import Any

import httpx
from defusedxml import ElementTree as SafeET

from . import config

_CACHE_DIR = config.RUNTIME_DIR / "cache"
_lock = threading.Lock()

ALLOWED_CONTENT_TYPES = ("application/json", "text/json", "application/xml", "text/xml")


class SupplierUnavailable(Exception):
    pass


# ---------------- primary-call budget ----------------
# Jasani allows at most SUPPLIER_DAILY_BUDGET primary GET calls (products,
# price, stock) per day, measured in UAE time (UTC+4). Branding endpoints are
# documented outside the limit. The counter persists across restarts.

def _market_day(market: str) -> str:
    """The supplier day for one market, in that market's own local time.

    KSA runs an hour behind the UAE, so a single shared clock would roll one
    market's allowance over at the wrong moment — an hour in which a sync
    looks due but the supplier still counts it against yesterday."""
    offset = config.JASANI_UTC_OFFSET.get(market, 4)
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset * 3600))


def _market_local(market: str) -> tuple[str, int]:
    """(local day, local hour) for a market."""
    offset = config.JASANI_UTC_OFFSET.get(market, 4)
    local = time.gmtime(time.time() + offset * 3600)
    return time.strftime("%Y-%m-%d", local), local.tm_hour


def _budget_file():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "supplier-budget.json"


def _read_all_budgets() -> dict:
    """Per-market counters. Accepts the single-counter file this replaced and
    charges the old count to both markets, so an upgrade mid-day can only
    under-spend, never over-spend."""
    try:
        data = json.loads(_budget_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    if "count" in data or "day" in data:          # legacy shared counter
        legacy = {"day": str(data.get("day", "")), "count": int(data.get("count", 0))}
        return {m: dict(legacy) for m in config.JASANI_HOSTS}
    out = {}
    for market, entry in data.items():
        if isinstance(entry, dict):
            out[market] = {"day": str(entry.get("day", "")), "count": int(entry.get("count", 0)),
                           "slots": entry.get("slots") if isinstance(entry.get("slots"), dict) else {}}
    return out


def _read_budget(market: str) -> dict:
    entry = _read_all_budgets().get(market) or {}
    return {"day": str(entry.get("day", "")), "count": int(entry.get("count", 0)),
            "slots": entry.get("slots") or {}}


def _write_budget(market: str, budget: dict) -> None:
    try:
        data = _read_all_budgets()
        data[market] = budget
        _budget_file().write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _budget_ok(market: str, manual: bool = False) -> bool:
    """Spend one primary call from this market's own allowance.

    Each market has its own supplier account and its own five calls a day.
    Background work stops at SUPPLIER_AUTO_BUDGET so the remaining call stays
    available for a person: when a catalogue is visibly wrong, an owner or
    admin must still be able to force a sync. Only an explicitly manual
    refresh may reach into that reserve."""
    day = _market_day(market)
    ceiling = config.SUPPLIER_DAILY_BUDGET if manual else config.SUPPLIER_AUTO_BUDGET
    with _lock:
        budget = _read_budget(market)
        if budget["day"] != day:
            budget = {"day": day, "count": 0, "slots": {}}
        if budget["count"] >= ceiling:
            return False
        budget["count"] += 1
        _write_budget(market, budget)
        return True


def _budget_refund(market: str) -> None:
    """Give back a call that never reached Jasani.

    _budget_ok() spends the call before the request goes out, so a DNS, TLS,
    connect or timeout failure — where the supplier never served anything —
    would otherwise burn one of the five. A handful of failed attempts could
    then exhaust the day for that market and look exactly like a dead API.
    Anything that came back with an HTTP status was served and still counts."""
    day = _market_day(market)
    with _lock:
        budget = _read_budget(market)
        if budget["day"] == day and budget["count"] > 0:
            budget["count"] -= 1
            _write_budget(market, budget)


def _budget_exhaust(market: str) -> None:
    """After a 403 (documented for over-limit, bad token or bad URL) stop
    calling this market's primary APIs until its day resets — never retry a
    403. The other market has its own token and is unaffected."""
    with _lock:
        budget = _read_budget(market)
        _write_budget(market, {"day": _market_day(market),
                               "count": config.SUPPLIER_DAILY_BUDGET,
                               "slots": budget.get("slots") or {}})


def _slot_done(market: str, day: str, hour: int) -> bool:
    return hour in (_read_budget(market).get("slots") or {}).get(day, [])


def _mark_slot(market: str, day: str, hour: int) -> None:
    with _lock:
        budget = _read_budget(market)
        slots = {day: sorted(set((budget.get("slots") or {}).get(day, []) + [hour]))}
        budget["slots"] = slots          # only today's slots are worth keeping
        _write_budget(market, budget)


def _token(market: str) -> str:
    return urllib.parse.quote(config.JASANI_TOKENS.get(market, ""), safe="")


def _status_file():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "supplier-status.json"


def _scrub(text: str) -> str:
    """A reason string is shown in the admin panel — never let it carry a token."""
    for token in config.JASANI_TOKENS.values():
        if token:
            text = text.replace(token, "***")
    return text[:160]


def record_attempt(market: str, what: str, ok: bool, reason: str = "") -> None:
    """Persist the outcome of a supplier call.

    Without this a failed refresh is a toast that disappears, and the console
    can only say 'nothing cached yet' — which is indistinguishable from never
    having tried. The supplier guide also asks that staff be alerted when a
    previously working configuration starts refusing calls."""
    with _lock:
        try:
            data = json.loads(_status_file().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[market] = {"ts": int(time.time()), "what": what, "ok": bool(ok),
                        "reason": _scrub(reason)}
        try:
            _status_file().write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass


def last_attempt(market: str) -> dict | None:
    try:
        data = json.loads(_status_file().read_text(encoding="utf-8"))
        entry = data.get(market) if isinstance(data, dict) else None
        return entry if isinstance(entry, dict) else None
    except (OSError, ValueError):
        return None


def _host(market: str) -> str:
    host = config.JASANI_HOSTS.get(market)
    if not host:
        raise SupplierUnavailable("unknown market")
    return host


async def _fetch(url: str, expected_host: str, market: str, primary: bool = True,
                 manual: bool = False) -> tuple[bytes, str]:
    """primary=True marks the rate-limited product/price/stock endpoints;
    branding endpoints are documented outside the daily limit. manual=True is
    an admin-triggered sync, the only thing allowed to use the reserved call.
    The budget spent is always the one belonging to `market`."""
    if not config.JASANI_TOKENS.get(market):
        raise SupplierUnavailable(f"no supplier token configured for {market.upper()}")
    if primary and not _budget_ok(market, manual):
        raise SupplierUnavailable(
            "daily supplier budget exhausted"
            if manual else
            "automatic supplier calls are used up for today — the reserved call "
            "is available from the Jasani console")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.port not in (None, 443):
        if primary:
            _budget_refund(market)
        raise SupplierUnavailable("blocked upstream url")
    try:
        async with httpx.AsyncClient(
            timeout=config.SUPPLIER_TIMEOUT_S,
            follow_redirects=False,   # no redirects
            trust_env=False,          # no environment proxy inheritance
        ) as client:
            async with client.stream("GET", url) as res:
                if res.status_code == 403 and primary:
                    # documented for over-limit / bad token / bad URL — do not retry today
                    _budget_exhaust(market)
                    raise SupplierUnavailable("upstream 403 — primary calls paused until the UAE-day reset")
                if res.status_code != 200:
                    raise SupplierUnavailable(f"upstream {res.status_code}")
                ctype = res.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and ctype not in ALLOWED_CONTENT_TYPES:
                    raise SupplierUnavailable(f"unexpected content type {ctype}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in res.aiter_bytes():
                    total += len(chunk)
                    if total > config.SUPPLIER_MAX_BYTES:
                        raise SupplierUnavailable("upstream response too large")
                    chunks.append(chunk)
    except SupplierUnavailable:
        raise
    except Exception as exc:  # network/TLS/protocol failures → controlled unavailability
        if primary:
            _budget_refund(market)   # nothing was served, so nothing was spent
        raise SupplierUnavailable(f"transport: {exc.__class__.__name__}") from exc
    return b"".join(chunks), ctype


# ---------------- parsing / normalization ----------------

def _parse_records(raw: bytes, ctype: str) -> list[dict]:
    """Accept ordinary JSON, XML record collections, or XML-RPC-style XML."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    if "json" in ctype or text[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            return []
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            for key in ("products", "data", "items", "records", "result"):
                v = data.get(key)
                if isinstance(v, list):
                    return [r for r in v if isinstance(r, dict)]
            return [data]
        return []
    # XML — hardened parser, entity expansion disabled by defusedxml
    try:
        root = SafeET.fromstring(text)
    except Exception:
        return []
    records: list[dict] = []

    def element_to_dict(el) -> dict:
        out: dict[str, Any] = {}
        for child in el:
            tag = re.sub(r"\{.*\}", "", child.tag).strip()
            if len(child):
                sub = element_to_dict(child)
                if tag in out and isinstance(out[tag], list):
                    out[tag].append(sub)
                elif tag in out:
                    out[tag] = [out[tag], sub]
                else:
                    out[tag] = sub
            else:
                out[tag] = (child.text or "").strip()
        return out

    # XML-RPC-style: <struct><member><name>..<value>..
    if root.find(".//struct") is not None:
        for struct in root.findall(".//struct"):
            rec: dict[str, Any] = {}
            for member in struct.findall("member"):
                name = member.findtext("name", "").strip()
                value_el = member.find("value")
                if not name or value_el is None:
                    continue
                leaf = value_el
                while len(leaf) == 1:
                    leaf = leaf[0]
                rec[name] = (leaf.text or "").strip()
            if rec:
                records.append(rec)
        return records
    # plain record collections: repeated child elements
    for child in root:
        if len(child):
            records.append(element_to_dict(child))
    return records


def _normalize_keys(rec: dict) -> dict:
    """Case/format-insensitive access: 'ProductDescription' → 'productdescription',
    'image-url' → 'image_url' → 'imageurl'. Original values are kept as-is."""
    out: dict = {}
    for k, v in rec.items():
        key = str(k).strip().lower().replace("-", "_")
        out.setdefault(key, v)
        out.setdefault(key.replace("_", ""), v)
    return out


# Odoo-style empty markers: the supplier serializes blank fields as boolean
# false, which some payloads stringify to "False"/"None".
_EMPTY_MARKERS = frozenset({"false", "none", "null", "n/a", "na", "-"})


def _s(rec: dict, *keys: str) -> str:
    for k in keys:
        v = rec.get(k)
        if v is None:
            v = rec.get(k.replace("_", ""))
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, (str, int, float)):
            s = str(v).strip()
            if s and s.lower() not in _EMPTY_MARKERS:
                return s
    return ""


def _i(rec: dict, *keys: str) -> int:
    raw = _s(rec, *keys)
    m = re.search(r"-?\d+", raw.replace(",", ""))
    return int(m.group()) if m else 0


def _clean_description(raw: str) -> str:
    """Strip markup and entities from supplier descriptions; keep readable text."""
    import html as _html

    text = re.sub(r"<\s*(br|/p|/li|/div)\s*/?\s*>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:2500]


def _weight(rec: dict, *keys: str, ndigits: int = 2) -> str:
    """Weight-ish numeric strings: trim float artifacts like 14.200000000000001."""
    raw = _s(rec, *keys)
    m = re.match(r"^(-?\d+(?:\.\d+)?)(.*)$", raw)
    if not m:
        return raw[:40]
    try:
        num = float(m.group(1))
    except ValueError:
        return raw[:40]
    if num <= 0:
        return ""
    trimmed = f"{num:.{ndigits}f}".rstrip("0").rstrip(".")
    return (trimmed + m.group(2))[:40]


def _rel_names(v: Any) -> list[str]:
    """Display names from Odoo relational values: [id, "Name"] pairs, lists of
    {display_name/name} dicts, or plain strings. Bare ids carry no name."""
    if v is None or isinstance(v, bool):
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s and s.lower() not in _EMPTY_MARKERS else []
    if isinstance(v, dict):
        for k in ("display_name", "name"):
            n = v.get(k)
            if isinstance(n, str) and n.strip():
                return [n.strip()]
        return []
    if isinstance(v, (list, tuple)):
        # a single many2one pair: [3, "Giftology"]
        if len(v) == 2 and isinstance(v[0], (int, float)) and isinstance(v[1], str):
            return [v[1].strip()] if v[1].strip() else []
        out: list[str] = []
        for item in v:
            out.extend(_rel_names(item))
        return out[:20]
    return []


def _rel_ids(v: Any) -> list[str]:
    """Record ids from Odoo relational values: ints, [id, name] pairs, or {id: ...} dicts."""
    if v is None or isinstance(v, bool):
        return []
    if isinstance(v, (int, float)):
        return [str(int(v))]
    if isinstance(v, str):
        return [p.strip() for p in re.split(r"[|;,]", v) if p.strip().isdigit()]
    if isinstance(v, dict):
        i = v.get("id")
        return [str(int(i))] if isinstance(i, (int, float)) and not isinstance(i, bool) else []
    if isinstance(v, (list, tuple)):
        if len(v) == 2 and isinstance(v[0], (int, float)) and isinstance(v[1], str):
            return [str(int(v[0]))]
        out: list[str] = []
        for item in v:
            out.extend(_rel_ids(item))
        return out[:20]
    return []


def _list(rec: dict, *keys: str) -> list[str]:
    for k in keys:
        v = rec.get(k)
        if isinstance(v, list):
            out: list[str] = []
            for x in v:
                if isinstance(x, dict):  # e.g. {"url": ...} or {"display_name": ...}
                    for dk in ("url", "image_url", "src", "href", "display_name", "name"):
                        dv = x.get(dk)
                        if isinstance(dv, str) and dv.strip():
                            out.append(dv.strip())
                            break
                elif isinstance(x, (str, int, float)) and not isinstance(x, bool):
                    s = str(x).strip()
                    if s and s.lower() not in _EMPTY_MARKERS:
                        out.append(s)
            return out[:20]
        if isinstance(v, str) and v.strip():
            return [p.strip() for p in re.split(r"[|;,]", v) if p.strip()][:20]
    return []


# Every YouTube link shape the supplier feed has been seen to carry. The
# watch form is matched on the query rather than immediately after "watch?",
# because real links routinely put other parameters first
# (…/watch?app=desktop&v=ID, …/watch?feature=share&v=ID).
_YT_PATH_RE = re.compile(
    r"(?:youtube\.com|youtube-nocookie\.com|youtu\.be)"
    r"(?:/(?:shorts|embed|live|v|e))?/([A-Za-z0-9_-]{6,20})")
_YT_QUERY_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{6,20})")


def _youtube_id(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    text = url.strip()
    if "youtu" not in text.lower():
        return ""
    m = _YT_QUERY_RE.search(text)
    if m:
        return m.group(1)
    m = _YT_PATH_RE.search(text)
    if not m:
        return ""
    # ".../watch" with no v= is not a video reference
    return "" if m.group(1).lower() in ("watch", "playlist", "channel", "user") else m.group(1)


_VIDEO_KEYS = ("video_url", "videourl", "video", "youtube_url", "youtubeurl",
               "youtube", "video_link", "videolink", "movie_url", "media_url")


def _entry_video_url(v: dict) -> str:
    """Truthy video link on an image record (Odoo attaches video_url to the
    entry and keeps the thumbnail in image_url).

    The supplier is not consistent about the key, so after the known names we
    fall back to any value in the record that reads as a YouTube link. Getting
    this wrong is not a missing field — the entry silently becomes a gallery
    image, which is why a product video shows up as a still picture."""
    for k in _VIDEO_KEYS:
        u = v.get(k)
        if isinstance(u, str) and u.strip() and u.strip().lower() not in _EMPTY_MARKERS:
            return u.strip()
    for value in v.values():
        if isinstance(value, str) and _youtube_id(value):
            return value.strip()
    return ""


def _image_urls(v: Any, depth: int = 0) -> list[str]:
    """URLs from the supplier's images field, which nests arbitrarily:
    images: [[{"id": 1954, "image_url": "..."}, ...]] — flatten everything.
    Entries carrying a video link are videos, not gallery images."""
    if depth > 4 or v is None or isinstance(v, bool):
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s and s.lower() not in _EMPTY_MARKERS else []
    if isinstance(v, dict):
        if _entry_video_url(v):
            return []
        for k in ("image_url", "imageurl", "url", "src", "href", "image"):
            u = v.get(k)
            if isinstance(u, str) and u.strip():
                return [u.strip()]
        return []
    if isinstance(v, (list, tuple)):
        out: list[str] = []
        for item in v:
            out.extend(_image_urls(item, depth + 1))
            if len(out) >= 40:
                break
        return out[:40]
    return []


def _video_entries(v: Any, depth: int = 0) -> list[dict]:
    """YouTube videos hidden in the images field: {youtubeId, thumbnail}.
    Only recognized YouTube ids are kept — no raw supplier URLs pass through."""
    if depth > 4 or v is None or isinstance(v, bool):
        return []
    if isinstance(v, str):
        vid = _youtube_id(v)
        return [{"youtubeId": vid, "thumbnail": ""}] if vid else []
    if isinstance(v, dict):
        url = _entry_video_url(v)
        vid = _youtube_id(url)
        if not vid:
            return []
        thumb = ""
        for k in ("image_url", "imageurl", "url", "src", "image"):
            u = v.get(k)
            if isinstance(u, str) and u.strip():
                thumb = u.strip()
                break
        return [{"youtubeId": vid, "thumbnail": thumb}]
    if isinstance(v, (list, tuple)):
        out: list[dict] = []
        for item in v:
            out.extend(_video_entries(item, depth + 1))
            if len(out) >= 6:
                break
        return out[:6]
    return []


# base domains whose https subdomains may serve product imagery / documents
_SUPPLIER_DOMAINS = ("giftsksa.com", "jasani.ae")


def _safe_supplier_url(url: str) -> str:
    """Only https URLs on an approved supplier domain (or its subdomains)."""
    if not url:
        return ""
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return ""
    hostname = p.hostname or ""
    allowed = any(hostname == d or hostname.endswith("." + d) for d in _SUPPLIER_DOMAINS)
    if p.scheme != "https" or not allowed or p.port not in (None, 443):
        return ""
    if p.username or p.password or p.fragment:
        return ""
    return urllib.parse.urlunsplit(("https", hostname, p.path, p.query, ""))


def _safe_image(url: str, host: str) -> str:
    return _safe_supplier_url(url)


def normalize_product(rec: dict, market: str) -> dict | None:
    """Map one supplier record to the public catalog shape (no cost fields)."""
    try:
        rec = _normalize_keys(rec)
        pid = _s(rec, "id", "product_id", "internal_id", "item_id", "itemid")
        code = _s(rec, "code", "product_code", "item_code", "sku", "default_code", "itemcode", "model")
        name = _s(rec, "name", "product_name", "title", "item_name", "itemname")
        if not (pid or code) or not name:
            return None
        host = config.JASANI_HOSTS[market]
        # primary image first (image_url), then the flattened images array
        images = []
        for key in ("image", "image_url", "main_image", "thumbnail"):
            v = _s(rec, key)
            if v:
                images.append(v)
        videos: list[dict] = []
        for key in ("images", "image_urls", "gallery", "additional_images", "extra_images", "videos"):
            raw_v = rec.get(key) or rec.get(key.replace("_", ""))
            images.extend(_image_urls(raw_v))
            videos.extend(_video_entries(raw_v))
        images = [u for u in (_safe_image(u, host) for u in images) if u][:36]
        seen_vids: set[str] = set()
        videos = [{"youtubeId": v["youtubeId"], "thumbnail": _safe_image(v["thumbnail"], host)}
                  for v in videos
                  if not (v["youtubeId"] in seen_vids or seen_vids.add(v["youtubeId"]))][:4]
        # de-duplicate while preserving order
        seen_imgs: set[str] = set()
        images = [u for u in images if not (u in seen_imgs or seen_imgs.add(u))]
        tags = _list(rec, "product_template_tags", "tags", "collections", "labels")
        if not tags:
            tags = _rel_names(rec.get("product_template_tags") or rec.get("producttemplatetags"))
        cats = _list(rec, "categories", "category", "product_category")
        if not cats:
            cats = _rel_names(rec.get("public_categ_ids") or rec.get("publiccategids"))
        lower = " ".join(tags + cats).lower()
        brand = _s(rec, "brand", "brand_name") or " / ".join(_rel_names(rec.get("brand_id")))
        raw_conf = rec.get("configurable")
        configurable = raw_conf is True or str(raw_conf).strip().lower() == "true"
        parent_id = (_rel_ids(rec.get("parent_id") or rec.get("parentid")
                              or rec.get("product_tmpl_id") or rec.get("producttmplid")) or [None])[0]
        # garment size / colour variants, e.g. [{"display_name": "Size: M"}, ...]
        options = _list(rec, "options", "variants", "attributes")
        options.extend(_rel_names(rec.get("product_template_attribute_value_ids")
                                  or rec.get("producttemplateattributevalueids")))
        seen_opts: set[str] = set()
        options = [o for o in options if not (o in seen_opts or seen_opts.add(o))][:20]
        # net_available_qty is Jasani's guaranteed-sellable quantity; the rest
        # are fallbacks seen in other payload variants
        available = max(0, _i(rec, "net_available_qty", "net_stock", "available_stock", "stock",
                              "net_available", "qty_available", "free_qty", "available_qty",
                              "quantity_available"))
        incoming = max(0, _i(rec, "incoming_qty", "incoming_stock", "incoming", "expected_stock"))
        return {
            "id": pid or code,
            "code": code or pid,
            "barcode": _s(rec, "barcode", "ean")[:40],
            "name": name[:200],
            "brand": brand[:100],
            "description": _clean_description(_s(
                rec, "description", "product_description", "description_sale",
                "website_description", "long_description", "web_description",
                "item_description", "short_description", "details",
                "specification", "specifications", "desc")),
            "categories": cats,
            "tags": tags,
            "market": market,
            # parent_id is the product template id; per the supplier docs it is
            # only meaningful for grouping when configurable is true, but it is
            # also the candidate id for the supplier's printing-manual PDF
            "configurable": configurable,
            "templateId": parent_id if configurable else None,
            "parentId": parent_id,
            "color": _s(rec, "color", "colour")[:60],
            "options": options,
            "image": images[0] if images else "",
            "images": images,
            "videos": videos,
            # alternative-colour product ids, resolved against the catalog later
            "_colorOptionIds": _rel_ids(rec.get("color_options") or rec.get("coloroptions")),
            "sequence": _i(rec, "website_sequence", "sequence", "sort_order", "newness"),
            "isNew": bool(re.search(r"\bnew\b", lower)) or _i(rec, "is_new") == 1,
            "sustainable": "sustain" in lower or "eco" in lower or "recycl" in lower,
            "luxury": "lux" in lower or "premium" in lower,
            "ramadan": "ramadan" in lower or "tradition" in lower,
            "hsCode": _s(rec, "hs_code", "hscode")[:30],
            "unitsPerCarton": _i(rec, "units_per_carton", "carton_qty") or None,
            "cartonDimensions": _s(rec, "carton_dimensions", "carton_size")[:80] or None,
            "cartonWeight": _weight(rec, "carton_weight", "carton_weight_kg") or None,
            "cartonVolume": _weight(rec, "carton_volume", "carton_cbm", ndigits=3) or None,
            # blocked_qty stays internal per supplier policy — never in this payload
            "stock": {
                "available": available,
                "incoming": incoming,
                "incomingDate": _s(rec, "incoming_date", "expected_date")[:30] or None,
            },
        }
    except Exception:
        # malformed records are untrusted input — skip safely
        return None


def _merge_stock(products: list[dict], stock_records: list[dict]) -> int:
    """Returns how many products found a matching stock row."""
    by_key: dict[str, dict] = {}
    for rec in stock_records:
        rec = _normalize_keys(rec)
        # a stock row may carry both an id and an item code — index it under every
        # identifier so products can match on either
        for key_name in ("id", "product_id", "code", "product_code", "sku",
                         "default_code", "item_code", "itemcode", "model"):
            key = _s(rec, key_name)
            if key:
                by_key.setdefault(key, rec)
    matched = 0
    for p in products:
        rec = by_key.get(p["id"]) or by_key.get(p["code"])
        if rec:
            matched += 1
            p["stock"]["available"] = max(0, _i(rec, "net_available_qty", "net_stock", "available_stock",
                                                "stock", "net_available", "qty_available", "free_qty",
                                                "available_qty", "quantity_available"))
            p["stock"]["incoming"] = max(0, _i(rec, "incoming_qty", "incoming_stock", "incoming", "expected_stock"))
            inc = _s(rec, "incoming_date", "expected_date")[:30]
            if inc:
                p["stock"]["incomingDate"] = inc
    return matched


# ---------------- cache ----------------

def _cache_file(market: str) -> Any:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"giveaways-{market}.json"


def _read_cache(market: str) -> dict | None:
    f = _cache_file(market)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(market: str, products: list[dict], fetched_at: float, stock_at: float) -> None:
    # explicit UTF-8: Windows' locale default (cp1252) cannot encode many
    # supplier product names, and a failed cache write must not fail the request
    try:
        f = _cache_file(market)
        f.write_text(json.dumps({"fetchedAt": int(fetched_at), "stockAt": int(stock_at),
                                 "products": products}, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError):
        pass


def _resolve_color_options(products: list[dict]) -> None:
    """Replace raw color_options ids with public references to catalog siblings.

    Per the supplier docs, color_options carries product TEMPLATE ids, so match
    against each product's parent/template id first; variant ids are only a
    fallback. Unresolved ids are dropped — never build links from raw ids."""
    by_template: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for p in products:
        by_id[p["id"]] = p
        tid = p.get("parentId")
        if tid:
            by_template.setdefault(tid, p)
    for p in products:
        ids = p.pop("_colorOptionIds", []) or []
        own_template = p.get("parentId")
        opts = []
        for cid in ids:
            if own_template and cid == own_template:
                continue
            alt = by_template.get(cid) or by_id.get(cid)
            if alt and alt["id"] != p["id"]:
                opts.append({"id": alt["id"], "name": alt["name"],
                             "color": alt["color"], "image": alt["image"]})
        p["colorOptions"] = opts[:12]


async def _fetch_products(market: str, manual: bool = False) -> list[dict]:
    """One primary Product API call, normalized. Raises SupplierUnavailable."""
    host = _host(market)
    raw, ctype = await _fetch(f"https://{host}/products/all/{_token(market)}", host,
                              market, manual=manual)
    records = _parse_records(raw, ctype)[: config.SUPPLIER_MAX_RECORDS]
    products = [p for p in (normalize_product(r, market) for r in records) if p]
    if not products:
        raise SupplierUnavailable("no usable records")
    _resolve_color_options(products)
    if not any(p["description"] for p in products):
        # no description in the whole catalog — dump one raw row so the actual
        # supplier field names are visible in the console
        print(f"[jasani] {market} no descriptions mapped; raw product sample: "
              f"{json.dumps(records[0], ensure_ascii=False, default=str)[:600]}", flush=True)
    return products


async def _apply_stock(market: str, products: list[dict], manual: bool = False) -> None:
    """One primary Stock API call merged onto products. Raises SupplierUnavailable."""
    host = _host(market)
    raw_s, ctype_s = await _fetch(f"https://{host}/products/stock/{_token(market)}", host,
                                  market, manual=manual)
    stock_records = _parse_records(raw_s, ctype_s)[: config.SUPPLIER_MAX_RECORDS]
    matched = _merge_stock(products, stock_records)
    in_stock = sum(1 for p in products if p["stock"]["available"] > 0)
    print(f"[jasani] {market}: {len(products)} products, {len(stock_records)} stock rows, "
          f"{matched} matched, {in_stock} with stock > 0", flush=True)
    if stock_records and not in_stock:
        # every quantity parsed to zero — show the raw row so the actual
        # field names (or supplier-side zeros) are visible in the console
        print(f"[jasani] {market} raw stock sample: "
              f"{json.dumps(stock_records[0], ensure_ascii=False, default=str)[:400]}", flush=True)


async def _refresh_in_background(market: str) -> None:
    """Bring a due snapshot up to date without anyone waiting for it."""
    lock = _refresh_lock(market)
    if lock.locked():
        return
    async with lock:
        cached = _read_cache(market)
        now = time.time()
        products_due = not cached or now - cached.get("fetchedAt", 0) >= config.PRODUCT_REFRESH_HOURS * 3600
        stock_due = not cached or now - cached.get("stockAt", cached.get("fetchedAt", 0)) >= config.STOCK_REFRESH_HOURS * 3600
        try:
            if products_due:
                products = await _fetch_products(market)
                stock_at = 0.0
                try:
                    await _apply_stock(market, products)
                    stock_at = now
                except SupplierUnavailable as exc:
                    record_attempt(market, "stock", False, str(exc))
                _write_cache(market, products, fetched_at=now, stock_at=stock_at)
                if stock_at:
                    record_attempt(market, "products", True, f"{len(products)} products with stock")
            elif stock_due and cached:
                products = cached["products"]
                await _apply_stock(market, products)
                _write_cache(market, products, fetched_at=cached.get("fetchedAt", now), stock_at=now)
                record_attempt(market, "stock", True, f"{len(products)} products")
        except SupplierUnavailable as exc:
            record_attempt(market, "products" if products_due else "stock", False, str(exc))
        except Exception as exc:  # never let a background task escape
            print(f"[jasani] {market}: background refresh error {exc.__class__.__name__}", flush=True)


def _schedule_refresh(market: str) -> None:
    """Kick off a refresh and forget about it. Nothing awaits this: a visitor
    must never wait on the supplier."""
    if _refresh_lock(market).locked():
        return
    try:
        task = asyncio.get_running_loop().create_task(_refresh_in_background(market))
        _background.add(task)
        task.add_done_callback(_background.discard)
    except RuntimeError:
        pass  # no running loop (tests, scripts) — the next request will try again


_background: set = set()


async def get_catalog(market: str) -> tuple[list[dict], str]:
    """Return (products, state) — state in {'live','cache','stale'}.

    A visitor is never made to wait on Jasani. The cached snapshot is returned
    straight away and, when it is due, a refresh runs in the background for the
    next visitor to benefit from. Only a completely cold cache — no snapshot at
    all — has anything to block on, and even then the page falls back to the
    local preview catalogue rather than hanging."""
    cached = _read_cache(market)
    if cached and cached.get("products"):
        now = time.time()
        products_fresh = now - cached.get("fetchedAt", 0) < config.PRODUCT_REFRESH_HOURS * 3600
        stock_fresh = now - cached.get("stockAt", cached.get("fetchedAt", 0)) < config.STOCK_REFRESH_HOURS * 3600
        # No refresh is triggered from a page load: the four scheduled syncs
        # own the automatic allowance, and a visitor-driven top-up on top of
        # them would push the market past four calls a day.
        return cached["products"], "cache" if (products_fresh and stock_fresh) else "stale"

    # Nothing cached at all: this is the only path that can wait, and it only
    # happens before the first successful sync of a market.
    lock = _refresh_lock(market)
    if lock.locked():
        raise SupplierUnavailable("first catalogue sync in progress")
    async with lock:
        cached = _read_cache(market)
        if cached and cached.get("products"):
            return cached["products"], "cache"
        now = time.time()
        try:
            products = await _fetch_products(market)
        except SupplierUnavailable as exc:
            record_attempt(market, "products", False, str(exc))
            raise
        stock_at = 0.0
        try:
            await _apply_stock(market, products)
            stock_at = now
        except SupplierUnavailable as exc:
            print(f"[jasani] {market}: stock feed unavailable ({exc})", flush=True)
            record_attempt(market, "stock", False, str(exc))
        _write_cache(market, products, fetched_at=now, stock_at=stock_at)
        if stock_at:
            record_attempt(market, "products", True, f"{len(products)} products with stock")
        return products, "live"


async def _refresh_products_only(market: str) -> None:
    """One products call, keeping the stock figures already cached.

    A full refresh costs two calls; the schedule allows four a day in total,
    so the midnight products sync spends exactly one and carries yesterday's
    stock forward until the morning stock call replaces it."""
    cached = _read_cache(market) or {}
    previous = {p["id"]: p.get("stock") for p in cached.get("products", []) if p.get("id")}
    products = await _fetch_products(market)
    for product in products:
        carried = previous.get(product["id"])
        if carried and not (product.get("stock") or {}).get("available"):
            product["stock"] = carried
    _write_cache(market, products,
                 fetched_at=time.time(),
                 stock_at=cached.get("stockAt", 0) or 0)
    record_attempt(market, "products", True, f"{len(products)} products (scheduled)")


async def run_due_slots() -> list[str]:
    """Run any automatic sync whose hour has arrived in that market's local
    time and which has not run yet today. One call per slot, never more."""
    ran = []
    for market in config.JASANI_HOSTS:
        if not config.JASANI_TOKENS.get(market):
            continue
        day, hour = _market_local(market)
        for slot_hour, what in config.JASANI_SCHEDULE:
            if slot_hour > hour or _slot_done(market, day, slot_hour):
                continue
            lock = _refresh_lock(market)
            if lock.locked():
                break
            async with lock:
                try:
                    if what == "products":
                        await _refresh_products_only(market)
                    else:
                        cached = _read_cache(market)
                        if not cached or not cached.get("products"):
                            await _refresh_products_only(market)
                        else:
                            products = cached["products"]
                            await _apply_stock(market, products)
                            _write_cache(market, products,
                                         fetched_at=cached.get("fetchedAt", time.time()),
                                         stock_at=time.time())
                            record_attempt(market, "stock", True,
                                           f"{len(products)} products (scheduled)")
                except SupplierUnavailable as exc:
                    record_attempt(market, what, False, str(exc))
                except Exception as exc:
                    print(f"[jasani] {market} scheduled {what}: {exc.__class__.__name__}", flush=True)
            # marked either way: a failed slot must not be retried all day,
            # which is how a single bad hour turns into a spent allowance
            _mark_slot(market, day, slot_hour)
            ran.append(f"{market}:{slot_hour:02d}:{what}")
            break            # at most one scheduled call per market per tick
    return ran


async def warm_catalogues() -> None:
    """Startup warm-up so the first visitor of the day meets a filled cache
    rather than a supplier call. Uses the automatic allowance only."""
    for market in config.JASANI_HOSTS:
        cached = _read_cache(market)
        now = time.time()
        due = (not cached or not cached.get("products")
               or now - cached.get("fetchedAt", 0) >= config.PRODUCT_REFRESH_HOURS * 3600
               or now - cached.get("stockAt", cached.get("fetchedAt", 0)) >= config.STOCK_REFRESH_HOURS * 3600)
        if due:
            await _refresh_in_background(market)


# ---------------- admin console (Phase 1) ----------------
# Read-only status plus explicitly guarded refresh actions for the admin
# panel. Everything here respects the same daily budget and never exposes
# the supplier token.

def next_slot(market: str) -> dict | None:
    """The next scheduled automatic sync for a market, in its local time."""
    day, hour = _market_local(market)
    done = (_read_budget(market).get("slots") or {}).get(day, [])
    for slot_hour, what in config.JASANI_SCHEDULE:
        if slot_hour not in done:
            # A slot whose hour has already passed is still run — a server
            # started at midday must not skip the morning sync — so report it
            # as due now rather than pointing at the next hour on the clock.
            return {"hour": slot_hour, "what": what, "today": True,
                    "due": slot_hour <= hour}
    first = config.JASANI_SCHEDULE[0]
    return {"hour": first[0], "what": first[1], "today": False, "due": False}


def budget_status(market: str) -> dict:
    """One market's primary-call budget, without consuming a call."""
    day = _market_day(market)
    offset = config.JASANI_UTC_OFFSET.get(market, 4)
    with _lock:
        budget = _read_budget(market)
    used = budget["count"] if budget["day"] == day else 0
    local_now = time.time() + offset * 3600
    return {"market": market, "day": day, "used": used,
            "limit": config.SUPPLIER_DAILY_BUDGET,
            "remaining": max(0, config.SUPPLIER_DAILY_BUDGET - used),
            "autoLimit": config.SUPPLIER_AUTO_BUDGET,
            "autoRemaining": max(0, config.SUPPLIER_AUTO_BUDGET - used),
            "reserved": max(0, config.SUPPLIER_DAILY_BUDGET - config.SUPPLIER_AUTO_BUDGET),
            "resetInSeconds": int(86400 - (local_now % 86400)),
            "utcOffset": offset,
            "tokenConfigured": bool(config.JASANI_TOKENS.get(market)),
            "schedule": [{"hour": h, "what": w} for h, w in config.JASANI_SCHEDULE],
            "slotsDone": (budget.get("slots") or {}).get(day, []),
            "nextSlot": next_slot(market)}


def budget_status_all() -> dict:
    return {m: budget_status(m) for m in config.JASANI_HOSTS}


def cache_status(market: str) -> dict:
    cached = _read_cache(market)
    attempt = last_attempt(market)
    if not cached:
        return {"market": market, "cached": False, "products": 0, "inStock": 0,
                "fetchedAt": None, "stockAt": None, "productsFresh": False,
                "stockFresh": False, "lastAttempt": attempt}
    now = time.time()
    products = cached.get("products", [])
    fetched_at = cached.get("fetchedAt", 0)
    stock_at = cached.get("stockAt", fetched_at)
    return {
        "market": market, "cached": True, "products": len(products),
        "inStock": sum(1 for p in products if (p.get("stock") or {}).get("available", 0) > 0),
        "fetchedAt": fetched_at or None, "stockAt": stock_at or None,
        "productsFresh": now - fetched_at < config.PRODUCT_REFRESH_HOURS * 3600,
        "stockFresh": now - stock_at < config.STOCK_REFRESH_HOURS * 3600,
        "lastAttempt": attempt,
    }


def manuals_status() -> dict:
    d = _CACHE_DIR / "manuals"
    pdfs = valid = failed = 0
    size = 0
    if d.exists():
        for f in d.glob("*.pdf"):
            pdfs += 1
            try:
                size += f.stat().st_size
            except OSError:
                pass
        for f in d.glob("*.json"):
            try:
                verdict = json.loads(f.read_text(encoding="utf-8"))
                if verdict.get("valid"):
                    valid += 1
                else:
                    failed += 1
            except (OSError, ValueError):
                pass
    return {"cachedPdfs": pdfs, "validVerdicts": valid, "failedVerdicts": failed,
            "bytes": size}


_refresh_locks: dict[str, asyncio.Lock] = {}


def _refresh_lock(market: str) -> asyncio.Lock:
    """One in-flight sync per market. Two admins pressing refresh together, or
    a double-click, must not spend two calls on the same work."""
    lock = _refresh_locks.get(market)
    if lock is None:
        lock = _refresh_locks[market] = asyncio.Lock()
    return lock


async def force_refresh(market: str, what: str, manual: bool = True) -> dict:
    """Admin-triggered refresh. what='products' does a full products+stock
    refetch (2 primary calls); what='stock' refreshes stock onto the cached
    products (1 primary call). Raises SupplierUnavailable when the budget is
    exhausted or upstream fails — the cached snapshot is left untouched."""
    lock = _refresh_lock(market)
    if lock.locked():
        raise SupplierUnavailable("a sync for this market is already running")
    async with lock:
        now = time.time()
        if what == "products":
            try:
                products = await _fetch_products(market, manual=manual)
            except SupplierUnavailable as exc:
                record_attempt(market, "products", False, str(exc))
                raise
            stock_at = 0.0
            try:
                await _apply_stock(market, products, manual=manual)
                stock_at = now
            except SupplierUnavailable as exc:
                print(f"[jasani] {market}: stock feed unavailable ({exc})", flush=True)
                record_attempt(market, "stock", False, str(exc))
            _write_cache(market, products, fetched_at=now, stock_at=stock_at)
            if stock_at:
                record_attempt(market, "products", True,
                               f"{len(products)} products with stock")
            return {"refreshed": "products", "products": len(products),
                    "stockApplied": stock_at > 0}
        if what == "stock":
            cached = _read_cache(market)
            if not cached or not cached.get("products"):
                raise SupplierUnavailable("no cached products — run a full product refresh first")
            products = cached["products"]
            try:
                await _apply_stock(market, products, manual=manual)
            except SupplierUnavailable as exc:
                record_attempt(market, "stock", False, str(exc))
                raise
            _write_cache(market, products, fetched_at=cached.get("fetchedAt", now), stock_at=now)
            record_attempt(market, "stock", True, f"{len(products)} products")
            return {"refreshed": "stock", "products": len(products), "stockApplied": True}
        raise ValueError("unknown refresh target")


def search_cached(market: str, q: str, limit: int = 30) -> list[dict]:
    """Search the cached snapshot by name / SKU / id — internal admin view."""
    cached = _read_cache(market)
    if not cached:
        return []
    needle = (q or "").strip().lower()
    out = []
    for p in cached.get("products", []):
        hay = f"{p.get('name', '')} {p.get('code', '')} {p.get('id', '')}".lower()
        if needle and needle not in hay:
            continue
        out.append({"id": p.get("id"), "code": p.get("code"), "name": p.get("name"),
                    "brand": p.get("brand"), "color": p.get("color"),
                    "image": p.get("image"),
                    "available": (p.get("stock") or {}).get("available", 0),
                    "incoming": (p.get("stock") or {}).get("incoming", 0)})
        if len(out) >= max(1, min(100, limit)):
            break
    return out


# ---------------- printing manuals ----------------
# The supplier's /preview_product?product_id={template_id} endpoint returns a
# printing-manual PDF for many products. parent_id is only a CANDIDATE manual
# id — every candidate is validated server-side (signature, page count, size)
# before it is ever served, and the verdict is cached either way. Customers
# download from the Elite Marcom domain only; no token is involved.

MANUAL_MAX_BYTES = 10 * 1024 * 1024
MANUAL_CACHE_HOURS = 24


def _manual_paths(market: str, template_id: str):
    d = _CACHE_DIR / "manuals"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]", "", str(template_id))[:40]
    return d / f"{market}-{safe}.pdf", d / f"{market}-{safe}.json"


def _valid_manual_pdf(data: bytes) -> bool:
    if len(data) < 1024 or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        return False
    pages = data.count(b"/Type /Page") + data.count(b"/Type/Page")
    pages -= data.count(b"/Type /Pages") + data.count(b"/Type/Pages")
    if pages < 1:
        counts = re.findall(rb"/Count\s+(\d+)", data)
        pages = max((int(c) for c in counts), default=0)
    return 1 <= pages <= 200


async def _fetch_manual_bytes(market: str, template_id: str) -> bytes:
    """Download one candidate manual PDF (public supplier route, no token).
    Not documented as part of the primary daily limit; still cached 24h."""
    host = _host(market)
    url = f"https://{host}/preview_product?product_id={urllib.parse.quote(str(template_id), safe='')}"
    try:
        async with httpx.AsyncClient(timeout=config.SUPPLIER_TIMEOUT_S,
                                     follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", url) as res:
                if res.status_code != 200:
                    raise SupplierUnavailable(f"manual upstream {res.status_code}")
                chunks: list[bytes] = []
                total = 0
                async for chunk in res.aiter_bytes():
                    total += len(chunk)
                    if total > MANUAL_MAX_BYTES:
                        raise SupplierUnavailable("manual response too large")
                    chunks.append(chunk)
    except SupplierUnavailable:
        raise
    except Exception as exc:
        raise SupplierUnavailable(f"transport: {exc.__class__.__name__}") from exc
    return b"".join(chunks)


async def _fetch_image_bytes(url: str) -> bytes | None:
    """Best-effort product photo download from an approved supplier host."""
    if not url or not _safe_supplier_url(url):
        return None
    host = urllib.parse.urlsplit(url).hostname or ""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", url) as res:
                if res.status_code != 200:
                    return None
                chunks: list[bytes] = []
                total = 0
                async for chunk in res.aiter_bytes():
                    total += len(chunk)
                    if total > 4 * 1024 * 1024:
                        return None
                    chunks.append(chunk)
        return b"".join(chunks)
    except Exception:
        return None


# v2: manuals generated before the branding decoder fix have no area images in
# them, so they must not be served from cache — the filename carries this, which
# leaves other cached manuals and every unrelated runtime cache alone.
GEN_MANUAL_VERSION = 2


async def _generated_manual(market: str, product: dict) -> bytes | None:
    """Elite Marcom-branded manual (design M1) from Branding API data, cached
    24h. Returns None when branding data is unavailable — caller falls back."""
    from . import manuals

    pdf_path, meta_path = _manual_paths(market, f"gen{GEN_MANUAL_VERSION}-{product['id']}")
    now = time.time()
    meta = None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if meta and now - meta.get("checkedAt", 0) < MANUAL_CACHE_HOURS * 3600:
        if meta.get("valid") and pdf_path.exists():
            return pdf_path.read_bytes()
        if not meta.get("valid"):
            return None
    try:
        areas = await get_branding_areas(market, product["id"])
    except SupplierUnavailable:
        # supplier outage: last-known-good generated copy, else fall back
        if meta and meta.get("valid") and pdf_path.exists():
            return pdf_path.read_bytes()
        return None
    if not areas:
        try:
            meta_path.write_text(json.dumps({"checkedAt": int(now), "valid": False}), encoding="utf-8")
        except OSError:
            pass
        return None
    photo = await _fetch_image_bytes(product.get("image") or "")
    try:
        data = manuals.build_manual(product, areas, market, photo)
    except Exception as exc:
        print(f"[jasani] {market}: manual generation failed ({exc.__class__.__name__})", flush=True)
        return None
    try:
        pdf_path.write_bytes(data)
        meta_path.write_text(json.dumps({"checkedAt": int(now), "valid": True,
                                         "size": len(data)}), encoding="utf-8")
    except OSError:
        pass
    return data


async def _supplier_manual(market: str, product: dict) -> bytes:
    """Fallback: the supplier's own preview_product PDF via validated candidate."""
    template_id = str(product.get("parentId") or product.get("templateId") or "")
    if not template_id.isdigit() or not 0 < int(template_id) < 10**12:
        raise SupplierUnavailable("no manual candidate for this product")
    pdf_path, meta_path = _manual_paths(market, template_id)
    now = time.time()
    meta = None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if meta and now - meta.get("checkedAt", 0) < MANUAL_CACHE_HOURS * 3600:
        if meta.get("valid") and pdf_path.exists():
            return pdf_path.read_bytes()
        if not meta.get("valid"):
            raise SupplierUnavailable("manual candidate previously failed validation")
    try:
        data = await _fetch_manual_bytes(market, template_id)
    except SupplierUnavailable:
        # supplier outage: keep serving the last-known-good copy
        if meta and meta.get("valid") and pdf_path.exists():
            return pdf_path.read_bytes()
        raise
    valid = _valid_manual_pdf(data)
    try:
        if valid:
            pdf_path.write_bytes(data)
        meta_path.write_text(json.dumps({"checkedAt": int(now), "valid": valid,
                                         "size": len(data)}), encoding="utf-8")
    except OSError:
        pass  # cache failures never break the response
    if not valid:
        raise SupplierUnavailable("candidate did not return a valid PDF")
    return data


async def get_manual(market: str, product_id: str) -> tuple[bytes, str]:
    """Printing-manual PDF for a catalog product: the Elite Marcom-branded
    generated manual when Branding API data exists, else the validated
    supplier PDF. Returns (pdf_bytes, product_code)."""
    products, _state = await get_catalog(market)
    product = next((p for p in products if p["id"] == product_id), None)
    if product is None:
        raise SupplierUnavailable("unknown product")
    data = await _generated_manual(market, product)
    if data is not None:
        return data, product["code"]
    return await _supplier_manual(market, product), product["code"]


# ---------------- branding ----------------

# Bumped when the branding decoder changes in a way that makes previously
# stored entries wrong. v2: web_image arrives as a Python bytes repr — b'…' —
# and everything cached before this parsed to corrupt bytes and stored no image.
BRANDING_DECODER_VERSION = 2


def _branding_cache_path(market: str, product_id: str):
    d = _CACHE_DIR / "branding"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]", "", str(product_id))[:60]
    return d / f"{market}-{safe}.json"


def _fnum(rec: dict, *keys: str) -> float | None:
    raw = _s(rec, *keys)
    m = re.match(r"^-?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


# The branding record does not always call the artwork the same thing.
_B64ISH_RE = re.compile(r"^(?:data:image/[a-z.+-]+;base64,)?[A-Za-z0-9+/=\s]+$")
_AREA_IMAGE_KEYS = ("web_image", "webimage", "image", "image_1920", "image1920",
                    "area_image", "areaimage", "view_image", "viewimage",
                    "branding_image", "brandingimage", "picture", "photo")


def _area_image_raw(rec: dict) -> Any:
    """The base64 artwork on a branding record, whatever key it arrived under.

    A missed key is not a blank field — the area simply renders as
    'Area image unavailable' in the manual, which is what a missing branding
    image looks like to a customer."""
    for key in _AREA_IMAGE_KEYS:
        val = rec.get(key)
        if isinstance(val, str) and len(val.strip()) >= 64:
            marker = val.strip().lower()
            if marker not in _EMPTY_MARKERS:
                return val
    # Fall back to any long value that actually decodes as an image. This is
    # self-validating — a field only qualifies if PIL can open what it holds —
    # so an unfamiliar field name costs a customer their area view no longer.
    for val in rec.values():
        if isinstance(val, str) and len(val.strip()) >= 512 and _B64ISH_RE.match(val.strip()[:64]):
            if _decode_web_image(val)[0] is not None:
                return val
    return None


_B64_ALPHABET = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _unwrap_base64(raw: str) -> str:
    """Get to the actual Base64 inside whatever the field is wrapped in.

    Jasani's UAE Branding API returns web_image as a JSON *string* holding a
    Python bytes repr — literally b'/9j/4AAQ…' with the marker and quotes as
    characters. Feeding that to b64decode(validate=False) does not fail: the
    non-alphabet characters are skipped and what comes out is shifted, so the
    JPEG magic FF D8 FF arrives as 6F FF 63 FF and Pillow rejects an image
    that was perfectly good on the wire.

    The wrapper is removed only when it is genuinely one — a b prefix with
    matching quotes at both ends — never by stripping stray quotes, so a
    payload that legitimately ends in a quote character is untouched. Parsed
    by hand rather than with ast.literal_eval: this needs to recognise one
    fixed shape, and a general literal parser on unbounded upstream input is
    more machinery and more surface than the job needs."""
    text = raw.strip()
    if text.startswith("data:"):
        text = text.split(",", 1)[-1]
    for prefix, quote in (("b'", "'"), ('b"', '"')):
        if text.startswith(prefix) and text.endswith(quote) and len(text) > len(prefix) + 1:
            text = text[len(prefix):-1]
            break
    text = "".join(text.split())          # newlines and spaces are not payload
    if not text or not _B64_ALPHABET.match(text):
        return ""
    pad = len(text) % 4
    if pad == 1:
        return ""                         # cannot be valid Base64, do not guess
    if pad:
        text += "=" * (4 - pad)
    return text


def _decode_web_image(raw: Any) -> tuple[bytes | None, int, int]:
    """Base64 branding artwork → (bytes, width, height).

    The image is fully decoded here rather than header-checked: PIL's verify()
    passes on a truncated payload that then fails at draw time, and by then the
    manual has already been generated with a missing area view. Whatever comes
    back is normalised to PNG at its original pixel size, so the area rectangle
    — which is expressed in those pixels — still lines up, and reportlab is
    never handed a palette or CMYK image it will refuse."""
    if not isinstance(raw, str) or len(raw) < 64:
        return None, 0, 0
    b64 = _unwrap_base64(raw)
    if not b64 or len(b64) > 24 * 1024 * 1024:
        return None, 0, 0
    import base64
    import io as _io

    try:
        data = base64.b64decode(b64, validate=False)
    except Exception:
        return None, 0, 0
    # 32 bytes is below any real image header; anything above that is left for
    # PIL to accept or reject, rather than guessing from the byte count.
    if len(data) < 32 or len(data) > 16 * 1024 * 1024:
        return None, 0, 0
    try:
        from PIL import Image as _Image

        im = _Image.open(_io.BytesIO(data))
        w, h = im.size
        if not (8 <= w <= 6000 and 8 <= h <= 6000):
            return None, 0, 0
        im.load()                      # actually decode: catches truncation now
        # Branding artwork is nearly always a cut-out on a transparent
        # background. Alpha survives into the PDF as a soft mask, which several
        # viewers — including the one most customers open the manual in — draw
        # as nothing at all, so the area view comes out blank. The manual is a
        # white page, so flatten onto white here and ship plain RGB: what is
        # printed is identical and there is no mask left to mishandle.
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            flat = _Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        elif im.mode != "RGB":
            im = im.convert("RGB")
        out = _io.BytesIO()
        im.save(out, format="PNG", optimize=False)
        normalised = out.getvalue()
    except Exception:
        return None, 0, 0
    # no size floor on the re-encoded bytes: a flat or largely transparent area
    # view compresses to almost nothing and is still a perfectly good image.
    return normalised, w, h


async def get_branding_areas(market: str, product_id: str) -> list[dict]:
    """Full branding areas for a known catalog product, cached on disk 24h.

    Each entry: {name, methods, areaWidthMm, areaHeightMm,
                 image: {data: bytes|None, width, height} | None,
                 rect: {left, top, width, height} | None,
                 colorChoices, leadTime}."""
    products, _state = await get_catalog(market)
    if not any(p["id"] == product_id for p in products):
        raise SupplierUnavailable("unknown product")
    import base64

    cache = _branding_cache_path(market, product_id)
    now = time.time()
    try:
        stored = json.loads(cache.read_text(encoding="utf-8"))
        fresh = now - stored.get("fetchedAt", 0) < config.BRANDING_CACHE_HOURS * 3600
        # An entry from an older decoder is not reusable however fresh it is:
        # it holds what that decoder managed to make of the payload, which for
        # v1 was nothing at all. Refetching is free — the Branding API sits
        # outside the primary five-call allowance.
        if fresh and stored.get("decoder") == BRANDING_DECODER_VERSION:
            for a in stored["areas"]:
                if a.get("imageB64"):
                    a["image"] = {"data": base64.b64decode(a.pop("imageB64")),
                                  "width": a.pop("imageW", 0), "height": a.pop("imageH", 0)}
                else:
                    a["image"] = None
                    a.pop("imageB64", None), a.pop("imageW", None), a.pop("imageH", None)
            return stored["areas"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    host = _host(market)
    # the Branding API is documented outside the daily primary-call limit
    raw, ctype = await _fetch(
        f"https://{host}/branding/{_token(market)}/{urllib.parse.quote(str(product_id), safe='')}",
        host, market,
        primary=False,
    )
    records = _parse_records(raw, ctype)[:20]
    areas: list[dict] = []
    dropped_images = 0
    for rec in records:
        rec = _normalize_keys(rec)
        methods = _rel_names(rec.get("pricing_products") or rec.get("pricingproducts"))[:8]
        img_data, img_w, img_h = _decode_web_image(_area_image_raw(rec))
        if img_data is None and _area_image_raw(rec):
            dropped_images += 1
        rect = None
        left, top = _fnum(rec, "left"), _fnum(rec, "top")
        r_w, r_h = _fnum(rec, "width"), _fnum(rec, "height")
        if (img_data and None not in (left, top, r_w, r_h) and r_w > 0 and r_h > 0
                and left >= -2 and top >= -2
                and left + r_w <= img_w + 2 and top + r_h <= img_h + 2):
            rect = {"left": max(0.0, left), "top": max(0.0, top), "width": r_w, "height": r_h}
        entry = {
            "name": _s(rec, "name", "area", "branding_area", "position", "location")[:120],
            "methods": methods or [m for m in
                                   [_s(rec, "method", "branding_method", "technique", "branding_type")[:120]] if m],
            "areaWidthMm": _weight(rec, "area_width", ndigits=1) or None,
            "areaHeightMm": _weight(rec, "area_height", ndigits=1) or None,
            "image": {"data": img_data, "width": img_w, "height": img_h} if img_data else None,
            "rect": rect,
            "colorChoices": "",  # enriched later from the Branding Prices API
            "leadTime": "",
        }
        if entry["name"] or entry["methods"] or entry["image"]:
            areas.append(entry)
    with_images = sum(1 for a in areas if a["image"])
    print(f"[jasani] {market} branding {product_id}: {len(areas)} areas, "
          f"{with_images} with artwork, {dropped_images} unreadable", flush=True)
    try:
        serializable = []
        for a in areas:
            s = {k: v for k, v in a.items() if k != "image"}
            if a["image"]:
                s["imageB64"] = base64.b64encode(a["image"]["data"]).decode()
                s["imageW"], s["imageH"] = a["image"]["width"], a["image"]["height"]
            serializable.append(s)
        cache.write_text(json.dumps({"fetchedAt": int(now), "areas": serializable,
                                     "decoder": BRANDING_DECODER_VERSION}),
                         encoding="utf-8")
    except OSError:
        pass
    return areas


async def get_branding(market: str, product_id: str) -> list[dict]:
    """Public text summary of the branding areas (no images or coordinates)."""
    areas = await get_branding_areas(market, product_id)
    branding = []
    for a in areas:
        dims = ""
        if a.get("areaWidthMm") and a.get("areaHeightMm"):
            dims = f"{a['areaWidthMm']} × {a['areaHeightMm']} mm"
        entry = {
            "area": (a.get("name") or "")[:120],
            "method": ", ".join(a.get("methods") or [])[:200],
            "dimensions": dims[:120],
        }
        if any(entry.values()):
            branding.append(entry)
    return branding
