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

ALLOWED_CONTENT_TYPES = ("application/json", "text/json", "application/xml", "text/xml")


class SupplierUnavailable(Exception):
    pass


# ---------------- primary-call budget ----------------
# Jasani allows at most SUPPLIER_DAILY_BUDGET primary GET calls (products,
# price, stock) per day, measured in UAE time (UTC+4). Branding endpoints are
# documented outside the limit. The counter persists across restarts.

def _uae_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 4 * 3600))


def _budget_file():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "supplier-budget.json"


def _read_budget() -> dict:
    try:
        data = json.loads(_budget_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"day": str(data.get("day", "")), "count": int(data.get("count", 0))}
    except (OSError, ValueError):
        pass
    return {"day": "", "count": 0}


def _write_budget(budget: dict) -> None:
    try:
        _budget_file().write_text(json.dumps(budget), encoding="utf-8")
    except OSError:
        pass


def _budget_ok() -> bool:
    day = _uae_day()
    with _lock:
        budget = _read_budget()
        if budget["day"] != day:
            budget = {"day": day, "count": 0}
        if budget["count"] >= config.SUPPLIER_DAILY_BUDGET:
            return False
        budget["count"] += 1
        _write_budget(budget)
        return True


def _budget_exhaust() -> None:
    """After a 403 (documented for over-limit, bad token or bad URL) stop
    calling the primary APIs until the UAE day resets — never retry a 403."""
    with _lock:
        _write_budget({"day": _uae_day(), "count": config.SUPPLIER_DAILY_BUDGET})


def _host(market: str) -> str:
    host = config.JASANI_HOSTS.get(market)
    if not host:
        raise SupplierUnavailable("unknown market")
    return host


async def _fetch(url: str, expected_host: str, primary: bool = True) -> tuple[bytes, str]:
    """primary=True marks the rate-limited product/price/stock endpoints;
    branding endpoints are documented outside the daily limit."""
    if not config.JASANI_API_TOKEN:
        raise SupplierUnavailable("no supplier token configured")
    if primary and not _budget_ok():
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
                if res.status_code == 403 and primary:
                    # documented for over-limit / bad token / bad URL — do not retry today
                    _budget_exhaust()
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


def _image_urls(v: Any, depth: int = 0) -> list[str]:
    """URLs from the supplier's images field, which nests arbitrarily:
    images: [[{"id": 1954, "image_url": "..."}, ...]] — flatten everything."""
    if depth > 4 or v is None or isinstance(v, bool):
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s and s.lower() not in _EMPTY_MARKERS else []
    if isinstance(v, dict):
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
        for key in ("images", "image_urls", "gallery", "additional_images", "extra_images"):
            images.extend(_image_urls(rec.get(key) or rec.get(key.replace("_", ""))))
        images = [u for u in (_safe_image(u, host) for u in images) if u][:36]
        # de-duplicate while preserving order
        seen_imgs: set[str] = set()
        images = [u for u in images if not (u in seen_imgs or seen_imgs.add(u))]
        manual = _safe_supplier_url(_s(rec, "printing_manual", "printingManual", "manual",
                                       "manual_url", "branding_manual", "pdf", "pdf_url"))
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
            # only meaningful for grouping when configurable is true
            "configurable": configurable,
            "templateId": parent_id if configurable else None,
            "_parentId": parent_id,  # internal: template-id resolution (popped later)
            "color": _s(rec, "color", "colour")[:60],
            "options": options,
            "image": images[0] if images else "",
            "images": images,
            "printingManual": manual or None,
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
        tid = p.get("_parentId")
        if tid:
            by_template.setdefault(tid, p)
    for p in products:
        ids = p.pop("_colorOptionIds", []) or []
        own_template = p.get("_parentId")
        opts = []
        for cid in ids:
            if own_template and cid == own_template:
                continue
            alt = by_template.get(cid) or by_id.get(cid)
            if alt and alt["id"] != p["id"]:
                opts.append({"id": alt["id"], "name": alt["name"],
                             "color": alt["color"], "image": alt["image"]})
        p["colorOptions"] = opts[:12]
    for p in products:
        p.pop("_parentId", None)


async def _fetch_products(market: str) -> list[dict]:
    """One primary Product API call, normalized. Raises SupplierUnavailable."""
    host = _host(market)
    raw, ctype = await _fetch(f"https://{host}/products/all/{_token()}", host)
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


async def _apply_stock(market: str, products: list[dict]) -> None:
    """One primary Stock API call merged onto products. Raises SupplierUnavailable."""
    host = _host(market)
    raw_s, ctype_s = await _fetch(f"https://{host}/products/stock/{_token()}", host)
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


async def get_catalog(market: str) -> tuple[list[dict], str]:
    """Return (products, state) — state in {'live','cache','stale'}.

    The supplier's daily primary-call limit rules out frequent upstream
    refreshes: the product feed refreshes about once per day and the stock
    feed about twice per day; everything else is served from the last-known-
    good snapshot. Raises SupplierUnavailable only when nothing is cached."""
    cached = _read_cache(market)
    now = time.time()
    products_fresh = bool(cached) and now - cached.get("fetchedAt", 0) < config.PRODUCT_REFRESH_HOURS * 3600
    stock_fresh = bool(cached) and now - cached.get("stockAt", cached.get("fetchedAt", 0)) < config.STOCK_REFRESH_HOURS * 3600
    if products_fresh and stock_fresh:
        return cached["products"], "cache"
    if not products_fresh:
        try:
            products = await _fetch_products(market)
            stock_at = 0.0
            try:
                await _apply_stock(market, products)
                stock_at = now
            except SupplierUnavailable as exc:
                # best-effort: the product payload may carry stock already
                print(f"[jasani] {market}: stock feed unavailable ({exc})", flush=True)
            _write_cache(market, products, fetched_at=now, stock_at=stock_at)
            return products, "live"
        except SupplierUnavailable:
            if cached:
                return cached["products"], "stale"
            raise
    # products are fresh; only the stock snapshot is due — refresh it in place
    products = cached["products"]
    try:
        await _apply_stock(market, products)
        _write_cache(market, products, fetched_at=cached.get("fetchedAt", now), stock_at=now)
        return products, "live"
    except SupplierUnavailable:
        # keep serving the products snapshot with the previous stock values
        return products, "cache"


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
    # the Branding API is documented outside the daily primary-call limit
    raw, ctype = await _fetch(
        f"https://{host}/branding/{_token()}/{urllib.parse.quote(str(product_id), safe='')}", host,
        primary=False,
    )
    records = _parse_records(raw, ctype)[:50]
    branding = []
    for rec in records:
        rec = _normalize_keys(rec)
        # documented shape: name, area_width/area_height (mm), pricing_products
        # (supported methods); web_image/coordinates stay server-side for now
        methods = _rel_names(rec.get("pricing_products") or rec.get("pricingproducts"))
        w = _weight(rec, "area_width", ndigits=1)
        h = _weight(rec, "area_height", ndigits=1)
        dims = f"{w} × {h} mm" if w and h else _s(rec, "dimensions", "size", "max_size", "area_size")[:120]
        entry = {
            "area": _s(rec, "name", "area", "branding_area", "position", "location")[:120],
            "method": (", ".join(methods) or _s(rec, "method", "branding_method", "technique", "branding_type"))[:200],
            "dimensions": dims[:120],
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
