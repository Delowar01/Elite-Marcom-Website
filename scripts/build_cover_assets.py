#!/usr/bin/env python3
"""Lift the approved cover's assets out of the design master, once.

    python scripts/build_cover_assets.py Elite_Marcom_Catalogue_Cover_MASTER.html

The master is a single self-contained HTML file: three Poppins faces, the
official wordmark, the watermark symbol and the branded hero are all base64
inside it. This script decodes them by **hash**, not by position, writes the
ones `server/cover.py` draws into `server/data/`, and bakes the hero.

Why the hero is baked rather than copied. It is 4096 x 2800 RGBA, and three
quarters of it is transparent so that the gradient, the orange field and the
watermark show through. ReportLab can embed a JPEG, or raw pixels with an
alpha channel, but not a JPEG with one — and at 300 dpi the alpha route costs
7.75 MB of Flate-compressed pixels where the JPEG costs 0.6 MB. On a
one-product catalogue that is the difference between a document somebody can
email and one they cannot.

So the three layers beneath the hero are computed here, from the same
constants `server/cover.py` draws them with, the hero is composited over
them, and the result is one opaque JPEG. The page still draws those layers as
vector everywhere else; the hero's band simply receives them as pixels that
are identical by construction. Nothing about the approved composition — the
photograph, the staging, the seven audited product applications — is touched.

The wordmark and the watermark are copied byte for byte. The wordmark's
SHA-256 is asserted against the approved source before anything is written.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import cover                                     # noqa: E402

from PIL import Image, ImageDraw                             # noqa: E402

Image.MAX_IMAGE_PIXELS = None

#: What the master must contain, by SHA-256. A master that does not carry
#: these is not the approved master, and this refuses rather than guessing.
LOGO_SHA = cover.LOGO_SHA256
WATERMARK_SHA = "5e0ce1aebce13876a81b88aa63059aa44fa97b15d1425a4f6bc908979c87c3ec"
HERO_SHA = "0e9bef8d5f5b397db8d5f343bd98c1db7812380f6887bee585f72d38d9f2b5c6"
FONT_SHA = {
    "Poppins-Regular.ttf": "707fdc5c8bab57a90061c6a8ed7b70d5ffb82fc810e994e79f90bace890c255a",
    "Poppins-Medium.ttf": "8d909883de81344e0fbcfef30e931872e92d9aeecdf85b6dcf6e0b28c078e98e",
    "Poppins-SemiBold.ttf": "248c0244b350ec68880996aa6be6d7796274b49992d5fcbbefe251906aa4ea36",
}

#: The master's own compositing canvas, so the approved artwork is embedded
#: at its native resolution and **nothing is resampled**. Four hundred and
#: ninety-five dots to the inch across the page is far beyond what the
#: photograph holds — its real detail is about 124 ppi — but the canvas is
#: 4x for a reason: it is what antialiases the seven applied brand marks,
#: and the pen's is 2.9 mm across. Resampling it to 300 dpi costs 0.7 MB
#: less and visibly softens that mark under a loupe, which is the one thing
#: the logo audit exists to check.
#:
#: Measured, baked and JPEG-encoded at 4:4:4: 300 dpi q92 1.03 MB, 400 dpi
#: q88 1.29 MB, native q88 1.75 MB, native q92 2.11 MB.
PAGE_PX = 4096
#: 4:4:4, because the brand marks are small and chroma subsampling is exactly
#: what would soften them.
HERO_QUALITY = 88

DATA = "data:(?:image/png|font/ttf);base64,([A-Za-z0-9+/=]+)"


def assets_in(html: str) -> dict[str, bytes]:
    """Everything embedded in the master, keyed by its own SHA-256."""
    found: dict[str, bytes] = {}
    for match in re.finditer(DATA, html):
        raw = base64.b64decode(match.group(1))
        found[hashlib.sha256(raw).hexdigest()] = raw
    return found


def _page_background(width: int, height: int) -> Image.Image:
    """Layer 1: white falling to Ground, vertical, so one colour per row."""
    im = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(im)
    (_, y0), (_, y1) = cover.GROUND_AXIS
    span = (y1 - y0) * height / cover.PAGE_H_MM
    top = y0 * height / cover.PAGE_H_MM
    for row in range(height):
        t = (row - top) / span if span else 0.0
        draw.line([(0, row), (width, row)],
                  fill=cover.lerp_stops(cover.GROUND_STOPS, t))
    return im


def _orange_field(width: int, height: int) -> tuple[Image.Image, Image.Image]:
    """Layer 2: the contour, filled with its axial shading. Returns the
    painted field and its mask, because the watermark is clipped to it."""
    scale = width / cover.PAGE_W_MM
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(
        [(x * scale, y * scale) for x, y in cover.field_path_points(512)], fill=255)

    (ax, ay), (bx, by) = cover.FIELD_AXIS
    dx, dy = (bx - ax) * scale, (by - ay) * scale
    denominator = dx * dx + dy * dy
    corners = [(0, 0), (width, 0), (0, height), (width, height)]
    ts = [((cx - ax * scale) * dx + (cy - ay * scale) * dy) / denominator
          for cx, cy in corners]
    t_lo, t_hi = min(ts), max(ts)

    #: one strip of the gradient, already clamped at both ends, mapped onto
    #: the page by an affine transform — PIL has no axial shading, and a
    #: per-pixel loop over five million pixels is not worth the minute
    steps = 4096
    strip = Image.new("RGB", (steps, 1))
    strip.putdata([cover.lerp_stops(cover.FIELD_STOPS,
                                    t_lo + (t_hi - t_lo) * i / (steps - 1))
                   for i in range(steps)])
    strip = strip.resize((steps, height), Image.NEAREST)
    # output (x,y) -> strip u = steps * (t(x,y) - t_lo) / (t_hi - t_lo)
    k = steps / ((t_hi - t_lo) * denominator)
    a = dx * k
    b = dy * k
    c = -(ax * scale * dx + ay * scale * dy) * k - t_lo * steps / (t_hi - t_lo)
    field = strip.transform((width, height), Image.AFFINE, (a, b, c, 0, 1, 0),
                            resample=Image.BILINEAR)
    return field, mask


def bake_hero(hero_png: bytes, watermark_png: bytes) -> bytes:
    """The approved hero, composited over exactly what sits beneath it."""
    width = PAGE_PX
    height = round(cover.PAGE_H_MM * width / cover.PAGE_W_MM)
    scale = width / cover.PAGE_W_MM

    page = _page_background(width, height)
    field, mask = _orange_field(width, height)
    page.paste(field, (0, 0), mask)

    wx, wtop, ww, wh = cover.WATERMARK_BOX
    mark = Image.open(io.BytesIO(watermark_png)).convert("RGBA")
    mark = mark.resize((round(ww * scale), round(wh * scale)), Image.LANCZOS)
    alpha = mark.getchannel("A").point(
        lambda v: round(v * cover.WATERMARK_ALPHA))
    faint = Image.new("RGBA", page.size, (0, 0, 0, 0))
    faint.paste(mark, (round(wx * scale), round(wtop * scale)), alpha)
    #: clipped to the field, exactly as the master clips it
    faint.putalpha(Image.composite(faint.getchannel("A"),
                                   Image.new("L", page.size, 0), mask))
    page = Image.alpha_composite(page.convert("RGBA"), faint)

    hx, htop, hw, hh = cover.HERO_BOX
    hero = Image.open(io.BytesIO(hero_png)).convert("RGBA")
    hero = hero.resize((round(hw * scale), round(hh * scale)), Image.LANCZOS)
    page.alpha_composite(hero, (round(hx * scale), round(htop * scale)))

    band = page.convert("RGB").crop((
        round(hx * scale), round(htop * scale),
        round((hx + hw) * scale), round((htop + hh) * scale)))
    out = io.BytesIO()
    band.save(out, "JPEG", quality=HERO_QUALITY, optimize=True,
              subsampling=0, progressive=False)
    return out.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("master", type=pathlib.Path,
                    help="Elite_Marcom_Catalogue_Cover_MASTER.html")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "server" / "data")
    args = ap.parse_args()

    html = args.master.read_text(encoding="utf-8")
    print(f"master   {args.master.name}  "
          f"sha256 {hashlib.sha256(args.master.read_bytes()).hexdigest()}")
    found = assets_in(html)
    for name, want in (("the official wordmark", LOGO_SHA),
                       ("the watermark symbol", WATERMARK_SHA),
                       ("the branded hero", HERO_SHA)):
        if want not in found:
            print(f"ERROR: {name} ({want[:16]}…) is not in this file", file=sys.stderr)
            return 2
    for file, want in FONT_SHA.items():
        if want not in found:
            print(f"ERROR: {file} ({want[:16]}…) is not in this file", file=sys.stderr)
            return 2

    fonts = args.out / "fonts"
    covers = args.out / "cover"
    fonts.mkdir(parents=True, exist_ok=True)
    covers.mkdir(parents=True, exist_ok=True)

    for file, digest in FONT_SHA.items():
        (fonts / file).write_bytes(found[digest])
        print(f"font     {file:<24} {len(found[digest]):>9,} bytes")
    (covers / "logo.png").write_bytes(found[LOGO_SHA])
    print(f"logo     logo.png                 {len(found[LOGO_SHA]):>9,} bytes  "
          f"sha256 {LOGO_SHA}")
    (covers / "watermark.png").write_bytes(found[WATERMARK_SHA])
    print(f"mark     watermark.png            {len(found[WATERMARK_SHA]):>9,} bytes")

    baked = bake_hero(found[HERO_SHA], found[WATERMARK_SHA])
    (covers / "hero.jpg").write_bytes(baked)
    print(f"hero     hero.jpg                 {len(baked):>9,} bytes  "
          f"(from {len(found[HERO_SHA]):,} bytes of RGBA, baked over its "
          f"background at {PAGE_PX}px/page)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
