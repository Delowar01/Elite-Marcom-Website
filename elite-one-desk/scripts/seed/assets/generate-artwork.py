"""
Artwork that ships with the seed.

Original geometric compositions rather than stock photography: licence-clean,
in the same visual language as the hero (fine line work, grids, arcs,
registration marks, one orange accent), and replaceable from the Media library
without touching code.

Drawn at 2x and downsampled, which is how the strokes get their anti-aliasing.
Every composition is centred with wide margins so one file crops cleanly to
16/9, 4/3 and 4/5 wherever it is placed.
"""
import math, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2                      # supersample factor
W = H = 1400
CW = CH = W * S
CX = CY = CW / 2
OUT = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

NAVY_DEEP = (7, 6, 28)
NAVY_MID = (21, 19, 72)
NAVY_TOP = (25, 22, 87)
ORANGE = (229, 108, 37)
PEACH = (255, 164, 118)
WARM = (248, 247, 244)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background():
    """Three-stop vertical wash, warmest at the top."""
    img = Image.new("RGB", (1, CH))
    px = img.load()
    for y in range(CH):
        t = y / (CH - 1)
        px[0, y] = lerp(NAVY_TOP, NAVY_MID, t / 0.52) if t < 0.52 else lerp(NAVY_MID, NAVY_DEEP, (t - 0.52) / 0.48)
    return img.resize((CW, CH))


def radial_mask(cx, cy, radius, inner=0.0, size=320):
    """Alpha ramp from `inner` (opaque) out to `radius` (transparent)."""
    small = Image.new("L", (size, size), 0)
    px = small.load()
    scale = CW / size
    for y in range(size):
        for x in range(size):
            d = math.hypot(x * scale - cx, y * scale - cy) / radius
            if d <= inner:
                px[x, y] = 255
            elif d < 1:
                t = (d - inner) / (1 - inner)
                px[x, y] = round(255 * (1 - t) ** 2)
    return small.resize((CW, CH), Image.BICUBIC)


def tint(base, colour, mask, strength=1.0):
    layer = Image.new("RGB", (CW, CH), colour)
    if strength < 1:
        mask = mask.point(lambda v: round(v * strength))
    return Image.composite(layer, base, mask)


def rgba(colour, alpha):
    return (*colour, round(255 * alpha))


