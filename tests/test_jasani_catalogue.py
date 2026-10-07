"""Jasani Items at scale, and the PDF catalogue it produces.

Two promises are load-bearing here and are tested as promises rather than as
implementation details:

* **No price, ever.** The catalogue is a document for a customer, and the
  supplier's prices are internal by supplier policy. The check reads the text
  back out of the finished PDF rather than trusting the code that wrote it.
* **No supplier call.** Searching, filtering, paging, selecting and generating
  all read the snapshot the scheduled synchronisation already wrote. A
  catalogue must never cost one of the five calls a market gets each day.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import catalogue as cat
from server import jasani
from server.main import app

client = TestClient(app)

#: the owner's 2FA secret, so a test may sign out and back in again
TOTP: dict[str, str] = {}


def sign_in() -> None:
    r = client.post("/api/admin/login",
                    json={"email": "owner@elitemarcom.com",
                          "password": "correct-horse-battery"}).json()
    client.post("/api/admin/2fa/verify",
                json={"pending": r["pending"],
                      "code": aa._totp_at(TOTP["secret"], int(time.time() // 30))})


@pytest.fixture(scope="module", autouse=True)
def admin(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("jz-catalogue")
    old_db = aa._DB_PATH
    aa._DB_PATH = runtime / "admin.db"
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    client.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com",
                                              "name": "Owner",
                                              "password": "correct-horse-battery",
                                              "setupCode": ""})
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    TOTP["secret"] = r["secret"]
    client.post("/api/admin/2fa/verify",
                json={"pending": r["pending"],
                      "code": aa._totp_at(r["secret"], int(time.time() // 30))})
    yield
    client.post("/api/admin/logout", headers=csrf())
    aa._DB_PATH = old_db
    if hasattr(aa._local, "conn"):
        del aa._local.conn


def csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


STOCK_AT = 1760000000          # a fixed, knowable synchronisation moment


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    """A 640-product KSA snapshot and a small UAE one, on disk, with no
    supplier anywhere near them."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = []
    for n in range(640):
        products.append({
            "id": str(1000 + n),
            "code": f"ITGL {1000 + n}",
            "name": f"Product Number {n:03d}",
            "brand": "Jasani" if n % 2 else "Elite",
            "color": "Blue" if n % 3 else "Black",
            "categories": ["Drinkware" if n % 2 else "Notebooks"],
            "description": f"A useful item, number {n}.",
            "image": f"https://www.giftsksa.com/img/{n}.jpg",
            "images": [f"https://www.giftsksa.com/img/{n}.jpg"],
            "unitsPerCarton": 24,
            "stock": {"available": n, "incoming": 0},
        })
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": products}),
        encoding="utf-8")
    (tmp_path / "giveaways-uae.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": [{
            "id": "u1", "code": "UAE 1", "name": "Dubai Mug", "brand": "Jasani",
            "color": "White", "categories": ["Drinkware"], "description": "A mug.",
            "image": "", "images": [], "stock": {"available": 7, "incoming": 0}}]}),
        encoding="utf-8")
    return products


def items(**params):
    base = {"market": "ksa", "perPage": 20}
    base.update(params)
    res = client.get("/api/admin/jasani/items", params=base)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------- the 20-item ceiling ----------------

def test_the_page_size_goes_to_five_hundred(snapshot):
    """The old ceiling was two hundred on the server and a hundred in the
    panel; the dataset was never the limit."""
    d = items(perPage=500)
    assert d["perPage"] == 500
    assert len(d["items"]) == 500
    assert d["matched"] == 640
    assert d["pages"] == 2
    assert d["perPageOptions"] == [20, 50, 100, 250, 500]


def test_every_offered_page_size_is_honoured(snapshot):
    for size in (20, 50, 100, 250, 500):
        d = items(perPage=size)
        assert d["perPage"] == size, size
        assert len(d["items"]) == min(size, 640), size


def test_a_page_size_beyond_the_ceiling_is_clamped_not_obeyed(snapshot):
    d = items(perPage=5000)
    assert d["perPage"] == 500 and len(d["items"]) == 500


def test_the_five_hundredth_item_can_actually_be_displayed(snapshot):
    d = items(perPage=500)
    names = [i["name"] for i in d["items"]]
    assert "Product Number 499" in names
    assert len(names) == len(set(names))


# ---------------- search across the whole catalogue ----------------

def test_search_reaches_past_the_first_page(snapshot):
    """Item 600 is nowhere near page one at any page size."""
    d = items(q="Product Number 600", perPage=20)
    assert d["matched"] == 1
    assert d["items"][0]["code"] == "ITGL 1600"


def test_search_matches_code_name_brand_and_category(snapshot):
    assert items(q="ITGL 1123")["matched"] == 1
    assert items(q="Number 321")["matched"] == 1
    assert items(q="Elite")["matched"] == 320
    assert items(q="Notebooks")["matched"] == 320


def test_pagination_counts_stay_right_whatever_the_page_size(snapshot):
    for size, pages in ((20, 32), (50, 13), (100, 7), (250, 3), (500, 2)):
        d = items(perPage=size)
        assert d["pages"] == pages, size
        assert d["matched"] == 640, size
    last = items(perPage=500, page=2)
    assert len(last["items"]) == 140 and last["page"] == 2


# ---------------- minimum stock ----------------

def test_minimum_stock_uses_greater_than_or_equal(snapshot):
    """Stock runs 0…639, so a minimum of 100 keeps exactly 540 — and the item
    sitting on exactly 100 is one of them."""
    d = items(minStock=100, perPage=500)
    assert d["matched"] == 540
    assert min(i["available"] for i in d["items"]) == 100
    assert any(i["available"] == 100 for i in d["items"])


@pytest.mark.parametrize("minimum,expected", [
    ("", 640), ("0", 640), ("1", 639), ("10", 630), ("50", 590),
    ("100", 540), ("500", 140), ("639", 1), ("640", 0),
])
def test_minimum_stock_across_the_whole_dataset(snapshot, minimum, expected):
    assert items(minStock=minimum, perPage=500)["matched"] == expected


def test_a_negative_minimum_is_refused(snapshot):
    res = client.get("/api/admin/jasani/items",
                     params={"market": "ksa", "minStock": "-5"})
    assert res.status_code == 400 and "negative" in res.json()["detail"].lower()


def test_minimum_stock_combines_with_the_other_filters(snapshot):
    d = items(q="Number", category="Drinkware", minStock=100, perPage=500)
    assert 0 < d["matched"] < 540
    assert all(i["available"] >= 100 for i in d["items"])
    assert all(i["category"] == "Drinkware" for i in d["items"])


def test_the_filter_is_the_market_being_viewed(snapshot):
    """KSA and UAE hold different quantities and are never added together."""
    assert items(market="uae", minStock=5)["matched"] == 1
    assert items(market="uae", minStock=8)["matched"] == 0
    assert items(market="ksa", minStock=8)["matched"] == 632


