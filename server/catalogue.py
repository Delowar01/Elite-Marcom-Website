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


# ---------------- the customer-facing record ----------------

#: Every field the renderer may see. The list is the guarantee: the renderer
#: is handed a dict built key by key from this, so a price field has no route
#: in at all. Checking the finished PDF for numbers that happen to equal a
#: price is not a guarantee — an item priced 100 with 100 in stock would trip
#: it, and a leak with an unusual value would not.
DTO_TEXT_FIELDS = ("id", "code", "name", "description", "brand", "color",
                   "material", "size", "capacity", "cartonDimensions",
                   "hsCode", "barcode")
DTO_NUMBER_FIELDS = ("unitsPerCarton", "cartonWeight", "cartonVolume")
DTO_LIST_FIELDS = ("categories", "options", "images")
DTO_FIELDS = DTO_TEXT_FIELDS + DTO_NUMBER_FIELDS + DTO_LIST_FIELDS + (
    "available", "availableKnown")

#: and the names that must never be among them, asserted at import time
FORBIDDEN_FIELDS = frozenset((
    "price", "list_price", "retail_price", "listPrice", "retailPrice",
    "wholesale", "reseller_price", "resellerPrice", "selling_price",
    "sellingPrice", "unit_price", "unitPrice", "vat", "discount", "currency",
    "booked", "blocked_qty", "blockedQty", "_int",
))
assert not (set(DTO_FIELDS) & FORBIDDEN_FIELDS), "a price field is in the DTO allowlist"


def _item_known(dto: dict) -> bool:
    """Whether this product's own quantity is real. ``None`` means the record
    does not say, so the market-level answer stands."""
    known = dto.get("availableKnown")
    return True if known is None else bool(known)


def to_dto(item: dict) -> dict:
    """The record the renderer is given: only allowlisted fields, copied one
    key at a time out of whatever the snapshot holds.

    This is the whole price guarantee. Nothing is deleted from a supplier
    dict and passed on — a new price field appearing in a future feed would
    be carried along by that approach. Here it simply never arrives.
    """
    out: dict = {}
    for key in DTO_TEXT_FIELDS:
        out[key] = clean_text(item.get(key), 1200 if key == "description" else 240)
    for key in DTO_NUMBER_FIELDS:
        value = item.get(key)
        out[key] = value if isinstance(value, (int, float)) and value > 0 else None
    for key in DTO_LIST_FIELDS:
        raw = item.get(key) or []
        out[key] = [str(v) for v in raw if v][:20] if isinstance(raw, (list, tuple)) else []
    available = item.get("available")
    try:
        out["available"] = int(available) if available is not None else None
    except (TypeError, ValueError):
        out["available"] = None
    known = item.get("availableKnown")
    #: absent is not "no": a record that carries no per-product verdict defers
    #: to the market-level answer, which is how a snapshot written before the
    #: per-product flag existed keeps printing its quantities.
    out["availableKnown"] = None if known is None else bool(known)
    return out


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


# ---------------- one picture, made small enough to hold ----------------

MAX_IMAGE_DIM = 1400          # a catalogue page is 595pt wide; more is waste
MAX_IMAGE_PIXELS = 50_000_000  # decompression-bomb ceiling, before decoding
PREPARED_QUALITY = 82


def prepare_image(raw: bytes):
    """Decode a downloaded photograph once, bound it, and hand back a small
    JPEG.

    Two jobs. It caps what a malicious or merely enormous file can cost —
    the dimensions are read from the header and refused before any pixels are
    decoded — and it shrinks what the renderer holds: a 4 MB original becomes
    tens of kilobytes at a size no A4 page can tell apart.
    """
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    try:
        from PIL import Image

        probe = Image.open(io.BytesIO(raw))
        if probe.width * probe.height > MAX_IMAGE_PIXELS:
            return None                      # a bomb, or close enough to one
        im = probe
        im.load()
        if max(im.width, im.height) > MAX_IMAGE_DIM:
            im.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=PREPARED_QUALITY, optimize=True)
        im.close()
        return out.getvalue()
    except Exception:
        return None                          # one bad photo, not a failed run


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

