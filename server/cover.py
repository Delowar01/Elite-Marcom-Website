"""The approved Elite Marcom catalogue cover, drawn in ReportLab.

This is a **translation, not a design**. Every number in it comes from
`docs/catalogue-cover-master.md` — the approved master's implementation map —
and the master's own HTML and PDF are the authority for anything this file
does not say. Nothing here may be improved, rounded off or re-judged: a
coordinate that looks odd is a coordinate that was measured.

Three rules the translation keeps.

**Only two things are raster.** The official wordmark and the branded hero
photograph are images because they are photographs and artwork; the
background, the orange field, the watermark, every letter, the metadata band,
its icons and its rules are vector or text. The page stays searchable, scales
without pixels, and does not carry a flattened picture of itself.

**The hero is supplied, not composed.** The seven product applications in it
— backpack, tote, bottle, two notebooks, power bank, pen — were projected
from the official artwork and audited once, in the master. They are not
recreated here and must never be: `scripts/build_cover_assets.py` lifts the
approved composition straight out of the master and this module draws it.

**What is behind the hero is baked into it.** The hero is 210 mm wide and
most of it is transparent, so the gradient, the orange field and the
watermark show through. ReportLab can draw a JPEG or an alpha channel but
not both, and the alpha channel route costs 7.75 MB of Flate-compressed
pixels against 0.6 MB of JPEG — on a one-product catalogue that is the
difference between a document somebody can email and one they cannot. So the
build script composites the hero over exactly the three layers beneath it,
computed from the constants in this file, and the result is drawn opaque.
The page still carries those layers as vector everywhere else; the band
simply gets them as pixels that are identical by construction.
"""
from __future__ import annotations

import io
import pathlib
import re

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------- the page ----------------

PAGE_W_MM = 210.0
PAGE_H_MM = 297.0

#: Brand tokens. These are the master's, and the orange heading's 3.229:1
#: against pure white is why it may sit nowhere else.
ORANGE = "#E56C25"
NAVY = "#02004C"
MUTED = "#6B6A75"
LINE = "#D9D5D0"
SHADOW = "#A7917E"

# ---------------- the two surfaces beneath everything ----------------

#: A restrained white-to-Ground fall, beginning only below the heading, so
#: the whole title sits on pure white.
GROUND_AXIS = ((0.0, 96.0), (0.0, 136.0))
GROUND_STOPS = ((0.00, "#FFFFFF"), (0.55, "#FAF8F5"), (1.00, "#F4F2F0"))

#: The orange field, in page top-left millimetres. Two cubics and a straight
#: run; do not approximate it with a polygon.
FIELD_PATH = "M152 0 C146 28 146 53 140 80 C134 108 121 138 108 151 L55 250.555 H210 V0 Z"
FIELD_AXIS = ((112.0, 0.0), (210.0, 65.0))
FIELD_STOPS = ((0.00, "#F4C09A"), (0.40, "#ED9458"), (0.76, "#E56C25"), (1.00, "#DE6423"))

#: A very faint symbol, clipped to the field. Its 12 mm right bleed is
#: deliberate and is cropped by the page.
WATERMARK_BOX = (126.0, 39.0, 96.0, 96.0)
WATERMARK_ALPHA = 0.075

# ---------------- the two raster assets ----------------

#: 57 mm wide; the height is the source's own 518/1629 ratio and nothing
#: else. The wordmark is never re-typeset, traced or recoloured.
LOGO_BOX = (16.0, 12.0, 57.0, 57.0 * 518.0 / 1629.0)
LOGO_SHA256 = "38cb42d7034a0bec3082aa9dab27afc66d4eea8c2d8a78d3a13e0c57ecfeaeb7"

#: Locked. A later hero may replace the file inside this box at this aspect
#: ratio (1024:700); it may not move the box.
HERO_BOX = (0.0, 107.0, 210.0, 143.5546875)

DATA_DIR = pathlib.Path(__file__).parent / "data"
COVER_DIR = DATA_DIR / "cover"
FONT_DIR = DATA_DIR / "fonts"