def test_unknown_stock_cannot_satisfy_a_positive_minimum(tmp_path, monkeypatch):
    """A snapshot with no stock sync behind it holds zeroes that mean "not
    checked", not "none left" — they must not pass a minimum of one."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "products": [
            {"id": "1", "code": "A", "name": "Unknown Stock Item", "brand": "", "color": "",
             "categories": [], "image": "", "stock": {"available": 0, "incoming": 0}}]}),
        encoding="utf-8")
    assert jasani.stock_known("ksa") is False
    assert items()["matched"] == 1              # still listed
    assert items(minStock=1)["matched"] == 0    # but not as "at least one"
    assert items(minStock=0)["matched"] == 1
    assert items()["stockKnown"] is False


# ---------------- selection ----------------

def test_the_listing_hands_over_every_matching_id(snapshot):
    """"Select all filtered" needs the whole result, not the rows on screen."""
    d = items(minStock=100, perPage=20)
    assert len(d["items"]) == 20
    assert len(d["ids"]) == 540 == d["matched"]
    assert len(set(d["ids"])) == 540


# ---------------- the catalogue ----------------

def start_catalogue(**body):
    payload = {"market": "ksa", "scope": "selected"}
    payload.update(body)
    return client.post("/api/admin/jasani/catalogue", json=payload, headers=csrf())


def finish(token: str) -> dict:
    for _ in range(3000):            # a real 500-photograph catalogue takes a while
        job = client.get("/api/admin/jasani/catalogue/status",
                         params={"token": token}).json()["job"]
        if job["state"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("catalogue did not finish")


def pdf_for(ids, **body) -> bytes:
    res = start_catalogue(ids=ids, **body)
    assert res.status_code == 200, res.text
    job = finish(res.json()["token"])
    assert job["state"] == "done", job
    got = client.get("/api/admin/jasani/catalogue/download",
                     params={"token": res.json()["token"]})
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/pdf"
    return got.content


@pytest.fixture(autouse=True)
def offline(monkeypatch, request):
    """No test touches the network. By default a fetch returns nothing, which
    is also the no-photograph case the layout must survive; a test that wants
    real pictures asks for the `photos` fixture, which serves bytes made here.
    """
    if "photos" in request.fixturenames:
        return

    async def nothing(url):
        return None

    monkeypatch.setattr(jasani, "_fetch_image_bytes", nothing)


_JPEG_POOL: dict[tuple, bytes] = {}


def jpeg_bytes(w=2400, h=1800, seed=0) -> bytes:
    """A representative supplier photograph: a real JPEG at product-photo
    size. Drawing one is slow, so a small pool is reused — the renderer still
    receives genuine image bytes, which is the point."""
    key = (w, h, seed % 8)
    if key in _JPEG_POOL:
        return _JPEG_POOL[key]
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), (248, 246, 243))
    d = ImageDraw.Draw(im)
    for i in range(0, w, 160):                # some detail, so it has real size
        d.line([(i, 0), (i + key[2] * 11, h)], fill=(200 - i % 55, 120, 60 + i % 90),
               width=9)
    d.ellipse([w * 0.2, h * 0.2, w * 0.8, h * 0.8], fill=(30 + key[2] * 25, 90, 160))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    _JPEG_POOL[key] = buf.getvalue()
    return _JPEG_POOL[key]


@pytest.fixture
def photos(monkeypatch):
    """Every image URL answers with a real JPEG, and the fetches are counted
    so a test can show what the renderer actually held."""
    made: dict[str, bytes] = {}
    stats = {"fetches": 0, "bytes": 0, "live": 0, "peak": 0}

    async def serve(url):
        stats["fetches"] += 1
        if url not in made:
            made[url] = jpeg_bytes(seed=len(made))
            stats["sample"] = len(made[url])
        stats["bytes"] += len(made[url])
        return made[url]

    monkeypatch.setattr(jasani, "_fetch_image_bytes", serve)

    # watch how much prepared imagery exists at once
    real_prepare = cat.prepare_image

    def counted(raw):
        out = real_prepare(raw)
        if out is not None:
            stats["live"] += len(out)
            stats["peak"] = max(stats["peak"], stats["live"])
        return out

    monkeypatch.setattr(cat, "prepare_image", counted)
    stats["sample"] = None
    return stats


def test_one_product_makes_a_cover_and_one_page(snapshot):
    blob = pdf_for(["1000"])
    text = cat.extract_text(blob)
    assert "Product Number 000" in text
    assert "ITGL 1000" in text
    assert "Page 2" in text and "Page 3" not in text   # cover + one product


@pytest.mark.parametrize("n", [1, 2, 50])
def test_every_product_gets_its_own_page(snapshot, n):
    ids = [str(1000 + i) for i in range(n)]
    text = cat.extract_text(pdf_for(ids))
    for i in range(n):
        assert f"Product Number {i:03d}" in text, i
    assert f"Page {1 + n}" in text
    assert f"Page {2 + n}" not in text


def test_a_five_hundred_product_catalogue_builds_with_real_photographs(snapshot, photos):
    """The load test that means something: every product carries actual JPEG
    bytes, so this measures a catalogue rather than five hundred placeholder
    pages."""
    ids = [str(1000 + i) for i in range(500)]
    started = time.time()
    blob = pdf_for(ids)
    took = time.time() - started
    text = cat.extract_text(blob)
    assert "Product Number 000" in text and "Product Number 499" in text
    assert "Page 501" in text and "Page 502" not in text
    assert photos["fetches"] >= 500, "the photographs were really fetched"
    assert text.count("Image unavailable") == 0, "no page fell back to a placeholder"
    assert len(blob) > 500 * 1024, "a catalogue of photographs is not a few bytes"
    assert took < 300, f"took {took:.1f}s"
    print(f"\n  500 products · {photos['fetches']} fetches · "
          f"source {photos['bytes'] / 1024 / 1024:.1f} MB · "
          f"PDF {len(blob) / 1024 / 1024:.2f} MB · {took:.1f}s")


def test_the_renderer_never_holds_every_products_photographs_at_once(snapshot, photos,
                                                                     monkeypatch):
    """The point of the streaming rewrite. Pictures for one product are drawn
    and released before the next product is fetched, so the working set does
    not grow with the catalogue."""
    held: dict[str, int] = {"max": 0}
    real_page = cat.Document.page

    def watched(self, dto, blobs):
        held["max"] = max(held["max"], sum(len(b) for b in blobs))
        real_page(self, dto, blobs)

    monkeypatch.setattr(cat.Document, "page", watched)
    ids = [str(1000 + i) for i in range(60)]
    blob = pdf_for(ids)
    assert len(blob) > 50 * 1024
    # whatever one page needs, it is a page's worth — not sixty products'
    assert held["max"] < 2 * 1024 * 1024, held["max"]
    # and the prepared bytes alive at any moment stay bounded by the cache
    assert photos["peak"] < 12 * 1024 * 1024, photos["peak"]
    print(f"\n  largest single page working set: {held['max'] / 1024:.0f} KB · "
          f"peak prepared bytes: {photos['peak'] / 1024 / 1024:.1f} MB")


def test_a_photograph_is_shrunk_before_it_is_drawn(photos):
    """A 4 MB original is not what the page holds."""
    raw = jpeg_bytes(3200, 2400)
    small = cat.prepare_image(raw)
    from PIL import Image

    assert small is not None and len(small) < len(raw) / 2
    assert max(Image.open(io.BytesIO(small)).size) <= cat.MAX_IMAGE_DIM


def test_an_enormous_image_is_refused_before_its_pixels_are_decoded():
    """A decompression bomb is judged on its header, not by decoding it."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, "PNG")
    header = buf.getvalue()
    monster = io.BytesIO()
    Image.new("L", (12000, 12000)).save(monster, "PNG")      # 144M pixels
    assert cat.prepare_image(monster.getvalue()) is None
    assert cat.prepare_image(header) is not None
    assert cat.prepare_image(b"x" * (cat.MAX_IMAGE_BYTES + 1)) is None


def test_one_unreachable_photograph_costs_that_product_only(snapshot, photos,
                                                            monkeypatch):
    real = jasani._fetch_image_bytes

    async def flaky(url):
        if url.endswith("/3.jpg"):
            raise OSError("the host hung up")
        return await real(url)

    monkeypatch.setattr(jasani, "_fetch_image_bytes", flaky)
    blob = pdf_for([str(1000 + i) for i in range(5)])
    text = cat.extract_text(blob)
    assert text.count("Image unavailable") == 1, "exactly the one that failed"
    assert "Product Number 004" in text, "the rest of the catalogue is unharmed"


