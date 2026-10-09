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

from reportlab.pdfbase.pdfmetrics import stringWidth

from .exports import (GREY, INK, LINE, ORANGE, PAGE_H, PAGE_W, _draw_contained,
                      _image_box, _wrap, logo_reader)

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


# ---------------- supplier price text ----------------
#
# A supplier writes what a supplier writes. Real Jasani descriptions carry
# lines like "RRP: SAR 45", and the finished-document guard — correctly —
# refuses the whole catalogue over one of them. Refusing is the right last
# resort and stays; it is the wrong *first* answer, because one careless
# description must not make a five-hundred page catalogue impossible.
#
# So price text is removed from customer-facing fields on the way into the
# DTO, before a single page is drawn. The guard then has nothing to find —
# and if it ever does, generation still fails.

#: The labels a price statement wears. Each is an indicator on its own:
#: "RRP available on request" carries no figure and is still a price
#: statement.
_LABELS = r"""(?:
      r\.?\s?r\.?\s?p\.?\b
    | recommended\s+retail\s+price
    | (?:retail|list|unit|selling|resell(?:er)?|whole\s?sale|trade|net|special)
      \s*-?\s*price
    | price\s+list
)"""

#: The currencies the two markets quote in. The finished-document guard
#: rejects a bare one of these, so the sanitizer has to remove a bare one
#: too — otherwise a description reading "quoted in SAR" would still fail.
_CCY = r"(?:sar|aed|usd|dhs)"

#: VAT phrasing, which only ever appears beside a figure.
_VAT = r"(?:(?:ex(?:cl(?:uding|usive)?)?|incl?(?:uding|usive)?)\.?\s*(?:of\s+)?vat)"

#: "price" alone is far too ordinary a word to treat as a label — a
#: price-conscious design is a design. It counts only where it is actually
#: introducing a figure: a colon, a spaced dash, a currency or a number.
_BARE_PRICE = (r"(?:\bprice\b\s*(?::|\s[-–—]\s)"
               r"|\bprice\b\s*:?\s*(?:" + _CCY + r"|\d))")

#: A currency with a figure, in either order.
_CCY_AMOUNT = r"(?:\b" + _CCY + r"\s*\.?\s*\d|\d\s*" + _CCY + r"\b)"

#: Any of these makes the text it sits in a price statement.
_INDICATOR = re.compile(
    r"(?:" + _LABELS + r"|" + _VAT + r"|" + _BARE_PRICE + r"|" + _CCY_AMOUNT
    + r"|\b" + _CCY + r"\b)",
    re.I | re.X)

#: Where a free-text field may be cut: a sentence of it, or a line of it.
#: That is the smallest piece worth keeping or dropping on its own.
_SEGMENT_RE = re.compile(r"[^\n]*?(?:[.;!?](?=\s|$)|$)")

#: A fragment left behind that is nothing but a figure. "R.R.P. 99" splits
#: into "R.R.P." and "99" — the label goes, and the amount it belonged to
#: must go with it rather than being printed on its own as a bare number.
_ONLY_FIGURE = re.compile(r"^[\s\d.,:;%/x\u00d7*+\-\u2013\u2014()\[\]]+$")

#: Fields that are prose, and are therefore cut fragment by fragment.
#: Everything else is a short structured value — a colour, a material, an
#: option — where sentence surgery would leave nonsense, so such a value is
#: kept whole or left out whole.
FREE_TEXT_FIELDS = ("description", "name")


def has_price_text(value) -> bool:
    """Whether this text carries a supplier price statement."""
    return bool(value) and bool(_INDICATOR.search(str(value)))


def _tidy(text: str) -> str:
    """Close the gap a removed fragment left, without reflowing the rest."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^[\s,;:.\-–—]+", "", text)
    text = re.sub(r"\s+([.,;])", r"\1", text)
    return text.strip(" \t\n,;:-–—")


def sanitize_catalogue_text(value: str, field: str = "") -> str:
    """Customer text with the supplier's price statements taken out.

    A different job from `clean_text`, which makes a value *printable* — tags
    gone, control characters gone, "undefined" gone. This one makes a
    printable value *ours to print*: the description of a bottle is useful to
    a customer and stays, while the "RRP: SAR 45" in the middle of it is a
    figure that is not ours to quote and goes.

    Prose is cut fragment by fragment, so one price sentence costs its
    sentence rather than the whole description. A short structured value is
    kept whole or dropped whole.

    It never leaves a dangling "RRP:", a stray "SAR", or the amount a deleted
    currency belonged to: whatever survives is checked again, and a value
    still carrying an indicator is dropped rather than handed on
    half-cleaned.
    """
    text = value or ""
    if not text or not _INDICATOR.search(text):
        return text
    if field not in FREE_TEXT_FIELDS:
        return ""                             # a structured value, omitted
    kept: list[str] = []
    for line in text.split("\n"):
        parts = [p for p in _SEGMENT_RE.findall(line) if p.strip()]
        good = [p.strip() for p in parts
                if not _INDICATOR.search(p) and not _ONLY_FIGURE.match(p.strip())]
        if good:
            kept.append(" ".join(good))
    out = _tidy("\n".join(kept))
    #: belt and braces: a value still matching is dropped whole rather than
    #: printed half-cleaned, because the "45" left behind by a deleted
    #: "SAR 45" is worse than no sentence at all
    return "" if _INDICATOR.search(out) else out


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


#: The three answers the availability band may give, and the only three.
#: `AVAILABLE_NOW` over `0 units` is what a reader takes away from the page,
#: and it is wrong — a label and the figure beneath it must be one statement.
STOCK_LABEL = {"in": "AVAILABLE NOW",
               "out": "OUT OF STOCK",
               "unknown": "AVAILABILITY UNAVAILABLE"}
#: What stands where the figure would, when there is no figure to print. Not
#: a number, because an unknown quantity printed as 0 is the same lie read
#: from the other direction.
STOCK_UNKNOWN_FIGURE = "Not reported"


def stock_state(available, known: bool) -> str:
    """``"in"`` | ``"out"`` | ``"unknown"`` — one reading of the figures that
    the label, the mark and the quantity all take, so they cannot disagree.

    The verdict is read off the integer `_num` would **print**, not the raw
    value, because that is the number on the page: a quantity of 0.4 prints
    as "0 units" and has to say OUT OF STOCK rather than AVAILABLE NOW.
    """
    if not known:
        return "unknown"
    try:
        n = int(round(float(available)))
    except (TypeError, ValueError):
        return "unknown"                 # exactly when `_num` prints nothing
    return "in" if n > 0 else "out"


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
DTO_NUMBER_FIELDS = ("unitsPerCarton",)
#: Measures are *normalized strings*, not numbers. `jasani._weight` trims the
#: float artifacts and hands back "9.5" — or "9.5 kg" when the supplier sent
#: the unit with the figure. Reading them as numbers dropped every one of
#: them, which is why a carton weight stopped printing.
DTO_MEASURE_FIELDS = ("cartonWeight", "cartonVolume")
DTO_LIST_FIELDS = ("categories", "options", "images")
DTO_FIELDS = DTO_TEXT_FIELDS + DTO_NUMBER_FIELDS + DTO_MEASURE_FIELDS + \
    DTO_LIST_FIELDS + ("available", "availableKnown")

#: and the names that must never be among them, asserted at import time
FORBIDDEN_FIELDS = frozenset((
    "price", "list_price", "retail_price", "listPrice", "retailPrice",
    "wholesale", "reseller_price", "resellerPrice", "selling_price",
    "sellingPrice", "unit_price", "unitPrice", "vat", "discount", "currency",
    "booked", "blocked_qty", "blockedQty", "_int",
))
assert not (set(DTO_FIELDS) & FORBIDDEN_FIELDS), "a price field is in the DTO allowlist"


def _measure(value) -> str | None:
    """A normalized measure, kept as the string the snapshot holds.

    A number is accepted too and printed without float artifacts, because a
    hand-built record or a future feed may send one; a string is kept as it
    stands, so a legitimate unit the supplier wrote survives. Anything that
    is not a positive figure is dropped rather than printed as "0".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    text = clean_text(value, 40)
    if not text:
        return None
    lead = re.match(r"^-?\d+(?:\.\d+)?", text)
    if not lead or float(lead.group(0)) <= 0:
        return None                          # "0", "-1", "n/a" are not measures
    return text


def _item_known(dto: dict) -> bool:
    """Whether this product's own quantity is real. ``None`` means the record
    does not say, so the market-level answer stands."""
    known = dto.get("availableKnown")
    return True if known is None else bool(known)