# ---------------- type ----------------

REGULAR, MEDIUM, SEMIBOLD = "Poppins", "Poppins-Medium", "Poppins-SemiBold"
#: Only if a deploy has lost the files. The cover then sets in the standard
#: fonts rather than failing, and `fonts_ready()` says so.
_FALLBACK = {REGULAR: "Helvetica", MEDIUM: "Helvetica", SEMIBOLD: "Helvetica-Bold"}
_FONT_FILES = {REGULAR: "Poppins-Regular.ttf", MEDIUM: "Poppins-Medium.ttf",
               SEMIBOLD: "Poppins-SemiBold.ttf"}
_registered: dict[str, bool] = {}


def fonts_ready() -> bool:
    """Whether the cover can set in Poppins. Registration is attempted once
    per process and remembered either way."""
    if not _registered:
        for name, file in _FONT_FILES.items():
            path = FONT_DIR / file
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                _registered[name] = True
            except Exception:
                _registered[name] = False
    return all(_registered.values())


def font(name: str) -> str:
    fonts_ready()
    return name if _registered.get(name) else _FALLBACK[name]


#: (font, size pt, tracking mm). Tracking is CSS letter-spacing: it is added
#: after every character including the last, which is why a right-aligned
#: string measures wider than its ink.
TYPE = {
    "market": (REGULAR, 9.0, 0.38),
    "eyebrow": (MEDIUM, 12.0, 1.34),
    #: -0.035 em at 59.5 pt
    "title": (SEMIBOLD, 59.5, -2.0825 / 72 * 25.4),
    "subtitle": (REGULAR, 14.0, 0.5),
    "promise": (MEDIUM, 7.4, 0.38),
    "label": (MEDIUM, 7.7, 0.24),
    "value": (SEMIBOLD, 12.5, -0.12),
    "stock": (SEMIBOLD, 11.2, -0.14),
    "disclaimer": (REGULAR, 10.0, 0.0),
    "website": (REGULAR, 10.0, 0.0),
}

#: Baselines measured from the approved PDF, top of page to baseline.
EYEBROW_TEXT = "CORPORATE GIFTS"
TITLE_LINES = (("PRODUCT", 66.135, NAVY), ("CATALOGUE", 86.508, ORANGE))
TITLE_X = 15.4
MARKET_BASELINE = 19.039
MARKET_RIGHT = 194.0
EYEBROW_BASELINE = 45.762
SUBTITLE_BASELINE = 98.679
PROMISE_BASELINE = 106.881
PROMISE_TEXT = ("PREMIUM GIFTS", "STRONGER BRANDS", "LASTING IMPRESSIONS")
RULE_BOX = (16.0, 90.5, 14.0, 0.8)
MARGIN = 16.0
FOOT_MARGIN = 12.0

# ---------------- the metadata band ----------------

BAND_BOX = (12.0, 253.2, 186.0, 20.2)
BAND_RADIUS = 4.0
BAND_SHADOWS = (  # (x, top, w, h, radius, alpha) relative to (10.8, 252.4)
    (0.0, 1.4, 188.4, 20.2, 5.2, 0.022),
    (0.6, 0.8, 187.2, 20.2, 4.6, 0.026),
    (1.2, 0.2, 186.0, 20.2, 4.0, 0.018),
)
BAND_SHADOW_ORIGIN = (10.8, 252.4)
COLUMN_X = (12.0, 69.0, 126.0)
TEXT_X = (30.0, 87.0, 144.0)
ICON_X = (17.0, 74.0, 131.0)
ICON_TOP = 259.1
ICON_SIZE = 8.0
CIRCLE_X = (14.5, 71.5, 128.5)
CIRCLE_TOP = 256.6
CIRCLE_D = 13.0
DIVIDER_X = (69.0, 126.0)
DIVIDER_TOP = 257.3
DIVIDER_W = 0.25
DIVIDER_H = 12.0
LABEL_BASELINE = 259.810
VALUE_BASELINE = 266.160