def test_more_than_five_hundred_is_refused_rather_than_attempted(snapshot):
    res = start_catalogue(scope="filtered", market="ksa")
    assert res.status_code == 400
    assert "at most" in res.json()["detail"]


def test_an_empty_selection_asks_for_one(snapshot):
    res = start_catalogue(ids=[], scope="selected")
    assert res.status_code == 400
    assert "select" in res.json()["detail"].lower()


# ---------------- no prices, ever ----------------

def test_no_price_field_can_reach_the_renderer(tmp_path, monkeypatch):
    """The guarantee is structural: the renderer is handed a record built key
    by key from an allowlist, so a price has no route in — including a price
    field a future supplier feed invents."""
    loaded = {
        "id": "7", "code": "EM-MUG-7", "name": "Expensive Mug", "brand": "Jasani",
        "color": "Black", "categories": ["Drinkware"], "available": 42,
        "availableKnown": True, "description": "A mug with a story.",
        "images": [], "unitsPerCarton": 24,
        "list_price": 12.5, "retail_price": 19.99, "listPrice": 12.5,
        "retailPrice": 19.99, "price": 12.5, "wholesale": 11.0,
        "reseller_price": 15.0, "selling_price": 17.5, "unit_price": 12.5,
        "vat": 1.875, "discount": 10, "currency": "SAR", "booked": 3,
        "blocked_qty": 3, "_int": {"price": 12.5},
        "future_price_field_nobody_has_written_yet": 99.0,
    }
    dto = cat.to_dto(loaded)
    assert set(dto) == set(cat.DTO_FIELDS), "the record is exactly the allowlist"
    assert not (set(dto) & cat.FORBIDDEN_FIELDS)
    for key in loaded:
        if key in cat.DTO_FIELDS:
            continue
        assert key not in dto, key
    # and nothing price-shaped survives into the drawn page
    pdf = cat.build([loaded], {}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf).lower()
    assert "expensive mug" in text, "the product really is in the document"
    for word in cat.PRICE_WORDS:
        assert word not in text, word
    cat.assert_price_free(pdf)


@pytest.mark.parametrize("price,field,value,must_remain", [
    (100, "available", 100, "100 units"),
    (500, "capacity", "500 ml", "500 ml"),
    (24, "unitsPerCarton", 24, "24"),
    (9.5, "cartonWeight", 9.5, "9.5 kg"),
    (1234, "barcode", "1234", "1234"),
])
def test_a_number_that_happens_to_equal_a_price_is_not_a_leak(price, field, value,
                                                              must_remain):
    """An item priced 100 with 100 units in stock prints "100 units". The old
    guard matched price figures against the page text and would have refused
    this honest catalogue, while still missing a leak at an unusual value."""
    item = {"id": "1", "code": "A", "name": "Coincidence Mug", "available": 7,
            "availableKnown": True, "price": price, "list_price": price,
            field: value}
    pdf = cat.build([item], {}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    cat.assert_price_free(pdf)                 # must not raise
    assert must_remain in cat.extract_text(pdf)


@pytest.mark.parametrize("injected", [
    "Retail price: 100 SAR", "Unit price 12", "Billed in AED",
    "List price on request", "RRP 40", "Selling price fixed", "Ex VAT",
])
def test_the_finished_document_guard_still_catches_a_real_indicator(injected,
                                                                   monkeypatch):
    """Second line of defence. A price label or a currency, however it got
    onto the page, is refused — and refused at build time, so a document
    carrying one is never handed to anybody.

    The sanitizer is switched off here on purpose: it would remove every one
    of these before a page was drawn, and then this would be a test of the
    sanitizer rather than of the guard behind it."""
    monkeypatch.setattr(cat, "sanitize_catalogue_text", lambda v, f="": v)
    with pytest.raises(cat.CatalogueError) as exc:
        cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 5,
                    "availableKnown": True, "description": injected}], {},
                  market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    assert "price indicator" in str(exc.value)


def test_the_guard_is_not_a_no_op():
    """A check that reads an empty string passes on everything, so prove the
    extractor really sees the drawn page: the same sentence without the
    currency comes back out of a document that was allowed through."""
    clean = cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 5,
                        "availableKnown": True, "description": "Priced fairly."}],
                      {}, market="ksa", title="T", stock_at=STOCK_AT,
                      stock_is_known=True)
    assert "Priced fairly" in cat.extract_text(clean)
    #: the sanitizer would remove the currency before a page was drawn, so it
    #: is switched off to leave the guard the only thing standing
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cat, "sanitize_catalogue_text", lambda v, f="": v)
        with pytest.raises(cat.CatalogueError):
            cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 5,
                        "availableKnown": True, "description": "Priced in SAR."}],
                      {}, market="ksa", title="T", stock_at=STOCK_AT,
                      stock_is_known=True)


