"""The Jasani product catalogue — a cover, an optional index, one page per item.

Two rules shape this file.

**No price, ever.** The supplier's `list_price` is internal by supplier policy
and this document is made to be sent to a customer. Nothing here reads a price
field, and `assert_price_free` re-checks the finished bytes before they leave
the building — a belt beside the braces, because a catalogue that leaks a
supplier price is not a bug you find later.

**No supplier API call.** Every figure comes from the snapshot the scheduled
synchronisation already wrote. Photographs are downloaded from the supplier's
public image host, which is a web page read rather than a primary endpoint and
is charged to nothing — the same distinction `server/supplier_video.py` draws.
A catalogue is never a reason to spend one of the five daily calls.
"""
from __future__ import annotations

import io
import re
import time

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .exports import (GREY, INK, LINE, ORANGE, PAGE_H, PAGE_W, _LOGO_PATH, _draw_contained,
                      _image_box, _wrap)

M = 46.0
SITE = "www.elitemarcom.com"
MAX_ITEMS = 500           # one catalogue, one sitting
MAX_IMAGE_BYTES = 4 * 1024 * 1024

MARKET_LABEL = {"ksa": "Saudi Arabia", "uae": "United Arab Emirates"}


class CatalogueError(Exception):
    """User-facing message, safe to show in the panel."""


# ---------------- text hygiene ----------------

_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")
_WS_RE = re.compile(r"[ \t ]+")
_EMPTY = {"", "none", "null", "undefined", "nan", "{}", "[]", "0.0"}


def clean_text(raw, limit: int = 1200) -> str:
    """Supplier text, made printable.

    Tags are removed rather than escaped — reportlab draws strings, so markup
    would simply be printed at a customer. The literal words a careless feed
    puts in a text field ("null", "undefined") are dropped too: a catalogue
    page saying "Material: undefined" is worse than one with no Material row.
    """
    if raw is None:
        return ""
    text = str(raw)
    if "<" in text:
        import html as _html

        text = _TAG_RE.sub(" ", text)
        text = _html.unescape(text)
        text = _TAG_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    text = text.strip()
    if text.lower() in _EMPTY:
        return ""
    return text[:limit]