DISCLAIMER = ("Quantities reflect the stock update shown above and are not reserved.",
              "Confirm availability before committing to a quantity.")
DISCLAIMER_BASELINES = (279.389, 284.152)
WEBSITE_BASELINE = 291.560
WEBSITE_RIGHT = 198.0
WEBSITE_TEXT = "www.elitemarcom.com"
WEBSITE_URL = "https://www.elitemarcom.com"

#: The three icons, in their own 24 x 24 viewBox with a 1.6 stroke and round
#: joins, exactly as the master draws them. Never an emoji, never a font.
ICON_STROKE = 1.6
ICONS = {
    "cube": ["m12 2 9 5v10l-9 5-9-5V7Z", "M3 7l9 5 9-5", "M12 12v10", "M7.5 4.5l9 5"],
    #: the body is a rounded rectangle and the dial a circle — primitives,
    #: not paths, because that is what the master draws
    "calendar": ["M7 2v6", "M17 2v6", "M3 11h18", "M7 15h2", "M15 15h2",
                 "M7 18h2", "M15 18h2"],
    "clock": ["M12 6v6l5 3"],
}


# ---------------- coordinates ----------------

def y_from_top(top_mm: float) -> float:
    """Page y for a distance measured down from the top edge."""
    return (PAGE_H_MM - top_mm) * mm


def rect_from_top(x: float, top: float, w: float, h: float):
    return x * mm, (PAGE_H_MM - (top + h)) * mm, w * mm, h * mm


def text_width(text: str, kind: str) -> float:
    """Advance width in mm, with the trailing tracking CSS also adds."""
    name, size, track = TYPE[kind]
    return pdfmetrics.stringWidth(text, font(name), size) / mm + track * len(text)


def draw_tracked(c, x_mm: float, baseline_mm: float, text: str, kind: str,
                 colour: str) -> float:
    """One run of letterspaced text; returns its advance width in mm.

    Character spacing is page state, so it is always put back: a tracked
    label that forgets leaves every later string on the page letterspaced,
    drawing wider than it was measured for.
    """
    name, size, track = TYPE[kind]
    t = c.beginText()
    t.setTextOrigin(x_mm * mm, y_from_top(baseline_mm))
    t.setFont(font(name), size)
    t.setFillColor(HexColor(colour))
    t.setCharSpace(track * mm)
    t.textOut(text)
    t.setCharSpace(0)
    c.drawText(t)
    return text_width(text, kind)


# ---------------- the orange contour ----------------

_NUM = re.compile(r"-?\d*\.?\d+")


def field_path_points(steps: int = 96) -> list[tuple[float, float]]:
    """The contour flattened to a polyline, in page top-left mm.

    The build script fills this with PIL, which has no Béziers; ReportLab
    draws the real curves. Both read the same string, so they cannot drift.
    """
    n = [float(v) for v in _NUM.findall(FIELD_PATH)]
    start = (n[0], n[1])
    curves = [((n[2], n[3]), (n[4], n[5]), (n[6], n[7])),
              ((n[8], n[9]), (n[10], n[11]), (n[12], n[13]))]
    out = [start]
    here = start
    for c1, c2, end in curves:
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            out.append((
                u ** 3 * here[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * end[0],
                u ** 3 * here[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * end[1]))
        here = end
    out.append((n[14], n[15]))                # L 55 250.555
    out.append((n[16], n[15]))                # H 210
    out.append((n[16], start[1]))             # V 0
    return out


def _field_clip(c) -> None:
    """Set the current clip to the orange field."""
    n = [float(v) for v in _NUM.findall(FIELD_PATH)]
    p = c.beginPath()
    p.moveTo(n[0] * mm, y_from_top(n[1]))
    p.curveTo(n[2] * mm, y_from_top(n[3]), n[4] * mm, y_from_top(n[5]),
              n[6] * mm, y_from_top(n[7]))
    p.curveTo(n[8] * mm, y_from_top(n[9]), n[10] * mm, y_from_top(n[11]),
              n[12] * mm, y_from_top(n[13]))
    p.lineTo(n[14] * mm, y_from_top(n[15]))
    p.lineTo(n[16] * mm, y_from_top(n[15]))
    p.lineTo(n[16] * mm, y_from_top(n[1]))
    p.close()
    c.clipPath(p, stroke=0, fill=0)


def _shade(c, axis, stops) -> None:
    (x0, t0), (x1, t1) = axis
    c.linearGradient(x0 * mm, y_from_top(t0), x1 * mm, y_from_top(t1),
                     [HexColor(s[1]) for s in stops], [s[0] for s in stops],
                     extend=True)


def lerp_stops(stops, t: float) -> tuple[int, int, int]:
    """The gradient's colour at `t`, with the end colours extended. The build
    script's PIL bake and ReportLab's axial shading must agree, so there is
    one implementation of the interpolation and this is it."""
    t = min(1.0, max(0.0, t))
    last = stops[0]
    for stop in stops:
        if t <= stop[0]:
            if stop[0] == last[0]:
                return _rgb(stop[1])
            f = (t - last[0]) / (stop[0] - last[0])
            a, b = _rgb(last[1]), _rgb(stop[1])
            return tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))
        last = stop
    return _rgb(stops[-1][1])


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------- assets ----------------