def to_dto(item: dict, stats: dict | None = None) -> dict:
    """The record the renderer is given: only allowlisted fields, copied one
    key at a time out of whatever the snapshot holds, each one with the
    supplier's price text taken out of it.

    Two separate guarantees, and both are needed. The allowlist is why no
    price *field* can arrive: nothing is deleted from a supplier dict and
    passed on, because that approach would carry along whatever price key a
    future feed invents. `sanitize_catalogue_text` is why no price *sentence*
    can arrive: a description is customer text written by the supplier, and
    the supplier puts "RRP: SAR 45" in it.

    `stats`, when given, is a counter — `{"products": n, "fields": n}` — so
    the panel can say that cleanup happened. It carries counts only; a figure
    that is not ours to show is not ours to log either.
    """
    out: dict = {}
    touched = 0
    for key in DTO_TEXT_FIELDS:
        if key == "description":
            #: clipped at a full stop rather than at the 1200th character —
            #: a hard cut lands mid-word, and the renderer downstream can
            #: only choose between the sentences it was given
            value = clean_text(item.get(key), 100_000)
            if len(value) > DESC_LIMIT:
                cut = value.rfind(". ", 0, DESC_LIMIT + 1)
                value = (value[:cut + 1] if cut > DESC_LIMIT * 0.4
                         else value[:DESC_LIMIT].rstrip() + " …")
        else:
            value = clean_text(item.get(key), 240)
        kept = sanitize_catalogue_text(value, key)
        if kept != value:
            touched += 1
        out[key] = kept
    for key in DTO_NUMBER_FIELDS:
        value = item.get(key)
        out[key] = value if isinstance(value, (int, float)) and value > 0 else None
    for key in DTO_MEASURE_FIELDS:
        out[key] = _measure(item.get(key))
    for key in DTO_LIST_FIELDS:
        raw = item.get(key) or []
        values = [str(v) for v in raw if v][:20] if isinstance(raw, (list, tuple)) else []
        if key == "images":
            out[key] = values                 # URLs, not customer text
            continue
        # a category or an option is a short structured value: one that is a
        # price statement is left out, and the others are unaffected
        picked = [v for v in values if not has_price_text(v)]
        if len(picked) != len(values):
            touched += 1
        out[key] = picked
    #: The admin rows carry the quantity flat (`_row` lifts it off the
    #: nested stock dict); a normalized product carries it under `stock`.
    #: Read whichever shape arrived, because a DTO that silently dropped the
    #: quantity of one of them is exactly the mismatch that lost the carton
    #: measures.
    stock = item.get("stock") if isinstance(item.get("stock"), dict) else {}
    available = item.get("available")
    if available is None:
        available = stock.get("available")
    try:
        out["available"] = int(available) if available is not None else None
    except (TypeError, ValueError):
        out["available"] = None
    known = item.get("availableKnown")
    if known is None:
        known = stock.get("known")
    #: absent is not "no": a record that carries no per-product verdict defers
    #: to the market-level answer, which is how a snapshot written before the
    #: per-product flag existed keeps printing its quantities.
    out["availableKnown"] = None if known is None else bool(known)
    if stats is not None and touched:
        stats["products"] = stats.get("products", 0) + 1
        stats["fields"] = stats.get("fields", 0) + touched
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

#: A normalized measure may already carry its own unit — the supplier sends
#: "9.5" on one product and "9.5 kg" on the next, and both reach us intact.
#: Appending the label's unit regardless printed "9.5 kg kg".
_HAS_UNIT = {
    "cartonWeight": re.compile(r"(?:kgs?|kilo(?:gram)?s?|g|gms?|grams?|lbs?|pounds?)"
                               r"\.?$", re.I),
    "cartonVolume": re.compile(r"(?:m³|m3|cbm|cu\.?\s?m|cubic\s*m(?:et(?:re|er)s?)?)"
                               r"\.?$", re.I),
}


def with_unit(key: str, value: str) -> str:
    """The printed measure: the label's unit appended unless the value brought
    one of its own."""
    suffix = _SUFFIX.get(key)
    if not suffix:
        return value
    pattern = _HAS_UNIT.get(key)
    if pattern and pattern.search(value.strip()):
        return value.strip()
    return value + suffix


def spec_rows(item: dict) -> list[tuple[str, str]]:
    """Label/value pairs, with anything empty or meaningless left out."""
    rows: list[tuple[str, str]] = []
    for key, label in SPEC_FIELDS:
        if key in DTO_MEASURE_FIELDS:
            # the same reading the DTO applies, so a bare "0" is a missing
            # measure here too rather than a printed "0 kg"
            value = _measure(item.get(key))
        else:
            value = clean_text(item.get(key), 120)
        if not value:
            continue
        rows.append((label, with_unit(key, value)))
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
PREPARED_QUALITY = 82         # the figure before quality modes; kept as the
                              # default for callers that name no mode

#: Two sizes, because a photograph is drawn in one of two sizes and no other.
#: The page is 503pt wide inside its margins and the gallery at most 366pt
#: tall, so a leading picture is never drawn larger than that; a supporting
#: one is never wider than 207pt. Past roughly three pixels to the point
#: nothing more is resolved on paper or on a screen, and the rest is weight.
#:
#:   standard  main 1000px -> 2.0 px/pt across a full-width tile, 2.7 down a
#:             square one; side 620px -> 3.0 px/pt
#:   high      main 1400px -> 2.8 / 3.8 px/pt; side 920px -> 4.4 px/pt
PHOTO_DIMS = {"standard": {"main": 1000, "side": 620},
              "high": {"main": MAX_IMAGE_DIM, "side": 920}}
#: JPEG quality and chroma subsampling per mode. 4:2:0 halves the colour
#: planes, which on a photograph is invisible and on the file is a third of
#: it; High keeps 4:2:2 for a document somebody may print.
PHOTO_QUALITY = {"standard": 72, "high": 86}
PHOTO_SUBSAMPLING = {"standard": 2, "high": 1}
QUALITY_MODES = ("standard", "high")
DEFAULT_QUALITY = "standard"
PHOTO_SLOTS = ("main", "side")


def quality_mode(value) -> str:
    """The mode to build in. Anything unrecognised is Standard, because an
    unreadable option must not quietly produce the heavier document."""
    text = str(value or "").strip().lower()
    return text if text in QUALITY_MODES else DEFAULT_QUALITY


def prepare_image(raw: bytes, *, slot: str = "main", quality: str | None = None):
    """Decode a downloaded photograph once, bound it, and hand back a small
    baseline JPEG.

    Three jobs now. It caps what a malicious or merely enormous file can cost
    — the dimensions are read from the header and refused before any pixels
    are decoded. It shrinks the picture to the size the page will actually
    draw it: `slot` says which of the two sizes a page has, a leading picture
    or a supporting one, and `quality` which of the two modes the admin asked
    for. And the JPEG it writes is the JPEG that goes into the document —
    `exports._image_box` hands it to reportlab untouched — so the encoder
    settings here are the file size there.

    Nothing of the original is carried over: no EXIF, no colour profile, no
    thumbnail. A supplier's camera metadata is not ours to put in a customer
    document, and a profile we are not reading is bytes on every page.
    """
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    mode = quality_mode(quality) if quality is not None else None
    dim = (PHOTO_DIMS[mode][slot if slot in PHOTO_SLOTS else "main"]
           if mode else MAX_IMAGE_DIM)
    jpeg_q = PHOTO_QUALITY[mode] if mode else PREPARED_QUALITY
    sub = PHOTO_SUBSAMPLING[mode] if mode else 0
    try:
        from PIL import Image

        probe = Image.open(io.BytesIO(raw))
        if probe.width * probe.height > MAX_IMAGE_PIXELS:
            return None                      # a bomb, or close enough to one
        im = probe
        im.load()
        if max(im.width, im.height) > dim:
            im.thumbnail((dim, dim))
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        out = io.BytesIO()
        #: `progressive` is off deliberately: a progressive JPEG is a coding
        #: `/DCTDecode` does not promise to read, so it would be the one
        #: picture that had to be re-encoded on its way into the document.
        im.save(out, "JPEG", quality=jpeg_q, optimize=True, progressive=False,
                subsampling=sub)
        im.close()
        return out.getvalue()
    except Exception:
        return None                          # one bad photo, not a failed run


# ---------------- the look of the document ----------------
#
# One A4 page per product, and the page is a composition rather than a form:
# an editorial gallery, then the product's identity, then the reading matter,
# then availability. The tokens below are the whole palette — orange is an
# accent and never a surface, the surfaces are warm neutrals, and nothing is
# boxed in a border where a tint or a hairline will do.