def _num(value) -> str:
    """1248 → "1,248". Never "1248.000000"."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    return f"{n:,}"


def stock_sentence(available, known: bool) -> tuple[str, str]:
    """(headline, note). An unknown quantity says so rather than printing 0."""
    if not known or available is None:
        return "Availability unavailable", ""
    n = _num(available)
    if n == "":
        return "Availability unavailable", ""
    return f"{n} units", ""


def when(ts) -> str:
    if not ts:
        return ""
    return time.strftime("%d %B %Y, %I:%M %p", time.localtime(float(ts)))


# ---------------- the specification rows ----------------

#: (source key, printed label) — the normalized product fields worth showing a
#: customer. No price field appears here, and none may be added.
SPEC_FIELDS: tuple[tuple[str, str], ...] = (
    ("brand", "Brand"),
    ("color", "Colour"),
    ("material", "Material"),
    ("size", "Size"),
    ("capacity", "Capacity"),
    ("unitsPerCarton", "Units per carton"),
    ("cartonDimensions", "Carton size"),
    ("cartonWeight", "Carton weight"),
    ("cartonVolume", "Carton volume"),
    ("hsCode", "HS code"),
    ("barcode", "Barcode"),
)

_SUFFIX = {"cartonWeight": " kg", "cartonVolume": " m³"}


def spec_rows(item: dict) -> list[tuple[str, str]]:
    """Label/value pairs, with anything empty or meaningless left out."""
    rows: list[tuple[str, str]] = []
    for key, label in SPEC_FIELDS:
        value = clean_text(item.get(key), 120)
        if not value:
            continue
        rows.append((label, value + _SUFFIX.get(key, "")))
    cats = [clean_text(c, 60) for c in (item.get("categories") or [])]
    cats = [c for c in cats if c]
    if cats:
        rows.append(("Category", ", ".join(cats)[:120]))
    options = [clean_text(o, 40) for o in (item.get("options") or [])]
    options = [o for o in options if o]
    if options:
        rows.append(("Options", ", ".join(options)[:120]))
    return rows[:14]


# ---------------- page furniture ----------------

def _logo(c, x: float, y: float, height: float = 26.0) -> float:
    try:
        if _LOGO_PATH.exists():
            from reportlab.lib.utils import ImageReader

            logo = ImageReader(str(_LOGO_PATH))
            lw, lh = logo.getSize()
            c.drawImage(logo, x, y - height, width=lw * (height / lh), height=height,
                        mask="auto")
            return height
    except Exception:
        pass
    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(*ORANGE)
    c.drawString(x, y - 16, "ELITE MARCOM")
    return 20.0


def _footer(c, page_no: int) -> None:
    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(0.6)
    c.line(M, 46, PAGE_W - M, 46)
    c.setFont("Helvetica", 7.4)
    c.setFillColorRGB(*GREY)
    c.drawString(M, 33, SITE)
    c.drawRightString(PAGE_W - M, 33, f"Page {page_no}")


# ---------------- the pages ----------------

def _cover(c, *, title: str, market: str, count: int, stock_at, generated: float) -> None:
    y = PAGE_H - 92
    _logo(c, M, y, 34)
    y -= 150
    c.setFillColorRGB(*ORANGE)
    c.rect(M, y + 54, 96, 3, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 30)
    c.setFillColorRGB(*INK)
    for line in _wrap(title, "Helvetica-Bold", 30, PAGE_W - 2 * M - 40)[:3]:
        c.drawString(M, y, line)
        y -= 36
    y -= 16
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(*GREY)
    c.drawString(M, y, MARKET_LABEL.get(market, market.upper()) + f"  ·  {market.upper()}")
    y -= 26
    c.setFont("Helvetica-Bold", 13)
    c.setFillColorRGB(*INK)
    c.drawString(M, y, f"{count:,} product{'' if count == 1 else 's'}")
    y -= 44
    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(0.8)
    c.line(M, y, PAGE_W - M, y)
    y -= 24
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*GREY)
    # the two dates are different things and are labelled as different things
    c.drawString(M, y, "Catalogue prepared")
    c.setFillColorRGB(*INK)
    c.drawString(M + 128, y, when(generated))
    y -= 16
    c.setFillColorRGB(*GREY)
    c.drawString(M, y, "Stock as of")
    c.setFillColorRGB(*INK)
    c.drawString(M + 128, y, when(stock_at) or "synchronisation date unavailable")
    y -= 40
    c.setFont("Helvetica", 8.4)
    c.setFillColorRGB(*GREY)
    for line in _wrap("Quantities are those recorded at the last stock synchronisation shown "
                      "above and are not a reservation. Please confirm availability before "
                      "committing to a quantity.", "Helvetica", 8.4, PAGE_W - 2 * M):
        c.drawString(M, y, line)
        y -= 11
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*GREY)
    c.drawString(M, 60, SITE)
    c.showPage()


def _contents(c, entries: list[tuple[str, str, int]], start_page: int) -> int:
    """Code / name / page, as many pages as it takes. Returns pages used."""
    used = 0
    i = 0
    while i < len(entries):
        used += 1
        y = PAGE_H - 70
        _logo(c, M, y, 22)
        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(*INK)
        c.drawRightString(PAGE_W - M, y - 12, "Contents")
        y -= 44
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(2)
        c.line(M, y, PAGE_W - M, y)
        y -= 20
        c.setFont("Helvetica", 7.6)
        c.setFillColorRGB(*GREY)
        c.drawString(M, y, "ITEM CODE")
        c.drawString(M + 112, y, "PRODUCT")
        c.drawRightString(PAGE_W - M, y, "PAGE")
        y -= 14
        while i < len(entries) and y > 70:
            code, name, page_no = entries[i]
            c.setFont("Helvetica", 8.6)
            c.setFillColorRGB(*GREY)
            c.drawString(M, y, code[:18])
            c.setFillColorRGB(*INK)
            name_w = PAGE_W - M - 46 - (M + 112)
            c.drawString(M + 112, y, _wrap(name, "Helvetica", 8.6, name_w)[0])
            c.drawRightString(PAGE_W - M, y, str(page_no))
            y -= 13
            i += 1
        _footer(c, start_page + used - 1)
        c.showPage()
    return used


def _product_page(c, item: dict, photos: list[bytes], *, page_no: int, options: dict,
                  stock_at, stock_is_known: bool) -> None:
    """One A4 portrait page. Everything is clipped to fit: a product never
    spills onto a second page, because the catalogue's contract is one page
    each and a reader counting pages must be able to trust it."""
    y = PAGE_H - 54
    _logo(c, M, y, 22)
    c.setFont("Helvetica", 7.4)
    c.setFillColorRGB(*GREY)
    c.drawRightString(PAGE_W - M, y - 7, "Corporate gifts · Product catalogue")
    c.drawRightString(PAGE_W - M, y - 18, MARKET_LABEL.get(options.get("market", ""), ""))
    y -= 36
    c.setFillColorRGB(*ORANGE)
    c.rect(M, y, PAGE_W - 2 * M, 2.4, stroke=0, fill=1)
    y -= 18

    # ---- the picture, given the room it deserves ----
    box_h = 250.0
    box_w = PAGE_W - 2 * M
    c.setFillColorRGB(0.98, 0.975, 0.97)
    c.rect(M, y - box_h, box_w, box_h, stroke=0, fill=1)
    main = None
    for blob in photos:
        reader = _image_box(blob)
        if reader[0] is not None:
            main = reader
            break
    if main is not None:
        _draw_contained(c, main, M + 10, y - box_h + 10, box_w - 20, box_h - 20)
    else:
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*GREY)
        c.drawCentredString(PAGE_W / 2, y - box_h / 2 - 3, "Image unavailable")
    y -= box_h + 8

    # a small strip of further photographs, only when there is room for it
    extras = []
    for blob in photos[1:4]:
        reader = _image_box(blob)
        if reader[0] is not None:
            extras.append(reader)
    if extras:
        strip_h = 52.0
        tile = 68.0
        x = M
        for reader in extras:
            c.setFillColorRGB(0.98, 0.975, 0.97)
            c.rect(x, y - strip_h, tile, strip_h, stroke=0, fill=1)
            _draw_contained(c, reader, x + 4, y - strip_h + 4, tile - 8, strip_h - 8)
            x += tile + 8
        y -= strip_h + 10

    # ---- name and code ----
    name = clean_text(item.get("name"), 220) or "Product"
    size = 17.0
    lines = _wrap(name, "Helvetica-Bold", size, PAGE_W - 2 * M)
    if len(lines) > 3:                      # an unusually long name steps down
        size = 14.0
        lines = _wrap(name, "Helvetica-Bold", size, PAGE_W - 2 * M)
    c.setFont("Helvetica-Bold", size)
    c.setFillColorRGB(*INK)
    for line in lines[:3]:
        c.drawString(M, y - size, line)
        y -= size + 4
    y -= 4
    if options.get("code", True):
        code = clean_text(item.get("code"), 60)
        if code:
            c.setFont("Helvetica", 9.2)
            c.setFillColorRGB(*GREY)
            c.drawString(M, y - 9, code)
            y -= 18

    # ---- description ----
    if options.get("description", True):
        body = clean_text(item.get("description"), 900)
        if body:
            y -= 6
            c.setFont("Helvetica-Bold", 8.6)
            c.setFillColorRGB(*ORANGE)
            c.drawString(M, y - 8, "DESCRIPTION")
            y -= 20
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(*INK)
            for line in _wrap(body, "Helvetica", 9, PAGE_W - 2 * M)[:7]:
                c.drawString(M, y - 9, line)
                y -= 12
            y -= 4

    # ---- specifications ----
    if options.get("specs", True):
        rows = spec_rows(item)
        if rows:
            room = int(max(0, (y - 150) // 13))
            rows = rows[:max(0, min(len(rows), room))]
        if rows:
            y -= 4
            c.setFont("Helvetica-Bold", 8.6)
            c.setFillColorRGB(*ORANGE)
            c.drawString(M, y - 8, "SPECIFICATIONS")
            y -= 20
            for label, value in rows:
                c.setFont("Helvetica", 8.8)
                c.setFillColorRGB(*GREY)
                c.drawString(M, y - 8, label)
                c.setFont("Helvetica-Bold", 8.8)
                c.setFillColorRGB(*INK)
                c.drawString(M + 132, y - 8,
                             _wrap(value, "Helvetica-Bold", 8.8, PAGE_W - M - (M + 132))[0])
                y -= 13
            y -= 4

    # ---- availability, pinned above the footer so every page agrees ----
    if options.get("stock", True):
        band_h = 60.0
        by = 62.0
        c.setFillColorRGB(0.98, 0.975, 0.97)
        c.rect(M, by, PAGE_W - 2 * M, band_h, stroke=0, fill=1)
        c.setFillColorRGB(*ORANGE)
        c.rect(M, by, 3, band_h, stroke=0, fill=1)
        c.setFont("Helvetica", 7.6)
        c.setFillColorRGB(*GREY)
        c.drawString(M + 16, by + band_h - 16, "AVAILABLE QUANTITY")
        headline, _ = stock_sentence(item.get("available"), stock_is_known)
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(*INK)
        c.drawString(M + 16, by + band_h - 38, headline)
        if options.get("stockDate", True):
            c.setFont("Helvetica", 7.8)
            c.setFillColorRGB(*GREY)
            stamp = when(stock_at)
            c.drawRightString(PAGE_W - M - 16, by + band_h - 20, "Stock as of")
            c.setFillColorRGB(*INK)
            c.drawRightString(PAGE_W - M - 16, by + band_h - 33,
                              stamp or "synchronisation date unavailable")
    _footer(c, page_no)
    c.showPage()


# ---------------- the whole document ----------------

def build(items: list[dict], photos: dict[str, list[bytes]], *, market: str,
          title: str, stock_at, stock_is_known: bool, options: dict | None = None,
          progress=None) -> bytes:
    """`photos` is keyed by product id and already fetched, so this function
    does no network work at all and the whole document is one consistent
    snapshot: every page shows the figures captured before the first page was
    drawn."""
    opts = {"description": True, "specs": True, "stock": True, "stockDate": True,
            "code": True, "contents": False, "market": market}
    opts.update(options or {})
    if not items:
        raise CatalogueError("Select at least one product for the catalogue.")
    if len(items) > MAX_ITEMS:
        raise CatalogueError(f"A catalogue holds at most {MAX_ITEMS} products.")

    generated = time.time()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(clean_text(title, 120) or "Elite Marcom Product Catalogue")
    c.setAuthor("Elite Marcom")
    c.setSubject("Corporate gifts product catalogue")

    _cover(c, title=clean_text(title, 120) or "Product Catalogue", market=market,
           count=len(items), stock_at=stock_at, generated=generated)

    # the cover is page 1 and is not a product page; the index, when asked
    # for, sits between the two and is sized before anything is numbered
    contents_pages = 0
    if opts.get("contents"):
        per_page = 46
        contents_pages = max(1, (len(items) + per_page - 1) // per_page)
    first_product_page = 2 + contents_pages
    if opts.get("contents"):
        entries = [(clean_text(it.get("code"), 40) or "—",
                    clean_text(it.get("name"), 120) or "Product",
                    first_product_page + n)
                   for n, it in enumerate(items)]
        _contents(c, entries, 2)

    for n, item in enumerate(items):
        _product_page(c, item, photos.get(str(item.get("id")), []),
                      page_no=first_product_page + n, options=opts,
                      stock_at=stock_at, stock_is_known=stock_is_known)
        if progress is not None:
            progress(n + 1)
    c.save()
    return buf.getvalue()


# ---------------- jobs: built in the background, never on disk ----------------

DEFAULT_TITLE = "Elite Marcom\nProduct Catalogue"
JOB_TTL_S = 20 * 60
IMAGES_PER_ITEM = 3

_jobs: dict[str, dict] = {}
_lock = __import__("threading").Lock()


def _prune(now: float) -> None:
    for token, job in list(_jobs.items()):
        if now - job["created"] > JOB_TTL_S:
            _jobs.pop(token, None)


def start(by: str, market: str, total: int) -> str:
    import secrets

    token = secrets.token_urlsafe(18)
    stamp = time.strftime("%Y-%m-%d")
    with _lock:
        _prune(time.time())
        _jobs[token] = {
            "created": time.time(), "by": by, "market": market,
            "total": total, "done": 0, "state": "preparing", "pdf": None,
            "error": "", "filename": f"Elite-Marcom-Jasani-Catalogue-"
                                     f"{market.upper()}-{stamp}.pdf",
        }
    return token


def get(token: str, by: str) -> dict | None:
    with _lock:
        job = _jobs.get(token)
        if job is None or job["by"] != by:
            return None
        if time.time() - job["created"] > JOB_TTL_S:
            _jobs.pop(token, None)
            return None
        return job


def collect(token: str) -> None:
    """The PDF is handed over once and then dropped — it is a document made on
    demand, not something to keep."""
    with _lock:
        job = _jobs.get(token)
        if job:
            job["pdf"] = None
            job["state"] = "collected"


def public(job: dict) -> dict:
    return {"state": job["state"], "done": job["done"], "total": job["total"],
            "error": job["error"], "filename": job["filename"],
            "ready": job["state"] == "done" and bool(job["pdf"])}


async def _collect_photos(market: str, rows: list[dict], job: dict) -> tuple[list, dict]:
    """Resolve each row to its full record and fetch its photographs.

    Pictures come from the supplier's public image host. That is a file read
    over HTTP, not one of the three primary endpoints, so it is charged to
    nothing — the same line `server/supplier_video.py` draws. One unreachable
    photograph costs that product its picture and nothing else.
    """
    from . import jasani

    items: list[dict] = []
    photos: dict[str, list[bytes]] = {}
    seen: dict[str, bytes] = {}            # one download per distinct address
    for n, row in enumerate(rows):
        detail = jasani.item_detail(market, row["id"]) or dict(row)
        # the quantity is the one the filter saw, so every page of the
        # document agrees even if the cache moves while it is being drawn
        detail["available"] = row.get("available")
        items.append(detail)
        urls = [u for u in (detail.get("images") or []) if u][:IMAGES_PER_ITEM]
        if not urls and detail.get("image"):
            urls = [detail["image"]]
        blobs: list[bytes] = []
        for url in urls:
            if url in seen:
                blobs.append(seen[url])
                continue
            try:
                blob = await jasani._fetch_image_bytes(url)
            except Exception:
                blob = None
            if blob and len(blob) <= MAX_IMAGE_BYTES:
                seen[url] = blob
                blobs.append(blob)
        photos[str(detail.get("id"))] = blobs
        job["done"] = n + 1
    return items, photos


def run(token: str, rows: list[dict], *, market: str, title: str,
        stock_at, stock_is_known: bool, options: dict) -> None:
    """Build the document. Runs on a worker thread, so the request that asked
    for it has already returned and a five-hundred page catalogue never holds
    a connection open."""
    import asyncio

    job = _jobs.get(token)
    if job is None:
        return
    try:
        job["state"] = "images"
        items, photos = asyncio.run(_collect_photos(market, rows, job))
        job["state"] = "drawing"
        job["done"] = 0
        pdf = build(items, photos, market=market, title=title, stock_at=stock_at,
                    stock_is_known=stock_is_known, options=options,
                    progress=lambda n: job.__setitem__("done", n))
        # checked against the figures this market actually holds for these
        # products, not against a guess at what a price looks like
        assert_price_free(pdf, price_values_of(market, [str(i.get("id")) for i in items]))
        job["pdf"] = pdf
        job["state"] = "done"
        job["done"] = len(items)
    except CatalogueError as exc:
        job["state"] = "failed"
        job["error"] = str(exc)[:200]
    except Exception as exc:                  # pragma: no cover - defensive
        job["state"] = "failed"
        job["error"] = f"The catalogue could not be built ({exc.__class__.__name__})."


def spawn(token: str, rows: list[dict], **kw) -> None:
    import threading

    threading.Thread(target=run, args=(token, rows), kwargs=kw, daemon=True).start()


# ---------------- the guarantee ----------------

#: every price-ish key the supplier feed or our internal store can carry
PRICE_KEYS = ("list_price", "retail_price", "listPrice", "retailPrice", "price",
              "wholesale", "reseller_price", "selling_price", "unit_price",
              "vat", "discount", "currency")
#: Tokens only a price could put on the page. Deliberately NOT a list of
#: ordinary English words: a supplier description may honestly say "low cost"
#: or "total weight", and refusing a whole catalogue over that would be a
#: worse failure than the one being guarded against. The real guarantee is
#: the value check below — the record's own figures, which must never appear.
PRICE_WORDS = ("sar", "aed", "usd", "list price", "retail price", "unit price",
               "selling price", "reseller price", "ex vat", "incl vat", "rrp")


def assert_price_free(pdf: bytes, values: list[str] | None = None) -> None:
    """Raise if anything price-shaped reached the finished document.

    reportlab writes page text into compressed streams, so the check reads the
    drawn strings back out of the PDF rather than scanning the raw bytes —
    scanning raw bytes would pass happily on a compressed stream and prove
    nothing at all.
    """
    text = extract_text(pdf).lower()
    for word in PRICE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text):
            raise CatalogueError(f"a price field reached the catalogue: {word!r}")
    for value in values or []:
        v = str(value).strip().lower()
        if not v or v in ("0", "0.0", "none"):
            continue
        # a figure is only damning as a whole token: "12.5" must not match
        # inside a carton volume of "112.55"
        if re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", text):
            raise CatalogueError(f"a price value reached the catalogue: {value!r}")


def price_values_of(market: str, ids: list[str]) -> list[str]:
    """Every price figure the internal store holds for these products, so the
    guarantee can be checked against the real numbers rather than a word list."""
    from . import jasani

    out: list[str] = []
    try:
        internal = jasani.internal_map(market)
    except Exception:
        return out
    for pid in ids:
        rec = internal.get(str(pid)) or {}
        for key in ("price", "wholesale", "list_price", "retail_price"):
            value = rec.get(key)
            if value in (None, "", 0):
                continue
            out.append(str(value))
            if isinstance(value, float) and value.is_integer():
                out.append(str(int(value)))
    return out


def _decode_stream(chunk: bytes) -> bytes:
    """reportlab writes ASCII85 over Flate by default, so a zlib attempt on
    its own decodes nothing — and a price check that silently reads an empty
    string would pass on every document ever made."""
    import base64
    import zlib

    body = chunk.strip()
    if body.startswith(b"Gb") or body.endswith(b"~>"):
        try:
            cut = body.split(b"~>")[0]
            body = base64.a85decode(cut, adobe=False)
        except Exception:
            return chunk
    for attempt in (body, chunk):
        try:
            return zlib.decompress(attempt)
        except Exception:
            continue
    return body


def extract_text(pdf: bytes) -> str:
    """The text actually drawn on the pages."""
    out: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        chunk = _decode_stream(match.group(1))
        for piece in re.findall(rb"\((?:\\.|[^\\()])*\)", chunk):
            body = piece[1:-1]
            body = re.sub(rb"\\([()\\])", rb"\1", body)
            out.append(body.decode("latin-1", errors="replace"))
    return " ".join(out)