class Document:
    """A catalogue being drawn, one page at a time.

    The document is streamed rather than assembled: a product's photographs
    are handed in, drawn, and dropped before the next product is fetched, so
    the memory a catalogue needs does not grow with its length. Five hundred
    products cost the same working set as five.
    """

    def __init__(self, *, market: str, title: str, count: int, stock_at,
                 stock_is_known: bool, options: dict | None = None):
        if count <= 0:
            raise CatalogueError("Select at least one product for the catalogue.")
        if count > MAX_ITEMS:
            raise CatalogueError(f"A catalogue holds at most {MAX_ITEMS} products.")
        self.opts = {"description": True, "specs": True, "stock": True,
                     "stockDate": True, "code": True, "contents": False,
                     "market": market}
        self.opts.update(options or {})
        self.market = market
        self.title = clean_text(title, 120) or "Product Catalogue"
        self.count = count
        self.stock_at = stock_at
        self.stock_is_known = stock_is_known
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.c.setTitle(self.title)
        self.c.setAuthor("Elite Marcom")
        self.c.setSubject("Corporate gifts product catalogue")
        self.contents_pages = 0
        if self.opts.get("contents"):
            self.contents_pages = max(1, (count + 45) // 46)
        self.first_product_page = 2 + self.contents_pages
        self.drawn = 0
        _cover(self.c, title=self.title, market=market, count=count,
               stock_at=stock_at, generated=time.time())

    def contents(self, entries: list[tuple[str, str]]) -> None:
        """(code, name) in order; page numbers are worked out from position."""
        if not self.opts.get("contents"):
            return
        rows = [(code, name, self.first_product_page + n)
                for n, (code, name) in enumerate(entries)]
        _contents(self.c, rows, 2)

    def page(self, dto: dict, photos: list[bytes]) -> None:
        _product_page(self.c, dto, photos,
                      page_no=self.first_product_page + self.drawn,
                      options=self.opts, stock_at=self.stock_at,
                      stock_is_known=self.stock_is_known and _item_known(dto))
        self.drawn += 1

    def finish(self) -> bytes:
        self.c.save()
        pdf = self.buf.getvalue()
        assert_price_free(pdf)
        return pdf


def build(items: list[dict], photos: dict[str, list[bytes]], *, market: str,
          title: str, stock_at, stock_is_known: bool, options: dict | None = None,
          progress=None) -> bytes:
    """Build a whole catalogue from records already in hand.

    The streaming path (`Document`) is what the panel uses; this is the same
    thing with every photograph supplied up front, which is how a test with
    a handful of products says what it means.
    """
    if not items:
        raise CatalogueError("Select at least one product for the catalogue.")
    doc = Document(market=market, title=title, count=len(items), stock_at=stock_at,
                   stock_is_known=stock_is_known, options=options)
    dtos = [to_dto(it) for it in items]
    doc.contents([(d["code"] or "—", d["name"] or "Product") for d in dtos])
    for n, dto in enumerate(dtos):
        doc.page(dto, photos.get(dto["id"], []))
        if progress is not None:
            progress(n + 1)
    return doc.finish()


# ---------------- jobs: built in the background, never on disk ----------------

DEFAULT_TITLE = "Elite Marcom\nProduct Catalogue"
JOB_TTL_S = 20 * 60
IMAGES_PER_ITEM = 3
#: distinct prepared photographs remembered between products. Each is tens of
#: kilobytes after `prepare_image`, so this is a few megabytes at worst —
#: bounded on purpose, because an unbounded one grows with the catalogue.
PHOTO_CACHE_MAX = 60

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
            "error": "", "on_finish": None,
            "filename": f"Elite-Marcom-Jasani-Catalogue-"
                        f"{market.upper()}-{stamp}.pdf",
        }
    return token


def set_on_finish(token: str, fn) -> None:
    """Called once by the worker with (ok, job) when the build settles, so the
    audit records what actually happened rather than what was asked for."""
    with _lock:
        job = _jobs.get(token)
        if job is not None:
            job["on_finish"] = fn


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


async def _photos_for(market: str, dto: dict, cache: dict) -> list[bytes]:
    """The pictures for one product, already shrunk.

    Pictures come from the supplier's public image host. That is a file read
    over HTTP, not one of the three primary endpoints, so it is charged to
    nothing — the same line `server/supplier_video.py` draws. One unreachable
    photograph costs that product its picture and nothing else.
    """
    from . import jasani

    out: list[bytes] = []
    for url in (dto.get("images") or [])[:IMAGES_PER_ITEM]:
        if url in cache:
            if cache[url] is not None:
                out.append(cache[url])
            continue
        try:
            raw = await jasani._fetch_image_bytes(url)
        except Exception:
            raw = None
        small = prepare_image(raw) if raw else None
        del raw                               # the original goes immediately
        # Only the main picture is worth remembering between products: a
        # gallery shot is rarely shared, and an unbounded cache is the very
        # thing this rewrite exists to avoid.
        if len(cache) < PHOTO_CACHE_MAX:
            cache[url] = small
        if small is not None:
            out.append(small)
    return out