PAPER = (0.992, 0.988, 0.983)     # the page, a warm off-white
SOFT = (0.957, 0.949, 0.937)      # an image ground
FAINT = (0.976, 0.971, 0.963)     # an alternating row
TINT = (0.980, 0.906, 0.851)      # orange, very dilute

#: The gallery takes the room the rest of the page does not need, between
#: these two. A fixed height is what leaves a hole under a sparse product and
#: squeezes the specifications off a rich one.
GALLERY_MIN = 232.0
#: A long description may push the gallery a further 44pt down — enough to
#: hold three or four more lines, which is usually the difference between a
#: complete description and a truncated one. The pictures stay large; this
#: is a moderate yield, not a retreat to thumbnails.
GALLERY_FLOOR = 188.0
GALLERY_MAX = 366.0


def _tracked(c, x: float, y: float, text: str, font: str, size: float,
             tracking: float = 1.4) -> None:
    """A letterspaced small-caps label. The canvas has no character spacing,
    but a text object does."""
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setCharSpace(tracking)
    t.textOut(text)
    #: Tc is page state, not text-object state: without this every later
    #: string on the page comes out letterspaced, and a measured line then
    #: draws wider than it was wrapped for and runs into its neighbour
    t.setCharSpace(0)
    c.drawText(t)


def _tracked_width(text: str, font: str, size: float, tracking: float = 1.4) -> float:
    return stringWidth(text, font, size) + tracking * max(0, len(text) - 1)


def _eyebrow(c, x: float, y: float, text: str, colour=ORANGE, size: float = 7.2) -> None:
    c.setFillColorRGB(*colour)
    _tracked(c, x, y, text.upper()[:48], "Helvetica-Bold", size, 1.6)


def _panel(c, x: float, y: float, w: float, h: float, fill=SOFT,
           radius: float = 3.0, shadow: bool = False) -> None:
    """A surface. The optional shadow is three dilute passes rather than a
    border, because a hairline around every picture is what makes a document
    look like a form."""
    if shadow:
        c.saveState()
        for n, (dx, dy, a) in enumerate(((1.6, -1.6, 0.05), (3.0, -3.0, 0.035),
                                         (5.0, -5.0, 0.022))):
            c.setFillColorRGB(0.35, 0.33, 0.30)
            c.setFillAlpha(a)
            c.roundRect(x + dx, y + dy, w, h, radius, stroke=0, fill=1)
        c.restoreState()
    c.setFillColorRGB(*fill)
    c.roundRect(x, y, w, h, radius, stroke=0, fill=1)


def _photo_tile(c, reader, x: float, y: float, w: float, h: float,
                pad: float = 0.0, shadow: bool = False) -> None:
    """One picture on its own ground, fitted inside and never stretched."""
    _panel(c, x, y, w, h, SOFT, 3.0, shadow)
    if reader is None or reader[0] is None:
        c.setFont("Helvetica", 7.6)
        c.setFillColorRGB(*GREY)
        c.drawCentredString(x + w / 2, y + h / 2 - 3, "Photograph unavailable")
        return
    inset = pad if pad else max(10.0, min(w, h) * 0.085)
    _draw_contained(c, reader, x + inset, y + inset, w - 2 * inset, h - 2 * inset)


def usable_photos(photos: list[bytes], limit: int = 4) -> list:
    """The readers worth drawing, in source order, deduplicated.

    A supplier that lists one photograph twice should not spend half the
    gallery showing it twice, and showing every picture it has is how a
    gallery turns into a strip of thumbnails. Quality over completeness:
    `limit` is a ceiling, not a target.
    """
    out, seen = [], set()
    for blob in photos or []:
        if not blob:
            continue
        key = (len(blob), blob[:64], blob[-64:])
        if key in seen:
            continue
        seen.add(key)
        reader = _image_box(blob)
        if reader[0] is not None:
            out.append(reader)
        if len(out) >= limit:
            break
    return out


def _gallery(c, readers: list, x: float, top: float, w: float, h: float) -> None:
    """The editorial gallery, composed for how many pictures there really are.

    The first picture leads, but only by a little: a second view a customer
    cannot read is worse than no second view, so a supporting image is a
    third of the composition rather than a 52pt thumbnail.
    """
    gap = 10.0
    bottom = top - h
    n = len(readers)
    if n == 0:
        _panel(c, x, bottom, w, h, FAINT, 3.0)
        c.setFont("Helvetica", 8.4)
        c.setFillColorRGB(*GREY)
        c.drawCentredString(x + w / 2, bottom + h / 2 + 4, "Photograph unavailable")
        c.setFont("Helvetica", 7.2)
        c.drawCentredString(x + w / 2, bottom + h / 2 - 9,
                            "Images can be supplied on request")
        return
    if n == 1:
        _photo_tile(c, readers[0], x, bottom, w, h, shadow=True)
        return
    if n == 2:
        main_w = (w - gap) * 0.64
        _photo_tile(c, readers[0], x, bottom, main_w, h, shadow=True)
        _photo_tile(c, readers[1], x + main_w + gap, bottom, w - main_w - gap, h)
        return
    if n == 3:
        main_w = (w - gap) * 0.62
        side_w = w - main_w - gap
        side_h = (h - gap) / 2
        _photo_tile(c, readers[0], x, bottom, main_w, h, shadow=True)
        _photo_tile(c, readers[1], x + main_w + gap, bottom + side_h + gap, side_w, side_h)
        _photo_tile(c, readers[2], x + main_w + gap, bottom, side_w, side_h)
        return
    # four: a tall main and three stacked views. A full-width fourth strip was
    # the other option and it is wrong for this catalogue — a portrait product
    # in a 500 x 75 letterbox is a picture nobody can read.
    main_w = (w - gap) * 0.62
    side_w = w - main_w - gap
    side_h = (h - 2 * gap) / 3
    _photo_tile(c, readers[0], x, bottom, main_w, h, shadow=True)
    for i, reader in enumerate(readers[1:4]):
        _photo_tile(c, reader, x + main_w + gap, bottom + (2 - i) * (side_h + gap),
                    side_w, side_h)


def name_parts(name: str) -> tuple[str, str, str]:
    """(lead, headline, tail) from the supplier's own " - " segments.

    "NAPIER - MagCase Phone Cardholder - Navy Blue" is a range, a product and
    a colour written as one string, and setting all of it at one size is what
    makes a catalogue page look generated. This is presentation only: every
    character of the stored name is still printed, just at three weights.
    """
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", name or "") if p.strip()]
    if len(parts) < 2:
        return "", (name or "").strip(), ""
    if len(parts) == 2:
        if len(parts[1]) <= 28:               # "Mug - Navy Blue": name, variant
            return "", parts[0], parts[1]
        if len(parts[0]) <= 28:               # "NAPIER - a longer product name"
            return parts[0], parts[1], ""
        return "", (name or "").strip(), ""
    #: a long first segment is the product's own name, not a range, so it
    #: stays the headline and the short segments after it become the variant
    lead = parts[0] if len(parts[0]) <= 28 else ""
    rest = parts[1:] if lead else parts
    return lead, rest[0], " - ".join(rest[1:])


# ---------------- what a product actually says about itself ----------------
#
# The feature row is the one part of the page that is not simply a field
# printed in a nicer typeface, so it is the one part that could lie. The rule
# is therefore narrow: a badge appears only when the product's own text says
# so, in words specific enough to be unambiguous, and the label is built from
# the matched text rather than written here. Nothing is inferred from a
# category, a brand or a product's general kind — a "power bank" does not get
# a wireless-charging badge for being a power bank.

#: What a supplier may put between the thousands of a figure. A comma is the
#: common one; `clean_text` turns a non-breaking space into a plain one but
#: leaves a narrow no-break space alone, and "5 000" is simply how much of
#: the world writes it.
_GROUP_SEP = r"[,\u202f\u00a0 ]"

