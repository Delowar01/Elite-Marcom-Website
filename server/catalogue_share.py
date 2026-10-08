"""Shareable web catalogues — a link a client opens in a browser.

A share is a **frozen copy** of a catalogue, not a live view of one. The
products, their quantities, the stock timestamp and the photographs are all
written once, when the link is made, and never rebuilt: a client opening a
month-old link sees the catalogue that was shared rather than whatever the
supplier sells today, and opening it reaches the supplier for nothing at all.
That is the whole design, and three properties fall out of it.

**No supplier call can happen on a page view.** The snapshot is built from the
same cached products the PDF is built from (`jasani.item_list` /
`item_detail`), and the photographs are copied into
``runtime/catalogue-assets`` while the share is being made. A visitor's
browser only ever reads our own database and our own files.

**The price boundary is the same boundary.** Every customer-facing string in a
snapshot comes out of `catalogue.to_dto` — the allowlist that cannot carry a
price field and the sanitizer that cannot carry a price sentence — and
`assert_snapshot_price_free` is the second line, exactly as
`catalogue.assert_price_free` is for the PDF. A snapshot that fails it is
refused; nothing is published half-checked.

**The link is the credential, so the database cannot hand one out.** Only
``sha256(token)`` is stored. A token is 128 bits from `secrets`, it is shown
to the admin who made it once, and it is never written to a log, an audit
entry or an error message — the audit records the share's id, which is what
somebody revoking it needs.

Pictures are addressed by the hash of their own bytes, so two products
carrying one photograph are one file and re-sharing the same products copies
nothing. `catalogue_assets` remembers which supplier URL produced which hash
so that re-share does not re-read the image host either. Cleanup is
mark-and-sweep over the live snapshots — a file no share references is a file
nothing can reach — with a grace period, because a build writes its pictures
before it has a snapshot to name them in.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import time

from . import catalogue as cat
from . import config

#: 16 bytes of `secrets` — 128 bits, URL-safe, 22 characters.
TOKEN_BYTES = 16
#: What the share dialog offers. 0 means no expiry; 30 days is the default,
#: because a link that outlives the stock figures printed on it is a link
#: that quietly becomes wrong.
EXPIRY_CHOICES = (7, 30, 90, 0)
DEFAULT_EXPIRY_DAYS = 30
SHARES_LISTED = 100

#: A browser is not a printing press. 900px is twice the width a card or a
#: detail pane draws a photograph at on a large screen, and WebP at 74 is
#: between a third and a half of the JPEG the PDF carries.
WEB_IMAGE_DIM = 900
WEB_QUALITY = 74
#: The same three the PDF carries: the grid shows the first, the detail pane
#: shows the set. More than that is a gallery nobody scrolls.
IMAGES_PER_PRODUCT = cat.IMAGES_PER_ITEM
#: Bounded exactly as the PDF's photo cache is: a share is built one product
#: at a time and must not grow a working set with the catalogue.
URL_CACHE_MAX = 200
#: How long a newly written picture is safe from the sweep. A build writes
#: its photographs before it has a snapshot to name them in, so a sweep
#: running at that moment would delete a share's imagery out from under it.
#: The index row is touched both when a picture is written and when one is
#: reused, so "recently touched" is the whole of that protection.
ASSET_GRACE_S = 3600.0
#: The sweep is cheap but not free, so an ordinary page of the panel runs it
#: at most this often.
CLEANUP_EVERY_S = 3600.0
_last_cleanup = 0.0

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class ShareError(Exception):
    """Something about this share cannot be published. The message is shown
    to an admin, so it says what to do about it."""


# ---------------- where the files live ----------------

def assets_dir():
    path = config.RUNTIME_DIR / "catalogue-assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pdf_dir():
    path = config.RUNTIME_DIR / "catalogue-shares"
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset_path(name: str):
    """The file for a picture, or None if that is not a picture's name.

    The name is a SHA-256 in lower-case hex and nothing else, so there is no
    separator a traversal could use — this is a shape check, not an escaping
    one.
    """
    stem = name[:-5] if name.endswith(".webp") else name
    if not _HASH_RE.match(stem):
        return None
    path = assets_dir() / f"{stem}.webp"
    return path if path.exists() else None


# ---------------- tokens ----------------

def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


# ---------------- pictures ----------------

def web_image(raw: bytes) -> bytes | None:
    """One photograph, re-encoded for a browser.

    The same ceilings as `catalogue.prepare_image`: the header is read and an
    enormous picture refused before a pixel is decoded, and transparency is
    flattened onto white rather than left to whatever the page background
    happens to be. Nothing of the original is carried over — no EXIF, no
    colour profile, no embedded thumbnail.
    """
    if not raw or len(raw) > cat.MAX_IMAGE_BYTES:
        return None
    try:
        from PIL import Image

        probe = Image.open(io.BytesIO(raw))
        if probe.width * probe.height > cat.MAX_IMAGE_PIXELS:
            return None
        im = probe
        im.load()
        if max(im.width, im.height) > WEB_IMAGE_DIM:
            im.thumbnail((WEB_IMAGE_DIM, WEB_IMAGE_DIM))
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "WEBP", quality=WEB_QUALITY, method=4)
        im.close()
        return out.getvalue()
    except Exception:
        return None                      # one bad photo, not a failed share


def store_asset(encoded: bytes) -> str:
    """Write a picture under the hash of its own bytes and return that hash.

    Content addressing is what makes a second share of the same products
    free: the file is already there, byte for byte, so it is not written
    again.
    """
    digest = hashlib.sha256(encoded).hexdigest()
    path = assets_dir() / f"{digest}.webp"
    if not path.exists():
        tmp = path.with_suffix(".webp.part")
        tmp.write_bytes(encoded)
        tmp.replace(path)                # a reader never sees a half file
    return digest


def _asset_for_url(url: str) -> str | None:
    """The hash this supplier URL was turned into last time, if the file is
    still on disk. A remembered hash whose file has gone is not a hit.

    A hit is **touched**: the picture is about to be named by a share that
    does not exist yet, and a touched row is what keeps the sweep off it in
    the meantime.
    """
    from . import adminauth as aa

    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    row = aa._connect().execute(
        "SELECT hash FROM catalogue_assets WHERE url_key=?", (key,)).fetchone()
    if row and (assets_dir() / f"{row['hash']}.webp").exists():
        with aa._lock:
            conn = aa._connect()
            conn.execute("UPDATE catalogue_assets SET created_at=? WHERE url_key=?",
                         (int(time.time()), key))
            conn.commit()
        return row["hash"]
    return None


def _remember_url(url: str, digest: str, size: int) -> None:
    from . import adminauth as aa

    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    with aa._lock:
        conn = aa._connect()
        conn.execute(
            "INSERT INTO catalogue_assets (url_key, hash, bytes, created_at) "
            "VALUES (?,?,?,?) ON CONFLICT(url_key) DO UPDATE SET "
            "hash=excluded.hash, bytes=excluded.bytes, created_at=excluded.created_at",
            (key, digest, size, int(time.time())))
        conn.commit()


# ---------------- the snapshot ----------------

#: What a share carries about one product. Every one of these comes out of
#: `catalogue.to_dto`, so the share and the PDF are the same record read
#: twice, and a field the panel's toggles switched off is left out of the
#: snapshot entirely rather than hidden by the viewer: a viewer cannot show
#: what it was never given.
def snapshot_product(dto: dict, images: list[str], options: dict) -> dict:
    out: dict = {"name": dto.get("name") or "Product"}
    if options.get("code", True):
        out["code"] = dto.get("code") or ""
    if options.get("description", True) and dto.get("description"):
        out["desc"] = dto["description"]
    if options.get("specs", True):
        rows = cat.spec_rows(dto)
        if rows:
            out["specs"] = [[k, v] for k, v in rows]
    if options.get("stock", True):
        out["qty"] = dto.get("available")
        out["known"] = cat._item_known(dto)
        #: the sentence itself, written by the same function the PDF page
        #: uses — "Availability unavailable" rather than a confident nought
        #: has to read identically in both, and two implementations of that
        #: are one that can drift
        out["stockText"] = cat.stock_sentence(dto.get("available"),
                                              cat._item_known(dto))[0]
    cats = [c for c in (dto.get("categories") or []) if c][:4]
    if cats:
        out["cats"] = cats
    if images:
        out["img"] = images
    return out


_PRICE_SCAN_KEYS = ("name", "code", "desc")


def assert_snapshot_price_free(products: list[dict], title: str = "") -> None:
    """Second line of defence for the web catalogue, and the same test the
    finished PDF gets.

    `to_dto` is what makes a snapshot price-free; this refuses to publish one
    where it did not. It reads the strings a client would see — the title, the
    names, the codes, the descriptions, the specification rows and the
    category labels — and nothing else, and it reports the indicator rather
    than the figure, because a number that is not ours to show is not ours to
    log either.
    """
    def check(value: str, where: str) -> None:
        if cat.has_price_text(value):
            raise ShareError(
                f"A price indicator reached the catalogue ({where}). "
                "The products need checking before this can be shared.")

    check(title, "the title")
    for n, item in enumerate(products, 1):
        for key in _PRICE_SCAN_KEYS:
            check(str(item.get(key) or ""), f"product {n}")
        for row in item.get("specs") or []:
            for cell in row:
                check(str(cell), f"product {n}")
        for label in item.get("cats") or []:
            check(str(label), f"product {n}")


# ---------------- making one ----------------

def _expiry(days) -> int | None:
    try:
        n = int(days)
    except (TypeError, ValueError):
        n = DEFAULT_EXPIRY_DAYS
    if n not in EXPIRY_CHOICES:
        n = DEFAULT_EXPIRY_DAYS
    return None if n == 0 else int(time.time()) + n * 86400


async def _build(job: dict, rows: list[dict], *, market: str, title: str,
                 options: dict, stock_at, stock_is_known: bool,
                 expiry_days, allow_pdf: bool, by: str) -> dict:
    """Freeze one catalogue: the records, the pictures, and optionally the PDF.

    One product at a time, exactly as the PDF is drawn — a picture is fetched,
    re-encoded, written and dropped before the next product is looked at — so
    a five-hundred product share costs the same working set as a five-product
    one. The PDF, when the share allows one, is drawn in the **same pass**:
    the photographs are already in hand, so the document a client downloads is
    built from the same pictures the page shows rather than from a second
    reading of the catalogue.
    """
    from . import jasani

    clean_title = cat.sanitize_catalogue_text(
        cat.clean_text(title, 120), "name") or cat.DEFAULT_TITLE
    doc = None
    if allow_pdf:
        doc = cat.Document(market=market, title=clean_title, count=len(rows),
                           stock_at=stock_at, stock_is_known=stock_is_known,
                           options=options)
    url_cache: dict[str, str | None] = {}
    prepared_cache: dict[tuple, bytes | None] = {}
    stats: dict[str, int] = {}
    products: list[dict] = []
    job["state"] = "images"

    async def pictures(dto: dict) -> tuple[list[str], list[bytes]]:
        """(asset hashes for the page, prepared JPEGs for the PDF)."""
        hashes: list[str] = []
        blobs: list[bytes] = []
        for n, url in enumerate((dto.get("images") or [])[:IMAGES_PER_PRODUCT]):
            slot = "main" if n == 0 else "side"
            known = url_cache.get(url, "?")
            raw = None
            if known == "?":
                digest = _asset_for_url(url)
                if digest is None:
                    try:
                        raw = await jasani._fetch_image_bytes(url)
                    except Exception:
                        raw = None
                    encoded = web_image(raw) if raw else None
                    if encoded is not None:
                        digest = store_asset(encoded)
                        _remember_url(url, digest, len(encoded))
                if len(url_cache) < URL_CACHE_MAX:
                    url_cache[url] = digest
                known = digest
            if known:
                hashes.append(known)
            if doc is not None:
                #: keyed on the slot as well, exactly as the PDF's own cache
                #: is: one URL used as a leading shot and as a side view is
                #: two different pictures
                blob = prepared_cache.get((url, slot), "?")
                if blob == "?":
                    if raw is None:
                        try:
                            raw = await jasani._fetch_image_bytes(url)
                        except Exception:
                            raw = None
                    blob = cat.prepare_image(raw, slot=slot,
                                             quality=options.get("quality")) if raw else None
                    if len(prepared_cache) < cat.PHOTO_CACHE_MAX:
                        prepared_cache[(url, slot)] = blob
                if blob:
                    blobs.append(blob)
            del raw
        return hashes, blobs

    # the cover's hero, and the first few products' pictures, come out of the
    # same pass: `_cover_photos` would be a second reading of the image host
    hero: list[bytes] = []
    first: list[tuple[dict, list[str], list[bytes]]] = []
    for row in rows[:cat.COVER_IMAGES]:
        detail = jasani.item_detail(market, row["id"]) or dict(row)
        detail["available"] = row.get("available")
        detail["availableKnown"] = row.get("availableKnown")
        dto = cat.to_dto(detail, stats)
        hashes, blobs = await pictures(dto)
        first.append((dto, hashes, blobs))
        if blobs:
            hero.append(blobs[0])
    if doc is not None:
        doc.cover(hero)
        if options.get("contents"):
            heads = []
            for row in rows:
                head = cat.to_dto(jasani.item_detail(market, row["id"]) or dict(row))
                heads.append((head["code"] or "—", head["name"] or "Product"))
            doc.contents(heads)
    del hero

    job["state"] = "drawing"
    job["done"] = 0
    for n, row in enumerate(rows):
        if n < len(first):
            dto, hashes, blobs = first[n]
            first[n] = (None, None, None)     # released as it is used
        else:
            detail = jasani.item_detail(market, row["id"]) or dict(row)
            detail["available"] = row.get("available")
            detail["availableKnown"] = row.get("availableKnown")
            dto = cat.to_dto(detail, stats)
            del detail
            hashes, blobs = await pictures(dto)
        products.append(snapshot_product(dto, hashes, options))
        if doc is not None:
            doc.page(dto, blobs)
        del dto, hashes, blobs
        job["done"] = n + 1
        job["sanitizedProducts"] = stats.get("products", 0)
        job["sanitizedFields"] = stats.get("fields", 0)

    assert_snapshot_price_free(products, clean_title)
    pdf = doc.finish() if doc is not None else None

    token = new_token()
    record = _insert(token, title=clean_title, market=market, products=products,
                     options=options, stock_at=stock_at,
                     stock_is_known=stock_is_known,
                     expires_at=_expiry(expiry_days), allow_pdf=bool(allow_pdf),
                     pdf=pdf, by=by)
    #: handed back once and never stored: only the hash is in the database,
    #: so neither the panel nor anybody else can read this link again
    record["url"] = f"/catalogue/{token}"
    return record


def _insert(token: str, *, title: str, market: str, products: list[dict],
            options: dict, stock_at, stock_is_known: bool, expires_at,
            allow_pdf: bool, pdf: bytes | None, by: str) -> dict:
    from . import adminauth as aa

    #: what the page shows, not how a picture was encoded — the quality mode
    #: is a property of the optional PDF and means nothing to the viewer
    shown = {k: bool(v) for k, v in options.items() if k != "quality"}
    snapshot = json.dumps({
        "title": title, "market": market, "stockAt": stock_at,
        "stockKnown": bool(stock_is_known),
        "lowStock": config.LOW_STOCK_THRESHOLD,
        "options": shown,
        "products": products,
    }, ensure_ascii=False, separators=(",", ":"))
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        cur = conn.execute(
            "INSERT INTO catalogue_shares (token_hash, title, market, products, "
            "options, snapshot, stock_at, allow_pdf, created_at, created_by, "
            "expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (hash_token(token), title, market, len(products),
             json.dumps(shown, sort_keys=True),
             snapshot, int(stock_at) if stock_at else None, 1 if allow_pdf else 0,
             now, by[:200], expires_at))
        share_id = int(cur.lastrowid)
        if pdf is not None:
            name = f"share-{share_id}.pdf"
            (pdf_dir() / name).write_bytes(pdf)
            conn.execute("UPDATE catalogue_shares SET pdf_file=?, pdf_bytes=? WHERE id=?",
                         (name, len(pdf), share_id))
        conn.commit()
    return {"id": share_id, "title": title, "market": market,
            "products": len(products), "allowPdf": bool(allow_pdf),
            "expiresAt": expires_at, "createdAt": now,
            "pdfBytes": len(pdf) if pdf else 0}


def spawn(job_token: str, rows: list[dict], **kw) -> None:
    """Run a share build on a worker thread, through the catalogue's own job
    registry — one progress mechanism, so the panel polls shares and PDFs the
    same way."""
    import threading

    def work() -> None:
        import asyncio

        job = cat._jobs.get(job_token)
        if job is None:
            return
        record, error = None, ""
        try:
            record = asyncio.run(_build(job, rows, **kw))
        except (ShareError, cat.CatalogueError) as exc:
            error = str(exc)[:200]
        except Exception as exc:              # pragma: no cover - defensive
            error = f"The catalogue could not be shared ({exc.__class__.__name__})."
        # the outcome is recorded before the terminal state is published, for
        # the same reason the PDF worker does it in that order: the panel
        # polls this job from another thread
        if record is None:
            job["error"] = error
        else:
            job["share"] = record
            job["done"] = len(rows)
        if job.get("on_finish"):
            try:
                job["on_finish"](record is not None, job)
            except Exception:
                pass
        job["state"] = "failed" if record is None else "done"
        job["finished"] = record is not None

    threading.Thread(target=work, daemon=True).start()


# ---------------- reading one ----------------

def resolve(token: str) -> tuple[dict | None, str]:
    """(record, reason) for a link.

    The reason is what the viewer shows, and the three answers are deliberately
    different: a link that never existed and a link that was taken down read
    the same to a visitor ("not available"), while one that simply ran out of
    time says so, because that is a thing the client can ask to have renewed.
    """
    from . import adminauth as aa

    if not token or len(token) > 120:
        return None, "unknown"
    #: every column but the snapshot. A grid of two dozen pictures is two
    #: dozen requests, and carrying half a megabyte of frozen catalogue
    #: through each of them to serve one photograph is the difference
    #: between a page that opens and one that crawls.
    row = aa._connect().execute(
        "SELECT id, title, market, products, options, stock_at, allow_pdf, "
        "pdf_file, pdf_bytes, created_at, created_by, expires_at, revoked_at, "
        "views, last_viewed_at FROM catalogue_shares WHERE token_hash=?",
        (hash_token(token),)).fetchone()
    if row is None:
        return None, "unknown"
    if row["revoked_at"]:
        return None, "revoked"
    if row["expires_at"] and int(row["expires_at"]) < int(time.time()):
        return None, "expired"
    return dict(row), "ok"


def count_view(share_id: int) -> None:
    """One more view. Deliberately the only thing recorded: a counter and a
    timestamp, no address, no user agent, no identifier of any kind — there
    is nothing here that could become tracking later."""
    from . import adminauth as aa

    try:
        with aa._lock:
            conn = aa._connect()
            conn.execute("UPDATE catalogue_shares SET views=views+1, "
                         "last_viewed_at=? WHERE id=?", (int(time.time()), share_id))
            conn.commit()
    except Exception:
        pass                                  # a counter must never fail a page


#: Parsed snapshots, kept briefly. Bounded and short-lived: this is a read
#: cache in front of one SQLite row, not a second copy of the store.
_SNAPSHOTS: dict[int, tuple[float, dict]] = {}
_SNAPSHOT_MAX = 8
_SNAPSHOT_TTL_S = 300.0


def _forget(share_id: int) -> None:
    _SNAPSHOTS.pop(share_id, None)


def snapshot_of(row: dict) -> dict:
    """The frozen catalogue behind a share, read and parsed once.

    `resolve` deliberately leaves the snapshot column behind, so this is
    where it is fetched — and remembered, because a client opening a
    catalogue asks for the index and then one product at a time.
    """
    share_id = int(row.get("id") or 0)
    raw = row.get("snapshot")
    if raw is None and share_id:
        hit = _SNAPSHOTS.get(share_id)
        now = time.time()
        if hit is not None and now - hit[0] < _SNAPSHOT_TTL_S:
            return hit[1]
        from . import adminauth as aa

        got = aa._connect().execute(
            "SELECT snapshot FROM catalogue_shares WHERE id=?",
            (share_id,)).fetchone()
        raw = got["snapshot"] if got else ""
        data = _parse_snapshot(raw)
        if len(_SNAPSHOTS) >= _SNAPSHOT_MAX:
            _SNAPSHOTS.pop(next(iter(_SNAPSHOTS)), None)
        _SNAPSHOTS[share_id] = (now, data)
        return data
    return _parse_snapshot(raw)


def _parse_snapshot(raw) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def index_payload(row: dict) -> dict:
    """The list a viewer loads first: one small record per product.

    Everything a grid, a search box and the category filter need, and nothing
    else — the specifications and the description are the bulk of a snapshot
    and are read one product at a time, when a client actually opens one.
    """
    data = snapshot_of(row)
    items = []
    for n, item in enumerate(data.get("products") or []):
        small = {"i": n, "name": item.get("name") or "Product"}
        if item.get("code"):
            small["code"] = item["code"]
        if item.get("img"):
            small["img"] = item["img"][0]
        if "qty" in item:
            small["qty"] = item.get("qty")
            small["known"] = bool(item.get("known", True))
            small["stockText"] = item.get("stockText") or ""
        if item.get("cats"):
            small["cats"] = item["cats"]
        items.append(small)
    return {
        "title": data.get("title") or row.get("title") or cat.DEFAULT_TITLE,
        "market": data.get("market") or row.get("market") or "",
        "stockAt": data.get("stockAt"),
        "stockKnown": bool(data.get("stockKnown", True)),
        "lowStock": data.get("lowStock", config.LOW_STOCK_THRESHOLD),
        "options": data.get("options") or {},
        "allowPdf": bool(row.get("allow_pdf")) and bool(row.get("pdf_file")),
        "sharedAt": row.get("created_at"),
        "expiresAt": row.get("expires_at"),
        "count": len(items),
        "items": items,
    }


#: Which pictures one share may serve, remembered alongside the snapshot it
#: came from so a grid of twenty-four images resolves it once.
_HASHES: dict[int, tuple[float, frozenset]] = {}
_HASHES_MAX = 24
_HASHES_TTL_S = 300.0


def hashes_for(row: dict) -> frozenset:
    """The set of pictures this share names.

    An asset is a product photograph from a public image host, so this is not
    secrecy; it is scope. A link hands out the catalogue it was made for, and
    nothing else in the store.
    """
    share_id = int(row.get("id") or 0)
    hit = _HASHES.get(share_id)
    now = time.time()
    if hit is not None and now - hit[0] < _HASHES_TTL_S:
        return hit[1]
    found = {str(h) for item in snapshot_of(row).get("products") or []
             for h in item.get("img") or []}
    if len(_HASHES) >= _HASHES_MAX:
        _HASHES.pop(next(iter(_HASHES)), None)
    _HASHES[share_id] = (now, frozenset(found))
    return _HASHES[share_id][1]


def product_payload(row: dict, index: int) -> dict | None:
    data = snapshot_of(row)
    items = data.get("products") or []
    if not isinstance(index, int) or index < 0 or index >= len(items):
        return None
    item = dict(items[index])
    item["i"] = index
    return item


# ---------------- the admin's own list ----------------

def listing(limit: int = SHARES_LISTED) -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute(
        "SELECT id, title, market, products, allow_pdf, pdf_bytes, created_at, "
        "created_by, expires_at, revoked_at, revoked_by, views, last_viewed_at "
        "FROM catalogue_shares ORDER BY created_at DESC LIMIT ?",
        (max(1, min(500, int(limit))),)).fetchall()
    now = int(time.time())
    out = []
    for r in rows:
        row = dict(r)
        state = ("revoked" if row["revoked_at"] else
                 "expired" if row["expires_at"] and row["expires_at"] < now else "live")
        out.append({
            "id": row["id"], "title": row["title"], "market": row["market"],
            "products": row["products"], "allowPdf": bool(row["allow_pdf"]),
            "pdfBytes": row["pdf_bytes"], "createdAt": row["created_at"],
            "createdBy": row["created_by"], "expiresAt": row["expires_at"],
            "revokedAt": row["revoked_at"], "revokedBy": row["revoked_by"],
            "views": row["views"], "lastViewedAt": row["last_viewed_at"],
            "state": state,
        })
    return out


def revoke(share_id: int, by: str) -> dict | None:
    """Take a link down. The row stays — who shared what, and when it was
    stopped, is the point of keeping it — but the snapshot and the PDF go,
    because a revoked share has no reason to hold a copy of the catalogue."""
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        row = conn.execute("SELECT * FROM catalogue_shares WHERE id=?",
                           (share_id,)).fetchone()
        if row is None:
            return None
        if not row["revoked_at"]:
            conn.execute("UPDATE catalogue_shares SET revoked_at=?, revoked_by=?, "
                         "snapshot='', pdf_file='', pdf_bytes=0 WHERE id=?",
                         (int(time.time()), by[:200], share_id))
            conn.commit()
            if row["pdf_file"]:
                (pdf_dir() / row["pdf_file"]).unlink(missing_ok=True)
    _HASHES.pop(share_id, None)
    _forget(share_id)
    return {"id": share_id, "title": row["title"], "products": row["products"]}


# ---------------- keeping the store honest ----------------

def cleanup(now: float | None = None, grace: float | None = None) -> dict:
    """Drop what no live share can reach.

    An expired share loses its snapshot and its PDF — the link already answers
    "expired", so the copy of the catalogue behind it is dead weight — and then
    every picture is swept: the hashes every live snapshot still names are
    marked, and a file nothing names is removed. Mark-and-sweep rather than
    reference counting, because a count that drifts leaves either a broken
    picture or a file nobody can ever delete.

    A picture written or reused in the last `ASSET_GRACE_S` is marked too. A
    build writes its photographs before it has a snapshot to name them in, so
    without that a sweep landing mid-build would delete the imagery of a share
    about to exist. `grace=0` sweeps everything unreferenced, which is what a
    test wants and what nothing in the application asks for.
    """
    from . import adminauth as aa

    stamp = int(now if now is not None else time.time())
    hold = stamp - (ASSET_GRACE_S if grace is None else grace)
    expired = 0
    with aa._lock:
        conn = aa._connect()
        rows = conn.execute(
            "SELECT id, pdf_file FROM catalogue_shares WHERE snapshot<>'' "
            "AND expires_at IS NOT NULL AND expires_at < ?", (stamp,)).fetchall()
        for row in rows:
            conn.execute("UPDATE catalogue_shares SET snapshot='', pdf_file='', "
                         "pdf_bytes=0 WHERE id=?", (row["id"],))
            _forget(int(row["id"]))
            _HASHES.pop(int(row["id"]), None)
            if row["pdf_file"]:
                (pdf_dir() / row["pdf_file"]).unlink(missing_ok=True)
            expired += 1
        if expired:
            conn.commit()
        live = conn.execute(
            "SELECT snapshot FROM catalogue_shares WHERE snapshot<>''").fetchall()
    keep: set[str] = set()
    for row in live:
        for item in snapshot_of(dict(row)).get("products") or []:
            for digest in item.get("img") or []:
                keep.add(str(digest))
    with aa._lock:
        #: strictly newer, so `grace=0` protects nothing at all rather than
        #: protecting everything written in the current second
        fresh = aa._connect().execute(
            "SELECT DISTINCT hash FROM catalogue_assets WHERE created_at > ?",
            (hold,)).fetchall()
    keep.update(str(r["hash"]) for r in fresh)
    removed = freed = 0
    for path in assets_dir().glob("*.webp"):
        if path.stem not in keep:
            try:
                freed += path.stat().st_size
                path.unlink()
                removed += 1
            except OSError:
                pass
    # the URL index remembers a hash only while its file is there, so the
    # sweep above is what decides which rows are still meaningful
    with aa._lock:
        conn = aa._connect()
        rows = conn.execute("SELECT url_key, hash FROM catalogue_assets").fetchall()
        gone = [(r["url_key"],) for r in rows
                if not (assets_dir() / f"{r['hash']}.webp").exists()]
        if gone:
            conn.executemany("DELETE FROM catalogue_assets WHERE url_key=?", gone)
            conn.commit()
    return {"expired": expired, "assetsRemoved": removed, "bytesFreed": freed}


def cleanup_due(force: bool = False) -> dict | None:
    """Sweep, but not on every page the panel draws."""
    global _last_cleanup

    now = time.time()
    if not force and now - _last_cleanup < CLEANUP_EVERY_S:
        return None
    _last_cleanup = now
    try:
        return cleanup(now)
    except Exception:                         # pragma: no cover - defensive
        return None                           # housekeeping never fails a page


def _size(path) -> int:
    try:
        return path.stat().st_size
    except OSError:                           # swept between glob and stat
        return 0


def store_status() -> dict:
    """What the share store is holding, for the panel."""
    from . import adminauth as aa

    files = list(assets_dir().glob("*.webp"))
    pdfs = list(pdf_dir().glob("*.pdf"))
    row = aa._connect().execute(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN revoked_at IS NULL AND "
        "(expires_at IS NULL OR expires_at > ?) THEN 1 ELSE 0 END) AS live "
        "FROM catalogue_shares", (int(time.time()),)).fetchone()
    return {"shares": row["n"] or 0, "live": row["live"] or 0,
            "assets": len(files), "assetBytes": sum(_size(f) for f in files),
            "pdfs": len(pdfs), "pdfBytes": sum(_size(f) for f in pdfs)}
