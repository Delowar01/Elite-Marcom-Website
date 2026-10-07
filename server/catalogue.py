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
        value = clean_text(item.get(key), 1200 if key == "description" else 240)
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
GALLERY_MAX = 366.0
COVER_IMAGES = 4                  # a bounded hero set, never the catalogue


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

def _cover_ground(c) -> None:
    """A designed surface rather than a blank one: a dilute orange field in
    the upper corner, one architectural hairline, a grounding band at the
    foot. Nothing here competes with a photograph."""
    _page_ground(c)
    c.saveState()
    c.setFillColorRGB(*ORANGE)
    c.setFillAlpha(0.07)
    c.circle(PAGE_W - 40, PAGE_H - 70, 250, stroke=0, fill=1)
    c.setFillAlpha(0.05)
    c.circle(PAGE_W - 40, PAGE_H - 70, 150, stroke=0, fill=1)
    c.setFillColorRGB(*INK)
    c.setFillAlpha(0.028)
    c.rect(0, 0, PAGE_W, 196, stroke=0, fill=1)
    c.restoreState()
    c.setFillColorRGB(*LINE)
    c.rect(M, 196, PAGE_W - 2 * M, 0.6, stroke=0, fill=1)


def _cover_hero(c, readers: list, x: float, bottom: float, w: float, h: float) -> None:
    """Up to four real products from this catalogue, layered. With none, the
    space belongs to the typography instead — a broken placeholder on a cover
    is worse than a cover without pictures."""
    gap = 12.0
    n = len(readers)
    if n == 0:
        return
    if n == 1:
        # one product is a deliberate presentation, not an empty page
        pw = w * 0.74
        _photo_tile(c, readers[0], x + (w - pw) / 2, bottom, pw, h, shadow=True)
        return
    if n == 2:
        main_w = (w - gap) * 0.62
        _photo_tile(c, readers[0], x, bottom, main_w, h, shadow=True)
        _photo_tile(c, readers[1], x + main_w + gap, bottom + h * 0.16,
                    w - main_w - gap, h * 0.68, shadow=True)
        return
    main_w = (w - gap) * 0.58
    side_w = w - main_w - gap
    _photo_tile(c, readers[0], x, bottom, main_w, h, shadow=True)
    if n == 3:
        side_h = (h - gap) / 2
        _photo_tile(c, readers[1], x + main_w + gap, bottom + side_h + gap,
                    side_w, side_h, shadow=True)
        _photo_tile(c, readers[2], x + main_w + gap, bottom, side_w, side_h, shadow=True)
        return
    side_h = (h - 2 * gap) / 3
    for i, reader in enumerate(readers[1:4]):
        _photo_tile(c, reader, x + main_w + gap,
                    bottom + (2 - i) * (side_h + gap), side_w, side_h, shadow=True)


def _cover_meta(c, *, market: str, count: int, stock_at, generated: float) -> None:
    """The operational facts, compact and at the foot. They have to be on the
    cover; they do not have to be the cover."""
    y = 150.0
    cols = [
        (f"{market.upper()} CATALOGUE",
         f"{count:,} product{'' if count == 1 else 's'}"),
        ("PREPARED", time.strftime("%d %b %Y", time.localtime(generated))),
        ("STOCK UPDATED",
         (time.strftime("%d %b %Y  ·  %H:%M", time.localtime(float(stock_at)))
          if stock_at else "not available")),
    ]
    w = (PAGE_W - 2 * M) / 3
    for i, (label, value) in enumerate(cols):
        x = M + i * w
        c.setFillColorRGB(*GREY)
        _tracked(c, x, y, label, "Helvetica", 6.6, 1.4)
        c.setFont("Helvetica-Bold", 10.5)
        c.setFillColorRGB(*INK)
        c.drawString(x, y - 17, value[:38])
    c.setFillColorRGB(*LINE)
    c.rect(M, 108, PAGE_W - 2 * M, 0.6, stroke=0, fill=1)
    c.setFont("Helvetica", 7.4)
    c.setFillColorRGB(*GREY)
    ty = 92.0
    for line in _wrap("Quantities are those recorded at the last stock synchronisation "
                      "shown above and are not a reservation. Please confirm "
                      "availability before committing to a quantity.",
                      "Helvetica", 7.4, PAGE_W - 2 * M - 150)[:3]:
        c.drawString(M, ty, line)
        ty -= 10.5
    c.setFont("Helvetica-Bold", 8.2)
    c.setFillColorRGB(*INK)
    c.drawRightString(PAGE_W - M, 92, SITE)