def test_an_honest_description_is_not_mistaken_for_a_price():
    """"Low cost" and "total weight" are things a supplier writes."""
    doc = cat.build([{"id": "1", "code": "A", "name": "Low Cost Tote",
                      "available": 5, "availableKnown": True,
                      "description": "A total of 12 colours. Low cost, high quality. "
                                     "Amounts to good value."}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    cat.assert_price_free(doc)
    assert "Low cost" in cat.extract_text(doc)


def test_a_generated_catalogue_from_a_priced_snapshot_succeeds(tmp_path, monkeypatch):
    """End to end: the snapshot holds prices in its internal store and the
    item's stock equals one of them. The catalogue is produced, not refused."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps({
        "fetchedAt": STOCK_AT, "stockAt": STOCK_AT,
        "internal": {"7": {"price": 100.0, "currency": "SAR", "booked": 3}},
        "products": [{
            "id": "7", "code": "EM-7", "name": "Hundred Mug", "brand": "Jasani",
            "color": "Black", "categories": ["Drinkware"], "description": "A mug.",
            "image": "", "images": [], "unitsPerCarton": 24,
            "stock": {"available": 100, "known": True, "incoming": 0},
            "list_price": 100.0, "retail_price": 100.0, "currency": "SAR"}]}),
        encoding="utf-8")
    blob = pdf_for(["7"])
    text = cat.extract_text(blob)
    assert "100 units" in text, "stock of 100 survives a price of 100"
    assert "SAR" not in text


# ---------------- what a page says ----------------

def test_the_quantity_and_its_date_are_both_on_the_page(snapshot):
    text = cat.extract_text(pdf_for(["1248"]))       # stock 248
    assert "248 units" in text
    assert "AVAILABLE QUANTITY" in text
    assert "Stock as of" in text
    assert time.strftime("%d %B %Y", time.localtime(STOCK_AT)) in text


def test_the_quantity_is_formatted_for_a_reader():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Bulk Item", "available": 1248}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "1,248 units" in text
    assert "1248.000000" not in text and "1248 units" not in text


def test_an_unknown_quantity_says_so_rather_than_printing_zero():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Mystery", "available": 0}],
                    {}, market="ksa", title="T", stock_at=None, stock_is_known=False)
    text = cat.extract_text(pdf)
    assert "Availability unavailable" in text
    assert "0 units" not in text
    assert "synchronisation date unavailable" in text


def test_zero_stock_is_printed_as_zero_when_it_really_is_zero():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Sold Out", "available": 0}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    assert "0 units" in cat.extract_text(pdf)


def test_a_product_the_stock_sync_passed_over_prints_as_unavailable():
    """Three states on one document: the market is synchronised, so a product
    the supplier answered for prints its figure, one it did not answer for
    prints as unavailable, and a record carrying no verdict at all — an older
    snapshot — follows the market rather than being read as a denial."""
    pdf = cat.build([
        {"id": "1", "code": "A", "name": "Answered", "available": 7,
         "availableKnown": True},
        {"id": "2", "code": "B", "name": "Skipped", "available": 0,
         "availableKnown": False},
        {"id": "3", "code": "C", "name": "No verdict", "available": 4},
    ], {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "7 units" in text
    assert "4 units" in text
    assert "Availability unavailable" in text
    #: and only the one product, not all three
    assert text.count("Availability unavailable") == 1


def test_the_stock_date_is_the_sync_not_the_moment_of_generation():
    """Generating at noon must not imply the stock was checked at noon."""
    old = time.time() - 60 * 60 * 30
    pdf = cat.build([{"id": "1", "code": "A", "name": "Item", "available": 3}],
                    {}, market="ksa", title="T", stock_at=old, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert time.strftime("%d %B %Y", time.localtime(old)) in text
    assert "Catalogue prepared" in text, "the two dates are labelled separately"


def test_supplier_html_is_printed_as_words_not_markup():
    pdf = cat.build([{
        "id": "1", "code": "A", "name": "Scripted <b>Item</b>",
        "description": "<p>Good</p><script>alert(1)</script>",
        "available": 2}], {}, market="ksa", title="T",
        stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "<b>" not in text and "<script>" not in text
    assert "Scripted Item" in text, "the tags are gone, the words remain"
    assert "Good" in text
    assert "alert(1)" in text, "script text is printed as inert words, never executed"


@pytest.mark.parametrize("junk", ["null", "undefined", "{}", "[]", "NaN", "none"])
def test_meaningless_values_are_left_out_rather_than_printed(junk):
    pdf = cat.build([{"id": "1", "code": "A", "name": "Item", "available": 1,
                      "description": junk, "brand": junk}], {},
                    market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert junk not in text
    assert "DESCRIPTION" not in text, "an empty description takes its heading with it"


def test_a_very_long_name_wraps_instead_of_overflowing():
    long_name = "Premium " * 40 + "Bottle"
    pdf = cat.build([{"id": "1", "code": "A", "name": long_name, "available": 1}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "Premium" in text
    assert "Page 2" in text and "Page 3" not in text, "still one page"


def test_a_long_description_and_many_specs_stay_on_one_page():
    pdf = cat.build([{
        "id": "1", "code": "A", "name": "Loaded Item", "available": 9,
        "description": "Sentence about the product. " * 120,
        "brand": "B", "color": "C", "material": "Steel", "size": "L",
        "capacity": "500 ml", "unitsPerCarton": 24, "cartonDimensions": "40x30x20",
        "cartonWeight": 9.5, "cartonVolume": 0.24, "hsCode": "1234",
        "barcode": "999", "categories": ["A", "B"], "options": ["X", "Y"]}], {},
        market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "Page 2" in text and "Page 3" not in text
    assert "SPECIFICATIONS" in text and "Units per carton" in text
    assert "AVAILABLE QUANTITY" in text, "the quantity is never pushed off the page"


def test_a_missing_image_gets_a_placeholder_and_does_not_fail_the_run():
    pdf = cat.build([{"id": "1", "code": "A", "name": "No Photo", "available": 1}],
                    {"1": []}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    assert "Image unavailable" in cat.extract_text(pdf)


def test_a_corrupt_image_does_not_fail_the_run():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Bad Photo", "available": 1}],
                    {"1": [b"this is not an image"]}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    assert "Image unavailable" in cat.extract_text(pdf)


def test_the_optional_sections_can_each_be_switched_off(snapshot):
    text = cat.extract_text(pdf_for(["1248"], description=False, specs=False,
                                    code=False, stockDate=False))
    assert "Product Number 248" in text
    assert "DESCRIPTION" not in text and "SPECIFICATIONS" not in text
    assert "ITGL 1248" not in text
    # the cover always names the snapshot date — that is what a cover is for.
    # The option governs the band on the product page, so the phrase appears
    # once rather than twice.
    assert text.count("Stock as of") == 1
    assert "248 units" in text


def test_a_contents_page_lists_every_item_and_its_page(snapshot):
    ids = [str(1000 + i) for i in range(4)]
    text = cat.extract_text(pdf_for(ids, contents=True))
    assert "Contents" in text and "ITEM CODE" in text
    assert "ITGL 1003" in text
    # cover, contents, then the four products
    assert "Page 3" in text and "Page 6" in text and "Page 7" not in text


def test_the_cover_names_the_market_and_the_count(snapshot):
    text = cat.extract_text(pdf_for([str(1000 + i) for i in range(3)]))
    assert "3 products" in text
    assert "Saudi Arabia" in text and "KSA" in text
    assert "Catalogue prepared" in text


def test_the_uae_catalogue_is_its_own_market(snapshot):
    res = start_catalogue(market="uae", ids=["u1"])
    assert res.status_code == 200
    token = res.json()["token"]
    assert finish(token)["state"] == "done"
    got = client.get("/api/admin/jasani/catalogue/download", params={"token": token})
    text = cat.extract_text(got.content)
    assert "Dubai Mug" in text and "United Arab Emirates" in text
    assert "7 units" in text
    assert "UAE" in got.headers["content-disposition"]


def test_the_filename_names_the_market_and_the_day(snapshot):
    res = start_catalogue(ids=["1000"])
    token = res.json()["token"]
    finish(token)
    got = client.get("/api/admin/jasani/catalogue/download", params={"token": token})
    name = got.headers["content-disposition"]
    assert "Elite-Marcom-Jasani-Catalogue-KSA-" in name
    assert time.strftime("%Y-%m-%d") in name and name.endswith('.pdf"')


def test_a_minimum_stock_carried_into_the_catalogue_excludes_the_short_items(snapshot):
    res = start_catalogue(scope="filtered", minStock="637")
    assert res.status_code == 200
    assert res.json()["items"] == 3           # 637, 638, 639
    text = cat.extract_text(pdf_for([], scope="filtered", minStock="637"))
    assert "Product Number 637" in text
    assert "Product Number 636" not in text


# ---------------- the supplier is never called ----------------

def test_nothing_on_this_screen_spends_a_supplier_call(snapshot, monkeypatch):
    """The budget is the thing to protect: five primary calls per market per
    day. Searching, filtering, paging, selecting and generating a catalogue
    must all read the snapshot and nothing else."""
    calls = []

    async def boom(*a, **k):
        calls.append(a)
        raise AssertionError("the supplier was called")

    monkeypatch.setattr(jasani, "_fetch", boom)
    for name in ("_fetch_products", "_fetch_stock", "_fetch_prices"):
        if hasattr(jasani, name):
            monkeypatch.setattr(jasani, name, boom)
    spent = []
    real_write = jasani._write_budget
    monkeypatch.setattr(jasani, "_write_budget",
                        lambda m, b: spent.append(m) or real_write(m, b))

    items(perPage=500)
    items(q="Number 600", perPage=500)
    items(minStock=100, perPage=250, page=2)
    blob = pdf_for([str(1000 + i) for i in range(5)])

    assert calls == [], "a supplier endpoint was reached"
    assert spent == [], "the daily budget file was written to"
    assert b"%PDF" in blob[:8]


def test_the_budget_file_is_untouched_by_a_catalogue(snapshot):
    """The five-a-day counter must read exactly the same afterwards."""
    before = {m: jasani._read_budget(m) for m in ("ksa", "uae")}
    pdf_for(["1000", "1001"])
    assert {m: jasani._read_budget(m) for m in ("ksa", "uae")} == before


# ---------------- permissions, CSRF, audit ----------------

def test_a_catalogue_needs_the_jasani_permission_server_side(snapshot):
    client.post("/api/admin/logout", headers=csrf())
    try:
        assert client.post("/api/admin/jasani/catalogue",
                           json={"market": "ksa", "ids": ["1000"]}).status_code == 401
        assert client.get("/api/admin/jasani/catalogue/status",
                          params={"token": "x"}).status_code == 401
        assert client.get("/api/admin/jasani/catalogue/download",
                          params={"token": "x"}).status_code == 401
        assert client.get("/api/admin/jasani/items").status_code == 401
    finally:
        sign_in()


def test_starting_a_catalogue_needs_the_csrf_header(snapshot):
    """Signed in, but without the header — the write is still refused."""
    assert client.get("/api/admin/me").status_code == 200, "signed in"
    assert client.post("/api/admin/jasani/catalogue",
                       json={"market": "ksa", "ids": ["1000"]}).status_code == 403


def test_one_admin_cannot_collect_another_admin_s_catalogue(snapshot):
    token = start_catalogue(ids=["1000"]).json()["token"]
    finish(token)
    assert cat.get(token, "someone.else@example.com") is None


def test_the_pdf_is_handed_over_once_and_not_kept(snapshot):
    token = start_catalogue(ids=["1000"]).json()["token"]
    finish(token)
    assert client.get("/api/admin/jasani/catalogue/download",
                      params={"token": token}).status_code == 200
    # collected: the bytes are dropped rather than sitting in memory
    assert client.get("/api/admin/jasani/catalogue/download",
                      params={"token": token}).status_code == 404


def test_a_catalogue_is_recorded_as_requested_then_as_generated(snapshot):
    """Two facts, two entries. "Generated" is written by the worker once the
    document exists — claiming it when the job was merely asked for would be
    an audit trail that records intentions rather than outcomes."""
    pdf_for(["1000", "1001"], minStock="")
    actions = [a["action"] for a in aa.audit_list(40)]
    assert "jasani.catalogue_requested" in actions
    assert "jasani.catalogue_generated" in actions
    # requested first, generated after — ids ascend with time
    entries = {a["action"]: a for a in aa.audit_list(40)
               if a["action"].startswith("jasani.catalogue")}
    assert entries["jasani.catalogue_requested"]["id"] < \
        entries["jasani.catalogue_generated"]["id"]
    for action in ("jasani.catalogue_requested", "jasani.catalogue_generated"):
        detail = json.loads(entries[action]["detail"])
        assert detail["market"] == "ksa" and detail["items"] == 2
        assert detail["stockAt"] == STOCK_AT
        assert entries[action]["user_email"] == "owner@elitemarcom.com"
    assert json.loads(entries["jasani.catalogue_generated"]["detail"])["pages"] == 2


def test_a_failed_catalogue_is_not_recorded_as_generated(snapshot, monkeypatch):
    """A build that dies must not leave "generated" in the log."""
    def boom(*a, **k):
        raise cat.CatalogueError("a price indicator reached the catalogue: 'sar'")

    monkeypatch.setattr(cat, "assert_price_free", boom)
    before = aa.audit_list(1)[0]["id"] if aa.audit_list(1) else 0
    res = start_catalogue(ids=["1000"])
    assert res.status_code == 200
    job = finish(res.json()["token"])
    assert job["state"] == "failed"
    # only what this build wrote, so an earlier test's success cannot mask it
    mine = [a["action"] for a in aa.audit_list(40) if a["id"] > before]
    assert "jasani.catalogue_requested" in mine
    assert "jasani.catalogue_failed" in mine
    assert "jasani.catalogue_generated" not in mine


# ---------------- zero stock is not unknown stock ----------------

def test_a_product_the_stock_sync_skipped_stays_unknown(tmp_path, monkeypatch):
    """A successful market sync is not a promise that it covered every
    product. One the supplier had no row for keeps an unknown quantity rather
    than becoming a confident zero."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = [
        {"id": "a", "code": "A", "name": "Counted Item", "brand": "", "color": "",
         "categories": [], "image": "", "images": [],
         "stock": {"available": 12, "known": True, "incoming": 0}},
        {"id": "b", "code": "B", "name": "Skipped Item", "brand": "", "color": "",
         "categories": [], "image": "", "images": [],
         "stock": {"available": 0, "known": False, "incoming": 0}},
        {"id": "c", "code": "C", "name": "Genuinely Empty", "brand": "", "color": "",
         "categories": [], "image": "", "images": [],
         "stock": {"available": 0, "known": True, "incoming": 0}},
    ]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": products}),
        encoding="utf-8")
    assert jasani.stock_known("ksa") is True, "the market did sync"
    rows = {r["id"]: r for r in items(perPage=100)["items"]}
    assert rows["a"]["availableKnown"] is True
    assert rows["b"]["availableKnown"] is False, "skipped by the sync"
    assert rows["c"]["availableKnown"] is True, "a real zero"
    # a positive minimum keeps the counted one and drops both the unknown and
    # the genuine zero, for different reasons
    assert [r["id"] for r in items(minStock=1, perPage=100)["items"]] == ["a"]
    # and the catalogue says which is which
    text = cat.extract_text(pdf_for(["a", "b", "c"]))
    assert "12 units" in text
    assert "0 units" in text, "a real zero is printed as zero"
    assert "Availability unavailable" in text, "an unknown one is not"