_assets: dict[str, object] = {}


def _reader(name: str):
    """An ImageReader for one cover asset, read once per process.

    A PNG is handed to reportlab **as it is**, so its alpha becomes a soft
    mask: the wordmark keeps its transparent ground and the watermark is a
    white symbol rather than a white rectangle. `exports._image_box` is the
    wrong tool here — it flattens alpha onto white, which on a white page
    makes the watermark disappear entirely. The hero is a JPEG and goes
    through the usual passthrough.
    """
    if name not in _assets:
        from reportlab.lib.utils import ImageReader

        from .exports import _image_box

        path = COVER_DIR / name
        try:
            raw = path.read_bytes()
            if name.endswith(".png"):
                from PIL import Image

                with Image.open(io.BytesIO(raw)) as probe:
                    size = probe.size
                _assets[name] = (ImageReader(io.BytesIO(raw)), size[0], size[1])
            else:
                _assets[name] = _image_box(raw)
        except Exception:
            _assets[name] = (None, 0, 0)
    return _assets[name]


def assets_ready() -> bool:
    return all((COVER_DIR / n).exists()
               for n in ("logo.png", "watermark.png", "hero.jpg"))


# ---------------- the icons ----------------

def _icon_path(c, commands: list[str], x: float, top: float, size: float) -> None:
    """Draw one 24-unit icon at `size` mm. Only the commands the three icons
    actually use are understood; a new icon adds its command here rather than
    arriving as a surprise at render time."""
    scale = size / 24.0
    px = lambda u: (x + u * scale) * mm
    py = lambda v: y_from_top(top + v * scale)
    c.setLineWidth(ICON_STROKE * scale * mm)
    c.setStrokeColor(HexColor(ORANGE))
    c.setLineCap(1)
    c.setLineJoin(1)
    for d in commands:
        p = c.beginPath()
        here = (0.0, 0.0)
        start = (0.0, 0.0)
        tokens = re.findall(r"[MmLlHhVvCcZz]|-?\d*\.?\d+", d)
        i = 0
        cmd = ""
        while i < len(tokens):
            if tokens[i].isalpha():
                cmd = tokens[i]
                i += 1
                if cmd in "Zz":
                    p.close()
                    here = start
                    continue
            rel = cmd.islower()
            up = cmd.upper()
            if up == "M":
                nx, ny = float(tokens[i]), float(tokens[i + 1])
                i += 2
                here = (here[0] + nx, here[1] + ny) if rel else (nx, ny)
                start = here
                p.moveTo(px(here[0]), py(here[1]))
                cmd = "l" if rel else "L"     # SVG: an implicit lineto follows
            elif up == "L":
                nx, ny = float(tokens[i]), float(tokens[i + 1])
                i += 2
                here = (here[0] + nx, here[1] + ny) if rel else (nx, ny)
                p.lineTo(px(here[0]), py(here[1]))
            elif up == "H":
                nx = float(tokens[i])
                i += 1
                here = (here[0] + nx, here[1]) if rel else (nx, here[1])
                p.lineTo(px(here[0]), py(here[1]))
            elif up == "V":
                ny = float(tokens[i])
                i += 1
                here = (here[0], here[1] + ny) if rel else (here[0], ny)
                p.lineTo(px(here[0]), py(here[1]))
            elif up == "C":
                vals = [float(v) for v in tokens[i:i + 6]]
                i += 6
                pts = []
                for k in range(0, 6, 2):
                    cx, cy = vals[k], vals[k + 1]
                    pts.append((here[0] + cx, here[1] + cy) if rel else (cx, cy))
                p.curveTo(px(pts[0][0]), py(pts[0][1]), px(pts[1][0]), py(pts[1][1]),
                          px(pts[2][0]), py(pts[2][1]))
                here = pts[2]
            else:                              # pragma: no cover - defensive
                raise ValueError(f"unsupported icon command {cmd!r}")
        c.drawPath(p, stroke=1, fill=0)


