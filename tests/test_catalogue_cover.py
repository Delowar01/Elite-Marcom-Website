"""The approved Elite Marcom cover, as translated into ReportLab.

The design was approved elsewhere and is not re-judged here. What these
tests hold is that the translation stays a translation: the official artwork
is the official artwork, the geometry is the measured geometry, the wording
is the approved wording, and the only things that move between one catalogue
and the next are the market, the year, the count and the two dates.

They also hold the boundaries the cover must not cross — the page stays
searchable, the fixture values in the proof are nowhere in the code, and
nothing about the catalogue's price guarantee or its size work is disturbed.
"""
from __future__ import annotations

import hashlib
import io
import re
import time

import pytest

from server import catalogue as cat
from server import cover

STOCK_AT = 1760000000
MM = 25.4 / 72


def one_product_pdf(market: str = "ksa", count: int = 1, **kw) -> bytes:
    items = [{"id": str(n), "code": f"ITGL {1000 + n}", "name": f"Item {n}",
              "description": "A useful item.", "available": 4 + n,
              "availableKnown": True} for n in range(count)]
    return cat.build(items, {}, market=market, title="Elite Marcom\nProduct Catalogue",
                     stock_at=STOCK_AT, stock_is_known=True, **kw)


def spans(pdf: bytes) -> list[tuple[str, float, float, float, float, str]]:
    """(text, x mm, baseline mm, right mm, size pt, font) for page 1."""
    import pymupdf

    page = pymupdf.open(stream=pdf, filetype="pdf")[0]
    out = []
    for block in page.get_text("rawdict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = "".join(ch["c"] for ch in span["chars"]).strip()
                if not text:
                    continue
                out.append((text, span["chars"][0]["origin"][0] * MM,
                            span["origin"][1] * MM, span["bbox"][2] * MM,
                            span["size"], span["font"]))
    return out


def find(rows, text):
    for row in rows:
        if row[0] == text:
            return row
    raise AssertionError(f"{text!r} is not on the cover: "
                         f"{[r[0] for r in rows]}")


try:                                           # a development tool, not a dependency
    import pymupdf
except ImportError:                            # pragma: no cover
    pymupdf = None

#: Only the tests that *measure* the page need it. The ones that hold the
#: artwork, the wording and the fixtures are plain file and text checks and
#: must run everywhere.
measured = pytest.mark.skipif(pymupdf is None,
                              reason="measuring the page needs PyMuPDF")


# ---------------- the artwork is the approved artwork ----------------

def test_the_official_wordmark_is_the_approved_file_byte_for_byte():
    """Never traced, never redrawn, never re-typeset. The hash is the one
    the approved master records for its source PNG."""
    raw = (cover.COVER_DIR / "logo.png").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == cover.LOGO_SHA256
    from PIL import Image

    with Image.open(io.BytesIO(raw)) as im:
        assert im.size == (1629, 518) and im.mode == "RGBA"


def test_the_wordmark_is_placed_at_its_own_aspect_ratio():
    x, top, w, h = cover.LOGO_BOX
    assert (x, top, w) == (16.0, 12.0, 57.0)
    assert h == pytest.approx(57.0 * 518 / 1629, abs=1e-6)
    assert h == pytest.approx(18.125230203, abs=1e-6)


def test_the_three_cover_assets_and_three_weights_are_present():
    assert cover.assets_ready()
    assert cover.fonts_ready(), "the cover sets in Poppins 400/500/600"
    for name in (cover.REGULAR, cover.MEDIUM, cover.SEMIBOLD):
        assert cover.font(name) == name, "no fallback is in use"


def test_the_hero_is_the_approved_composition_and_is_not_rebuilt():
    """The seven product applications were projected and audited once, in
    the master. Nothing in the generator recreates them."""
    from PIL import Image

    hero = cover.COVER_DIR / "hero.jpg"
    with Image.open(hero) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
        assert im.width / im.height == pytest.approx(1024 / 700, rel=0.01)
    x, top, w, h = cover.HERO_BOX
    assert (x, top, w) == (0.0, 107.0, 210.0)
    assert h == pytest.approx(143.5546875, abs=1e-6)
    source = (cover.__file__, cat.__file__)
    for path in source:
        body = open(path, encoding="utf-8").read().lower()
        for forbidden in ("homograph", "perspective", "quadrilateral"):
            assert forbidden not in body, "the generator must not re-project a mark"


# ---------------- the page is a page, not a picture of one ----------------

@measured
def test_the_cover_is_exactly_one_page_and_the_product_follows():
    doc = pymupdf.open(stream=one_product_pdf(), filetype="pdf")
    assert doc.page_count == 2
    assert doc[0].rect.width == pytest.approx(595.2755905511812, abs=0.001)
    assert doc[0].rect.height == pytest.approx(841.8897637795277, abs=0.001)


@measured
def test_only_the_three_approved_cover_assets_are_raster():
    """Three pictures, and they are the approved artwork: the official
    wordmark, the faint watermark symbol derived from it, and the branded
    hero. Everything else — the field, the gradient, the band, the icons,
    every letter — stays vector or text.

    The count of *drawn* pictures is three; the count of image XObjects
    behind them is five, because the two PNGs keep their transparency as a
    separate greyscale soft mask. Both are asserted, so neither reading can
    be mistaken for the other, and a fourth picture fails whichever way it
    arrives.
    """
    doc = pymupdf.open(stream=one_product_pdf(), filetype="pdf")
    #: (xref, smask xref, width, height, bpc, colourspace, …, filter, …)
    images = doc[0].get_images(full=True)
    by_size = {(im[2], im[3]): im for im in images}
    assert len(images) == 3, (
        f"one more raster than the design has: {sorted(by_size)}")

    wordmark = by_size.get((1629, 518))
    watermark = by_size.get((518, 518))
    assert wordmark, f"the official wordmark, at its own size: {sorted(by_size)}"
    assert watermark, f"the watermark symbol: {sorted(by_size)}"
    hero = next(im for im in images if im is not wordmark and im is not watermark)

    masks = []
    for name, im in (("wordmark", wordmark), ("watermark", watermark)):
        assert im[1], f"the {name}'s transparency must survive as a soft mask"
        masks.append(im[1])
        assert doc.xref_get_key(im[1], "ColorSpace")[1] == "/DeviceGray", name
    assert hero[1] == 0, "the hero is baked opaque, so it carries no mask"
    assert hero[8] == "DCTDecode", f"the hero goes in as its own JPEG: {hero[8]}"
    assert hero[3] / hero[2] == pytest.approx(
        cover.HERO_BOX[3] / cover.HERO_BOX[2], abs=0.001), "the hero's own box"

    xobjects = {im[0] for im in images} | set(masks)
    assert len(xobjects) == 5, (
        f"three pictures, two soft masks, nothing else: {sorted(xobjects)}")


def test_the_cover_text_is_real_text():
    text = cat.extract_text(one_product_pdf())
    for wanted in ("CORPORATE GIFTS", "PRODUCT", "CATALOGUE", "Saudi Arabia",
                   "KSA", "PREMIUM GIFTS", "STRONGER BRANDS",
                   "LASTING IMPRESSIONS", "KSA CATALOGUE", "PREPARED",
                   "STOCK UPDATED", "www.elitemarcom.com",
                   "Confirm availability before committing to a quantity."):
        assert wanted in text, wanted


def test_the_cover_carries_no_reference_render_label():
    text = cat.extract_text(one_product_pdf()).lower()
    for label in ("reference", "render", "draft", "sample", "mockup", "master"):
        assert label not in text, label


# ---------------- the measured geometry ----------------

@measured
@pytest.mark.parametrize("text,x,baseline,size,weight", [
    ("PRODUCT", 15.400, 66.135, 59.5, "SemiBold"),
    ("CATALOGUE", 15.400, 86.508, 59.5, "SemiBold"),
    ("Saudi Arabia", 16.000, 98.679, 14.0, "Regular"),
    ("KSA CATALOGUE", 30.000, 259.810, 7.7, "Medium"),
    ("1 product", 30.000, 266.160, 12.5, "SemiBold"),
    ("PREPARED", 87.000, 259.810, 7.7, "Medium"),
    ("STOCK UPDATED", 144.000, 259.810, 7.7, "Medium"),
])
def test_a_measured_baseline_lands_where_the_master_put_it(text, x, baseline,
                                                           size, weight):
    """Within 0.2 mm of the approved PDF, which is the agreement the
    implementation map asks for."""
    row = find(spans(one_product_pdf()), text)
    assert row[1] == pytest.approx(x, abs=0.2), "x"
    assert row[2] == pytest.approx(baseline, abs=0.2), "baseline"
    assert row[4] == pytest.approx(size, abs=0.01), "size"
    assert row[5].endswith(weight), row[5]


@measured
def test_the_right_aligned_strings_end_where_they_should():
    rows = spans(one_product_pdf())
    header = find(rows, "Saudi Arabia · KSA")
    #: the ink stops short of 194 by exactly the trailing letter-space
    assert header[3] == pytest.approx(194.0 - 0.38, abs=0.2)
    assert find(rows, "www.elitemarcom.com")[3] == pytest.approx(198.0, abs=0.2)


@measured
def test_the_title_is_navy_then_orange_on_pure_white():
    """`#E56C25` clears 3:1 against white and nothing else, so the heading
    may sit nowhere but there."""
    import pymupdf

    page = pymupdf.open(stream=one_product_pdf(), filetype="pdf")[0]
    pix = page.get_pixmap(dpi=150)
    at = lambda xm, ym: pix.pixel(round(xm / 25.4 * 150), round(ym / 25.4 * 150))
    assert at(100, 20) == (255, 255, 255), "the heading's ground is pure white"
    assert at(100, 60) == (255, 255, 255)
    for row in spans(one_product_pdf()):
        if row[0] == "PRODUCT":
            assert row[2] < 90.5, "both lines sit above the rule"


def test_the_orange_field_is_the_approved_contour():
    assert cover.FIELD_PATH == (
        "M152 0 C146 28 146 53 140 80 C134 108 121 138 108 151 "
        "L55 250.555 H210 V0 Z")
    points = cover.field_path_points(256)
    assert points[0] == (152.0, 0.0)
    assert points[-3:] == [(55.0, 250.555), (210.0, 250.555), (210.0, 0.0)]
    xs = [p[0] for p in points]
    assert min(xs) == 55.0 and max(xs) == 210.0
    #: the two cubics really curve: a polygon through the same ends would not
    middle = [p for p in points if 70 < p[1] < 140]
    assert max(p[0] for p in middle) - min(p[0] for p in middle) > 10


def test_the_two_shadings_are_vector_and_carry_the_approved_stops():
    pdf = one_product_pdf()
    assert pdf.count(b"/ShadingType") == 2, "background and field, both vector"
    assert cover.GROUND_STOPS[0] == (0.00, "#FFFFFF")
    assert cover.GROUND_STOPS[-1] == (1.00, "#F4F2F0")
    assert cover.FIELD_STOPS == ((0.00, "#F4C09A"), (0.40, "#ED9458"),
                                 (0.76, "#E56C25"), (1.00, "#DE6423"))
    assert cover.FIELD_AXIS == ((112.0, 0.0), (210.0, 65.0))
    assert cover.GROUND_AXIS == ((0.0, 96.0), (0.0, 136.0))


@measured
def test_the_watermark_is_a_faint_clipped_symbol():
    assert cover.WATERMARK_BOX == (126.0, 39.0, 96.0, 96.0)
    assert cover.WATERMARK_ALPHA == 0.075
    import pymupdf

    page = pymupdf.open(stream=one_product_pdf(), filetype="pdf")[0]
    pix = page.get_pixmap(dpi=150)
    at = lambda xm, ym: pix.pixel(round(xm / 25.4 * 150), round(ym / 25.4 * 150))
    on_mark, plain = at(150, 70), at(170, 95)
    assert on_mark != plain, "the watermark is visible"
    assert max(abs(on_mark[i] - plain[i]) for i in range(3)) < 40, "and very faint"
    assert at(135, 50) == (255, 255, 255), "it is clipped to the field"


# ---------------- what changes, and what never does ----------------

@measured
def test_the_facts_are_the_catalogue_and_not_the_fixture():
    rows = spans(one_product_pdf(market="uae", count=25))
    assert find(rows, "United Arab Emirates · UAE")
    assert find(rows, "UAE CATALOGUE")
    assert find(rows, "25 products")
    #: the stock moment, to the minute, as the master prints it
    assert find(rows, time.strftime("%d %b %Y · %H:%M", time.localtime(STOCK_AT)))
    #: and "prepared" is when the document was made, not when stock moved
    assert find(rows, time.strftime("%d %b %Y", time.localtime(time.time())))
    text = cat.extract_text(one_product_pdf(market="uae", count=25))
    assert "Saudi Arabia" not in text and "KSA" not in text


def test_one_product_is_singular_and_two_are_not():
    assert "1 product" in cat.extract_text(one_product_pdf(count=1))
    assert "2 products" in cat.extract_text(one_product_pdf(count=2))


def test_an_unknown_stock_time_says_so_rather_than_inventing_one():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Item", "available": None,
                      "availableKnown": False}], {}, market="ksa", title="T",
                    stock_at=None, stock_is_known=False)
    assert "not available" in cat.extract_text(pdf)