def test_the_merge_marks_only_the_products_the_supplier_answered_for():
    """The contract this rests on, asserted directly."""
    products = [jasani.normalize_product({"id": "1", "code": "A", "name": "One"}, "ksa"),
                jasani.normalize_product({"id": "2", "code": "B", "name": "Two"}, "ksa")]
    assert [p["stock"]["known"] for p in products] == [False, False], (
        "a products feed with no quantity field leaves both unknown")
    matched = jasani._merge_stock(products, [{"id": "1", "net_available_qty": 9}])
    assert matched == 1
    assert products[0]["stock"] == {"available": 9, "known": True, "incoming": 0,
                                    "incomingDate": None}
    assert products[1]["stock"]["known"] is False
    assert products[1]["stock"]["available"] == 0


def test_a_products_feed_that_carries_quantities_is_known_without_a_stock_call():
    p = jasani.normalize_product(
        {"id": "1", "code": "A", "name": "One", "net_available_qty": 40}, "ksa")
    assert p["stock"] == {"available": 40, "known": True, "incoming": 0,
                          "incomingDate": None}


def test_an_older_snapshot_without_the_flag_falls_back_to_the_market(tmp_path,
                                                                    monkeypatch):
    """A file written before per-item tracking carries no flag; reading it as
    the market-level answer is the honest interpretation."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    old_shape = [{"id": "1", "code": "A", "name": "Legacy", "brand": "", "color": "",
                  "categories": [], "image": "", "images": [],
                  "stock": {"available": 5, "incoming": 0}}]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": old_shape}),
        encoding="utf-8")
    assert items()["items"][0]["availableKnown"] is True
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "products": old_shape}), encoding="utf-8")
    assert items()["items"][0]["availableKnown"] is False


# ---------------- normalized measures reach the page ----------------

def _normalized(**extra) -> dict:
    """A product as `normalize_product` really produces it, so a test cannot
    pass by hand-building the shape the renderer happens to want."""
    rec = {"id": "1", "code": "ITGL 1", "name": "Carton Item",
           "description": "A boxed item.", "units_per_carton": 24}
    rec.update(extra)
    return jasani.normalize_product(rec, "ksa")


def test_the_normalizer_really_produces_measure_strings():
    """The premise of the fix: these fields are strings, not numbers. A test
    that asserted on numeric dicts would have passed throughout the bug."""
    p = _normalized(carton_weight="9.500000000000001", carton_volume="0.240")
    assert p["cartonWeight"] == "9.5" and isinstance(p["cartonWeight"], str)
    assert p["cartonVolume"] == "0.24" and isinstance(p["cartonVolume"], str)


def test_a_normalized_carton_weight_and_volume_reach_the_catalogue(snapshot):
    """What the review found: read as numbers, every normalized measure was
    dropped and the carton rows vanished from the document."""
    p = _normalized(carton_weight="9.5", carton_volume="0.24")
    dto = cat.to_dto(p)
    assert dto["cartonWeight"] == "9.5" and dto["cartonVolume"] == "0.24"
    pdf = cat.build([dto], {}, market="ksa", title="T", stock_at=STOCK_AT,
                    stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "9.5 kg" in text
    assert "0.24 m" in text                   # m³ may decode as m³ or m3
    assert "Carton weight" in text and "Carton volume" in text


def test_a_unit_the_supplier_already_wrote_is_not_doubled(snapshot):
    """The supplier sends "9.5" on one product and "9.5 kg" on the next, and
    `_weight` keeps whatever suffix came with the figure."""
    p = _normalized(carton_weight="9.5 kg", carton_volume="0.24 m³")
    assert p["cartonWeight"] == "9.5 kg"      # the normalizer kept the unit
    text = cat.extract_text(cat.build([cat.to_dto(p)], {}, market="ksa", title="T",
                                      stock_at=STOCK_AT, stock_is_known=True))
    assert "9.5 kg" in text
    assert "kg kg" not in text
    assert "m³ m³" not in text and "m3 m3" not in text


@pytest.mark.parametrize("key,value,printed", [
    ("cartonWeight", "9.5", "9.5 kg"),
    ("cartonWeight", "9.5 kg", "9.5 kg"),
    ("cartonWeight", "9.5kg", "9.5kg"),
    ("cartonWeight", "9.5 KGS", "9.5 KGS"),
    ("cartonVolume", "0.24", "0.24 m³"),
    ("cartonVolume", "0.24 m³", "0.24 m³"),
    ("cartonVolume", "0.24 m3", "0.24 m3"),
    ("cartonVolume", "0.24 CBM", "0.24 CBM"),
])
def test_a_measure_is_printed_with_exactly_one_unit(key, value, printed):
    assert cat.with_unit(key, value) == printed


@pytest.mark.parametrize("value", ["0", "0.0", "-2", "n/a", "", "   ", None])
def test_a_measure_that_is_not_a_positive_figure_is_left_out(value):
    """Printing "Carton weight 0 kg" would be inventing a fact; the row is
    simply absent instead."""
    assert cat._measure(value) is None
    rows = dict(cat.spec_rows({"cartonWeight": value, "cartonVolume": value}))
    assert "Carton weight" not in rows and "Carton volume" not in rows


def test_a_numeric_measure_from_a_future_feed_still_prints():
    """Strings are what we get today; a number must not break tomorrow."""
    assert cat._measure(9.5) == "9.5" and cat._measure(24) == "24"
    assert dict(cat.spec_rows({"cartonWeight": 9.5}))["Carton weight"] == "9.5 kg"


# ---------------- a matched stock row is not a quantity ----------------

def _two_products() -> list[dict]:
    return [jasani.normalize_product({"id": "1", "code": "A", "name": "One",
                                      "net_available_qty": 50}, "ksa"),
            jasani.normalize_product({"id": "2", "code": "B", "name": "Two",
                                      "net_available_qty": 50}, "ksa")]


def test_a_stock_row_that_really_says_zero_is_a_known_zero():
    products = _two_products()
    assert jasani._merge_stock(products, [{"id": "1", "net_available_qty": 0}]) == 1
    assert products[0]["stock"]["available"] == 0
    assert products[0]["stock"]["known"] is True


def test_a_stock_row_with_a_quantity_replaces_the_figure():
    products = _two_products()
    assert jasani._merge_stock(products, [{"id": "1", "net_available_qty": 25}]) == 1
    assert products[0]["stock"]["available"] == 25
    assert products[0]["stock"]["known"] is True


def test_a_matched_stock_row_carrying_no_quantity_is_not_a_known_zero():
    """A row that matches on id but holds no recognized quantity key tells us
    nothing about this product. `_i` returning its default is not the supplier
    saying nought, and treating it as one wiped a real fifty."""
    products = _two_products()
    row = {"id": "1", "incoming_qty": 4, "incoming_date": "2026-11-01"}
    assert jasani._merge_stock(products, [row]) == 1
    assert products[0]["stock"]["available"] == 50, "the known figure survived"
    assert products[0]["stock"]["known"] is True, "and is still the products feed's"
    assert products[0]["stock"]["incoming"] == 4, "what the row did carry applied"


def test_a_matched_row_without_a_quantity_leaves_an_unknown_product_unknown():
    products = [jasani.normalize_product({"id": "1", "code": "A", "name": "One"}, "ksa")]
    assert products[0]["stock"]["known"] is False
    jasani._merge_stock(products, [{"id": "1", "blocked_qty": 3}])
    assert products[0]["stock"]["known"] is False, "no quantity, no verdict"
    assert products[0]["stock"]["available"] == 0


# ---------------- carry-forward is about known, not about zero ----------------

def test_an_explicit_zero_from_the_products_feed_survives_carry_forward():
    """A genuine sold-out must not be overwritten by yesterday's fifty. The
    old test was `available == 0`, which could not tell the two apart."""
    cached = {"products": [{"id": "1", "stock": {"available": 50, "known": True}}]}
    fresh = [jasani.normalize_product({"id": "1", "code": "A", "name": "One",
                                       "net_available_qty": 0}, "ksa")]
    assert jasani._carry_stock(fresh, cached) == 0
    assert fresh[0]["stock"]["available"] == 0
    assert fresh[0]["stock"]["known"] is True


def test_a_products_feed_with_no_quantity_takes_yesterdays_stock():
    cached = {"products": [{"id": "1", "stock": {"available": 50, "known": True,
                                                 "incoming": 0, "incomingDate": None}}]}
    fresh = [jasani.normalize_product({"id": "1", "code": "A", "name": "One"}, "ksa")]
    assert fresh[0]["stock"]["known"] is False
    assert jasani._carry_stock(fresh, cached) == 1
    assert fresh[0]["stock"]["available"] == 50
    assert fresh[0]["stock"]["known"] is True, "yesterday's figure was a real one"


def test_a_products_feed_with_a_real_quantity_keeps_its_own():
    cached = {"products": [{"id": "1", "stock": {"available": 50, "known": True}}]}
    fresh = [jasani.normalize_product({"id": "1", "code": "A", "name": "One",
                                       "net_available_qty": 12}, "ksa")]
    assert jasani._carry_stock(fresh, cached) == 0
    assert fresh[0]["stock"]["available"] == 12


def test_an_older_cached_snapshot_is_still_carried_forward():
    """A file written before the flag existed: read its figure, which is the
    only reading that file supports."""
    cached = {"products": [{"id": "1", "stock": {"available": 50, "incoming": 0}}]}
    fresh = [jasani.normalize_product({"id": "1", "code": "A", "name": "One"}, "ksa")]
    assert jasani._carry_stock(fresh, cached) == 1
    assert fresh[0]["stock"]["available"] == 50


def test_the_scheduled_products_sync_carries_stock_the_same_way(tmp_path, monkeypatch):
    """The whole path, not just the helper: the midnight products call."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps({
        "fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": [
            {"id": "1", "code": "A", "name": "Kept", "stock": {"available": 50,
                                                               "known": True}},
            {"id": "2", "code": "B", "name": "Emptied", "stock": {"available": 50,
                                                                  "known": True}},
        ]}), encoding="utf-8")

    async def feed(market, manual=False):
        return [jasani.normalize_product({"id": "1", "code": "A", "name": "Kept"}, "ksa"),
                jasani.normalize_product({"id": "2", "code": "B", "name": "Emptied",
                                          "net_available_qty": 0}, "ksa")]

    monkeypatch.setattr(jasani, "_fetch_products", feed)
    asyncio.run(jasani._refresh_products_only("ksa"))
    by_id = {p["id"]: p for p in jasani._read_cache("ksa")["products"]}
    assert by_id["1"]["stock"]["available"] == 50, "no quantity in the feed"
    assert by_id["2"]["stock"]["available"] == 0, "the feed really said nought"
    assert by_id["2"]["stock"]["known"] is True


