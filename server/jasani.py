"""Elite Marcom website backend — giveaways supplier integration.

Backend-only Jasani client: exact host allowlist, no redirects, response
caps, hardened XML parsing, normalized private cache, daily budget.
The supplier token never reaches the browser.
"""
from __future__ import annotations

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

_budget = {"day": "", "count": 0}

ALLOWED_CONTENT_TYPES = ("application/json", "text/json", "application/xml", "text/xml")


class SupplierUnavailable(Exception):
    pass


def _budget_ok() -> bool:
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _budget["day"] != day:
            _budget["day"] = day
            _budget["count"] = 0
        if _budget["count"] >= config.SUPPLIER_DAILY_BUDGET:
            return False
        _budget["count"] += 1
        return True


def _host(market: str) -> str:
    host = config.JASANI_HOSTS.get(market)
    if not host:
        raise SupplierUnavailable("unknown market")
    return host


async def _fetch(url: str, expected_host: str) -> tuple[bytes, str]:
    if not config.JASANI_API_TOKEN:
        raise SupplierUnavailable("no supplier token configured")
    if not _budget_ok():
        raise SupplierUnavailable("daily supplier budget exhausted")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.port not in (None, 443):
        raise SupplierUnavailable("blocked upstream url")
    try:
        async with httpx.AsyncClient(
            timeout=config.SUPPLIER_TIMEOUT_S,
            follow_redirects=False,   # no redirects
            trust_env=False,          # no environment proxy inheritance
        ) as client:
            async with client.stream("GET", url) as res:
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
        raise SupplierUnavailable(f"transport: {exc.__class__.__name__}") from exc
    return b"".join(chunks), ctype


def _token() -> str:
    return urllib.parse.quote(config.JASANI_API_TOKEN, safe="")


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


def _weight(rec: dict, *keys: str) -> str:
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
    trimmed = f"{num:.2f}".rstrip("0").rstrip(".")
    return (trimmed + m.group(2))[:40]