async def _render(token: str, rows: list[dict], *, market: str, title: str,
                  stock_at, stock_is_known: bool, options: dict) -> bytes:
    """Draw the catalogue, one product at a time.

    Each product's photographs are fetched, drawn and dropped before the next
    product is looked at, so the working set is one page's worth of pictures
    rather than five hundred products' worth. The quantities were captured
    when the rows were read, so every page still shows one consistent
    snapshot.
    """
    from . import jasani

    job = _jobs[token]
    doc = Document(market=market, title=title, count=len(rows), stock_at=stock_at,
                   stock_is_known=stock_is_known, options=options)
    if options.get("contents"):
        # the index needs names before any page is drawn; those are text, not
        # pictures, so reading them ahead costs nothing worth bounding
        heads = []
        for row in rows:
            detail = jasani.item_detail(market, row["id"]) or dict(row)
            heads.append((clean_text(detail.get("code"), 40) or "—",
                          clean_text(detail.get("name"), 120) or "Product"))
        doc.contents(heads)
    cache: dict[str, bytes | None] = {}
    job["state"] = "drawing"
    job["done"] = 0
    for n, row in enumerate(rows):
        detail = jasani.item_detail(market, row["id"]) or dict(row)
        # the filter's figures win, so the document is one snapshot
        detail["available"] = row.get("available")
        detail["availableKnown"] = row.get("availableKnown")
        dto = to_dto(detail)
        del detail
        photos = await _photos_for(market, dto, cache)
        doc.page(dto, photos)
        del photos, dto                       # released before the next product
        job["done"] = n + 1
    return doc.finish()


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
        pdf = asyncio.run(_render(token, rows, market=market, title=title,
                                  stock_at=stock_at, stock_is_known=stock_is_known,
                                  options=options))
        job["pdf"] = pdf
        job["state"] = "done"
        job["done"] = len(rows)
        job["finished"] = True
    except CatalogueError as exc:
        job["state"] = "failed"
        job["error"] = str(exc)[:200]
    except Exception as exc:                  # pragma: no cover - defensive
        job["state"] = "failed"
        job["error"] = f"The catalogue could not be built ({exc.__class__.__name__})."
    finally:
        done = job["state"] == "done"
        if job.get("on_finish"):
            try:
                job["on_finish"](done, job)
            except Exception:
                pass


def spawn(token: str, rows: list[dict], **kw) -> None:
    import threading

    threading.Thread(target=run, args=(token, rows), kwargs=kw, daemon=True).start()


# ---------------- the guarantee ----------------

#: every price-ish key the supplier feed or our internal store can carry
PRICE_KEYS = ("list_price", "retail_price", "listPrice", "retailPrice", "price",
              "wholesale", "reseller_price", "selling_price", "unit_price",
              "vat", "discount", "currency")
#: Tokens only a price could put on the page — a currency, or a price label.
#: Deliberately NOT ordinary English words: a supplier description may
#: honestly say "low cost" or "total weight", and refusing a catalogue over
#: that would be a worse failure than the one being guarded against.
#:
#: Note what is *not* here: the price figures themselves. A number equal to a
#: price proves nothing — an item priced 100 with 100 units in stock prints
#: "100 units", a 500 ml capacity beside a price of 500, a carton of 24
#: beside a price of 24. Matching on those would reject honest catalogues
#: while still missing a leak at an unusual value. The guarantee lives in
#: `to_dto`, which never lets a price into the renderer; this is the second
#: line, catching a label or a currency however it got there.
PRICE_WORDS = ("sar", "aed", "usd", "list price", "retail price", "unit price",
               "selling price", "reseller price", "ex vat", "incl vat", "rrp",
               "price:", "price :")


def assert_price_free(pdf: bytes) -> None:
    """Second line of defence: raise if a currency or a price label reached
    the finished document.

    reportlab writes page text as ASCII85 over Flate, so this reads the drawn
    strings back out rather than scanning raw bytes — a raw scan would pass
    happily on a compressed stream and prove nothing at all.

    It deliberately does not look for price *values*. `to_dto` is what makes
    the document price-free; a numeric coincidence is not evidence of a leak
    and rejecting one would only break honest catalogues.
    """
    text = extract_text(pdf).lower()
    for word in PRICE_WORDS:
        pattern = rf"\b{re.escape(word)}" if word.endswith((":", " :")) else \
            rf"\b{re.escape(word)}\b"
        if re.search(pattern, text):
            raise CatalogueError(f"a price indicator reached the catalogue: {word!r}")


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
