"""Elite Marcom-branded printing-manual PDF (design M1, "Clean Corporate").

Generated from the supplier's Branding API data: one card per branding area,
each drawn on that area's own image with its own rectangle — coordinates are
never shared between products. No supplier branding, no prices, no tokens.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
M = 42.0                      # page margin
FOOTER_H = 96.0               # reserved space for the last-page footer

ORANGE = (0.941, 0.435, 0.133)      # #f06f22
ORANGE_SOFT = (0.973, 0.647, 0.255)  # #f8a541
INK = (0.078, 0.094, 0.122)          # #14181f
GREY = (0.541, 0.561, 0.596)         # #8a8f98
LINE = (0.910, 0.894, 0.871)         # #e8e4de

_LOGO_PATH = Path(__file__).parent / "data" / "logo-print.png"


def _logo_path() -> Path:
    """Admin-uploaded PDF logo override wins over the shipped asset."""
    try:
        from . import media

        override = media.pdf_logo_path()
        if override is not None:
            return override
    except Exception:
        pass
    return _LOGO_PATH

DISCLAIMER = ("All branding placements, methods and dimensions are subject to artwork review, "
              "product compatibility, technical feasibility and final production approval by "
              "Elite Marcom. This document shows the maximum printable areas provided by the "
              "supplier; lead times, where shown, are estimates only.")
CONTACT_LEFT = "Elite Marcom — Riyadh · Dubai · Worldwide"
CONTACT_RIGHT = "info@elitemarcom.com · +966 59 925 5995"

MARKET_LABEL = {"ksa": "Saudi Arabia", "uae": "United Arab Emirates"}


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    cur = ""
    for w in words:
        probe = (cur + " " + w).strip()
        if stringWidth(probe, font, size) <= width or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _image_reader(data: bytes) -> tuple[ImageReader | None, int, int]:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.width < 8 or im.height < 8 or im.width > 6000 or im.height > 6000:
            return None, 0, 0
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        return ImageReader(im), im.width, im.height
    except Exception:
        return None, 0, 0


def _contain(nat_w: float, nat_h: float, box_w: float, box_h: float) -> tuple[float, float, float]:
    scale = min(box_w / nat_w, box_h / nat_h)
    return nat_w * scale, nat_h * scale, scale


class _Doc:
    def __init__(self, buf: io.BytesIO):
        self.c = canvas.Canvas(buf, pagesize=A4)
        self.page = 1

    def new_page(self):
        self._page_footer()
        self.c.showPage()
        self.page += 1

    def _page_footer(self):
        c = self.c
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*GREY)
        c.drawString(M, 30, "Elite Marcom — Printing Manual")
        c.drawRightString(PAGE_W - M, 30, f"Page {self.page}")

    def final_footer(self, y_limit: float):
        """Disclaimer + contact block pinned to the bottom of the last page."""
        c = self.c
        lines = _wrap(DISCLAIMER, "Helvetica", 7.5, PAGE_W - 2 * M)
        block_h = len(lines) * 10 + 26
        y = 40 + block_h
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(0.8)
        c.line(M, y, PAGE_W - M, y)
        yy = y - 14
        c.setFont("Helvetica", 7.5)
        c.setFillColorRGB(*GREY)
        for ln in lines:
            c.drawString(M, yy, ln)
            yy -= 10
        yy -= 4
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColorRGB(*INK)
        c.drawString(M, yy, CONTACT_LEFT)
        c.setFillColorRGB(*ORANGE)
        c.drawRightString(PAGE_W - M, yy, CONTACT_RIGHT)
        self._page_footer()


def build_manual(product: dict, areas: list[dict], market: str,
                 product_image: bytes | None = None) -> bytes:
    """Render the M1 printing manual. `areas` entries follow jasani.get_branding_areas:
    {name, methods: [...], areaWidthMm, areaHeightMm,
     image: {"data": bytes|None, "width": int, "height": int} | None,
     rect: {"left","top","width","height"} | None,
     colorChoices: str, leadTime: str}"""
    buf = io.BytesIO()
    doc = _Doc(buf)
    c = doc.c
    y = PAGE_H - M

    # ---------- header ----------
    logo_h = 26.0
    try:
        logo = ImageReader(str(_logo_path()))
        lw, lh = logo.getSize()
        logo_w = logo_h * lw / lh
        c.drawImage(logo, M, y - logo_h, width=logo_w, height=logo_h,
                    preserveAspectRatio=True, mask="auto")
    except Exception:
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(*INK)
        c.drawString(M, y - 16, "ELITE MARCOM")
    c.setFont("Helvetica-Bold", 21)
    c.setFillColorRGB(*INK)
    c.drawRightString(PAGE_W - M, y - 16, "Printing Manual")
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColorRGB(*GREY)
    sub = f"CORPORATE GIFTS · {MARKET_LABEL.get(market, market).upper()} CATALOG"
    c.drawRightString(PAGE_W - M, y - 30, " ".join(sub))  # letter-spaced
    y -= 44

    # brand rule
    c.setFillColorRGB(*ORANGE)
    c.rect(M, y, (PAGE_W - 2 * M) * 0.55, 2.6, stroke=0, fill=1)
    c.setFillColorRGB(*ORANGE_SOFT)
    c.rect(M + (PAGE_W - 2 * M) * 0.55, y, (PAGE_W - 2 * M) * 0.45, 2.6, stroke=0, fill=1)
    y -= 24

    # ---------- product block ----------
    img_box = 118.0
    text_x = M
    reader = None
    if product_image:
        reader, nw, nh = _image_reader(product_image)
    if reader:
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(1)
        c.roundRect(M, y - img_box, img_box, img_box, 8, stroke=1, fill=0)
        dw, dh, _ = _contain(nw, nh, img_box - 10, img_box - 10)
        c.drawImage(reader, M + (img_box - dw) / 2, y - img_box + (img_box - dh) / 2,
                    width=dw, height=dh, mask="auto")
        text_x = M + img_box + 20
    name_w = PAGE_W - M - text_x
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 14.5)
    ny = y - 16
    for ln in _wrap(product.get("name", ""), "Helvetica-Bold", 14.5, name_w)[:3]:
        c.drawString(text_x, ny, ln)
        ny -= 18
    ny -= 4
    # key/value rows: label on the left, value directly to its right
    rows = [("ITEM CODE", product.get("code", ""))]
    if product.get("color"):
        rows.append(("COLOUR", product["color"]))
    rows.append(("MARKET", MARKET_LABEL.get(market, market)))
    rows.append(("BRANDING AREAS", str(len(areas))))
    label_w = 105.0
    for label, value in rows:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColorRGB(*GREY)
        c.drawString(text_x, ny, label)
        c.setFont("Helvetica", 10.5)
        c.setFillColorRGB(*INK)
        c.drawString(text_x + label_w, ny - 0.5, str(value))
        ny -= 16
    y = min(y - img_box, ny) - 26 if reader else ny - 22

    # ---------- section label ----------
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(*ORANGE)
    c.drawString(M, y, " ".join("BRANDING AREAS & PRINTING METHODS"))
    y -= 16

    # ---------- area cards ----------
    pad = 14.0
    view_w, view_h = 208.0, 152.0
    info_x_off = view_w + pad * 2
    info_w = PAGE_W - 2 * M - info_x_off - pad
    lbl_w = 108.0

    for idx, area in enumerate(areas):
        spec_rows: list[tuple[str, str]] = []
        w_mm, h_mm = area.get("areaWidthMm"), area.get("areaHeightMm")
        if w_mm and h_mm:
            spec_rows.append(("Maximum branding size", f"{w_mm} × {h_mm} mm"))
        if area.get("methods"):
            spec_rows.append(("Printing methods", " · ".join(area["methods"])))
        if area.get("colorChoices"):
            spec_rows.append(("Colour options", area["colorChoices"]))
        if area.get("leadTime"):
            spec_rows.append(("Estimated lead time", f"{area['leadTime']} (estimate)"))
        spec_rows.append(("Placement", "Confirmed at artwork review"))

        # measure rows (values wrap)
        row_heights = []
        for _label, value in spec_rows:
            n = len(_wrap(value, "Helvetica", 10, info_w - lbl_w))
            row_heights.append(max(1, n) * 13 + 8)
        info_h = 22 + sum(row_heights)
        card_h = max(view_h, info_h) + 2 * pad

        if y - card_h < FOOTER_H:
            doc.new_page()
            y = PAGE_H - M

        top = y
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(1)
        c.roundRect(M, top - card_h, PAGE_W - 2 * M, card_h, 12, stroke=1, fill=0)

        # area view image + rectangle
        img = area.get("image") or {}
        img_reader = None
        if img.get("data"):
            img_reader, inw, inh = _image_reader(img["data"])
        vx, vy = M + pad, top - pad - view_h
        if img_reader:
            dw, dh, scale = _contain(inw, inh, view_w, view_h)
            ix, iy = vx + (view_w - dw) / 2, vy + (view_h - dh) / 2
            c.drawImage(img_reader, ix, iy, width=dw, height=dh, mask="auto")
            rect = area.get("rect")
            if rect:
                rx = ix + rect["left"] * scale
                ry = iy + dh - (rect["top"] + rect["height"]) * scale  # top-left → bottom-left
                rw, rh = rect["width"] * scale, rect["height"] * scale
                c.saveState()
                c.setFillColorRGB(*ORANGE)
                c.setFillAlpha(0.12)
                c.rect(rx, ry, rw, rh, stroke=0, fill=1)
                c.restoreState()
                c.setStrokeColorRGB(*ORANGE)
                c.setLineWidth(1.6)
                c.setDash(5, 4)
                c.rect(rx, ry, rw, rh, stroke=1, fill=0)
                c.setDash()
                if w_mm and h_mm:
                    tag = f"{w_mm} × {h_mm} mm"
                    tw = stringWidth(tag, "Helvetica-Bold", 6.5) + 8
                    ty = ry + rh + 3 if ry + rh + 14 < vy + view_h else ry - 14
                    c.setFillColorRGB(*ORANGE)
                    c.roundRect(rx, ty, tw, 11, 2, stroke=0, fill=1)
                    c.setFillColorRGB(1, 1, 1)
                    c.setFont("Helvetica-Bold", 6.5)
                    c.drawString(rx + 4, ty + 3, tag)
        else:
            c.setFillColorRGB(0.965, 0.953, 0.937)
            c.roundRect(vx, vy, view_w, view_h, 8, stroke=0, fill=1)
            c.setFont("Helvetica", 8.5)
            c.setFillColorRGB(*GREY)
            c.drawCentredString(vx + view_w / 2, vy + view_h / 2 - 3, "Area image unavailable")

        # info column: label left, value right of it
        info_x = M + info_x_off
        iy2 = top - pad - 14
        c.setFont("Helvetica-Bold", 12.5)
        c.setFillColorRGB(*INK)
        c.drawString(info_x, iy2, (area.get("name") or f"Branding area {idx + 1}").title()[:60])
        iy2 -= 18
        for (label, value), rh_row in zip(spec_rows, row_heights):
            c.setFont("Helvetica-Bold", 8)
            c.setFillColorRGB(*GREY)
            c.drawString(info_x, iy2 - 9, label)
            c.setFont("Helvetica", 10)
            c.setFillColorRGB(*INK)
            vy2 = iy2 - 9
            for ln in _wrap(value, "Helvetica", 10, info_w - lbl_w):
                c.drawString(info_x + lbl_w, vy2, ln)
                vy2 -= 13
            iy2 -= rh_row
            c.setStrokeColorRGB(0.941, 0.925, 0.902)
            c.setLineWidth(0.7)
            c.line(info_x, iy2 + 3, info_x + info_w, iy2 + 3)

        y = top - card_h - 14

    if not areas:
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(*GREY)
        c.drawString(M, y - 10, "Branding details for this product are provided on request.")
        y -= 30

    doc.final_footer(y)
    c.setTitle(f"{product.get('code', 'Product')} — Printing Manual")
    c.setAuthor("Elite Marcom")
    c.showPage()
    c.save()
    return buf.getvalue()


def generated_at() -> int:
    return int(time.time())
