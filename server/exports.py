"""Elite Marcom admin — request exports (CSV / Excel / PDF).

CSV and XLSX are generated with the standard library only (a minimal but
valid Office Open XML package); the PDF reuses the reportlab styling of the
printing manuals. Exports contain decrypted customer data, so every call
into this module is wrapped in an audited admin endpoint.
"""
from __future__ import annotations

import csv
import io
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

#: Streams go in as binary rather than wrapped in ASCII base-85.
#:
#: Base-85 encodes four bytes as five printable characters, so it adds a flat
#: 25% to every compressed stream in the file — on a photographic catalogue
#: that is a quarter of the whole document, spent on making the bytes safe
#: for a 7-bit transport nobody has used in thirty years. A PDF is a binary
#: format and every reader has read binary streams since 1.0.
#:
#: It is a library-wide setting because reportlab reads it when it writes a
#: stream, so it is set once here, at the module every PDF in this
#: application is drawn through, rather than toggled around a build where two
#: threads could disagree. The one thing that depended on it is
#: `catalogue.extract_text`, which now identifies a stream by the dictionary
#: in front of it instead of trusting that stream data is printable.
rl_config.useA85 = 0

KIND_LABELS = {
    "contact": "Contact enquiry",
    "career": "Career application",
    "giveaway_enquiry": "Gift enquiry",
    "giveaway_notification": "Gift stock alert",
    "rental_enquiry": "Rental enquiry",
    "rental_notification": "Rental alert",
}

COLUMNS = ("Reference", "Type", "Received", "Status", "Assigned to", "Name",
           "Company", "Email", "Phone", "Market", "Service / Role", "Dates",
           "City", "Shipping address", "Items", "Message / Notes")


def _when(ts) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _items_text(payload: dict) -> str:
    parts = []
    for it in payload.get("items") or []:
        bits = [str(it.get("name") or it.get("productId") or it.get("id") or "item")]
        if it.get("code"):
            bits.append(str(it["code"]))
        if it.get("quantity"):
            bits.append(f"qty {it['quantity']}")
        if it.get("days"):
            bits.append(f"{it['days']} day(s)")
        pref = it.get("brandingPreference") or {}
        if pref.get("area") or pref.get("method"):
            bits.append("branding: " + " / ".join(
                str(pref[k]) for k in ("area", "method") if pref.get(k)))
        parts.append(" · ".join(bits))
    return " | ".join(parts)


def request_row(item: dict) -> list[str]:
    """Flatten one decrypted request {reference, kind, createdAt, payload, meta}."""
    p = item.get("payload") or {}
    meta = item.get("meta") or {}
    dates = " – ".join(str(p[k]) for k in ("startDate", "endDate") if p.get(k)) \
        or str(p.get("eventDate") or p.get("projectDate") or "")
    return [
        item.get("reference", ""),
        KIND_LABELS.get(item.get("kind", ""), item.get("kind", "")),
        _when(item.get("createdAt")),
        str(meta.get("status", "new")),
        str(meta.get("assignee", "")),
        str(p.get("fullName", "")),
        str(p.get("company", "")),
        str(p.get("email", "")),
        str(p.get("phone", "")),
        str(p.get("market", "")),
        str(p.get("service") or p.get("roleTitle") or p.get("enquiryType") or ""),
        dates,
        str(p.get("eventCity") or p.get("projectCity") or p.get("location") or ""),
        str(p.get("shippingAddress", "")),
        _items_text(p),
        str(p.get("message") or p.get("notes") or p.get("introduction") or ""),
    ]


