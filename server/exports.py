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

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

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


def to_csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    # UTF-8 BOM so Excel opens Arabic/accented names correctly
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


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
    for r, row in enumerate([list(COLUMNS)] + rows, start=1):
        cells = []
        for cidx, value in enumerate(row):
            text = escape(str(value)).replace("\r", "").replace("\n", "&#10;")
            cells.append(f'<c r="{_col_ref(cidx)}{r}" t="inlineStr"><is><t xml:space="preserve">'
                         f"{text}</t></is></c>")
        out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def to_xlsx(rows: list[list[str]]) -> bytes:
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
                   '<sheets><sheet name="Requests" sheetId="1" r:id="rId1"/></sheets></workbook>')
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


def export_filename(fmt: str, scope: str, prefix: str = "requests") -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"elite-marcom-{prefix}-{scope}-{stamp}.{fmt}"