def test_the_proof_fixtures_are_nowhere_in_the_code():
    """The dates, the count and the market in the approved proof are an
    example. A generator that hard-coded them would look right once."""
    for path in (cover.__file__, cat.__file__):
        body = open(path, encoding="utf-8").read()
        for fixture in ("08 Oct 2026", "15:01", "1 product", "Saudi Arabia · KSA"):
            assert fixture not in body, fixture
    assert "2026" not in open(cover.__file__, encoding="utf-8").read()


def test_the_cover_is_the_same_composition_whatever_the_catalogue():
    """A client recognises the cover before reading it, so one product and a
    hundred get the same page but for the facts."""
    small = cat.extract_text(one_product_pdf(count=1))
    large = cat.extract_text(one_product_pdf(count=30))
    for fixed in ("CORPORATE GIFTS", "PRODUCT", "CATALOGUE", "PREMIUM GIFTS",
                  "Quantities reflect the stock update shown above and are not "
                  "reserved."):
        assert fixed in small and fixed in large


def test_the_approved_wording_is_exactly_the_approved_wording():
    assert cover.EYEBROW_TEXT == "CORPORATE GIFTS"
    assert [t for t, _, _ in cover.TITLE_LINES] == ["PRODUCT", "CATALOGUE"]
    assert cover.PROMISE_TEXT == ("PREMIUM GIFTS", "STRONGER BRANDS",
                                  "LASTING IMPRESSIONS")
    assert cover.DISCLAIMER == (
        "Quantities reflect the stock update shown above and are not reserved.",
        "Confirm availability before committing to a quantity.")
    assert cover.WEBSITE_TEXT == "www.elitemarcom.com"