def to_csv_rows(rows: list[list[str]]) -> bytes:
    """Rows exactly as given, header included — the caller owns the columns."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerows(rows)
    # UTF-8 BOM so Excel opens Arabic/accented names correctly
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def to_csv(rows: list[list[str]]) -> bytes:
    return to_csv_rows([list(COLUMNS)] + rows)


# ---------------- minimal XLSX (stdlib only) ----------------

def _col_ref(idx: int) -> str:
    ref = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        ref = chr(65 + rem) + ref
    return ref


def _sheet_xml(rows: list[list[str]]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           "<sheetData>"]
    for r, row in enumerate(rows, start=1):
        cells = []
        for cidx, value in enumerate(row):
            text = escape(str(value)).replace("\r", "").replace("\n", "&#10;")
            cells.append(f'<c r="{_col_ref(cidx)}{r}" t="inlineStr"><is><t xml:space="preserve">'
                         f"{text}</t></is></c>")
        out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def to_xlsx(rows: list[list[str]]) -> bytes:
    return to_xlsx_rows([list(COLUMNS)] + rows, sheet="Requests")


def to_xlsx_rows(rows: list[list[str]], sheet: str = "Sheet1") -> bytes:
    """Rows exactly as given, header included."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f'<sheets><sheet name="{escape(sheet[:28])}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   "</Relationships>")
        z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return buf.getvalue()


# ---------------- branded PDF (reportlab, matches the manual style) ----------------

PAGE_W, PAGE_H = A4
M = 42.0
ORANGE = (0.941, 0.435, 0.133)
INK = (0.078, 0.094, 0.122)
GREY = (0.541, 0.561, 0.596)
LINE = (0.910, 0.894, 0.871)
_LOGO_PATH = Path(__file__).parent / "data" / "logo-print.png"

#: The wordmark, resized once and shared by every page of every document.
_LOGO_CACHE: dict[int, tuple] = {}
#: pixels per point. Three is already beyond what print resolves; six leaves
#: room for a reader zooming in and still costs a few kilobytes.
LOGO_PX_PER_PT = 6.0