class Canvas:
    def __init__(self, warmth=(0.5, 0.34, 0.78, 0.18)):
        self.img = background()
        cx, cy, r, strength = warmth
        self.img = tint(self.img, ORANGE, radial_mask(CW * cx, CH * cy, CW * r), strength)
        self.overlay = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.overlay)

    def grid(self, step=70, alpha=0.05):
        step *= S
        for x in range(0, CW + 1, step):
            self.d.line([(x, 0), (x, CH)], fill=rgba(WARM, alpha), width=S)
        for y in range(0, CH + 1, step):
            self.d.line([(0, y), (CW, y)], fill=rgba(WARM, alpha), width=S)

    def line(self, pts, colour, alpha, width=1.4, dash=None):
        pts = [(x * S, y * S) for x, y in pts]
        if not dash:
            self.d.line(pts, fill=rgba(colour, alpha), width=max(1, round(width * S)), joint="curve")
            return
        on, off = dash[0] * S, dash[1] * S
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            seg = math.hypot(x2 - x1, y2 - y1)
            pos = 0.0
            while pos < seg:
                end = min(pos + on, seg)
                self.d.line(
                    [(x1 + (x2 - x1) * pos / seg, y1 + (y2 - y1) * pos / seg),
                     (x1 + (x2 - x1) * end / seg, y1 + (y2 - y1) * end / seg)],
                    fill=rgba(colour, alpha), width=max(1, round(width * S)))
                pos = end + off

    def curve(self, p0, p1, p2, colour, alpha, width=1.4, dash=None, taper=False):
        """Quadratic Bézier, flattened. `taper` fades the stroke along its run."""
        pts = []
        for i in range(81):
            t = i / 80
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            pts.append((x, y))
        if not taper:
            self.line(pts, colour, alpha, width, dash)
            return
        for i in range(len(pts) - 1):
            t = i / (len(pts) - 2)
            fade = min(1.0, t * 3.2) * (1 - max(0.0, (t - 0.62) / 0.38) * 0.8)
            self.line([pts[i], pts[i + 1]], colour, alpha * fade, width)

    def arc(self, cx, cy, r, start, end, colour, alpha, width=1.4, dash=None):
        pts = []
        steps = max(24, int(abs(end - start) / 2))
        for i in range(steps + 1):
            a = math.radians(start + (end - start) * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.line(pts, colour, alpha, width, dash)

    def circle(self, cx, cy, r, stroke=None, alpha=1.0, width=1.4, fill=None, fill_alpha=0.0):
        box = [(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S]
        if fill:
            self.d.ellipse(box, fill=rgba(fill, fill_alpha))
        if stroke:
            self.d.ellipse(box, outline=rgba(stroke, alpha), width=max(1, round(width * S)))

    def rect(self, x, y, w, h, stroke=None, alpha=1.0, width=1.4, fill=None, fill_alpha=0.0, radius=0):
        box = [x * S, y * S, (x + w) * S, (y + h) * S]
        kw = {}
        if fill:
            kw["fill"] = rgba(fill, fill_alpha)
        if stroke:
            kw["outline"] = rgba(stroke, alpha)
            kw["width"] = max(1, round(width * S))
        if radius:
            self.d.rounded_rectangle(box, radius=radius * S, **kw)
        else:
            self.d.rectangle(box, **kw)

    def poly(self, pts, stroke=None, alpha=1.0, width=1.4, fill=None, fill_alpha=0.0):
        pts = [(x * S, y * S) for x, y in pts]
        if fill:
            self.d.polygon(pts, fill=rgba(fill, fill_alpha))
        if stroke:
            self.d.line(pts + [pts[0]], fill=rgba(stroke, alpha), width=max(1, round(width * S)), joint="curve")

    def dot(self, x, y, r=5, colour=PEACH, alpha=0.85):
        self.circle(x, y, r, fill=colour, fill_alpha=alpha)

    def plane(self, x, y, angle, size=1.0, colour=ORANGE):
        shape = [(-22, -2), (20, -19), (11, -2), (20, 16), (9, 11), (2, 18), (0, 9), (-9, 7), (-3, 2)]
        a = math.radians(angle)
        pts = [(x + (px * math.cos(a) - py * math.sin(a)) * size,
                y + (px * math.sin(a) + py * math.cos(a)) * size) for px, py in shape]
        self.poly(pts, fill=colour, fill_alpha=1.0)

    def ticks(self):
        m, s = 92, 34
        for path in ([(m, m + s), (m, m), (m + s, m)],
                     [(W - m - s, m), (W - m, m), (W - m, m + s)],
                     [(m, H - m - s), (m, H - m), (m + s, H - m)],
                     [(W - m, H - m - s), (W - m, H - m), (W - m - s, H - m)]):
            self.line(path, WARM, 0.22, 1.6)

    def label(self, text):
        font = ImageFont.truetype(FONT, 21 * S)
        spaced = " ".join(text)
        box = self.d.textbbox((0, 0), spaced, font=font)
        self.d.text(((CW - (box[2] - box[0])) / 2, (H - 116) * S), spaced,
                    font=font, fill=rgba(WARM, 0.3))

    def finish(self, label):
        self.ticks()
        self.label(label)
        # Soft bloom on the accent work, then the vignette last.
        glow = self.overlay.filter(ImageFilter.GaussianBlur(9 * S))
        base = Image.alpha_composite(self.img.convert("RGBA"), glow.point(lambda v: round(v * 0.42)))
        base = Image.alpha_composite(base, self.overlay)
        out = base.convert("RGB")
        shade = radial_mask(CX, CH * 0.46, CW * 0.92, inner=0.66).point(lambda v: round((255 - v) * 0.66))
        out = Image.composite(Image.new("RGB", (CW, CH), NAVY_DEEP), out, shade)
        return out.resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------------------
# Compositions
# --------------------------------------------------------------------------
CXp = CYp = W / 2   # page-space centre


def travel():
    c = Canvas(); c.grid()
    hub = (CXp, CYp + 30)
    c.circle(*hub, 330, WARM, 0.12)
    for i in range(9):
        a = math.radians(i * 40)
        c.line([(hub[0] + 238 * math.cos(a), hub[1] + 238 * math.sin(a) * 0.3),
                (hub[0] + 330 * math.cos(a), hub[1] + 330 * math.sin(a) * 0.3)], WARM, 0.1)
    pts = [(hub[0] + 330 * math.cos(math.radians(t)), hub[1] + 330 * 0.3 * math.sin(math.radians(t)))
           for t in range(0, 361, 4)]
    c.line(pts, WARM, 0.14)
    nodes = [(390, 470), (1010, 428), (352, 884), (1040, 900), (700, 320)]
    for i, (x, y) in enumerate(nodes):
        mid = ((hub[0] + x) / 2, (hub[1] + y) / 2 - 150 - i * 22)
        c.curve(hub, mid, (x, y), WARM, 0.2, 1.4, dash=(5, 9))
        c.dot(x, y, 5, WARM, 0.4)
    hot = (1010, 428)
    mid = ((hub[0] + hot[0]) / 2, (hub[1] + hot[1]) / 2 - 196)
    c.curve(hub, mid, hot, ORANGE, 0.95, 3.4, taper=True)
    c.circle(*hub, 9, fill=ORANGE, fill_alpha=1)
    c.circle(*hub, 20, ORANGE, 0.45, 1.6)
    c.plane(hot[0], hot[1], -36, 1.05)
    return c.finish("ROUTES")


def business():
    c = Canvas(); c.grid()
    base = CYp + 250
    heights = [180, 268, 352, 470, 300]
    w, gap = 86, 42
    total = len(heights) * w + (len(heights) - 1) * gap
    x = CXp - total / 2
    lit_index = 3
    for i, h in enumerate(heights):
        lit = i == lit_index
        col, alpha = (ORANGE, 1.0) if lit else (WARM, 0.16)
        if lit:
            c.rect(x, base - h, w, h, fill=ORANGE, fill_alpha=0.08, radius=8)
        c.rect(x, base - h, w, h, col, alpha, 2.4 if lit else 1.4, radius=8)
        for row in range(1, int(h // 54)):
            c.line([(x + 16, base - row * 54), (x + w - 16, base - row * 54)], col, 0.35 if lit else 0.09)
        if lit:
            top = base - h
            c.dot(x + w / 2, top - 34, 7, ORANGE, 1)
            c.circle(x + w / 2, top - 34, 17, ORANGE, 0.5, 1.6)
        x += w + gap
    c.line([(CXp - total / 2 - 70, base), (CXp + total / 2 + 70, base)], WARM, 0.3, 1.6)
    c.line([(CXp - total / 2 - 40, base + 22), (CXp + total / 2 + 40, base + 22)], WARM, 0.12)
    start = (CXp - total / 2 + w / 2, base - 180 - 40)
    end = (CXp + total / 2 - w / 2 - (w + gap), base - 470 - 62)
    c.curve(start, ((start[0] + end[0]) / 2, start[1] - 150), end, PEACH, 0.45, 1.6, dash=(4, 9))
    return c.finish("LICENSING")


def formation():
    c = Canvas(); c.grid()
    cy = CYp - 30
    for i, size in enumerate([560, 452, 344]):
        ang = -9 + i * 4
        half = size / 2
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
        a = math.radians(ang)
        pts = [(CXp + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a))
               for px, py in corners]
        c.poly(pts, WARM, 0.15 + i * 0.03, 1.4)
    c.rect(CXp - 118, cy - 118, 236, 236, ORANGE, 1.0, 2.6, fill=ORANGE, fill_alpha=0.08, radius=16)
    for i, y in enumerate([-58, 0, 58]):
        width = 132 - abs(i - 1) * 34
        c.line([(CXp - width / 2, cy + y), (CXp + width / 2, cy + y)], PEACH, 0.55 - i * 0.12, 2.2)
    c.circle(CXp, cy, 330, PEACH, 0.16, 1.2)
    for t in range(0, 360, 30):
        a = math.radians(t)
        c.line([(CXp + 322 * math.cos(a), cy + 322 * math.sin(a)),
                (CXp + 338 * math.cos(a), cy + 338 * math.sin(a))], PEACH, 0.3)
    return c.finish("FORMATION")


def documents():
    c = Canvas(); c.grid()
    for i in range(4):
        off = (3 - i) * 34
        lit = i == 3
        x, y, w, h = CXp - 250 + off * 0.5, CYp - 250 + off, 500, 330
        c.rect(x, y, w, h, None, fill=NAVY_MID, fill_alpha=0.55 + i * 0.14, radius=20)
        c.rect(x, y, w, h, ORANGE if lit else WARM, 1.0 if lit else 0.13, 2.4 if lit else 1.3, radius=20)
        if not lit:
            continue
        c.circle(x + 80, y + 98, 34, PEACH, 0.7, 2)
        c.curve((x + 44, y + 168), (x + 80, y + 122), (x + 116, y + 168), PEACH, 0.55, 2)
        for r, wd in enumerate([258, 208, 168]):
            c.rect(x + 154, y + 72 + r * 40, wd, 10, None, fill=WARM, fill_alpha=0.28 - r * 0.07, radius=5)
        c.rect(x + 44, y + 220, w - 88, 10, None, fill=ORANGE, fill_alpha=0.55, radius=5)
        c.rect(x + 44, y + 256, (w - 88) * 0.62, 10, None, fill=WARM, fill_alpha=0.14, radius=5)
    return c.finish("DOCUMENTATION")


def renewal():
    c = Canvas(); c.grid()
    cy = CYp - 20
    for i, r in enumerate([268, 196, 124]):
        c.arc(CXp, cy, r, -60, 190 - i * 26, WARM, 0.16 - i * 0.035, 1.4)
    c.arc(CXp, cy, 340, -46, 162, ORANGE, 0.95, 3.4)
    a = math.radians(162)
    hx, hy = CXp + 340 * math.cos(a), cy + 340 * math.sin(a)
    ang = math.degrees(a) + 90
    pts = [(0, -24), (16, 4), (-16, 4)]
    ar = math.radians(ang)
    c.poly([(hx + px * math.cos(ar) - py * math.sin(ar), hy + px * math.sin(ar) + py * math.cos(ar))
            for px, py in pts], fill=ORANGE, fill_alpha=1)
    c.arc(CXp, cy, 340, 175, 300, WARM, 0.1, 1.4)
    c.circle(CXp, cy, 66, ORANGE, 0.5, 1.8, fill=ORANGE, fill_alpha=0.08)
    c.line([(CXp - 24, cy - 2), (CXp - 6, cy + 17), (CXp + 26, cy - 20)], PEACH, 0.9, 3.4)
    for t in range(0, 360, 15):
        ta = math.radians(t)
        c.line([(CXp + 386 * math.cos(ta), cy + 386 * math.sin(ta)),
                (CXp + (400 if t % 45 == 0 else 394) * math.cos(ta), cy + (400 if t % 45 == 0 else 394) * math.sin(ta))],
               WARM, 0.2 if t % 45 == 0 else 0.1)
    return c.finish("RENEWAL")


def government():
    c = Canvas(); c.grid()
    base, top, span = CYp + 246, CYp - 176, 520
    c.line([(CXp - span / 2 - 46, top), (CXp, top - 128), (CXp + span / 2 + 46, top),
            (CXp - span / 2 - 46, top)], WARM, 0.24, 1.6)
    c.rect(CXp - span / 2 - 56, top + 6, span + 112, 30, WARM, 0.22, 1.5, radius=6)
    cols = 5
    for i in range(cols):
        x = CXp - span / 2 + i * (span / (cols - 1))
        lit = i == 2
        col, alpha = (ORANGE, 1.0) if lit else (WARM, 0.16)
        if lit:
            c.rect(x - 22, top + 44, 44, base - top - 44, None, fill=ORANGE, fill_alpha=0.07, radius=6)
        c.rect(x - 22, top + 44, 44, base - top - 44, col, alpha, 2.4 if lit else 1.4, radius=6)
        for fl in (-11, 0, 11):
            c.line([(x + fl, top + 58), (x + fl, base - 14)], col, 0.3 if lit else 0.07)
    c.line([(CXp - span / 2 - 90, base), (CXp + span / 2 + 90, base)], WARM, 0.3, 1.6)
    c.line([(CXp - span / 2 - 58, base + 22), (CXp + span / 2 + 58, base + 22)], WARM, 0.13)
    c.dot(CXp, top - 128, 8, ORANGE, 1)
    c.circle(CXp, top - 128, 22, ORANGE, 0.4, 1.5)
    return c.finish("GOVERNMENT RELATIONS")


def investor():
    c = Canvas(); c.grid()
    pts = [(300, 1000), (520, 900), (720, 762), (930, 560), (1120, 420)]
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        mid = ((p0[0] + p1[0]) / 2, p1[1] + (p0[1] - p1[1]) * 0.18)
        c.curve(p0, mid, p1, WARM, 0.12, 13)
        c.curve(p0, mid, p1, ORANGE, 0.9, 3.4)
    for i, (x, y) in enumerate(pts):
        last = i == len(pts) - 1
        c.circle(x, y, 21 if last else 13, None, fill=NAVY_DEEP, fill_alpha=1)
        c.circle(x, y, 21 if last else 13, ORANGE if last else PEACH, 1.0 if last else 0.6, 2.6 if last else 1.6)
        if last:
            c.circle(x, y, 9, fill=ORANGE, fill_alpha=1)
            c.circle(x, y, 38, ORANGE, 0.35, 1.4)
        c.line([(x, y + 28), (x, 1090)], WARM, 0.08, 1, dash=(3, 8))
    c.line([(240, 1090), (1180, 1090)], WARM, 0.22, 1.4)
    for i in range(9):
        x = 260 + i * 115
        c.line([(x, 1090), (x, 1104)], WARM, 0.14)
    return c.finish("INVESTOR JOURNEY")


def egypt():
    c = Canvas(); c.grid()
    sun = (CXp + 40, CYp - 196)
    c.circle(*sun, 150, ORANGE, 0.45, 1.6, fill=ORANGE, fill_alpha=0.1)
    for i, r in enumerate((198, 250)):
        c.circle(*sun, r, PEACH, 0.2 - i * 0.08, 1.2)
    base = CYp + 268
    for cx, w, h, lit in ((CXp - 252, 300, 230, False), (CXp + 30, 420, 340, True), (CXp + 322, 240, 180, False)):
        col, alpha = (ORANGE, 1.0) if lit else (WARM, 0.2)
        c.poly([(cx - w / 2, base), (cx, base - h), (cx, base)], fill=col, fill_alpha=0.09 if lit else 0.035)
        c.poly([(cx - w / 2, base), (cx, base - h), (cx + w / 2, base)], col, alpha, 2.4 if lit else 1.4)
        c.line([(cx, base - h), (cx, base)], col, 0.45 if lit else 0.1)
    c.line([(180, base), (1220, base)], WARM, 0.28, 1.4)
    for i, off in enumerate((46, 86, 126)):
        c.curve((180, base + off), (CXp, base + off + 16 - i * 8), (1220, base + off),
                PEACH, 0.26 - i * 0.07, 1.4, dash=(16, 22))
    return c.finish("EGYPT")


def converge():
    c = Canvas(warmth=(0.66, 0.5, 0.62, 0.17)); c.grid()
    tx, ty = CXp + 208, CYp
    for i in range(7):
        y = 318 + i * 128
        lit = i == 3
        mid = ((220 + tx) / 2, y + (ty - y) * 0.34)
        c.curve((220, y), mid, (tx, ty), ORANGE if lit else WARM, 0.9 if lit else 0.13,
                3.0 if lit else 1.4, taper=lit)
        c.dot(220, y, 5, ORANGE if lit else WARM, 0.8 if lit else 0.34)
    c.circle(tx, ty, 92, ORANGE, 0.6, 2, fill=ORANGE, fill_alpha=0.09)
    c.circle(tx, ty, 136, PEACH, 0.22, 1.2)
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 96 * S)
    box = c.d.textbbox((0, 0), "1", font=font)
    c.d.text((tx * S - (box[2] - box[0]) / 2 - box[0], ty * S - (box[3] - box[1]) / 2 - box[1]),
             "1", font=font, fill=rgba(WARM, 0.88))
    return c.finish("ONE DESK")


IMAGES = {
    "travel-tourism": travel,
    "business-setup": business,
    "company-formation": formation,
    "general-services": documents,
    "license-renewal": renewal,
    "government-relations": government,
    "investor-licence": investor,
    "egypt": egypt,
    "one-desk": converge,
}

if __name__ == "__main__":
    for name, fn in IMAGES.items():
        fn().save(os.path.join(OUT, f"{name}.png"), optimize=True)
        print("·", name)