def _draw_icon(c, kind: str, x: float, top: float) -> None:
    """One metadata icon, in its own 24-unit space scaled to 8 mm."""
    scale = ICON_SIZE / 24.0
    unit = lambda u: u * scale
    c.saveState()
    c.setLineWidth(ICON_STROKE * scale * mm)
    c.setStrokeColor(HexColor(ORANGE))
    c.setLineCap(1)
    c.setLineJoin(1)
    if kind == "clock":
        c.circle((x + unit(12)) * mm, y_from_top(top + unit(12)),
                 unit(9.5) * mm, stroke=1, fill=0)
    elif kind == "calendar":
        c.roundRect((x + unit(3)) * mm, y_from_top(top + unit(22)),
                    unit(18) * mm, unit(17) * mm, unit(1) * mm, stroke=1, fill=0)
    _icon_path(c, ICONS[kind], x, top, ICON_SIZE)
    c.restoreState()


# ---------------- the cover ----------------

def draw(c, *, market: str, country: str, year: str, count_text: str,
         prepared_text: str, stock_text: str) -> None:
    """Paint the approved cover onto a fresh A4 page, in the master's order.

    Only the six strings this takes change between catalogues. The wording,
    the geometry and the artwork are the approved design and are the same on
    a one-product catalogue and a five-hundred-product one — which is the
    point: a client recognises the cover before they read it.
    """
    fonts_ready()

    # 1. the page, and the restrained fall to Ground below the heading
    c.saveState()
    page = c.beginPath()
    page.rect(0, 0, PAGE_W_MM * mm, PAGE_H_MM * mm)
    c.clipPath(page, stroke=0, fill=0)
    _shade(c, GROUND_AXIS, GROUND_STOPS)
    c.restoreState()

    # 2. the orange field
    c.saveState()
    _field_clip(c)
    _shade(c, FIELD_AXIS, FIELD_STOPS)
    # 3. the watermark, inside the same clip
    reader = _reader("watermark.png")
    if reader[0] is not None:
        c.setFillAlpha(WATERMARK_ALPHA)
        wx, wtop, ww, wh = WATERMARK_BOX
        c.drawImage(reader[0], *rect_from_top(wx, wtop, ww, wh), mask="auto")
        c.setFillAlpha(1)
    c.restoreState()

    # 4. the branded hero. It carries the three layers above baked into it,
    #    so it is opaque and the band is identical to what it covers.
    hero = _reader("hero.jpg")
    if hero[0] is not None:
        c.drawImage(hero[0], *rect_from_top(*HERO_BOX), mask=None)

    # 5. the official wordmark and the market line
    logo = _reader("logo.png")
    if logo[0] is not None:
        c.drawImage(logo[0], *rect_from_top(*LOGO_BOX), mask="auto")
    header = f"{market} · {country}"
    draw_tracked(c, MARKET_RIGHT - text_width(header, "market"), MARKET_BASELINE,
                 header, "market", NAVY)

    # 6. the title block
    draw_tracked(c, MARGIN, EYEBROW_BASELINE, EYEBROW_TEXT, "eyebrow", NAVY)
    for text, baseline, colour in TITLE_LINES:
        draw_tracked(c, TITLE_X, baseline, text, "title", colour)
    c.setFillColor(HexColor(ORANGE))
    c.rect(*rect_from_top(*RULE_BOX), stroke=0, fill=1)

    x = MARGIN
    for n, part in enumerate((market, country, year)):
        if n:
            x += 2.8
            x += draw_tracked(c, x, SUBTITLE_BASELINE, "·", "subtitle", NAVY)
            x += 2.8
        x += draw_tracked(c, x, SUBTITLE_BASELINE, part, "subtitle", NAVY)

    x = MARGIN
    for n, part in enumerate(PROMISE_TEXT):
        if n:
            x += 1.6
            x += draw_tracked(c, x, PROMISE_BASELINE, "|", "promise", MUTED)
            x += 1.6
        x += draw_tracked(c, x, PROMISE_BASELINE, part, "promise", MUTED)

    # 7. three faint rectangles rather than a blurred shadow
    ox, otop = BAND_SHADOW_ORIGIN
    c.saveState()
    c.setFillColor(HexColor(SHADOW))
    for sx, stop, sw, sh, radius, alpha in BAND_SHADOWS:
        c.setFillAlpha(alpha)
        c.roundRect(*rect_from_top(ox + sx, otop + stop, sw, sh), radius * mm,
                    stroke=0, fill=1)
    c.restoreState()

    # 8. the band, its icon grounds, its rules, its icons and its facts
    c.saveState()
    c.setFillColor(Color(1, 1, 1, alpha=0.90))
    c.roundRect(*rect_from_top(*BAND_BOX), BAND_RADIUS * mm, stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    c.setFillColor(Color(1, 1, 1, alpha=0.95))
    for cx in CIRCLE_X:
        c.circle((cx + CIRCLE_D / 2) * mm, y_from_top(CIRCLE_TOP + CIRCLE_D / 2),
                 CIRCLE_D / 2 * mm, stroke=0, fill=1)
    c.restoreState()
    c.setFillColor(HexColor(LINE))
    for dx in DIVIDER_X:
        c.rect(*rect_from_top(dx, DIVIDER_TOP, DIVIDER_W, DIVIDER_H),
               stroke=0, fill=1)
    facts = ((f"{country} CATALOGUE", count_text, "cube", "value"),
             ("PREPARED", prepared_text, "calendar", "value"),
             ("STOCK UPDATED", stock_text, "clock", "stock"))
    for n, (label, value, icon, value_kind) in enumerate(facts):
        _draw_icon(c, icon, ICON_X[n], ICON_TOP)
        draw_tracked(c, TEXT_X[n], LABEL_BASELINE, label, "label", NAVY)
        draw_tracked(c, TEXT_X[n], VALUE_BASELINE, value, value_kind, NAVY)

    # 9. the fixed footing
    for line, baseline in zip(DISCLAIMER, DISCLAIMER_BASELINES):
        draw_tracked(c, FOOT_MARGIN, baseline, line, "disclaimer", MUTED)
    width = text_width(WEBSITE_TEXT, "website")
    left = WEBSITE_RIGHT - width
    draw_tracked(c, left, WEBSITE_BASELINE, WEBSITE_TEXT, "website", NAVY)
    c.linkURL(WEBSITE_URL,
              (left * mm, y_from_top(WEBSITE_BASELINE) - 1.2 * mm,
               WEBSITE_RIGHT * mm, y_from_top(WEBSITE_BASELINE) + 3.2 * mm),
              relative=0, thickness=0)