#: One figure, however it is punctuated: "5000", "5,000", "5 000", "22.5",
#: "1,000.5". Three branches, and the order and the guards are the whole of
#: the correction:
#:
#: 1. the **grouped** form first, so a scan arriving at the "5" of "5,000"
#:    takes the whole number instead of failing there and matching the "000"
#:    three characters later — precisely how `\d{3,6}` turned a 5,000 mAh
#:    power bank into a badge reading "0 mAh" on a customer document;
#: 2. **four digits or more**, which cannot be the tail of a group, so it
#:    needs no guard and "USB 3.0 and a 5000 mAh cell" still matches;
#: 3. a **short** run of one to three digits, which *could* be a group tail,
#:    so it is refused directly after a digit or after a digit and a
#:    separator. That is what stops a malformed "5,00" or "5 00" from being
#:    read as a number of its own — better no badge than a wrong one.
_FIGURE = (r"\d{1,3}(?:" + _GROUP_SEP + r"\d{3})+(?:\.\d+)?"
           r"|\d{4,}(?:\.\d+)?"
           r"|(?<!\d)(?<!\d" + _GROUP_SEP + r")\d{1,3}(?:\.\d+)?")

#: Where a figure may begin. `\b` keeps it out of the middle of a part
#: number ("ITGL5000"), and the lookbehind keeps the scan from starting
#: *inside* a figure: after a comma or a decimal point `\b` holds, so without
#: it the tail of a malformed "5,00" would still be read as a number of its
#: own. A digit needs no mention — `\b` already refuses after one.
_FIGURE_IN = r"\b(?<![.,])(" + _FIGURE + r")(?![\d,])"


def _figure_before(unit: str, lead: str = "") -> str:
    """A pattern catching one figure immediately before `unit`.

    Every numeric rule is built from this, so a separator a supplier happens
    to use cannot make one badge right and another wrong. `lead` is for a
    rule whose figure follows a word rather than whitespace ("PD22.5W"),
    where a word boundary would refuse the digit.
    """
    if lead:
        return lead + "(" + _FIGURE + r")(?![\d,])\s*" + unit
    return _FIGURE_IN + r"\s*" + unit


def _fig(m, group: int = 1) -> str:
    """A captured figure as the page should print it: grouped in thousands,
    the fraction as the supplier wrote it, and no trailing ".0".

    One normalization for every rule. "5000" and "5,000" and "5 000" are the
    same number and must produce the same badge, because a reader comparing
    two products should not be reading two conventions.
    """
    raw = re.sub(_GROUP_SEP, "", m.group(group) or "")
    whole, _, frac = raw.partition(".")
    frac = frac.rstrip("0")
    if not whole.isdigit():
        return ""
    return f"{int(whole):,}.{frac}" if frac else f"{int(whole):,}"


#: (pattern, icon, label, family). The pattern is searched in the product's
#: own sanitized name, description and specification values — nowhere else.
#: A family fires once: "PD 22.5W" and "22.5W charging" are the same fact
#: twice, and a row that says it twice has a third thing it is not saying.
#: Order is priority order, most product-defining first.
FEATURE_RULES: tuple[tuple[str, str, object, str], ...] = (
    (r"\bmagsafe\b", "magnet", "MagSafe compatible", "magnet"),
    (_figure_before(r"w\b") + r"[^.]{0,24}\bwireless\b"
     r"|\bwireless\b[^.]{0,24}?" + _figure_before(r"w\b"),
     "wireless", lambda m: f"{_fig(m) if m.group(1) else _fig(m, 2)}W wireless",
     "wireless"),
    (r"\bwireless charg", "wireless", "Wireless charging", "wireless"),
    (_figure_before(r"w\b", lead=r"\bpd\s*"), "bolt", lambda m: f"PD {_fig(m)}W",
     "charge"),
    (_figure_before(r"w\b") + r"\s*(?:fast\s*)?charg", "bolt",
     lambda m: f"{_fig(m)}W charging", "charge"),
    (r"\bfast charg", "bolt", "Fast charging", "charge"),
    (_figure_before(r"mah\b"), "battery", lambda m: f"{_fig(m)} mAh",
     "battery"),
    (_figure_before(r"ml\b"), "droplet", lambda m: f"{_fig(m)} ml", "volume"),
    (r"\bdouble[- ]?wall(?:ed)?\b", "layers", "Double-walled", "build"),
    (r"\bstainless steel\b", "layers", "Stainless steel", "build"),
    (_figure_before(r"(?:hours|hrs?)\b"), "clock", lambda m: f"{_fig(m)} hours",
     "time"),
    (r"\bip(\d{2})\b", "droplet", lambda m: f"IP{m.group(1)} rated", "water"),
    (r"\b(?:water[- ]?proof|waterproof)\b", "droplet", "Waterproof", "water"),
    (r"\bleak[- ]?proof\b", "droplet", "Leak-proof", "water"),
    (r"\bdishwasher[- ]safe\b", "droplet", "Dishwasher safe", "water"),
    (r"\b(?:usb[- ]?c|type[- ]?c)\b", "plug", "USB-C", "port"),
    (r"\bbluetooth\b", "wireless", "Bluetooth", "radio"),
    (r"\bsolar\b", "sun", "Solar", "power"),
    (r"\bbpa[- ]?free\b", "leaf", "BPA free", "eco"),
    (r"\b(?:recycled|rpet|bamboo|organic cotton)\b", "leaf", "Sustainable", "eco"),
    (r"\b(?:laser engrav|deboss|emboss|screen print|pad print|embroider)",
     "brand", "Brandable", "brand"),
    (r"\bgift (?:box|packaging|set)\b", "box", "Gift boxed", "pack"),
)

#: Three is a row, five is a toolbar. Four keeps the page calm.
MAX_FEATURES = 4


#: "Dishwasher safe parts are not applicable" is a supplier saying the
#: opposite of what the words alone suggest. A badge is a claim, so a claim
#: with a negation in front of it in the same sentence is not made.
_NEGATED = re.compile(r"\b(?:not|no|never|without|excluding|except|unsuitable)\b",
                      re.I)


def _affirmed(hay: str, pattern: str):
    """The first match of `pattern` that nothing in its sentence negates."""
    for m in re.finditer(pattern, hay, re.I):
        lead = hay[max(0, m.start() - 70):m.start()]
        tail = hay[m.end():m.end() + 70]
        for stop in (".", "!", "?", "\n", ";"):
            lead = lead.rsplit(stop, 1)[-1]
            tail = tail.split(stop, 1)[0]
        #: both directions, because "dishwasher safe parts are not
        #: applicable" puts the negation after the words it cancels
        if not _NEGATED.search(lead) and not _NEGATED.search(tail):
            return m
    return None


def product_features(dto: dict) -> list[tuple[str, str]]:
    """[(icon, label)] the product's own words support, at most MAX_FEATURES.

    Reads the sanitized DTO only, so a price statement cannot arrive here
    either. Returns [] when nothing is certain — a row of invented badges on
    a customer document would be worse than no row.
    """
    parts = [dto.get("name") or "", dto.get("description") or ""]
    parts += [str(v) for k, v in dto.items()
              if k in ("material", "size", "capacity") and v]
    hay = " ".join(parts).lower()
    out: list[tuple[str, str]] = []
    families: set[str] = set()
    for pattern, icon, label, family in FEATURE_RULES:
        if family in families:
            continue
        m = _affirmed(hay, pattern)
        if not m:
            continue
        text = label(m) if callable(label) else label
        if not text or len(text) > 22:
            continue
        families.add(family)
        out.append((icon, text))
        if len(out) >= MAX_FEATURES:
            break
    return out


# ---------------- the icons, drawn rather than downloaded ----------------