def _list(rec: dict, *keys: str) -> list[str]:
    for k in keys:
        v = rec.get(k)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:20]
        if isinstance(v, str) and v.strip():
            return [p.strip() for p in re.split(r"[|;,]", v) if p.strip()][:20]
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
        images = []
        for key in ("images", "image_urls", "gallery"):
            images.extend(_list(rec, key))
        for key in ("image", "image_url", "main_image", "thumbnail"):
            v = _s(rec, key)
            if v:
                images.append(v)
        images = [u for u in (_safe_image(u, host) for u in images) if u][:12]
        # de-duplicate while preserving order
        seen_imgs: set[str] = set()
        images = [u for u in images if not (u in seen_imgs or seen_imgs.add(u))]
        manual = _safe_supplier_url(_s(rec, "printing_manual", "printingManual", "manual",
                                       "manual_url", "branding_manual", "pdf", "pdf_url"))
        tags = _list(rec, "tags", "collections", "labels")
        cats = _list(rec, "categories", "category", "product_category")
        lower = " ".join(tags + cats).lower()
        available = max(0, _i(rec, "net_stock", "available_stock", "stock", "net_available",
                              "qty_available", "free_qty", "available_qty", "quantity_available"))
        blocked = max(0, _i(rec, "blocked_stock", "blocked", "reserved"))
        incoming = max(0, _i(rec, "incoming_stock", "incoming", "expected_stock"))
        return {
            "id": pid or code,
            "code": code or pid,
            "barcode": _s(rec, "barcode", "ean")[:40],
            "name": name[:200],
            "brand": _s(rec, "brand", "brand_name")[:100],
            "description": _clean_description(_s(
                rec, "description", "product_description", "description_sale",
                "website_description", "long_description", "web_description",
                "item_description", "short_description", "details",
                "specification", "specifications", "desc")),
            "categories": cats,
            "tags": tags,
            "market": market,
            "color": _s(rec, "color", "colour")[:60],
            "options": _list(rec, "options", "variants", "attributes"),
            "image": images[0] if images else "",
            "images": images,
            "printingManual": manual or None,
            "sequence": _i(rec, "sequence", "sort_order", "newness"),
            "isNew": bool(re.search(r"\bnew\b", lower)) or _i(rec, "is_new") == 1,
            "sustainable": "sustain" in lower or "eco" in lower or "recycl" in lower,
            "luxury": "lux" in lower or "premium" in lower,
            "ramadan": "ramadan" in lower or "tradition" in lower,
            "hsCode": _s(rec, "hs_code", "hscode")[:30],
            "unitsPerCarton": _i(rec, "units_per_carton", "carton_qty") or None,
            "cartonDimensions": _s(rec, "carton_dimensions", "carton_size")[:80] or None,
            "cartonWeight": _weight(rec, "carton_weight", "carton_weight_kg") or None,
            "stock": {
                "available": available,
                "blocked": blocked,
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
            p["stock"]["available"] = max(0, _i(rec, "net_stock", "available_stock", "stock", "net_available",
                                                "qty_available", "free_qty", "available_qty", "quantity_available"))
            p["stock"]["blocked"] = max(0, _i(rec, "blocked_stock", "blocked", "reserved"))
            p["stock"]["incoming"] = max(0, _i(rec, "incoming_stock", "incoming", "expected_stock"))
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


def _write_cache(market: str, products: list[dict]) -> None:
    # explicit UTF-8: Windows' locale default (cp1252) cannot encode many
    # supplier product names, and a failed cache write must not fail the request
    try:
        f = _cache_file(market)
        f.write_text(json.dumps({"fetchedAt": int(time.time()), "products": products},
                                ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError):
        pass


async def _fetch_catalog(market: str) -> list[dict]:
    host = _host(market)
    token = _token()
    raw, ctype = await _fetch(f"https://{host}/products/all/{token}", host)
    records = _parse_records(raw, ctype)[: config.SUPPLIER_MAX_RECORDS]
    products = [p for p in (normalize_product(r, market) for r in records) if p]
    try:
        raw_s, ctype_s = await _fetch(f"https://{host}/products/stock/{token}", host)
        stock_records = _parse_records(raw_s, ctype_s)[: config.SUPPLIER_MAX_RECORDS]
        matched = _merge_stock(products, stock_records)
        print(f"[jasani] {market}: {len(products)} products, {len(stock_records)} stock rows, "
              f"{matched} matched, {sum(1 for p in products if p['stock']['available'] > 0)} with stock > 0",
              flush=True)
    except SupplierUnavailable as exc:
        # stock merge is best-effort; product payload often carries stock already
        print(f"[jasani] {market}: stock feed unavailable ({exc})", flush=True)
    if not products:
        raise SupplierUnavailable("no usable records")
    return products


async def get_catalog(market: str) -> tuple[list[dict], str]:
    """Return (products, state) — state in {'live','cache','stale'}. Raises SupplierUnavailable."""
    cached = _read_cache(market)
    now = time.time()
    if cached and now - cached.get("fetchedAt", 0) < config.CATALOG_REFRESH_MINUTES * 60:
        return cached["products"], "cache"
    try:
        products = await _fetch_catalog(market)
        _write_cache(market, products)
        return products, "live"
    except SupplierUnavailable:
        if cached:
            return cached["products"], "stale"
        raise


# ---------------- branding ----------------

_branding_cache: dict[str, tuple[float, list[dict]]] = {}


async def get_branding(market: str, product_id: str) -> list[dict]:
    """Branding only for a product already known in the market's normalized catalog."""
    products, _state = await get_catalog(market)
    known = None
    for p in products:
        if p["id"] == product_id:
            known = p
            break
    if known is None:
        raise SupplierUnavailable("unknown product")
    key = f"{market}:{product_id}"
    now = time.time()
    hit = _branding_cache.get(key)
    if hit and now - hit[0] < config.BRANDING_CACHE_HOURS * 3600:
        return hit[1]
    host = _host(market)
    raw, ctype = await _fetch(
        f"https://{host}/branding/{_token()}/{urllib.parse.quote(str(product_id), safe='')}", host
    )
    records = _parse_records(raw, ctype)[:50]
    branding = []
    for rec in records:
        rec = _normalize_keys(rec)
        entry = {
            "area": _s(rec, "area", "branding_area", "position", "location")[:120],
            "method": _s(rec, "method", "branding_method", "technique", "branding_type")[:120],
            "dimensions": _s(rec, "dimensions", "size", "max_size", "area_size")[:120],
        }
        if any(entry.values()):
            branding.append(entry)
    with _lock:
        if len(_branding_cache) >= config.BRANDING_CACHE_MAX_ENTRIES:
            oldest = sorted(_branding_cache.items(), key=lambda kv: kv[1][0])[:50]
            for k, _v in oldest:
                _branding_cache.pop(k, None)
        _branding_cache[key] = (now, branding)
    return branding