def cover_title(title: str) -> tuple[str, str]:
    """(eyebrow, headline) — the hierarchy the cover is set in.

    The stored title is one string ("Elite Marcom / Product Catalogue") and
    setting all of it at 36pt is what made the old cover read as a label. The
    first line becomes the small line above, the rest becomes the headline,
    and a leading "Corporate Gifts" is lifted out rather than printed twice.
    Presentation only: every word of the title is still on the page.
    """
    text = (title or "").strip()
    head, _, rest = text.partition("\n")
    if rest.strip():
        return head.strip()[:40], rest.strip()
    low = text.lower()
    for lead in ("elite marcom", "corporate gifts"):
        if low.startswith(lead) and len(text) > len(lead) + 2:
            return text[:len(lead)], text[len(lead):].lstrip(" -·—").strip()
    return "Corporate gifts", text


def _cover(c, *, title: str, market: str, count: int, stock_at, generated: float,
           photos: list[bytes] | None = None) -> None:
    """The opening page. Hero first, then the title, then the facts."""
    _cover_ground(c)
    _logo(c, M, PAGE_H - 52, 26)
    label = MARKET_LABEL.get(market, market.upper())
    c.setFillColorRGB(*GREY)
    _tracked(c, PAGE_W - M - _tracked_width(f"{label}  ·  {market.upper()}",
                                            "Helvetica", 7.4, 1.5),
             PAGE_H - 66, f"{label}  ·  {market.upper()}", "Helvetica", 7.4, 1.5)

    readers = usable_photos(photos or [], COVER_IMAGES)

    # ---- the title block is anchored to the foot, and the hero takes the
    # ---- room above it: that is what stops a cover ending in dead space ----
    eyebrow, headline = cover_title(title)
    head_size = 36.0 if readers else 50.0
    lines = _wrap(headline.upper(), "Helvetica-Bold", head_size, PAGE_W - 2 * M)
    if len(lines) > 2:
        head_size = 27.0 if readers else 38.0
        lines = _wrap(headline.upper(), "Helvetica-Bold", head_size, PAGE_W - 2 * M)
    lines = lines[:3]
    #: the market line lands here, a measured distance above the facts band at
    #: 196, and the block is laid out upwards from it — so the cover ends on a
    #: deliberate interval rather than on whatever was left over
    y = 240.0 + head_size * 0.95 * len(lines) + 24
    hero_top = PAGE_H - 112
    hero_h = max(214.0, min(352.0, hero_top - (y + 34) - 44))
    if readers:
        _cover_hero(c, readers, M, hero_top - hero_h, PAGE_W - 2 * M, hero_h)
    else:
        #: no pictures: the type is the page, set low with an open field above
        y = 262.0 + head_size * 0.95 * len(lines) + 24
    c.setFillColorRGB(*ORANGE)
    c.rect(M, y + 32, 38, 2.2, stroke=0, fill=1)
    _eyebrow(c, M, y + 14, eyebrow, ORANGE, 8.0)
    c.setFont("Helvetica-Bold", head_size)
    c.setFillColorRGB(*INK)
    for line in lines:
        y -= head_size * 0.95
        c.drawString(M, y, line)
    y -= 24
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(*GREY)
    c.drawString(M, y, f"{label}  ·  {market.upper()}  ·  "
                       + time.strftime("%Y", time.localtime(generated)))
    _cover_meta(c, market=market, count=count, stock_at=stock_at, generated=generated)
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


def _description_height(body: str, w: float) -> float:
    """What the description wants, capped: no single field may own the page."""
    if not body:
        return 0.0
    lines = min(len(_wrap(body, "Helvetica", 9.0, w)), 14)
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