@measured
def test_the_website_is_a_link_and_not_only_words():
    import pymupdf

    page = pymupdf.open(stream=one_product_pdf(), filetype="pdf")[0]
    links = [l for l in page.get_links() if l.get("uri")]
    assert [l["uri"] for l in links] == ["https://www.elitemarcom.com"]


# ---------------- nothing else moved ----------------

def test_the_price_guarantee_is_untouched():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 3,
                      "availableKnown": True}], {}, market="ksa",
                    title="T", stock_at=STOCK_AT, stock_is_known=True)
    cat.assert_price_free(pdf)                 # raises if anything leaked
    text = cat.extract_text(pdf).lower()
    assert not re.search(r"\b(sar|aed|usd|rrp)\b", text)


def test_both_quality_modes_still_build_and_differ():
    from PIL import Image

    raw = io.BytesIO()
    Image.new("RGB", (1800, 1800), (120, 90, 60)).save(raw, "JPEG", quality=95)
    standard = cat.prepare_image(raw.getvalue(), slot="main", quality="standard")
    high = cat.prepare_image(raw.getvalue(), slot="main", quality="high")
    assert len(standard) < len(high)
    for mode, blob in (("standard", standard), ("high", high)):
        pdf = cat.build([{"id": "1", "code": "A", "name": "Item", "available": 2,
                          "availableKnown": True}], {"1": [blob]}, market="ksa",
                        title="T", stock_at=STOCK_AT, stock_is_known=True,
                        options={"quality": mode})
        assert pdf[:5] == b"%PDF-"
        assert b"/DCTDecode" in pdf, mode


def test_the_cover_costs_one_image_object_however_long_the_catalogue():
    """The hero and the wordmark are drawn once and reportlab keys an image
    by its content, so a long catalogue does not pay for the cover twice."""
    def image_bytes(pdf):
        total = 0
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
            head = pdf[max(0, m.start() - 2500):m.start()]
            if re.search(rb"/Subtype\s*/Image", head):
                total += len(m.group(1))
        return total

    one = image_bytes(one_product_pdf(count=1))
    many = image_bytes(one_product_pdf(count=12))
    assert many == one, "the cover's imagery is not repeated per page"