def _icon(c, name: str, cx: float, cy: float, r: float) -> None:
    """A simple line mark in a circle of radius `r` centred on (cx, cy).

    Drawn with reportlab primitives: no icon font, no third-party file, and
    nothing to go missing from a deploy.
    """
    c.setLineWidth(max(0.9, r * 0.11))
    c.setLineCap(1)
    c.setLineJoin(1)
    c.setStrokeColorRGB(*INK)
    u = r * 0.52                              # the mark's half-extent
    if name == "battery":
        c.rect(cx - u, cy - u * 0.62, u * 1.7, u * 1.24, stroke=1, fill=0)
        c.setFillColorRGB(*ORANGE)
        c.rect(cx - u + 1.6, cy - u * 0.62 + 1.6, u * 0.8, u * 1.24 - 3.2,
               stroke=0, fill=1)
        c.setFillColorRGB(*INK)
        c.rect(cx + u * 0.7, cy - u * 0.22, u * 0.22, u * 0.44, stroke=0, fill=1)
    elif name == "bolt":
        p = c.beginPath()
        p.moveTo(cx + u * 0.26, cy + u)
        p.lineTo(cx - u * 0.5, cy + u * 0.02)
        p.lineTo(cx + u * 0.06, cy + u * 0.02)
        p.lineTo(cx - u * 0.2, cy - u)
        p.lineTo(cx + u * 0.56, cy - u * 0.06)
        p.lineTo(cx, cy - u * 0.06)
        p.close()
        c.setFillColorRGB(*ORANGE)
        c.drawPath(p, stroke=0, fill=1)
    elif name == "wireless":
        for k, scale in enumerate((0.42, 0.72, 1.0)):
            c.setStrokeColorRGB(*(ORANGE if k == 0 else INK))
            c.arc(cx - u * scale, cy - u * scale - u * 0.3,
                  cx + u * scale, cy + u * scale - u * 0.3, 35, 110)
        c.setFillColorRGB(*INK)
        c.circle(cx, cy - u * 0.74, max(0.8, u * 0.12), stroke=0, fill=1)
    elif name == "magnet":
        c.arc(cx - u, cy - u * 0.5, cx + u, cy + u * 1.5, 0, 180)
        c.line(cx - u, cy + u * 0.5, cx - u, cy - u)
        c.line(cx + u, cy + u * 0.5, cx + u, cy - u)
        c.setStrokeColorRGB(*ORANGE)
        c.line(cx - u, cy - u, cx - u * 0.34, cy - u)
        c.line(cx + u, cy - u, cx + u * 0.34, cy - u)
    elif name == "plug":
        c.rect(cx - u * 0.6, cy - u, u * 1.2, u * 1.4, stroke=1, fill=0)
        c.line(cx - u * 0.26, cy + u * 0.4, cx - u * 0.26, cy + u)
        c.line(cx + u * 0.26, cy + u * 0.4, cx + u * 0.26, cy + u)
    elif name == "droplet":
        p = c.beginPath()
        p.moveTo(cx, cy + u)
        p.curveTo(cx + u * 0.95, cy, cx + u * 0.7, cy - u, cx, cy - u)
        p.curveTo(cx - u * 0.7, cy - u, cx - u * 0.95, cy, cx, cy + u)
        c.drawPath(p, stroke=1, fill=0)
    elif name == "leaf":
        p = c.beginPath()
        p.moveTo(cx - u * 0.8, cy - u * 0.8)
        p.curveTo(cx - u, cy + u * 0.6, cx + u * 0.4, cy + u, cx + u * 0.85, cy + u * 0.85)
        p.curveTo(cx + u, cy - u * 0.4, cx + u * 0.1, cy - u, cx - u * 0.8, cy - u * 0.8)
        c.drawPath(p, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        c.line(cx - u * 0.5, cy - u * 0.5, cx + u * 0.6, cy + u * 0.6)
    elif name == "layers":
        for k, dy in enumerate((u * 0.62, 0.0, -u * 0.62)):
            c.setStrokeColorRGB(*(ORANGE if k == 0 else INK))
            p = c.beginPath()
            p.moveTo(cx - u, cy + dy)
            p.lineTo(cx, cy + dy + u * 0.42)
            p.lineTo(cx + u, cy + dy)
            p.lineTo(cx, cy + dy - u * 0.42)
            p.close()
            c.drawPath(p, stroke=1, fill=0)
    elif name == "clock":
        c.circle(cx, cy, u, stroke=1, fill=0)
        c.line(cx, cy, cx, cy + u * 0.55)
        c.setStrokeColorRGB(*ORANGE)
        c.line(cx, cy, cx + u * 0.45, cy)
    elif name == "sun":
        c.circle(cx, cy, u * 0.46, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        for k in range(8):
            a = k * 3.14159 / 4
            import math

            c.line(cx + math.cos(a) * u * 0.72, cy + math.sin(a) * u * 0.72,
                   cx + math.cos(a) * u, cy + math.sin(a) * u)
    elif name == "box":
        c.rect(cx - u, cy - u * 0.85, u * 2, u * 1.7, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        c.line(cx, cy - u * 0.85, cx, cy + u * 0.85)
        c.line(cx - u, cy + u * 0.2, cx + u, cy + u * 0.2)
    elif name == "calendar":
        c.rect(cx - u, cy - u * 0.9, u * 2, u * 1.7, stroke=1, fill=0)
        c.line(cx - u, cy + u * 0.34, cx + u, cy + u * 0.34)
        c.setStrokeColorRGB(*ORANGE)
        c.line(cx - u * 0.45, cy + u * 0.8, cx - u * 0.45, cy + u * 1.15)
        c.line(cx + u * 0.45, cy + u * 0.8, cx + u * 0.45, cy + u * 1.15)
    elif name == "check":
        c.circle(cx, cy, u * 0.95, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(max(1.1, r * 0.14))
        p = c.beginPath()
        p.moveTo(cx - u * 0.42, cy + u * 0.04)
        p.lineTo(cx - u * 0.08, cy - u * 0.36)
        p.lineTo(cx + u * 0.46, cy + u * 0.38)
        c.drawPath(p, stroke=1, fill=0)
    elif name == "cross":
        #: out of stock. A tick beside "OUT OF STOCK" is the same
        #: contradiction as the words, so the mark changes with them.
        c.circle(cx, cy, u * 0.95, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(max(1.1, r * 0.14))
        c.line(cx - u * 0.36, cy - u * 0.36, cx + u * 0.36, cy + u * 0.36)
        c.line(cx - u * 0.36, cy + u * 0.36, cx + u * 0.36, cy - u * 0.36)
    elif name == "dash":
        #: nothing is known. A bar rather than a cross, because the supplier
        #: did not say empty, it said nothing.
        c.circle(cx, cy, u * 0.95, stroke=1, fill=0)
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(max(1.1, r * 0.14))
        c.line(cx - u * 0.4, cy, cx + u * 0.4, cy)
    elif name == "brand":
        c.circle(cx, cy, u * 0.92, stroke=1, fill=0)
        c.setFillColorRGB(*ORANGE)
        c.circle(cx, cy, u * 0.34, stroke=0, fill=1)
    else:                                     # a mark rather than nothing
        c.circle(cx, cy, u * 0.8, stroke=1, fill=0)
    c.setStrokeColorRGB(*INK)


FEATURE_ROW_H = 54.0


def _feature_row(c, features: list[tuple[str, str]], x: float, top: float,
                 w: float) -> None:
    """A quiet row of what the product does, under its name.

    Not a table and not a badge wall: a hairline above, evenly spaced marks,
    a short label under each. Four at most, and none of them invented.
    """
    if not features:
        return
    c.setFillColorRGB(*LINE)
    c.rect(x, top, w, 0.6, stroke=0, fill=1)
    slot = w / len(features)
    for i, (icon, label) in enumerate(features):
        cx = x + slot * i + slot / 2
        _icon(c, icon, cx, top - 20, 11.0)
        c.setFont("Helvetica-Bold", 7.4)
        c.setFillColorRGB(0.28, 0.30, 0.34)
        c.drawCentredString(cx, top - 44, label[:24])
    c.setFillColorRGB(*LINE)
    c.rect(x, top - FEATURE_ROW_H, w, 0.6, stroke=0, fill=1)


# ---------------- page furniture ----------------

def _logo(c, x: float, y: float, height: float = 26.0) -> float:
    #: `logo_reader` hands back the wordmark already resized to the size a
    #: page draws it and cached, so a five-hundred page catalogue carries one
    #: small object rather than 1,660 pixels of artwork per document.
    logo, lw, lh = logo_reader(height)
    if logo is not None and lh:
        try:
            c.drawImage(logo, x, y - height, width=lw * (height / lh), height=height,
                        mask="auto")
            return height
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 15)
    c.setFillColorRGB(*ORANGE)
    c.drawString(x, y - 16, "ELITE MARCOM")
    return 20.0


def _page_ground(c) -> None:
    c.setFillColorRGB(*PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)


def _header(c, market: str) -> float:
    """Light and editorial: the mark, a quiet label, one hairline with a short
    orange lead. Returns the y the page content starts at."""
    top = PAGE_H - 44
    _logo(c, M, top, 19)
    c.setFillColorRGB(*GREY)
    _tracked(c, PAGE_W - M - _tracked_width("CORPORATE GIFTS CATALOGUE",
                                            "Helvetica", 6.8, 1.5),
             top - 12, "CORPORATE GIFTS CATALOGUE", "Helvetica", 6.8, 1.5)
    label = MARKET_LABEL.get(market, (market or "").upper())
    if label:
        c.setFont("Helvetica-Bold", 7.6)
        c.setFillColorRGB(*INK)
        c.drawRightString(PAGE_W - M, top - 24, label)
    rule_y = top - 36
    c.setFillColorRGB(*LINE)
    c.rect(M, rule_y, PAGE_W - 2 * M, 0.6, stroke=0, fill=1)
    c.setFillColorRGB(*ORANGE)
    c.rect(M, rule_y, 44, 1.6, stroke=0, fill=1)
    return rule_y - 20


def _footer(c, page_no: int) -> None:
    c.setFillColorRGB(*LINE)
    c.rect(M, 46, PAGE_W - 2 * M, 0.6, stroke=0, fill=1)
    c.setFont("Helvetica", 7.2)
    c.setFillColorRGB(*GREY)
    c.drawString(M, 33, SITE)
    c.drawCentredString(PAGE_W / 2, 33, "Elite Marcom  ·  Corporate Gifts")
    c.setFont("Helvetica-Bold", 7.2)
    c.setFillColorRGB(*INK)
    c.drawRightString(PAGE_W - M, 33, f"Page {page_no}")


# ---------------- the pages ----------------

def _cover(c, *, market: str, count: int, stock_at, generated: float) -> None:
    """The approved cover, drawn by `server/cover.py`.

    The page that used to be composed here — a hero made from the catalogue's
    own first few products, a headline split out of the admin's title — is
    replaced by the approved Elite Marcom Corporate Gifts master. It is the
    same cover on a one-product catalogue and a five-hundred-product one,
    which is the point: a client recognises it before reading it. Only the
    market, the year, the count and the two dates change.
    """
    from . import cover as cover_master

    label = MARKET_LABEL.get(market, market.upper())
    cover_master.draw(
        c, market=label, country=market.upper(),
        year=time.strftime("%Y", time.localtime(generated)),
        count_text=f"{count:,} product{'' if count == 1 else 's'}",
        prepared_text=time.strftime("%d %b %Y", time.localtime(generated)),
        stock_text=(time.strftime("%d %b %Y · %H:%M",
                                  time.localtime(float(stock_at)))
                    if stock_at else "not available"))
    c.showPage()


def _contents(c, entries: list[tuple[str, str, int]], start_page: int) -> int:
    """Code / name / page, as many pages as it takes. Returns pages used."""
    used = 0
    i = 0
    while i < len(entries):
        used += 1
        _page_ground(c)
        y = _header(c, "") + 6
        c.setFont("Helvetica-Bold", 20)
        c.setFillColorRGB(*INK)
        c.drawString(M, y - 20, "Contents")
        y -= 44
        c.setFillColorRGB(*GREY)
        _tracked(c, M, y, "ITEM CODE", "Helvetica", 6.8, 1.4)
        _tracked(c, M + 116, y, "PRODUCT", "Helvetica", 6.8, 1.4)
        c.drawRightString(PAGE_W - M, y, "PAGE")
        y -= 8
        c.setFillColorRGB(*LINE)
        c.rect(M, y, PAGE_W - 2 * M, 0.6, stroke=0, fill=1)
        y -= 18
        band = 0
        while i < len(entries) and y > 76:
            code, name, page_no = entries[i]
            if band % 2 == 0:
                c.setFillColorRGB(*FAINT)
                c.rect(M - 6, y - 4, PAGE_W - 2 * M + 12, 15, stroke=0, fill=1)
            c.setFont("Helvetica", 8.4)
            c.setFillColorRGB(*GREY)
            c.drawString(M, y, code[:18])
            c.setFont("Helvetica", 8.8)
            c.setFillColorRGB(*INK)
            name_w = PAGE_W - M - 46 - (M + 116)
            c.drawString(M + 116, y, _wrap(name, "Helvetica", 8.8, name_w)[0])
            c.setFont("Helvetica-Bold", 8.4)
            c.drawRightString(PAGE_W - M, y, str(page_no))
            y -= 15
            i += 1
            band += 1
        _footer(c, start_page + used - 1)
        c.showPage()
    return used


def _identity_plan(item: dict, w: float, show_code: bool) -> dict:
    """What the identity block will be, and how tall. Measured and drawn by
    the same rules, so the page can be composed before anything is on it."""
    cats = [clean_text(v, 40) for v in (item.get("categories") or [])]
    cats = [v for v in cats if v]
    lead, headline, tail = name_parts(clean_text(item.get("name"), 220) or "Product")
    size = 21.0
    lines = _wrap(headline, "Helvetica-Bold", size, w)
    if len(lines) > 2:
        size = 16.5
        lines = _wrap(headline, "Helvetica-Bold", size, w)
    lines = lines[:3]
    bits = []
    if tail:
        bits.append(tail)
    if show_code:
        code = clean_text(item.get("code"), 60)
        if code:
            bits.append(code)
    height = (16 if cats else 0) + (17 if lead else 0) + size * 0.96 * len(lines) \
        + 15 + (14 if bits else 0)
    return {"category": cats[0] if cats else "", "lead": lead, "lines": lines,
            "size": size, "bits": bits, "height": height}


def _identity(c, plan: dict, x: float, top: float) -> float:
    """Category, then the name in its own hierarchy, then the variant and the
    code. Returns the y it finished at."""
    y = top
    if plan["category"]:
        _eyebrow(c, x, y, plan["category"], ORANGE, 7.2)
        y -= 16
    if plan["lead"]:
        c.setFillColorRGB(*GREY)
        _tracked(c, x, y, plan["lead"].upper()[:40], "Helvetica-Bold", 9.0, 1.8)
        y -= 17
    c.setFont("Helvetica-Bold", plan["size"])
    c.setFillColorRGB(*INK)
    for line in plan["lines"]:
        y -= plan["size"] * 0.96
        c.drawString(x, y, line)
    y -= 15
    if plan["bits"]:
        c.setFont("Helvetica", 9.6)
        c.setFillColorRGB(*GREY)
        c.drawString(x, y, "   ·   ".join(plan["bits"])[:90])
        y -= 14
    return y


#: Enough for a long supplier description; past this a page would be a wall
#: of text whatever the gallery gave up.
DESC_MAX_LINES = 22
#: How much description the DTO carries. Clipped at a sentence, not a
#: character count.
DESC_LIMIT = 1200


def _description_height(body: str, w: float) -> float:
    """What the description wants. It asks for all of itself, so the composer
    can decide whether the gallery can afford it — a fixed line cap here
    discarded text while vertical space was still recoverable."""
    if not body:
        return 0.0
    lines = min(len(_wrap(body, "Helvetica", 9.0, w)), DESC_MAX_LINES)
    return 26 + lines * 12.6


def _specs_height(rows: list[tuple[str, str]], w: float) -> float:
    if not rows:
        return 0.0
    label_w = max(78.0, min(118.0, w * 0.42))
    #: 24 for the heading, then exactly what the loop below will consume —
    #: the two have to agree or the composer reserves room for twelve rows
    #: and the renderer prints eleven
    total = 24.0
    for _, value in rows:
        total += 13.0 if len(_wrap(value, "Helvetica-Bold", 8.5,
                                   w - label_w - 8)) == 1 else 23.0
    return total


def trim_to_sentence(body: str, w: float, room: int) -> str:
    """As much of the description as `room` lines hold, ending on a full stop.

    "Includes extra magnetic ring for compatibility with …" is a supplier
    sentence cut in half, and it reads as a fault in the document rather than
    as an edit. Falling back to the last **complete** sentence that fits
    costs a line or two and reads as if it were written that way. Only when
    not even one sentence fits does an ellipsis appear, because something has
    to give.
    """
    if room <= 0:
        return ""
    lines = _wrap(body, "Helvetica", 9.0, w)
    if len(lines) <= room:
        return body
    kept = " ".join(lines[:room])
    cut = max(kept.rfind(". "), kept.rfind("! "), kept.rfind("? "),
              kept.rfind(".\n"))
    if kept.endswith("."):
        cut = max(cut, len(kept) - 1)
    if cut > len(kept) * 0.35:                # a sentence worth keeping
        return body[:cut + 1].rstrip()
    return kept.rstrip(" ,;:")[:max(0, len(kept) - 2)].rstrip() + " …"


def _description(c, body: str, x: float, top: float, w: float, max_h: float) -> float:
    """Set for reading: a narrow measure, generous leading, and only as much
    as the page can give it."""
    if not body or max_h < 34:
        return top
    _eyebrow(c, x, top - 8, "Description", ORANGE, 7.0)
    y = top - 26
    room = int(max(0, (max_h - 26) // 12.6))
    lines = _wrap(trim_to_sentence(body, w, room), "Helvetica", 9.0, w)[:room]
    c.setFont("Helvetica", 9.0)
    c.setFillColorRGB(0.21, 0.23, 0.26)
    for line in lines[:room]:
        c.drawString(x, y - 9, line)
        y -= 12.6
    return y


def _specs(c, rows: list[tuple[str, str]], x: float, top: float, w: float,
           max_h: float) -> float:
    """Label and value on an alternating rhythm — no borders, no rules between
    every pair. A long value wraps to a second line rather than being cut."""
    if not rows or max_h < 34:
        return top
    _eyebrow(c, x, top - 8, "Specifications", ORANGE, 7.0)
    y = top - 24
    label_w = max(78.0, min(118.0, w * 0.42))
    value_w = w - label_w - 8
    band = 0
    for label, value in rows:
        wrapped = _wrap(value, "Helvetica-Bold", 8.5, value_w)
        vlines = wrapped[:2]
        if len(wrapped) > 2:
            # a list of six categories ends on an ellipsis, not a dangling comma
            vlines[1] = vlines[1].rstrip(" ,;") + " …"
        row_h = 13.0 if len(vlines) == 1 else 23.0
        #: the half point is float slack, not spare room: the composer
        #: reserves exactly this many points and a rounding error of 1e-13
        #: would otherwise drop the last specification off the page
        if (top - y) + row_h > max_h + 0.5:
            break
        if band % 2 == 0:
            c.setFillColorRGB(*FAINT)
            c.rect(x - 5, y - row_h + 3.5, w + 10, row_h, stroke=0, fill=1)
        c.setFont("Helvetica", 8.3)
        c.setFillColorRGB(*GREY)
        c.drawString(x, y - 6, label[:28])
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColorRGB(*INK)
        vy = y - 6
        for vline in vlines:
            c.drawRightString(x + w, vy, vline)
            vy -= 10
        y -= row_h
        band += 1
    return y


#: Which mark stands beside each of the three labels.
_STOCK_ICON = {"in": "check", "out": "cross", "unknown": "dash"}


def _availability(c, item: dict, *, stock_at, stock_is_known: bool,
                  show_date: bool) -> None:
    """Pinned above the footer so every page in the document agrees, and read
    as part of the catalogue rather than stamped on it.

    The label is not a heading, it is the **verdict**, so it is read from the
    same figures as the number beneath it. The band used to print a fixed
    "AVAILABLE NOW" over whatever `stock_sentence` returned, which on a
    genuinely empty product (ITWC 1302, Maglite 5K - Navy Blue) said
    "AVAILABLE NOW / 0 units" — two statements, one page, contradicting each
    other. There are three states and each one gets its own label, its own
    mark and its own treatment of the quantity.
    """
    band_h = 74.0
    by = 64.0
    state = stock_state(item.get("available"), stock_is_known)
    _panel(c, M, by, PAGE_W - 2 * M, band_h, FAINT, 3.0)
    c.setFillColorRGB(*ORANGE)
    c.rect(M, by, 2.6, band_h, stroke=0, fill=1)
    _icon(c, _STOCK_ICON[state], M + 26, by + band_h - 23, 8.5)
    c.setFillColorRGB(*GREY)
    _tracked(c, M + 40, by + band_h - 20, STOCK_LABEL[state],
             "Helvetica-Bold", 7.0, 1.6)
    if state == "unknown":
        #: no number at all — a quantity nobody reported is not a nought,
        #: and printing one is the same mistake the other way round
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(*INK)
        c.drawString(M + 26, by + 20, STOCK_UNKNOWN_FIGURE)
    else:
        figure, _, unit = stock_sentence(item.get("available"),
                                         stock_is_known)[0].partition(" ")
        c.setFont("Helvetica-Bold", 25)
        c.setFillColorRGB(*INK)
        c.drawString(M + 26, by + 18, figure)
        c.setFont("Helvetica", 9.4)
        c.setFillColorRGB(*GREY)
        c.drawString(M + 32 + stringWidth(figure, "Helvetica-Bold", 25), by + 18, unit)
    if show_date:
        c.setFillColorRGB(*GREY)
        _tracked(c, PAGE_W - M - 18 - _tracked_width("STOCK UPDATED", "Helvetica",
                                                     6.6, 1.4),
                 by + band_h - 20, "STOCK UPDATED", "Helvetica", 6.6, 1.4)
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColorRGB(*INK)
        c.drawRightString(PAGE_W - M - 18, by + 22,
                          when(stock_at) or "synchronisation date unavailable")


def _product_page(c, item: dict, photos: list[bytes], *, page_no: int, options: dict,
                  stock_at, stock_is_known: bool) -> None:
    """One A4 portrait page, composed as a whole.

    Everything is still clipped to fit — a product never spills onto a second
    page, because the catalogue's contract is one page each and a reader
    counting pages must be able to trust it. What changed is how the room is
    divided: the gallery grows when a product has little to say and gives way
    when it has a lot, so a short record does not leave a hole and a long one
    does not crowd the footer.
    """
    _page_ground(c)
    top = _header(c, options.get("market", ""))
    content_w = PAGE_W - 2 * M

    readers = usable_photos(photos, 4)
    #: already clean, already sanitized, already clipped at a sentence
    body = item.get("description") or "" if options.get("description", True) else ""
    rows = spec_rows(item) if options.get("specs", True) else []

    # ---- compose the page before drawing any of it ----
    gap = 22.0
    two_up = bool(body and rows)
    if two_up:
        left_w = (content_w - gap) * 0.56
        right_w = content_w - gap - left_w
    elif body:
        left_w = right_w = min(content_w, 430.0)
    else:
        left_w = right_w = min(content_w, 330.0)
    plan = _identity_plan(item, content_w, options.get("code", True))
    floor = (64.0 + 74.0 + 22.0) if options.get("stock", True) else 70.0
    need = max(_description_height(body, left_w) if body else 0.0,
               _specs_height(rows, right_w) if rows else 0.0)
    #: the gallery is what is left over, inside its own bounds — so a sparse
    #: product fills the page with its photographs instead of leaving a hole,
    #: and a product with twelve specifications still prints all twelve
    #: what the product's own words support, under its name — and only if
    #: the page can seat it without taking the pictures below their floor
    features = product_features(item) if options.get("specs", True) else []
    feat_h = FEATURE_ROW_H + 14 if features else 0.0
    spare = top - (plan["height"] + 12 + feat_h + need + floor) - 26
    #: a short record keeps the gallery generous; a long one is allowed to
    #: take a further 44pt from it rather than lose its last sentences
    lowest = GALLERY_FLOOR if (need > 210 or features) else GALLERY_MIN
    if features and spare < GALLERY_FLOOR:
        features, feat_h = [], 0.0           # content first, badges second
        spare = top - (plan["height"] + 12 + need + floor) - 26
    gallery_h = max(lowest, min(GALLERY_MAX, spare))
    if not readers:
        #: with no photograph there is nothing to grow: a half-page of empty
        #: grey is worse than a modest note and honest white space
        gallery_h = min(gallery_h, 210.0)

    _gallery(c, readers, M, top, content_w, gallery_h)
    y = top - gallery_h - 26
    y = _identity(c, plan, M, y)
    y -= 12
    if features:
        _feature_row(c, features, M, y, content_w)
        y -= feat_h

    band_h = max(0.0, y - floor)
    if two_up:
        _description(c, body, M, y, left_w, band_h)
        _specs(c, rows, M + left_w + gap, y, right_w, band_h)
    elif body:
        _description(c, body, M, y, left_w, band_h)
    elif rows:
        _specs(c, rows, M, y, right_w, band_h)

    if options.get("stock", True):
        _availability(c, item, stock_at=stock_at, stock_is_known=stock_is_known,
                      show_date=options.get("stockDate", True))
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
        # the title is the admin's, not the supplier's, but it is customer
        # text on a customer document and reaches the PDF's own metadata, so
        # it goes through the same boundary as everything else
        self.title = sanitize_catalogue_text(
            clean_text(title, 120), "name") or "Product Catalogue"
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
        self._covered = False

    def cover(self, photos: list[bytes] | None = None) -> None:
        """Draw the approved opening page.

        `photos` is accepted and ignored. The cover used to be built from the
        catalogue's own first few products; the approved master is a fixed
        Elite Marcom Corporate Gifts composition, so a caller that still
        hands pictures over is not wrong, it simply no longer changes the
        page. Nothing fetches imagery for the cover any more.
        """
        if self._covered:
            return
        self._covered = True
        _cover(self.c, market=self.market, count=self.count,
               stock_at=self.stock_at, generated=time.time())

    def contents(self, entries: list[tuple[str, str]]) -> None:
        """(code, name) in order; page numbers are worked out from position."""
        self.cover()
        if not self.opts.get("contents"):
            return
        rows = [(code, name, self.first_product_page + n)
                for n, (code, name) in enumerate(entries)]
        _contents(self.c, rows, 2)

    def page(self, dto: dict, photos: list[bytes]) -> None:
        self.cover()                          # a document always opens on one
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
    doc.cover()                               # the approved, fixed master
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
            #: a share build runs through this same registry, and puts the
            #: link it made here — the panel polls one endpoint either way
            "share": None,
            # how much supplier price text had to be removed — counts only
            "sanitizedProducts": 0, "sanitizedFields": 0,
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
    out = {"state": job["state"], "done": job["done"], "total": job["total"],
           "error": job["error"], "filename": job["filename"],
           # ordinary supplier-data cleanup, reported rather than hidden
           "sanitizedProducts": job.get("sanitizedProducts", 0),
           "sanitizedFields": job.get("sanitizedFields", 0),
           "ready": job["state"] == "done" and bool(job["pdf"])}
    share = job.get("share")
    if share:
        #: the one time the token is ever handed over. It is not stored
        #: anywhere in a readable form and is not in the audit entry, so an
        #: admin who closes this dialog without copying the link has to make
        #: another share — which is the right trade for a link that is itself
        #: the credential.
        out["share"] = share
        out["ready"] = job["state"] == "done"
    return out


async def _photos_for(market: str, dto: dict, cache: dict,
                      quality: str = DEFAULT_QUALITY) -> list[bytes]:
    """The pictures for one product, already shrunk.

    Pictures come from the supplier's public image host. That is a file read
    over HTTP, not one of the three primary endpoints, so it is charged to
    nothing — the same line `server/supplier_video.py` draws. One unreachable
    photograph costs that product its picture and nothing else.
    """
    from . import jasani

    out: list[bytes] = []
    for n, url in enumerate((dto.get("images") or [])[:IMAGES_PER_ITEM]):
        #: The slot is part of the key, not just of the encoding. The first
        #: picture leads the gallery and is drawn up to the full width of the
        #: page; the others are never wider than 207pt and are prepared
        #: smaller. One URL in both slots is prepared twice and embedded
        #: twice, which is honest — the alternative is a leading photograph
        #: that is soft because some other product used it as a side view.
        slot = "main" if n == 0 else "side"
        key = (url, slot)
        if key in cache:
            if cache[key] is not None:
                out.append(cache[key])
            continue
        try:
            raw = await jasani._fetch_image_bytes(url)
        except Exception:
            raw = None
        small = prepare_image(raw, slot=slot, quality=quality) if raw else None
        del raw                               # the original goes immediately
        # Only the main picture is worth remembering between products: a
        # gallery shot is rarely shared, and an unbounded cache is the very
        # thing this rewrite exists to avoid.
        if len(cache) < PHOTO_CACHE_MAX:
            cache[key] = small
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
    quality = quality_mode(options.get("quality"))
    cache: dict[tuple, bytes | None] = {}
    job["state"] = "images"
    doc.cover()
    if options.get("contents"):
        # the index needs names before any page is drawn; those are text, not
        # pictures, so reading them ahead costs nothing worth bounding
        heads = []
        for row in rows:
            detail = jasani.item_detail(market, row["id"]) or dict(row)
            # through the DTO, like every other customer-facing string. Doing
            # the cleaning again here would be a second implementation of the
            # boundary, and a second implementation is one that can drift.
            head = to_dto(detail)
            heads.append((head["code"] or "—", head["name"] or "Product"))
        doc.contents(heads)
    stats: dict[str, int] = {}
    job["state"] = "drawing"
    job["done"] = 0
    for n, row in enumerate(rows):
        detail = jasani.item_detail(market, row["id"]) or dict(row)
        # the filter's figures win, so the document is one snapshot
        detail["available"] = row.get("available")
        detail["availableKnown"] = row.get("availableKnown")
        dto = to_dto(detail, stats)
        del detail
        photos = await _photos_for(market, dto, cache, quality)
        doc.page(dto, photos)
        del photos, dto                       # released before the next product
        job["done"] = n + 1
        job["sanitizedProducts"] = stats.get("products", 0)
        job["sanitizedFields"] = stats.get("fields", 0)
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
    pdf: bytes | None = None
    error = ""
    try:
        job["state"] = "images"
        pdf = asyncio.run(_render(token, rows, market=market, title=title,
                                  stock_at=stock_at, stock_is_known=stock_is_known,
                                  options=options))
    except CatalogueError as exc:
        error = str(exc)[:200]
    except Exception as exc:                  # pragma: no cover - defensive
        error = f"The catalogue could not be built ({exc.__class__.__name__})."
    # The outcome is recorded *before* the terminal state is published. The
    # panel polls this job from another thread, so a caller that sees "done"
    # or "failed" can rely on the audit entry already existing — the other
    # order left a window in which the build was over and the log did not
    # say so yet.
    if pdf is None:
        job["error"] = error
    else:
        job["done"] = len(rows)
    if job.get("on_finish"):
        try:
            job["on_finish"](pdf is not None, job)
        except Exception:
            pass
    if pdf is None:
        job["state"] = "failed"
    else:
        job["pdf"] = pdf
        job["finished"] = True
        job["state"] = "done"


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

    reportlab writes page text as a compressed stream, so this reads the drawn
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
    """Flate, or ASCII85 over Flate — whichever this document carries.

    `exports` asks reportlab for binary streams, so page text is plain Flate
    here; a document written before that, or by anything else, is base-85
    over Flate, and a zlib attempt on its own would decode nothing. A price
    check that silently read an empty string would pass on every document
    ever made, so every encoding is tried and the base-85 attempt falls
    through to zlib rather than giving up on it.
    """
    import base64
    import zlib

    body = chunk.strip()
    if body.startswith(b"Gb") or body.endswith(b"~>"):
        try:
            body = base64.a85decode(body.split(b"~>")[0], adobe=False)
        except Exception:
            body = chunk
    for attempt in (body, chunk):
        try:
            return zlib.decompress(attempt)
        except Exception:
            continue
    return body


#: A stream that is not page text. An image XObject decompresses to millions
#: of bytes of pixels and a font to a binary program; neither is anything a
#: customer reads.
_NOT_TEXT = re.compile(rb"/Subtype\s*/Image|/DCTDecode|/JPXDecode|/CCITTFax"
                       rb"|/FontFile|/Type\s*/(?:Font|Metadata|XRef)", re.S)
#: Drawn text lives between BT and ET. Nothing else in a content stream is a
#: string a reader sees.
_TEXT_BLOCK = re.compile(rb"\bBT\b(.*?)\bET\b", re.S)
_PDF_STRING = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)


def extract_text(pdf: bytes) -> str:
    """The text actually drawn on the pages — and **only** that.

    This is what `assert_price_free` reads, so what it counts as text decides
    what the guard can refuse a document over. It used to walk every
    `stream ... endstream` in the file and treat any parenthesised run of
    bytes inside as a drawn string. A photograph is an image XObject: 1200 x
    1200 RGB decompresses to 4.3 MB of pixels, and in that much photographic
    noise the three letters of a currency or a label turn up by chance,
    inside brackets, sooner or later. That is how a catalogue whose every
    customer-facing field was clean was refused for carrying 'rrp' — the
    bytes were never text, and no amount of sanitizing the text could have
    fixed it.

    Three filters, and the document's real text passes all three. The word
    "stream" has to be the keyword that opens one — every real stream is
    introduced by its own dictionary, so the bytes in front of it end in
    `>>`, and a photograph's data that happens to spell "stream" does not.
    The dictionary must not say image or font. And a string must sit inside
    a BT/ET text block.

    The first of those is what makes binary streams safe to read: without
    it, a run of JPEG bytes could be mistaken for a content stream and the
    letters that turn up by chance in it read as drawn text, which is the
    very failure this function was rewritten to stop.
    """
    out: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        head = pdf[max(0, match.start() - 2500):match.start()]
        if not head.rstrip().endswith(b">>"):
            continue                          # not a stream keyword at all
        cut = head.rfind(b" obj")
        if cut >= 0:
            head = head[cut:]
        if _NOT_TEXT.search(head):
            continue
        chunk = _decode_stream(match.group(1))
        for block in _TEXT_BLOCK.findall(chunk):
            for piece in _PDF_STRING.findall(block):
                body = piece[1:-1]
                body = re.sub(rb"\\([()\\])", rb"\1", body)
                out.append(body.decode("latin-1", errors="replace"))
    return " ".join(out)