def _description(c, body: str, x: float, top: float, w: float, max_h: float) -> float:
    """Set for reading: a narrow measure, generous leading, and only as much
    as the page can give it."""
    if not body or max_h < 34:
        return top
    _eyebrow(c, x, top - 8, "Description", ORANGE, 7.0)
    y = top - 26
    lines = _wrap(body, "Helvetica", 9.0, w)
    room = int(max(0, (max_h - 26) // 12.6))
    if len(lines) > room and room > 0:
        lines = lines[:room]
        lines[-1] = lines[-1].rstrip(" ,;:")[:120] + " …"
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
            c.drawString(x + label_w, vy, vline)
            vy -= 10
        y -= row_h
        band += 1
    return y


def _availability(c, item: dict, *, stock_at, stock_is_known: bool,
                  show_date: bool) -> None:
    """Pinned above the footer so every page in the document agrees, and read
    as part of the catalogue rather than stamped on it."""
    band_h = 74.0
    by = 64.0
    _panel(c, M, by, PAGE_W - 2 * M, band_h, FAINT, 3.0)
    c.setFillColorRGB(*ORANGE)
    c.rect(M, by, 2.6, band_h, stroke=0, fill=1)
    c.setFillColorRGB(*GREY)
    _tracked(c, M + 18, by + band_h - 20, "AVAILABLE NOW", "Helvetica-Bold", 7.0, 1.6)
    headline, _ = stock_sentence(item.get("available"), stock_is_known)
    figure, _, unit = headline.partition(" ")
    if unit:
        c.setFont("Helvetica-Bold", 25)
        c.setFillColorRGB(*INK)
        c.drawString(M + 18, by + 18, figure)
        c.setFont("Helvetica", 9.4)
        c.setFillColorRGB(*GREY)
        c.drawString(M + 24 + stringWidth(figure, "Helvetica-Bold", 25), by + 18, unit)
    else:
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(*INK)
        c.drawString(M + 18, by + 20, headline)
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
    body = clean_text(item.get("description"), 900) if options.get("description", True) else ""
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
    gallery_h = max(GALLERY_MIN, min(GALLERY_MAX,
                                     top - (plan["height"] + 12 + need + floor) - 26))
    if not readers:
        #: with no photograph there is nothing to grow: a half-page of empty
        #: grey is worse than a modest note and honest white space
        gallery_h = min(gallery_h, 210.0)

    _gallery(c, readers, M, top, content_w, gallery_h)
    y = top - gallery_h - 26
    y = _identity(c, plan, M, y)
    y -= 12

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
        self._covered = False

    def cover(self, photos: list[bytes] | None = None) -> None:
        """Draw the opening page, with a **bounded** set of real products from
        this catalogue as its hero. At most `COVER_IMAGES` pictures are ever
        held for it — the cover is a composition, not a contact sheet, and
        preloading the catalogue's imagery is exactly what the streaming
        rewrite exists to prevent."""
        if self._covered:
            return
        self._covered = True
        _cover(self.c, title=self.title, market=self.market, count=self.count,
               stock_at=self.stock_at, generated=time.time(),
               photos=(photos or [])[:COVER_IMAGES])

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
    # the cover's hero is the first picture of each of the first few products
    hero: list[bytes] = []
    for dto in dtos:
        got = photos.get(dto["id"]) or []
        if got:
            hero.append(got[0])
        if len(hero) >= COVER_IMAGES:
            break
    doc.cover(hero)
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
    return {"state": job["state"], "done": job["done"], "total": job["total"],
            "error": job["error"], "filename": job["filename"],
            # ordinary supplier-data cleanup, reported rather than hidden
            "sanitizedProducts": job.get("sanitizedProducts", 0),
            "sanitizedFields": job.get("sanitizedFields", 0),
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


async def _cover_photos(market: str, rows: list[dict], cache: dict) -> list[bytes]:
    """A handful of real products for the cover's hero composition.

    Bounded twice over: one picture per product, and at most `COVER_IMAGES`
    of them. They go through the same cache the pages use, so a hero picture
    is not fetched again when its own page comes round, and the catalogue's
    imagery is never preloaded to build a cover.
    """
    from . import jasani

    out: list[bytes] = []
    for row in rows[:COVER_IMAGES * 3]:
        if len(out) >= COVER_IMAGES:
            break
        detail = jasani.item_detail(market, row["id"]) or dict(row)
        urls = to_dto(detail).get("images") or []
        if not urls:
            continue
        url = urls[0]
        if url in cache:
            if cache[url] is not None:
                out.append(cache[url])
            continue
        try:
            raw = await jasani._fetch_image_bytes(url)
        except Exception:
            raw = None
        small = prepare_image(raw) if raw else None
        del raw
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
    cache: dict[str, bytes | None] = {}
    job["state"] = "images"
    doc.cover(await _cover_photos(market, rows, cache))
    if options.get("contents"):
        # the index needs names before any page is drawn; those are text, not
        # pictures, so reading them ahead costs nothing worth bounding
        heads = []
        for row in rows:
            detail = jasani.item_detail(market, row["id"]) or dict(row)
            # the same sanitization the page gets: a name carrying a price
            # statement must not slip into the contents list instead
            heads.append((sanitize_catalogue_text(
                              clean_text(detail.get("code"), 40), "code") or "—",
                          sanitize_catalogue_text(
                              clean_text(detail.get("name"), 120), "name") or "Product"))
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
        photos = await _photos_for(market, dto, cache)
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