# ---------------- three pictures on one page, still bounded ----------------

def test_a_product_with_three_photographs_draws_and_releases_all_three(photos,
                                                                      monkeypatch,
                                                                      tmp_path):
    """The 500-product load test is one picture per product, because that is
    what the fixture snapshot carries. This is the three-picture path: the
    main image and the secondary strip, measured on a small number of
    products so a full test run does not pay for 1,500 transformations."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = [{
        "id": str(n), "code": f"ITGL {n}", "name": f"Three Shot {n}",
        "brand": "Elite", "color": "Blue", "categories": ["Drinkware"],
        "description": "Photographed from three angles.",
        "image": f"https://www.giftsksa.com/img/{n}-a.jpg",
        "images": [f"https://www.giftsksa.com/img/{n}-a.jpg",
                   f"https://www.giftsksa.com/img/{n}-b.jpg",
                   f"https://www.giftsksa.com/img/{n}-c.jpg"],
        "unitsPerCarton": 24,
        "stock": {"available": 10, "known": True, "incoming": 0},
    } for n in range(8)]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": products}),
        encoding="utf-8")

    held = {"max": 0, "pages": 0, "three": 0}
    real_page = cat.Document.page

    def watched(self, dto, blobs):
        held["max"] = max(held["max"], sum(len(b) for b in blobs))
        held["pages"] += 1
        if len(blobs) == 3:
            held["three"] += 1
        real_page(self, dto, blobs)

    monkeypatch.setattr(cat.Document, "page", watched)
    blob = pdf_for([str(n) for n in range(8)])
    text = cat.extract_text(blob)

    assert held["pages"] == 8
    assert held["three"] == 8, "every page received all three photographs"
    assert photos["fetches"] == 24, "three per product, fetched once each"
    assert text.count("Image unavailable") == 0
    assert "Three Shot 0" in text and "Three Shot 7" in text
    # three prepared pictures, not three originals, and released afterwards
    assert held["max"] < 1024 * 1024, held["max"]
    assert photos["peak"] < 4 * 1024 * 1024, photos["peak"]
    print(f"\n  8 products x 3 photographs · {photos['fetches']} fetches · "
          f"source {photos['bytes'] / 1024 / 1024:.1f} MB · "
          f"largest page working set {held['max'] / 1024:.0f} KB · "
          f"peak prepared {photos['peak'] / 1024 / 1024:.1f} MB")


def test_the_photograph_cache_stays_bounded_across_many_products(snapshot, photos,
                                                                 monkeypatch):
    """`PHOTO_CACHE_MAX` is the ceiling on what is remembered between
    products, so a long catalogue cannot grow one."""
    seen = {"max": 0}
    real = cat._photos_for

    async def watched(market, dto, cache):
        out = await real(market, dto, cache)
        seen["max"] = max(seen["max"], len(cache))
        return out

    monkeypatch.setattr(cat, "_photos_for", watched)
    pdf_for([str(1000 + i) for i in range(80)])
    assert seen["max"] <= cat.PHOTO_CACHE_MAX, seen["max"]


def test_the_dto_reads_a_quantity_in_either_shape():
    """The admin row carries it flat, a normalized product under `stock`. A
    DTO that understood only one shape is how the carton measures were lost,
    so it understands both."""
    p = jasani.normalize_product({"id": "1", "code": "A", "name": "One",
                                  "net_available_qty": 10}, "ksa")
    nested = cat.to_dto(p)
    assert nested["available"] == 10 and nested["availableKnown"] is True
    flat = cat.to_dto({"id": "1", "code": "A", "name": "One",
                       "available": 10, "availableKnown": True})
    assert flat["available"] == 10 and flat["availableKnown"] is True
    # and a row that says "not known" still wins over a nested figure
    mixed = cat.to_dto({**p, "available": 0, "availableKnown": False})
    assert mixed["available"] == 0 and mixed["availableKnown"] is False
    assert "10 units" in cat.extract_text(
        cat.build([nested], {}, market="ksa", title="T", stock_at=STOCK_AT,
                  stock_is_known=True))


# ---------------- the production failure: supplier price text ----------------
#
# "a price indicator reached the catalogue: 'rrp'" was a real Jasani product
# with "RRP: SAR 45" inside its description. Refusing the document is the
# right last resort, but one careless supplier sentence must not make a
# catalogue impossible — so the text is cleaned on the way in and the guard
# then has nothing to find.

def _priced_snapshot(tmp_path, monkeypatch, products):
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    rows = []
    for n, extra in enumerate(products):
        row = {"id": str(n + 1), "code": f"ITGL {1291 + n}", "name": f"Item {n}",
               "brand": "Jasani", "color": "Black", "categories": ["Drinkware"],
               "description": "", "image": "", "images": [],
               "stock": {"available": 100, "known": True, "incoming": 0}}
        row.update(extra)
        rows.append(row)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": rows}),
        encoding="utf-8")
    return rows


def test_a_the_production_record_builds_and_keeps_the_useful_description(tmp_path,
                                                                        monkeypatch):
    """Case A — the exact shape that failed in production."""
    _priced_snapshot(tmp_path, monkeypatch, [{
        "name": "Premium Bottle",
        "description": "Premium Bottle. RRP: SAR 45. Capacity 500 ml.",
        "capacity": "500 ml"}])
    text = cat.extract_text(pdf_for(["1"]))
    assert "Premium Bottle" in text
    assert "Capacity 500 ml" in text or "500 ml" in text
    assert "rrp" not in text.lower()
    assert not re.search(r"\b(?:sar|aed|usd)\b", text, re.I)
    assert not re.search(r"\b45\b", text), "the amount went with its currency"
    assert "100 units" in text, "the quantity is unaffected"


def test_b_a_description_that_is_only_a_price_is_omitted(tmp_path, monkeypatch):
    """Case B — nothing useful to keep, so the field simply does not print."""
    _priced_snapshot(tmp_path, monkeypatch, [{
        "name": "Canvas Tote", "description": "Retail Price: AED 29"}])
    text = cat.extract_text(pdf_for(["1"]))
    assert "Canvas Tote" in text
    assert "Retail Price" not in text and "AED" not in text
    #: a word boundary, because the product code is ITGL 1291 and a bare "29"
    #: substring test would be reading the code rather than the amount
    assert not re.search(r"\b29\b", text)


def test_c_ordinary_words_that_look_like_prices_survive(tmp_path, monkeypatch):
    """Case C — "low cost" is a description, not a price."""
    _priced_snapshot(tmp_path, monkeypatch, [{
        "name": "Value Pen",
        "description": "Low cost, high quality. A price-conscious design."}])
    text = cat.extract_text(pdf_for(["1"]))
    assert "Low cost, high quality." in text
    assert "price-conscious design" in text


def test_d_a_capacity_that_equals_a_price_still_prints(tmp_path, monkeypatch):
    """Case D — the numeric false positive stays fixed: 500 ml beside a
    supplier price of 500."""
    _priced_snapshot(tmp_path, monkeypatch, [{
        "name": "Half Litre Bottle", "capacity": "500 ml",
        "description": "Holds 500 ml.", "cartonWeight": "9.5 kg"}])
    text = cat.extract_text(pdf_for(["1"]))
    assert "500 ml" in text
    assert "9.5 kg" in text


def test_e_a_quantity_that_equals_a_price_still_prints(tmp_path, monkeypatch):
    """Case E — 100 in stock beside a supplier price of 100."""
    _priced_snapshot(tmp_path, monkeypatch, [{"name": "Hundred Item"}])
    assert "100 units" in cat.extract_text(pdf_for(["1"]))


def test_f_a_price_option_is_left_out_and_the_others_kept(tmp_path, monkeypatch):
    """Case F — one bad option costs that option, not the row."""
    _priced_snapshot(tmp_path, monkeypatch, [{
        "name": "Three Colours", "options": ["Black", "RRP 20 SAR", "Blue"]}])
    text = cat.extract_text(pdf_for(["1"]))
    assert "Black" in text and "Blue" in text
    assert "RRP" not in text and not re.search(r"\b20\b", text)


def test_g_bypassing_the_sanitizer_still_fails_the_document(snapshot, monkeypatch):
    """Case G — the final guard is still fail-closed. Sanitization is the
    first answer, never the only one."""
    def unsanitized(value, field=""):
        return value                           # the sanitizer, switched off

    monkeypatch.setattr(cat, "sanitize_catalogue_text", unsanitized)
    with pytest.raises(cat.CatalogueError) as exc:
        cat.build([{"id": "1", "code": "A", "name": "Leaky",
                    "description": "Retail Price: 100 SAR"}],
                  {}, market="ksa", title="T", stock_at=STOCK_AT,
                  stock_is_known=True)
    assert "price indicator" in str(exc.value)


def test_the_guard_still_runs_on_every_finished_document():
    """Not a mock: `Document.finish` really calls it, so no path can skip."""
    import inspect

    assert "assert_price_free" in inspect.getsource(cat.Document.finish)
    assert "rrp" in cat.PRICE_WORDS, "the indicator was not quietly deleted"


@pytest.mark.parametrize("raw,field,expected", [
    # the four worked examples from the bug report
    ("Premium stainless steel bottle. RRP: SAR 45. Capacity 500 ml.",
     "description", "Premium stainless steel bottle. Capacity 500 ml."),
    ("Material: ABS\nRetail Price: AED 29\nAvailable colours: Black, Blue",
     "description", "Material: ABS\nAvailable colours: Black, Blue"),
    ("High quality notebook. RRP available on request.",
     "description", "High quality notebook."),
    ("List Price 22.50 SAR", "description", ""),
    # the label shapes a supplier actually writes
    ("R.R.P. 99", "description", ""),
    ("Recommended Retail Price 40", "description", ""),
    ("Unit Price: 3", "description", ""),
    ("Selling price 12 AED", "description", ""),
    ("Reseller Price on request", "description", ""),
    ("Wholesale Price 12", "description", ""),
    ("Price: 10", "description", ""),
    ("Price - 45", "description", ""),
    ("Quoted ex VAT.", "description", ""),
    ("Notebook A5. Including VAT.", "description", "Notebook A5."),
    # and the ordinary words that must survive
    ("Low cost, high quality.", "description", "Low cost, high quality."),
    ("A price-conscious design.", "description", "A price-conscious design."),
    ("Made for the UAE market.", "description", "Made for the UAE market."),
    ("Saed Classic Pen", "name", "Saed Classic Pen"),
    ("Priceless craftsmanship.", "description", "Priceless craftsmanship."),
    # structured values are kept whole or dropped whole
    ("Black", "color", "Black"),
    ("500 ml", "capacity", "500 ml"),
    ("30 x 20 x 15 cm", "cartonDimensions", "30 x 20 x 15 cm"),
    ("RRP 20 SAR", "option", ""),
    ("Retail price group", "brand", ""),
])
def test_the_sanitizer_on_the_shapes_a_supplier_writes(raw, field, expected):
    assert cat.sanitize_catalogue_text(raw, field) == expected


def test_a_removed_currency_never_leaves_its_amount_behind():
    """"Retail price: 45 SAR" must not become "45"."""
    for raw in ("Retail price: 45 SAR", "45 SAR", "SAR 45", "AED 12.50", "USD 5",
                "R.R.P. 99", "Bottle. RRP - 45. Blue."):
        out = cat.sanitize_catalogue_text(raw, "description")
        assert not re.search(r"\b(?:sar|aed|usd)\b", out, re.I), (raw, out)
        assert not re.search(r"\b(?:45|99|12\.50|5)\b", out), (raw, out)


def test_nothing_the_sanitizer_passes_can_trip_the_guard():
    """The two halves agree: what sanitization keeps, the guard accepts."""
    for raw in ("Premium bottle. RRP: SAR 45. Holds 500 ml.",
                "Retail Price: AED 29", "List Price 22.50 SAR", "R.R.P. 99",
                "Low cost, high quality.", "A price-conscious design.",
                "Material: ABS\nRetail Price: AED 29\nColours: Black"):
        kept = cat.sanitize_catalogue_text(raw, "description")
        if kept:
            cat.assert_price_free(cat.build(
                [{"id": "1", "code": "A", "name": "One", "description": kept,
                  "available": 100, "availableKnown": True}],
                {}, market="ksa", title="T", stock_at=STOCK_AT,
                stock_is_known=True))


def test_the_cleanup_is_counted_and_reported(tmp_path, monkeypatch):
    """Silently editing a customer document is worse than saying so. The job
    carries counts — never the figure that was removed."""
    _priced_snapshot(tmp_path, monkeypatch, [
        {"name": "One", "description": "Bottle. RRP: SAR 45. Blue.",
         "options": ["Black", "Price 20 AED"]},
        {"name": "Two", "description": "Plain notebook."},
        {"name": "Three", "description": "Retail Price: AED 29"},
    ])
    res = start_catalogue(ids=["1", "2", "3"])
    assert res.status_code == 200
    job = finish(res.json()["token"])
    assert job["state"] == "done"
    assert job["sanitizedProducts"] == 2, job
    assert job["sanitizedFields"] == 3, job
    blob = json.dumps(job)
    assert "45" not in blob and "29" not in blob, "no removed figure is reported"


def test_a_clean_catalogue_reports_no_cleanup(snapshot):
    res = start_catalogue(ids=["1000"])
    job = finish(res.json()["token"])
    assert job["state"] == "done"
    assert job["sanitizedProducts"] == 0 and job["sanitizedFields"] == 0


def test_a_price_name_cannot_slip_in_through_the_contents_page(tmp_path,
                                                              monkeypatch):
    """The contents list reads the name separately, so it is sanitized
    separately — otherwise a priced name would fail the whole document."""
    _priced_snapshot(tmp_path, monkeypatch, [
        {"name": "Bottle RRP SAR 45", "description": "A bottle."},
        {"name": "Notebook", "description": "A notebook."},
    ])
    text = cat.extract_text(pdf_for(["1", "2"], contents=True))
    assert "RRP" not in text and not re.search(r"\b(?:sar|aed)\b", text, re.I)
    assert not re.search(r"\b45\b", text)
    assert "Notebook" in text


def test_the_audit_script_names_the_field_and_never_the_price(tmp_path,
                                                              monkeypatch, capsys):
    """`scripts/audit_catalogue_text.py` answers "which product caused it"
    from the cache alone — no supplier call, and no supplier price in the
    output."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_catalogue_text", "scripts/audit_catalogue_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CACHE", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps({"products": [
        {"id": "1", "code": "ITGL 1291", "name": "Flask",
         "description": "Steel flask, 500 ml. RRP: SAR 45. Hot for 12 hours.",
         "options": ["Black", "RRP 20 SAR"]},
        {"id": "2", "code": "ITGL 1400", "name": "Pad",
         "description": "Plain notepad."},
    ]}), encoding="utf-8")
    hits = mod.audit("ksa")
    out = capsys.readouterr().out
    assert hits == 2
    assert "ITGL 1291" in out and "description" in out
    assert "ITGL 1400" not in out
    assert "45" not in out and "20" not in out, "no supplier price is printed"
    assert "rrp" in out