def logo_reader(height: float = 26.0):
    """(reader, width, height) for the logo, no larger than it is drawn.

    The shipped artwork is 1660 x 560 — roughly 1,500 dots to the inch at the
    size a page draws it — and because it carries an alpha channel reportlab
    writes it as raw RGB plus a soft mask: 49 KB in every document, which on
    a one-product catalogue was a fifth of the whole file. Resized once to
    six pixels to the point it is a few kilobytes, the alpha is kept so the
    mark still sits on a tinted band, and reportlab's own content digest
    means every page shares the single object.
    """
    #: rounded up to a 16pt bucket, so the 19pt page header and the 26pt
    #: cover share one object instead of embedding the artwork twice. The
    #: drawn size is whatever the caller asked for; only the stored pixels
    #: are quantized.
    key = int(max(16, min(160, -(-max(1.0, height) // 16) * 16)))
    hit = _LOGO_CACHE.get(key)
    if hit is not None:
        return hit
    from PIL import Image

    try:
        with Image.open(_LOGO_PATH) as art:
            art.load()
            want_h = max(1, int(key * LOGO_PX_PER_PT))
            if art.height > want_h:
                art = art.resize((max(1, round(art.width * want_h / art.height)),
                                  want_h), Image.LANCZOS)
            buf = io.BytesIO()
            art.save(buf, "PNG", optimize=True)
        buf.seek(0)
        out = (ImageReader(buf), art.width, art.height)
    except Exception:
        out = (None, 0, 0)
    _LOGO_CACHE[key] = out
    return out


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for para in str(text).splitlines() or [""]:
        cur = ""
        for w in para.split():
            probe = (cur + " " + w).strip()
            if stringWidth(probe, font, size) <= width or not cur:
                cur = probe
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines or [""]


class _Pdf:
    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.page = 1
        self.y = PAGE_H - M

    def footer(self):
        self.c.setFont("Helvetica", 7)
        self.c.setFillColorRGB(*GREY)
        self.c.drawString(M, 30, "Elite Marcom — Requests export · internal use only")
        self.c.drawRightString(PAGE_W - M, 30, f"Page {self.page}")

    def need(self, h: float):
        if self.y - h < 60:
            self.footer()
            self.c.showPage()
            self.page += 1
            self.y = PAGE_H - M

    def header(self, title: str, subtitle: str):
        c = self.c
        try:
            from PIL import Image

            from .manuals import _logo_path

            im = Image.open(_logo_path())
            lw = 108.0
            lh = lw * im.height / im.width
            c.drawImage(ImageReader(im), M, self.y - lh, width=lw, height=lh,
                        mask="auto")
        except Exception:
            lh = 20.0
        c.setFont("Helvetica-Bold", 15)
        c.setFillColorRGB(*INK)
        c.drawRightString(PAGE_W - M, self.y - 14, title)
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(*GREY)
        c.drawRightString(PAGE_W - M, self.y - 28, subtitle)
        self.y -= max(lh, 34) + 10
        c.setStrokeColorRGB(*ORANGE)
        c.setLineWidth(2)
        c.line(M, self.y, PAGE_W - M, self.y)
        self.y -= 18

    def kv(self, label: str, value: str):
        width = PAGE_W - 2 * M - 130
        lines = _wrap(value, "Helvetica-Bold", 9, width)
        h = max(14.0, len(lines) * 12 + 2)
        self.need(h)
        c = self.c
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*GREY)
        c.drawString(M, self.y - 9, label)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(*INK)
        yy = self.y - 9
        for ln in lines:
            c.drawRightString(PAGE_W - M, yy, ln)
            yy -= 12
        self.y -= h
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(0.6)
        c.line(M, self.y, PAGE_W - M, self.y)
        self.y -= 6

    def section(self, title: str):
        self.need(30)
        self.c.setFont("Helvetica-Bold", 10.5)
        self.c.setFillColorRGB(*ORANGE)
        self.c.drawString(M, self.y - 10, title.upper())
        self.y -= 24

    def paragraph(self, text: str):
        width = PAGE_W - 2 * M
        for ln in _wrap(text, "Helvetica", 9, width):
            self.need(13)
            self.c.setFont("Helvetica", 9)
            self.c.setFillColorRGB(*INK)
            self.c.drawString(M, self.y - 9, ln)
            self.y -= 12
        self.y -= 4

    def done(self) -> bytes:
        self.footer()
        self.c.save()
        return self.buf.getvalue()


_PDF_FIELDS = (
    ("fullName", "Full name"), ("company", "Company"), ("email", "Email"),
    ("phone", "Phone"), ("market", "Market"), ("enquiryType", "Enquiry type"),
    ("service", "Service"), ("roleTitle", "Role"), ("location", "Location"),
    ("eventDate", "Event date"), ("projectDate", "Project date"),
    ("startDate", "Start date"), ("endDate", "End date"),
    ("eventCity", "Event city"), ("projectCity", "Project city"),
    ("venue", "Venue"), ("shippingAddress", "Shipping address"),
    ("portfolioUrl", "Portfolio"),
)


def to_pdf(items: list[dict]) -> bytes:
    """One branded summary per request; multiple requests concatenate."""
    pdf = _Pdf()
    for idx, item in enumerate(items):
        if idx:
            pdf.footer()
            pdf.c.showPage()
            pdf.page += 1
            pdf.y = PAGE_H - M
        p = item.get("payload") or {}
        meta = item.get("meta") or {}
        kind = KIND_LABELS.get(item.get("kind", ""), item.get("kind", ""))
        pdf.header(item.get("reference", ""),
                   f"{kind} · received {_when(item.get('createdAt'))}")
        pdf.kv("Status", str(meta.get("status", "new")).replace("_", " ").title())
        if meta.get("assignee"):
            pdf.kv("Assigned to", str(meta["assignee"]))
        for key, label in _PDF_FIELDS:
            if p.get(key):
                pdf.kv(label, str(p[key]))
        items_list = p.get("items") or []
        if items_list:
            pdf.section(f"Requested items ({len(items_list)})")
            for it in items_list:
                bits = [str(it.get("name") or it.get("productId") or "item")]
                if it.get("code"):
                    bits.append(str(it["code"]))
                if it.get("quantity"):
                    bits.append(f"qty {it['quantity']}")
                if it.get("days"):
                    bits.append(f"{it['days']} day(s)")
                pdf.paragraph("•  " + " · ".join(bits))
                pref = it.get("brandingPreference") or {}
                if pref.get("area") or pref.get("method") or pref.get("note"):
                    pdf.paragraph("    Branding preference: " + " · ".join(
                        str(pref[k]) for k in ("area", "method", "note") if pref.get(k)))
        message = p.get("message") or p.get("notes") or p.get("introduction")
        if message:
            pdf.section("Message")
            pdf.paragraph(str(message))
        notes = meta.get("notes") or []
        if notes:
            pdf.section(f"Internal notes ({len(notes)})")
            for n in notes:
                pdf.paragraph(f"{_when(n.get('ts'))} — {n.get('by', '')}: {n.get('text', '')}")
    return pdf.done()


# ---------------- Jasani items ----------------

_ITEM_COLUMNS = [("code", "SKU"), ("name", "Name"), ("brand", "Brand"),
                 ("color", "Colour"), ("category", "Category")]
_ITEM_STOCK = [("available", "Available"), ("incoming", "Incoming"),
               ("incomingDate", "Incoming date (estimated)")]
_ITEM_PRICES = [("price", "Price"), ("booked", "Booked")]


def item_rows(items: list[dict], with_prices: bool, currency: str = "") -> list[list[str]]:
    """Header + one row per item. Prices only when the caller may see them —
    an export must not become the way an internal figure leaves the panel."""
    cols = list(_ITEM_COLUMNS)
    cols += [(k, f"{lbl} ({currency})" if currency and k != "booked" else lbl)
             for k, lbl in _ITEM_PRICES] if with_prices else []
    cols += _ITEM_STOCK + [("websiteState", "On the website")]
    rows = [["SN"] + [lbl for _, lbl in cols]]
    for i, it in enumerate(items, start=1):
        state = ("Hidden by hand" if it.get("hidden")
                 else "Hidden — no stock" if it.get("hiddenByRule") else "Live")
        row = [str(i)]
        for key, _lbl in cols:
            if key == "websiteState":
                row.append(state)
                continue
            value = it.get(key)
            row.append("" if value is None else str(value))
        rows.append(row)
    return rows


def items_to_pdf(items: list[dict], *, market: str, with_prices: bool,
                 currency: str = "", note: str = "") -> bytes:
    """The filtered item list as a branded table."""
    pdf = _Pdf()
    pdf.header(f"Jasani items — {market.upper()}",
               f"{len(items)} item(s) · {time.strftime('%d %b %Y %H:%M')}"
               + (f" · {note}" if note else ""))
    if with_prices:
        pdf.paragraph("Prices exclude VAT and are internal to Elite Marcom — "
                      "they must not be shared with a customer.")
    cols = [("code", "SKU", 74), ("name", "Name", 150), ("brand", "Brand", 70),
            ("color", "Colour", 60)]
    if with_prices:
        cols += [("price", f"Price {currency}".strip(), 62), ("booked", "Bkd", 34)]
    cols += [("available", "Avail", 42), ("incoming", "Inc", 36)]
    total = sum(w for _, _, w in cols)
    scale = (PAGE_W - 2 * M) / total
    widths = [w * scale for _, _, w in cols]

    def head_row():
        pdf.c.setFont("Helvetica-Bold", 7)
        pdf.c.setFillColorRGB(*GREY)
        x = M
        for (_, label, _), w in zip(cols, widths):
            pdf.c.drawString(x, pdf.y, label.upper())
            x += w
        pdf.y -= 4
        pdf.c.setStrokeColorRGB(*LINE)
        pdf.c.line(M, pdf.y, PAGE_W - M, pdf.y)
        pdf.y -= 11

    pdf.y -= 6
    head_row()
    for it in items:
        pdf.need(16)
        if pdf.y > PAGE_H - M - 40 and pdf.page > 1:
            head_row()
        pdf.c.setFont("Helvetica", 7.4)
        pdf.c.setFillColorRGB(*INK)
        x = M
        for (key, _label, _), w in zip(cols, widths):
            value = it.get(key)
            text = "" if value is None else str(value)
            if len(text) > 2:
                while stringWidth(text, "Helvetica", 7.4) > w - 6 and len(text) > 4:
                    text = text[:-2]
                if text != str(value):
                    text += "…"
            pdf.c.drawString(x, pdf.y, text)
            x += w
        pdf.y -= 13
    return pdf.done()


def product_sheet_pdf(item: dict, images: list[bytes], *, currency: str = "") -> bytes:
    """One A4 product sheet for a customer.

    Carries no price of any kind: the supplier's list_price is internal by
    supplier policy, and this document is meant to be sent out.
    """
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = PAGE_H - M

    drawn = False
    logo, lw, lh = logo_reader(26.0)
    if logo is not None:
        try:
            h = 26.0
            c.drawImage(logo, M, y - h, width=lw * (h / lh), height=h, mask="auto")
            drawn = True
        except Exception:
            drawn = False
    if not drawn:
        c.setFont("Helvetica-Bold", 15)
        c.setFillColorRGB(*ORANGE)
        c.drawString(M, y - 18, "ELITE MARCOM")
    c.setFont("Helvetica", 7.6)
    c.setFillColorRGB(*GREY)
    c.drawRightString(PAGE_W - M, y - 8, "Corporate gifts · Product sheet")
    c.drawRightString(PAGE_W - M, y - 19, "Riyadh · Dubai · elitemarcom.com")
    y -= 40
    c.setFillColorRGB(*ORANGE)
    c.rect(M, y, PAGE_W - 2 * M, 2.4, stroke=0, fill=1)
    y -= 26

    c.setFont("Helvetica-Bold", 17)
    c.setFillColorRGB(*INK)
    for line in _wrap(item.get("name", ""), "Helvetica-Bold", 17, PAGE_W - 2 * M)[:2]:
        c.drawString(M, y, line)
        y -= 21
    c.setFont("Helvetica", 9.4)
    c.setFillColorRGB(*GREY)
    meta = " · ".join(x for x in (item.get("code"), item.get("brand"), item.get("color")) if x)
    c.drawString(M, y, meta)
    y -= 20

    #: Unknown is not zero. The sheet read `available <= 0` and therefore
    #: told an admin "Currently out of stock" about a product the stock
    #: synchronisation had simply never answered for — the one reading the
    #: catalogue page is careful never to make. `catalogue.stock_state` is
    #: that reading, and this is the third surface to go through it.
    from .catalogue import stock_state

    #: imported inside the function because `catalogue` draws through this
    #: module, so a module-level import would be a cycle
    known = item.get("availableKnown")
    state = stock_state(item.get("available"),
                        True if known is None else bool(known))
    chips = [{"in": "In stock",
              "out": "Currently out of stock",
              "unknown": "Availability not reported"}[state]]
    if item.get("incoming"):
        chips.append("More arriving " + str(item.get("incomingDate") or "soon") + " (estimated)")
    c.setFont("Helvetica", 7.6)
    x = M
    for chip in chips:
        w = stringWidth(chip, "Helvetica", 7.6) + 16
        c.setStrokeColorRGB(*LINE)
        c.setFillColorRGB(*GREY)
        c.roundRect(x, y - 4, w, 15, 7, stroke=1, fill=0)
        c.drawString(x + 8, y, chip)
        x += w + 6
    y -= 22

    # image band: one hero and up to three supporting shots
    band = 210.0
    readers = []
    for raw in images[:4]:
        reader, nw, nh = _image_box(raw)
        if reader:
            readers.append((reader, nw, nh))
    if readers:
        hero_w = (PAGE_W - 2 * M) * (0.66 if len(readers) > 1 else 1.0)
        _draw_contained(c, readers[0], M, y - band, hero_w, band)
        if len(readers) > 1:
            side_x = M + hero_w + 8
            side_w = PAGE_W - M - side_x
            each = (band - 8 * (len(readers) - 2)) / (len(readers) - 1)
            sy = y
            for r in readers[1:]:
                _draw_contained(c, r, side_x, sy - each, side_w, each)
                sy -= each + 8
        y -= band + 22

    col_w = (PAGE_W - 2 * M - 28) / 2
    left_y = right_y = y

    def heading(text, x, yy):
        c.setFont("Helvetica-Bold", 7.4)
        c.setFillColorRGB(*ORANGE)
        c.drawString(x, yy, text.upper())
        c.setStrokeColorRGB(*LINE)
        c.line(x, yy - 5, x + col_w, yy - 5)
        return yy - 17

    left_y = heading("Description", M, left_y)
    c.setFont("Helvetica", 8.6)
    c.setFillColorRGB(*INK)
    for line in _wrap(item.get("description", ""), "Helvetica", 8.6, col_w)[:16]:
        c.drawString(M, left_y, line)
        left_y -= 12

    specs = [s for s in (item.get("specs") or []) if s[1]]
    if specs:
        right_y = heading("Specifications", M + col_w + 28, right_y)
        for label, value in specs[:14]:
            c.setFont("Helvetica", 8.2)
            c.setFillColorRGB(*GREY)
            c.drawString(M + col_w + 28, right_y, str(label))
            c.setFillColorRGB(*INK)
            c.drawRightString(PAGE_W - M, right_y, str(value))
            c.setStrokeColorRGB(*LINE)
            c.line(M + col_w + 28, right_y - 4, PAGE_W - M, right_y - 4)
            right_y -= 15

    c.setStrokeColorRGB(*LINE)
    c.line(M, 46, PAGE_W - M, 46)
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*GREY)
    c.drawString(M, 34, "Elite Marcom · info@elitemarcom.com · +966 59 925 5995")
    c.drawRightString(PAGE_W - M, 34, "Stock and lead times on request.")
    c.showPage()
    c.save()
    return buf.getvalue()


class _JPEGReader(ImageReader):
    """A photograph handed to reportlab as the JPEG it already is.

    reportlab will embed a JPEG verbatim — `/DCTDecode`, the supplier's own
    bytes — but only when it is given the compressed file; handed a decoded
    picture it zlib-compresses raw RGB instead, and raw RGB of a photograph
    barely compresses at all. That was the whole of a catalogue's size: a
    140 KB product shot became about 1.55 MB in the file, measured, and a
    page of three of them 5 MB.

    `Canvas.drawImage` also calls `getRGBData()` for the digest it keys an
    image by — a second full decode of every photograph. The digest is only
    ever a key, so the compressed bytes serve it exactly as well: the same
    picture still collapses to one object, and nothing is decoded twice.
    `_dataA` is the soft mask `drawImage` reads straight afterwards, and a
    JPEG has no alpha channel, so it is set here rather than left unbound.
    """

    def getRGBData(self):                    # noqa: N802 - reportlab's name
        self._dataA = None
        return self._jpeg


def _is_baseline_jpeg(im) -> bool:
    """Whether this picture can go into a PDF untouched.

    `/DCTDecode` is baseline and extended-sequential JPEG. A progressive one
    is a different coding and not every reader accepts it inside a PDF, so it
    takes the re-encoding path; CMYK and anything with an alpha channel do
    too, because the drawing code expects RGB on white.
    """
    return (getattr(im, "format", None) == "JPEG"
            and im.mode in ("RGB", "L")
            and not im.info.get("progressive")
            and not im.info.get("progression"))


def _image_box(raw: bytes):
    """(reader, width, height) for a picture about to be drawn.

    A JPEG is passed straight through, because every caller already hands in
    a bounded one (`catalogue.prepare_image` makes it) and re-encoding it was
    costing an order of magnitude in file size. Everything else — a PNG, a
    palette image, anything carrying transparency — is still flattened onto
    white and re-encoded, which is what keeps the drawing code able to assume
    RGB.
    """
    from PIL import Image

    try:
        im = Image.open(io.BytesIO(raw))
        if _is_baseline_jpeg(im):
            width, height = im.size
            im.close()
            reader = _JPEGReader(io.BytesIO(raw))
            reader._jpeg = raw
            return reader, width, height
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            flat = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            flat.paste(rgba, mask=rgba.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "PNG")
        out.seek(0)
        return ImageReader(out), im.width, im.height
    except Exception:
        return None, 0, 0


def _draw_contained(c, reader_tuple, x, y, box_w, box_h) -> None:
    reader, nw, nh = reader_tuple
    if not nw or not nh:
        return
    scale = min(box_w / nw, box_h / nh)
    w, h = nw * scale, nh * scale
    c.drawImage(reader, x + (box_w - w) / 2, y + (box_h - h) / 2,
                width=w, height=h, mask="auto")


def export_filename(fmt: str, scope: str, prefix: str = "requests") -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"elite-marcom-{prefix}-{scope}-{stamp}.{fmt}"
