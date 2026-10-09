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

    def counted(raw, **kw):
        out = real_prepare(raw, **kw)
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
    assert text.count("Photograph unavailable") == 0, "no page fell back to a placeholder"
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
    assert text.count("Photograph unavailable") == 1, "exactly the one that failed"
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
    assert "AVAILABLE NOW" in text
    assert "STOCK UPDATED" in text
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
    assert "AVAILABILITY UNAVAILABLE" in text
    assert "AVAILABLE NOW" not in text, "and it must not also claim to be"
    assert "0 units" not in text
    assert "synchronisation date unavailable" in text


def test_zero_stock_is_printed_as_zero_when_it_really_is_zero():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Sold Out", "available": 0}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    assert "0 units" in cat.extract_text(pdf)


# ---------------- the availability label is the verdict ----------------
#
# Production review found "AVAILABLE NOW" over "0 units" on ITWC 1302,
# Maglite 5K - Navy Blue: a genuinely empty product, correctly reported as
# empty, under a label that had been written once and never read the figures.
# A reader takes the label away from the page, so the label is the bug.


@pytest.mark.parametrize("available,known,state", [
    (7, True, "in"),
    (1, True, "in"),
    (1248, True, "in"),
    (0, True, "out"),
    (0.4, True, "out"),            # prints "0 units", so it is not available
    (0.6, True, "in"),             # prints "1 units"
    (0, False, "unknown"),
    (7, False, "unknown"),         # a figure nobody vouches for is no figure
    (None, True, "unknown"),
    ("", True, "unknown"),
    ("n/a", True, "unknown"),
])
def test_the_three_availability_states_are_read_from_the_figures(available, known, state):
    assert cat.stock_state(available, known) == state


@pytest.mark.parametrize("available,known", [
    (7, True), (0, True), (0.4, True), (1248, True),
    (0, False), (None, True), ("n/a", True),
])
def test_the_state_and_the_printed_quantity_cannot_disagree(available, known):
    """The whole of the defect in one assertion: whatever the band says in
    words must be what its number says. `stock_state` reads the integer
    `stock_sentence` would print, not the raw value, which is why a quantity
    of 0.4 is OUT OF STOCK rather than AVAILABLE NOW over a printed nought."""
    state = cat.stock_state(available, known)
    headline = cat.stock_sentence(available, known)[0]
    if state == "unknown":
        assert headline == "Availability unavailable"
        return
    figure = headline.partition(" ")[0]
    assert headline.endswith(" units"), headline
    n = int(figure.replace(",", ""))
    assert (n > 0) == (state == "in"), (state, headline)


def test_a_genuinely_empty_product_is_not_labelled_available(snapshot):
    """The reported page, rebuilt."""
    pdf = cat.build([{"id": "1", "code": "ITWC 1302",
                      "name": "Maglite 5K - Navy Blue", "available": 0,
                      "availableKnown": True}], {}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "OUT OF STOCK" in text
    assert "AVAILABLE NOW" not in text, "the contradiction this corrects"
    assert "0 units" in text, "the real figure still prints"
    #: and the market's synchronisation date is untouched by any of it
    assert "STOCK UPDATED" in text
    assert time.strftime("%d %B %Y", time.localtime(STOCK_AT)) in text


def test_all_three_availability_states_on_one_document():
    """One PDF, one market, three products — the three states the band can
    be in — read back out of the finished document's text."""
    pdf = cat.build([
        {"id": "1", "code": "ITGL 1000", "name": "In Stock", "available": 1248,
         "availableKnown": True},
        {"id": "2", "code": "ITWC 1302", "name": "Maglite 5K - Navy Blue",
         "available": 0, "availableKnown": True},
        {"id": "3", "code": "ITGL 1002", "name": "Not Synchronised",
         "available": 0, "availableKnown": False},
    ], {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)

    #: each label exactly once, on its own product's page
    assert text.count("AVAILABLE NOW") == 1
    assert text.count("OUT OF STOCK") == 1
    assert text.count("AVAILABILITY UNAVAILABLE") == 1

    #: and the quantities that belong with them
    assert "1,248 units" in text, "known positive"
    assert "0 units" in text, "known zero"
    assert text.count("units") == 2, "the unknown one prints no quantity"
    assert cat.STOCK_UNKNOWN_FIGURE in text

    #: each label and its figure are on the same page, not merely both
    #: somewhere in the document — the code is one drawn string, while the
    #: name is set in parts, so the code is what a page is found by
    pages = {code: chunk for code, chunk in
             ((c, text.split(c, 1)[1].split("www.elitemarcom.com", 1)[0])
              for c in ("ITGL 1000", "ITWC 1302", "ITGL 1002"))}
    assert "AVAILABLE NOW" in pages["ITGL 1000"]
    assert "1,248 units" in pages["ITGL 1000"]
    assert "OUT OF STOCK" in pages["ITWC 1302"]
    assert "0 units" in pages["ITWC 1302"]
    assert "AVAILABLE NOW" not in pages["ITWC 1302"], "the reported defect"
    assert "AVAILABILITY UNAVAILABLE" in pages["ITGL 1002"]
    assert "units" not in pages["ITGL 1002"]
    assert cat.STOCK_UNKNOWN_FIGURE in pages["ITGL 1002"]

    #: the market timestamp is on all three product pages, unchanged — and a
    #: fourth time on the approved cover's own metadata band
    assert text.count("STOCK UPDATED") == 4
    assert time.strftime("%d %B %Y", time.localtime(STOCK_AT)) in text


def test_an_unknown_quantity_prints_no_number_at_all():
    """Not a nought, and not the raw figure either — a quantity nobody
    reported is the one case where there is nothing honest to print."""
    pdf = cat.build([{"id": "1", "code": "A", "name": "Not Synchronised",
                      "available": 99, "availableKnown": False}], {},
                    market="ksa", title="T", stock_at=STOCK_AT,
                    stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "AVAILABILITY UNAVAILABLE" in text
    assert "99" not in text, "a figure the sync never confirmed"
    assert "units" not in text, "and no quantity of any kind"
    assert cat.STOCK_UNKNOWN_FIGURE in text
    #: the figure's own place carries words, never a nought. The market's
    #: synchronisation date is a different fact and still prints.
    between = text.split("AVAILABILITY UNAVAILABLE", 1)[1]
    assert between.split("STOCK UPDATED", 1)[0].strip() == cat.STOCK_UNKNOWN_FIGURE
    assert "STOCK UPDATED" in between


@pytest.mark.parametrize("available,known,mark", [
    (7, True, "check"),
    (0, True, "cross"),
    (0, False, "dash"),
])
def test_every_state_draws_its_own_mark(available, known, mark, snapshot):
    """A tick beside OUT OF STOCK is the same contradiction as the words, so
    the mark is chosen from the same verdict as the label."""
    assert set(cat._STOCK_ICON) == set(cat.STOCK_LABEL) == {"in", "out", "unknown"}
    assert len(set(cat._STOCK_ICON.values())) == 3, "three states, three marks"

    marks: list[str] = []
    real = cat._icon

    def watched(c, name, cx, cy, r):
        marks.append(name)
        real(c, name, cx, cy, r)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cat, "_icon", watched)
        cat.build([{"id": "1", "code": "A", "name": "Item",
                    "available": available, "availableKnown": known}], {},
                  market="ksa", title="T", stock_at=STOCK_AT,
                  stock_is_known=True)
    assert mark in marks, (mark, marks)
    for other in set(cat._STOCK_ICON.values()) - {mark}:
        assert other not in marks, f"{other} does not belong on this page"


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
    assert "AVAILABILITY UNAVAILABLE" in text
    #: and only the one product, not all three
    assert text.count("AVAILABILITY UNAVAILABLE") == 1
    assert text.count("AVAILABLE NOW") == 2, "the two that really are"


def test_the_stock_date_is_the_sync_not_the_moment_of_generation():
    """Generating at noon must not imply the stock was checked at noon."""
    old = time.time() - 60 * 60 * 30
    pdf = cat.build([{"id": "1", "code": "A", "name": "Item", "available": 3}],
                    {}, market="ksa", title="T", stock_at=old, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert time.strftime("%d %B %Y", time.localtime(old)) in text
    assert "PREPARED" in text, "the two dates are labelled separately"


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
    assert "AVAILABLE NOW" in text, "the quantity is never pushed off the page"


def test_a_missing_image_gets_a_placeholder_and_does_not_fail_the_run():
    pdf = cat.build([{"id": "1", "code": "A", "name": "No Photo", "available": 1}],
                    {"1": []}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    assert "Photograph unavailable" in cat.extract_text(pdf)


def test_a_corrupt_image_does_not_fail_the_run():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Bad Photo", "available": 1}],
                    {"1": [b"this is not an image"]}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    assert "Photograph unavailable" in cat.extract_text(pdf)


def test_the_optional_sections_can_each_be_switched_off(snapshot):
    text = cat.extract_text(pdf_for(["1248"], description=False, specs=False,
                                    code=False, stockDate=False))
    assert "Product Number 248" in text
    assert "DESCRIPTION" not in text and "SPECIFICATIONS" not in text
    assert "ITGL 1248" not in text
    # the cover always names the snapshot date — that is what a cover is for.
    # The option governs the band on the product page, so the phrase appears
    # once rather than twice.
    assert text.count("STOCK UPDATED") == 1
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
    assert "PREPARED" in text and "STOCK UPDATED" in text


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
    # only this build's entries: other tests in the file generate catalogues
    # too, and a window of the last 40 rows could pair one build's "requested"
    # with another's "generated"
    before = aa.audit_list(1)[0]["id"] if aa.audit_list(1) else 0
    pdf_for(["1000", "1001"], minStock="")
    mine = [a for a in aa.audit_list(60) if a["id"] > before]
    actions = [a["action"] for a in mine]
    assert "jasani.catalogue_requested" in actions
    assert "jasani.catalogue_generated" in actions
    # requested first, generated after — ids ascend with time
    entries = {a["action"]: a for a in mine
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
    assert "AVAILABILITY UNAVAILABLE" in text, "an unknown one is not"
    #: and each of the three is labelled as what it is
    assert text.count("AVAILABLE NOW") == 1, "only the counted one"
    assert text.count("OUT OF STOCK") == 1, "only the genuinely empty one"


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
    assert text.count("Photograph unavailable") == 0
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

    async def watched(market, dto, cache, *rest):
        out = await real(market, dto, cache, *rest)
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


# ---------------- the look of the document ----------------
#
# A PDF's appearance cannot be asserted from its text, so these go at the
# geometry: which pictures the renderer was handed, where each tile was
# drawn, and how large it is relative to the main one. Rendered pages were
# reviewed by eye as well — a passing test is not a design review.

class _Tiles:
    """Every (x, y, w, h) the document draws, split into the cover's hero and
    the product pages' galleries."""

    def __init__(self):
        self.all: list[tuple] = []
        self.cover: list[tuple] = []

    @property
    def pages(self) -> list[tuple]:
        return self.all[len(self.cover):]


def _tiles(monkeypatch) -> _Tiles:
    """Every gallery tile the document draws.

    `rec.cover` stays empty: the cover is the approved fixed composition and
    draws no product photograph at all, so every tile belongs to a page.
    """
    rec = _Tiles()
    real_tile = cat._photo_tile

    def watched(c, reader, x, y, w, h, pad=0.0, shadow=False):
        rec.all.append((round(x, 1), round(y, 1), round(w, 1), round(h, 1)))
        real_tile(c, reader, x, y, w, h, pad, shadow)

    monkeypatch.setattr(cat, "_photo_tile", watched)
    return rec


def _one(photos, **kw):
    item = {"id": "1", "code": "ITGL 1290", "name": "NAPIER - MagCase - Navy Blue",
            "brand": "Giftology", "available": 13, "availableKnown": True,
            "description": "A slim magnetic cardholder.", "categories": ["Mobile"]}
    item.update(kw)
    return cat.build([item], {"1": photos}, market="ksa", title="T",
                     stock_at=STOCK_AT, stock_is_known=True)


@pytest.mark.parametrize("n,tiles", [(1, 1), (2, 2), (3, 3), (4, 4), (5, 4), (9, 4)])
def test_the_gallery_draws_one_tile_per_usable_photograph_up_to_four(n, tiles,
                                                                    monkeypatch):
    """Four is the ceiling, not a target: a fifth view would cost the others
    the room that makes them readable."""
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(seed=i, w=900, h=900) for i in range(n)])
    assert len(rec.pages) == tiles, rec.pages


@pytest.mark.parametrize("n", [2, 3, 4])
def test_a_secondary_photograph_is_never_a_thumbnail(n, monkeypatch):
    """The complaint that started this: the main image was large and the rest
    were 52pt boxes. A supporting view is now a third of the composition."""
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(seed=i, w=900, h=900) for i in range(n)])
    drawn = rec.pages
    main = drawn[0][2] * drawn[0][3]
    for x, y, w, h in drawn[1:]:
        assert min(w, h) >= 70, f"a {w:.0f}x{h:.0f} tile is a thumbnail"
        assert w * h >= main * 0.12, "a supporting view must be legible"
    # and the main picture leads without swallowing the page
    total = sum(w * h for _, _, w, h in drawn)
    assert 0.5 <= main / total <= 0.72, main / total


def test_one_photograph_fills_the_gallery(monkeypatch):
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(w=900, h=900)])
    assert len(rec.pages) == 1
    assert rec.pages[0][2] > cat.PAGE_W - 2 * cat.M - 1, "a single view spans the page"


def test_two_photographs_sit_side_by_side(monkeypatch):
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(seed=i, w=900, h=900) for i in range(2)])
    (x1, y1, w1, h1), (x2, y2, w2, h2) = rec.pages
    assert x2 > x1 + w1, "the second is beside the first, not beneath it"
    assert abs(h1 - h2) < 1, "both are full height"
    assert 0.55 < w1 / (w1 + w2) < 0.70, "roughly a 64/36 split"


def test_three_photographs_stack_two_beside_the_main(monkeypatch):
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(seed=i, w=900, h=900) for i in range(3)])
    main, upper, lower = rec.pages
    assert upper[0] > main[0] + main[2] - 1 and lower[0] == upper[0]
    assert upper[1] > lower[1], "stacked, upper first"
    assert abs(upper[2] - lower[2]) < 1 and abs(upper[3] - lower[3]) < 1


def test_four_photographs_stack_three_beside_the_main(monkeypatch):
    """Not a full-width fourth strip: a portrait product in a 500x75
    letterbox is a picture nobody can read."""
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(seed=i, w=900, h=900) for i in range(4)])
    drawn = rec.pages
    main = drawn[0]
    for tile in drawn[1:]:
        assert tile[0] > main[0] + main[2] - 1, "all three are in the side column"
        assert tile[2] < main[2], "and none is wider than the main picture"


def test_a_repeated_photograph_is_shown_once(monkeypatch):
    """Suppliers list the same file twice. Spending half the gallery on a
    duplicate is worse than showing one view."""
    blob = jpeg_bytes(w=900, h=900)
    rec = _tiles(monkeypatch)
    _one([blob, blob, blob])
    assert len(rec.pages) == 1


def test_an_unusable_photograph_does_not_take_a_tile(monkeypatch):
    rec = _tiles(monkeypatch)
    _one([b"not an image", jpeg_bytes(w=900, h=900), b""])
    assert len(rec.pages) == 1


def test_a_product_with_no_photograph_says_so_once(monkeypatch):
    rec = _tiles(monkeypatch)
    text = cat.extract_text(_one([]))
    assert rec.all == [], "no tile is drawn for a product with no picture"
    assert text.count("Photograph unavailable") == 1
    assert "Images can be supplied on request" in text


def test_the_cover_never_spends_a_product_photograph_on_itself(monkeypatch):
    """The approved cover is a fixed Elite Marcom composition, so a
    catalogue's own pictures all belong to its pages."""
    rec = _tiles(monkeypatch)
    items = [{"id": str(n), "code": f"C{n}", "name": f"Item {n}", "available": 5,
              "availableKnown": True} for n in range(3)]
    photos = {str(n): [jpeg_bytes(seed=n, w=900, h=900)] for n in range(3)}
    cat.build(items, photos, market="ksa", title="T", stock_at=STOCK_AT,
              stock_is_known=True)
    assert len(rec.pages) == 3 and rec.cover == [], rec.all


@pytest.mark.parametrize("name,parts", [
    ("NAPIER - MagCase Phone Cardholder - Navy Blue",
     ("NAPIER", "MagCase Phone Cardholder", "Navy Blue")),
    ("Mug - Navy Blue", ("", "Mug", "Navy Blue")),
    ("Simple Pen", ("", "Simple Pen", "")),
    ("NAPIER - A rather longer descriptive product name here",
     ("NAPIER", "A rather longer descriptive product name here", "")),
])
def test_a_supplier_name_is_set_as_a_hierarchy(name, parts):
    assert cat.name_parts(name) == parts


def test_every_word_of_the_name_still_reaches_the_page():
    """The hierarchy is presentation. A name that lost a word would be a
    different product."""
    name = "NAPIER - MagCase Phone Cardholder - Navy Blue"
    text = cat.extract_text(_one([], name=name))
    for word in ("NAPIER", "MagCase Phone Cardholder", "Navy Blue"):
        assert word in text, word


def test_a_sparse_product_fills_the_page_rather_than_leaving_a_hole(monkeypatch):
    """The gallery takes the room the rest of the page does not need."""
    rec = _tiles(monkeypatch)
    _one([jpeg_bytes(w=900, h=900)], description="", categories=[])
    sparse = rec.pages[0][3]
    rec.all.clear()
    rec.cover.clear()
    _one([jpeg_bytes(w=900, h=900)],
         description="A full sentence about the product. " * 20,
         brand="B", color="C", material="M", size="S", capacity="500 ml",
         unitsPerCarton=24, cartonDimensions="40x30x20", cartonWeight="9.5",
         cartonVolume="0.24", hsCode="1234", barcode="999")
    loaded = rec.pages[0][3]
    assert sparse > loaded, "a page with little to say gives the room to the picture"
    #: the floor, not GALLERY_MIN: a loaded page may also be carrying a
    #: feature row, and the gallery is what yields for it
    assert cat.GALLERY_FLOOR <= loaded <= sparse <= cat.GALLERY_MAX


def test_twelve_specifications_all_print_on_the_one_page():
    """The composition exists so nothing is quietly dropped: the gallery
    yields rather than the specifications being cut."""
    text = cat.extract_text(_one(
        [jpeg_bytes(w=900, h=900)],
        description="A slim magnetic cardholder that attaches to a phone. " * 4,
        brand="Giftology", color="Navy Blue", material="Recycled PU leather",
        size="95 x 62 x 6 mm", capacity="3 cards", unitsPerCarton=300,
        cartonDimensions="48 x 36 x 30 cm", cartonWeight="17.5",
        cartonVolume="0.24", hsCode="4202.31", barcode="6291108201299",
        categories=["Mobile Accessories"], options=["Navy", "Black"]))
    for label in ("Brand", "Colour", "Material", "Size", "Capacity",
                  "Units per carton", "Carton size", "Carton weight",
                  "Carton volume", "HS code", "Barcode", "Category", "Options"):
        assert label in text, label
    assert "Page 2" in text and "Page 3" not in text, "still one page per product"


def test_the_redesign_keeps_every_guarantee():
    """A visual change must not quietly cost a contract."""
    text = cat.extract_text(_one(
        [jpeg_bytes(w=900, h=900)], available=13,
        description="Premium bottle. RRP: SAR 45. Holds 500 ml."))
    assert "13 units" in text, "availability"
    assert "STOCK UPDATED" in text, "the stock timestamp"
    assert "Giftology" in text, "specifications"
    assert "Page 2" in text and "Page 3" not in text, "one product, one page"
    assert "rrp" not in text.lower() and "SAR" not in text, "no price"
    assert "Holds 500 ml" in text, "and the honest part of the sentence stayed"


# ---------------- the production 'rrp' that was never text ----------------
#
# A catalogue of real photographs was refused for carrying 'rrp' while every
# customer-facing field was clean. The indicator was not in the document's
# text at all: `extract_text` walked every stream in the file, and a 1200 x
# 1200 photograph decompresses to 4.3 MB of pixels in which three letters
# turn up by chance, inside brackets. The guard was reading pixels.

MAGLITE = {
    "id": "24310", "code": "ITGL 1455",
    "name": "Maglite 5K - 5000 mAh Magnetic Wireless Power Bank - Black",
    "brand": "Giftology", "color": "Black", "material": "ABS + silicone",
    "size": "104 x 66 x 15 mm", "capacity": "5000 mAh", "unitsPerCarton": 100,
    "cartonWeight": "14.2", "cartonVolume": "0.08",
    "cartonDimensions": "44 x 32 x 26 cm", "hsCode": "8507.60",
    "barcode": "6291108214558",
    "categories": ["Power Banks", "Technology & Gadgets"],
    "options": ["Black", "White", "RRP 120 SAR"],
    "description": (
        "A 5000 mAh magnetic wireless power bank that snaps onto the back of a "
        "MagSafe-compatible phone and charges it without a cable. RRP: SAR 120. "
        "USB-C in and out, an LED charge indicator and a soft-touch finish."),
    "available": 42, "availableKnown": True,
}


def noisy_photo(seed: int = 0, w: int = 900, h: int = 900) -> bytes:
    """A photograph with real grain. Flat colour compresses to almost
    nothing; a catalogue's problem is megabytes of noise."""
    import random

    from PIL import Image

    rnd = random.Random(seed * 7919 + 13)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            v = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for dy in range(3):
                for dx in range(3):
                    px[x + dx, y + dy] = v
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return cat.prepare_image(buf.getvalue())


def test_a_photograph_is_not_text():
    """The exact production failure. Pixels are not strings, and a guard that
    reads them refuses honest documents at random."""
    blobs = [noisy_photo(i) for i in range(3)]
    dto = cat.to_dto(dict(MAGLITE))
    assert not any(cat.has_price_text(str(v)) for v in dto.values()
                   if isinstance(v, str)), "the record itself is clean"
    pdf = cat.build([dto], {dto["id"]: blobs}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)   # must not raise
    text = cat.extract_text(pdf)
    assert "MAGLITE 5K" in text and "42 units" in text
    # the bytes really are in the file; they are simply not read as text
    raw = b"".join(cat._decode_stream(m.group(1)) for m in
                   re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S))
    assert len(raw) > 1_000_000, "a real photograph is embedded"
    assert len(text) < 4000, "and the extracted text is a page of words"


def test_extract_text_reads_pages_not_pictures():
    """Belt and braces on the same point, with a token planted in an image."""
    pdf = cat.build([{"id": "1", "code": "A", "name": "Plain", "available": 4,
                      "availableKnown": True}],
                    {"1": [noisy_photo(99)]}, market="ksa", title="T",
                    stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    for word in cat.PRICE_WORDS:
        assert word not in text.lower(), word
    assert "Plain" in text, "the drawn text is still read"


def _all_image_streams(pdf: bytes) -> list[tuple[int, bool]]:
    """(bytes, is_jpeg) for every image in the file, the cover's included."""
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        head = pdf[max(0, m.start() - 2500):m.start()]
        cut = head.rfind(b" obj")
        head = head[cut:] if cut >= 0 else head
        if re.search(rb"/Subtype\s*/Image", head):
            out.append((len(m.group(1)), b"DCTDecode" in head))
    return out


# ---------------- what the document weighs ----------------
#
# The photographs are the document. Everything in this section is about the
# one fact that decided a catalogue's size: whether a picture goes into the
# file as the JPEG it already is, or is decoded and embedded as compressed
# raw pixels.


#: Every image a catalogue carries that is not a product's photograph: the
#: approved cover's three pictures — the wordmark, the watermark and the
#: branded hero — plus the header wordmark each product page draws. That is
#: **seven** image XObjects rather than four, because the wordmark, the
#: watermark and the page header each keep their transparency as a separate
#: greyscale soft mask; only the baked hero goes in alone. They are the same
#: bytes in every catalogue, so a test about a product's photographs
#: subtracts them.
CHROME_IMAGE_BYTES = sorted(
    n for n, _ in _all_image_streams(cat.build(
        [{"id": "x", "code": "X", "name": "X", "available": 1,
          "availableKnown": True}], {}, market="ksa", title="T",
        stock_at=STOCK_AT, stock_is_known=True)))


def image_streams(pdf: bytes) -> list[tuple[int, bool]]:
    """(bytes, is_jpeg) for every image a *product* put in the file."""
    out = list(_all_image_streams(pdf))
    for size in CHROME_IMAGE_BYTES:
        for n, row in enumerate(out):
            if row[0] == size:
                out.pop(n)
                break
    return out


def test_a_photograph_is_embedded_as_the_jpeg_it_already_is():
    """The whole of the size problem, in one assertion.

    `prepare_image` produces a small JPEG and the document used to decode it
    and embed zlib-compressed raw RGB — measured, a 140 KB product shot became
    about 1.55 MB in the file. The stream in the document is now that JPEG,
    so the photographs weigh what they weighed.
    """
    blobs = [noisy_photo(i) for i in range(3)]
    pdf = cat.build([{"id": "1", "code": "A", "name": "One", "available": 5,
                      "availableKnown": True}], {"1": blobs}, market="ksa",
                    title="T", stock_at=STOCK_AT, stock_is_known=True)
    photos = [(n, jpeg) for n, jpeg in image_streams(pdf) if jpeg]
    assert len(photos) == 3, "every photograph is a DCTDecode stream"
    carried = sum(n for n, _ in photos)
    source = sum(len(b) for b in blobs)
    assert carried == source, "the prepared bytes are the embedded bytes"


def test_no_stream_is_wrapped_in_ascii_base_eighty_five():
    """Base-85 adds a flat 25% to every stream so the bytes are printable,
    which is a cost paid for a transport nobody uses."""
    pdf = cat.build([{"id": "1", "code": "A", "name": "One", "available": 5,
                      "availableKnown": True}], {"1": [noisy_photo(4)]},
                    market="ksa", title="T", stock_at=STOCK_AT,
                    stock_is_known=True)
    assert b"ASCII85Decode" not in pdf
    assert b"/DCTDecode" in pdf


def test_drawn_text_is_still_read_back_out_of_binary_streams():
    """The guard's input. With binary streams a run of photographic bytes can
    spell "stream", so a stream is now identified by the dictionary in front
    of it — and the document's real text still reads back."""
    dto = cat.to_dto(dict(MAGLITE))
    pdf = cat.build([dto], {dto["id"]: [noisy_photo(7)]},
                    market="ksa", title="Elite Marcom\nProduct Catalogue",
                    stock_at=STOCK_AT, stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "MAGLITE 5K" in text and "42 units" in text
    assert MAGLITE["code"] in text
    assert "5000 mAh magnetic wireless power bank" in text
    cat.assert_price_free(pdf)


def test_the_same_photograph_is_stored_once_however_often_it_is_drawn():
    """Two products listing one picture, and the cover drawing it again."""
    one = noisy_photo(11)
    pdf = cat.build(
        [{"id": "1", "code": "A", "name": "One", "available": 5, "availableKnown": True},
         {"id": "2", "code": "B", "name": "Two", "available": 6, "availableKnown": True}],
        {"1": [one], "2": [one]}, market="ksa", title="T", stock_at=STOCK_AT,
        stock_is_known=True)
    photos = [n for n, jpeg in image_streams(pdf) if jpeg]
    assert len(photos) == 1, "one picture, one object"


def test_standard_quality_is_lighter_than_high_and_is_the_default():
    raw = jpeg_bytes(w=2000, h=2000, seed=3)
    standard = cat.prepare_image(raw, slot="main", quality="standard")
    high = cat.prepare_image(raw, slot="main", quality="high")
    assert len(standard) < len(high)
    assert cat.quality_mode(None) == "standard"
    assert cat.quality_mode("high") == "high"
    for junk in ("", "HIGHEST", "medium", "0", None, 7):
        assert cat.quality_mode(junk) in ("standard", "high")
    assert cat.quality_mode("nonsense") == "standard", "unreadable means lighter"


def test_a_supporting_picture_is_prepared_smaller_than_the_leading_one():
    """The page draws a side tile at most 207pt wide and a leading one up to
    503pt, so preparing them at one size is weight nobody sees."""
    from PIL import Image

    raw = jpeg_bytes(w=2000, h=2000, seed=5)
    main = cat.prepare_image(raw, slot="main", quality="standard")
    side = cat.prepare_image(raw, slot="side", quality="standard")
    assert Image.open(io.BytesIO(main)).width == cat.PHOTO_DIMS["standard"]["main"]
    assert Image.open(io.BytesIO(side)).width == cat.PHOTO_DIMS["standard"]["side"]
    assert len(side) < len(main)


def test_a_prepared_photograph_carries_no_metadata_and_is_baseline():
    """A supplier's camera metadata is not ours to put in a customer document,
    and a progressive JPEG is a coding /DCTDecode does not promise to read."""
    from PIL import Image

    source = Image.new("RGB", (900, 900), (120, 90, 60))
    buf = io.BytesIO()
    source.save(buf, "JPEG", quality=95, progressive=True,
                exif=b"Exif\x00\x00" + b"\x00" * 400)
    out = cat.prepare_image(buf.getvalue(), slot="main", quality="standard")
    done = Image.open(io.BytesIO(out))
    assert not done.info.get("exif") and not done.info.get("icc_profile")
    assert not done.info.get("progressive") and not done.info.get("progression")


def test_the_logo_is_not_embedded_at_sixteen_hundred_pixels():
    """The shipped wordmark is 1660 x 560 and a page draws it 26pt tall:
    1,500 dots to the inch, and with an alpha channel it costs 49 KB of raw
    RGB plus a soft mask in every single document."""
    from server import exports

    exports._LOGO_CACHE.clear()
    reader, width, height = exports.logo_reader(26.0)
    assert reader is not None
    assert height < 560 and width < 1660, "not the shipped artwork"
    assert height <= 32 * exports.LOGO_PX_PER_PT, "no more than the 16pt bucket"
    assert exports.logo_reader(26.0)[0] is reader, "cached, not rebuilt per page"
    # the 19pt page header and the 26pt cover are one object, not two
    assert exports.logo_reader(19.0)[0] is reader


def test_the_document_weighs_what_its_photographs_weigh():
    """An upper bound on a whole catalogue rather than on one picture. The
    pool of test photographs repeats, so reportlab's content digest collapses
    some of them — which is why this is a ceiling and not an equality."""
    items, photos = [], {}
    for n in range(8):
        items.append({"id": str(n), "code": f"ITGL {n}", "name": f"Item {n}",
                      "description": "A useful item.", "material": "Steel",
                      "available": 10 + n, "availableKnown": True})
        photos[str(n)] = [cat.prepare_image(jpeg_bytes(seed=n * 3 + k))
                          for k in range(3)]
    pdf = cat.build(items, photos, market="ksa", title="T", stock_at=STOCK_AT,
                    stock_is_known=True)
    supplied = sum(len(b) for blobs in photos.values() for b in blobs)
    embedded = sum(n for n, _ in image_streams(pdf))
    assert embedded <= supplied + 60_000, "images plus the small logo"
    #: the chrome is a fixed cost — the approved cover's wordmark, watermark
    #: and branded hero, plus each page's header wordmark, the same bytes
    #: whatever the catalogue — so it is named rather than hidden inside a
    #: looser bound
    chrome_cost = sum(CHROME_IMAGE_BYTES)
    assert len(pdf) < supplied * 1.2 + chrome_cost + 200_000
    photographs = [jpeg for size, jpeg in image_streams(pdf) if size > 20_000]
    assert photographs and all(photographs), "the photographs are JPEG streams"


# ---------------- the sanitizer and the guard cannot drift ----------------

@pytest.mark.parametrize("word", cat.PRICE_WORDS)
def test_whatever_the_guard_rejects_the_sanitizer_removes(word):
    """The contract. If the finished-document guard would refuse a string,
    the sanitizer must have taken it out first — otherwise a product exists
    that can never be put in a catalogue."""
    body = f"A useful opening sentence. {word.upper()} 99. A closing sentence."
    assert cat.has_price_text(body), word
    kept = cat.sanitize_catalogue_text(body, "description")
    assert word not in kept.lower(), (word, kept)
    cat.assert_price_free(cat.build(
        [{"id": "1", "code": "A", "name": "One", "description": kept,
          "available": 5, "availableKnown": True}], {}, market="ksa",
        title="T", stock_at=STOCK_AT, stock_is_known=True))


@pytest.mark.parametrize("variant", [
    "RRP 99", "RRP: 99", "RRP - 99", "RRP–99", "RRP—99",
    "RRP SAR 99", "RRP: SAR 99", "SAR 99 RRP", "99 SAR RRP",
    "R.R.P 99", "R.R.P. 99", "R R P 99",
    "Recommended Retail Price 99", "Recommended Retail Price: SAR 99",
    "Recommended Retail Price (RRP): SAR 99",
    "Retail Selling Price on request", "Suggested Retail Price 40",
])
def test_every_rrp_variant_is_removed(variant):
    body = f"A magnetic power bank. {variant}. USB-C in and out."
    kept = cat.sanitize_catalogue_text(body, "description")
    assert "rrp" not in kept.lower() and "retail price" not in kept.lower()
    assert not re.search(r"\b(?:sar|aed|usd)\b", kept, re.I)
    assert not re.search(r"\b99\b", kept), "no orphaned amount"
    assert "A magnetic power bank." in kept, "the useful text stayed"


# ---------------- nothing reaches a renderer except the DTO ----------------

def _dirty(**kw) -> dict:
    """Every customer-facing field carrying a price statement."""
    item = {"id": "9", "code": "ITGL 9", "name": "Grubby - RRP SAR 10 - Black",
            "brand": "Retail Price Co", "color": "Black", "material": "RRP 5 SAR",
            "size": "10 cm", "capacity": "1 L", "cartonDimensions": "RRP: 9",
            "hsCode": "1234", "barcode": "999",
            "categories": ["Drinkware", "RRP 20 SAR"],
            "options": ["Black", "RRP 20 SAR"],
            "description": "A useful bottle. RRP: SAR 45. Holds 500 ml.",
            "available": 7, "availableKnown": True}
    item.update(kw)
    return item


def test_no_renderer_sees_unsanitized_text(snapshot, tmp_path, monkeypatch):
    """Cover, contents, identity, specifications — through the admin path, on
    a record whose every field is dirty."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    rows = [dict(_dirty(), image="", images=[],
                 stock={"available": 7, "known": True, "incoming": 0}),
            dict(_dirty(), id="10", code="ITGL 10", name="Clean Item",
                 description="An honest description.", image="", images=[],
                 categories=["Drinkware"], options=["Blue"],
                 brand="Jasani", material="Steel", cartonDimensions="40x30x20",
                 stock={"available": 9, "known": True, "incoming": 0})]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": rows}),
        encoding="utf-8")
    text = cat.extract_text(pdf_for(["9", "10"], contents=True))
    assert "rrp" not in text.lower()
    assert not re.search(r"\b(?:sar|aed|usd)\b", text, re.I)
    assert "retail price" not in text.lower()
    assert "Clean Item" in text and "An honest description." in text
    assert "Holds 500 ml" in text, "the honest half of the dirty one survived"


def test_the_contents_page_is_built_from_the_dto(snapshot, tmp_path, monkeypatch):
    """It used to clean its own strings, which is a second implementation of
    the boundary and therefore one that can drift."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": [
            {"id": "1", "code": "ITGL 1", "name": "Bottle - RRP SAR 45 - Blue",
             "brand": "", "color": "", "categories": [], "image": "", "images": [],
             "description": "A bottle.",
             "stock": {"available": 3, "known": True, "incoming": 0}}]}),
        encoding="utf-8")
    text = cat.extract_text(pdf_for(["1"], contents=True))
    assert "Contents" in text and "ITGL 1" in text
    assert "rrp" not in text.lower() and "SAR" not in text


def test_the_document_title_goes_through_the_boundary_too():
    pdf = cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 2,
                      "availableKnown": True}], {}, market="ksa",
                    title="Ramadan RRP SAR 99 Selection", stock_at=STOCK_AT,
                    stock_is_known=True)
    text = cat.extract_text(pdf)
    assert "rrp" not in text.lower() and "SAR" not in text


def test_one_dirty_record_does_not_cost_the_catalogue(snapshot, tmp_path,
                                                      monkeypatch):
    """Five selected, one carrying RRP: five pages, and the dirty one keeps
    everything about it that was not a price."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    rows = []
    for n in range(4):
        rows.append({"id": f"c{n}", "code": f"ITGL {200 + n}",
                     "name": f"Clean Item {n}", "brand": "Jasani", "color": "Blue",
                     "categories": ["Drinkware"], "image": "", "images": [],
                     "description": "An ordinary corporate gift.",
                     "stock": {"available": 20 + n, "known": True, "incoming": 0}})
    rows.append(dict(_dirty(), id="dirty", code="ITGL 1455",
                     name="Maglite 5K - 5000 mAh Power Bank - Black",
                     image="", images=[],
                     stock={"available": 42, "known": True, "incoming": 0}))
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": rows}),
        encoding="utf-8")
    text = cat.extract_text(pdf_for([r["id"] for r in rows]))
    for n in range(4):
        assert f"Clean Item {n}" in text, n
    assert "MAGLITE 5K" in text, "the dirty record is still in the catalogue"
    assert "42 units" in text, "with its quantity"
    assert "Holds 500 ml" in text, "and the useful half of its description"
    assert "Page 6" in text and "Page 7" not in text, "cover plus five pages"
    assert "rrp" not in text.lower()


# ---------------- the description is not silently cut ----------------

NAPIER_BODY = (
    "A slim magnetic cardholder that attaches to the back of any "
    "MagSafe-compatible phone, holding up to three cards securely while "
    "staying thin enough for a pocket. The outer shell is recycled PU leather "
    "with a soft-touch finish, and the magnet array is strong enough to hold "
    "through a protective case. Branding is applied by debossing or screen "
    "print on the rear panel. Includes extra magnetic ring for compatibility "
    "with non-MagSafe smartphones.")


def test_the_whole_napier_description_fits():
    """The production complaint: the last sentence was being cut mid-clause
    even though the gallery could still have yielded the room."""
    text = cat.extract_text(cat.build([{
        "id": "1", "code": "ITGL 1290",
        "name": "NAPIER - MagCase Phone Cardholder - Navy Blue",
        "brand": "Giftology", "color": "Navy Blue",
        "material": "Recycled PU leather", "size": "95 x 62 x 6 mm",
        "capacity": "3 cards", "unitsPerCarton": 300, "cartonWeight": "17.5",
        "cartonVolume": "0.24", "cartonDimensions": "48 x 36 x 30 cm",
        "hsCode": "4202.31", "barcode": "6291108201299",
        "categories": ["Mobile Accessories"], "options": ["Navy Blue", "Black"],
        "description": NAPIER_BODY, "available": 13, "availableKnown": True}],
        {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True))
    assert "non-MagSafe smartphones." in text, "the last sentence is whole"
    assert "…" not in text, "and nothing was cut mid-sentence"
    assert "Barcode" in text and "6291108201299" in text, "specs survived too"
    assert "Page 2" in text and "Page 3" not in text


@pytest.mark.parametrize("room,ends", [
    (3, "thin enough for a pocket."), (5, "through a protective case."),
    (6, "on the rear panel."), (7, "with non-MagSafe smartphones."),
    (40, "with non-MagSafe smartphones."),
])
def test_a_description_is_trimmed_at_a_sentence(room, ends):
    out = cat.trim_to_sentence(NAPIER_BODY, 270.0, room)
    assert out.endswith(ends), out[-60:]
    assert "…" not in out


def test_an_unbroken_wall_of_text_still_gets_an_ellipsis():
    """One sentence longer than the page has no boundary to fall back to."""
    out = cat.trim_to_sentence("word " * 400, 270.0, 5)
    assert out.endswith("…") and len(out) < 400


def test_a_long_description_takes_room_from_the_gallery(monkeypatch):
    """Moderate yield, not a retreat to thumbnails."""
    rec = _Tiles()
    real = cat._photo_tile

    def watched(c, reader, x, y, w, h, pad=0.0, shadow=False):
        rec.all.append((round(x, 1), round(y, 1), round(w, 1), round(h, 1)))
        real(c, reader, x, y, w, h, pad, shadow)

    monkeypatch.setattr(cat, "_photo_tile", watched)
    item = {"id": "1", "code": "A", "name": "Wordy", "available": 5,
            "availableKnown": True, "brand": "B", "color": "C",
            "material": "M", "size": "S", "capacity": "500 ml",
            "unitsPerCarton": 24, "cartonDimensions": "40x30x20",
            "cartonWeight": "9.5", "cartonVolume": "0.24", "hsCode": "1",
            "barcode": "2", "description": NAPIER_BODY * 2}
    cat.build([item], {"1": [jpeg_bytes(w=600, h=600)]}, market="ksa", title="T",
              stock_at=STOCK_AT, stock_is_known=True)
    wordy = rec.all[0][3]                      # the cover draws no tile
    rec.all.clear()
    cat.build([dict(item, description="Short.")],
              {"1": [jpeg_bytes(w=600, h=600)]}, market="ksa", title="T",
              stock_at=STOCK_AT, stock_is_known=True)
    sparse = rec.all[0][3]
    assert wordy < sparse, "a wordy product takes room from the gallery"
    assert wordy >= cat.GALLERY_FLOOR, "but the pictures stay large"
    assert sparse <= cat.GALLERY_MAX


def test_the_cover_sets_the_full_hierarchy():
    """The approved cover's own wording. The house name is the official
    wordmark — artwork, not a typeset line — so it is not among these."""
    text = cat.extract_text(cat.build(
        [{"id": "1", "code": "A", "name": "Mug", "available": 2,
          "availableKnown": True}], {}, market="ksa",
        title="Elite Marcom\nProduct Catalogue", stock_at=STOCK_AT,
        stock_is_known=True))
    for line in ("CORPORATE GIFTS", "PRODUCT", "CATALOGUE", "Saudi Arabia",
                 "KSA CATALOGUE", "PREPARED", "STOCK UPDATED"):
        assert line in text, line


# ---------------- the feature row says only what the product says ----------

def _feat(**kw) -> list[tuple[str, str]]:
    item = {"id": "1", "code": "A", "name": "Item", "available": 5,
            "availableKnown": True}
    item.update(kw)
    return cat.product_features(cat.to_dto(item))


def test_the_maglite_features_are_the_ones_its_own_words_support():
    assert _feat(
        name="Maglite 5K - 5000 mAh Magnetic Wireless Power Bank - Black",
        description=("15W wireless charging and PD 22.5W fast charging over "
                     "USB-C for any MagSafe-compatible phone."),
        capacity="5000 mAh") == [
        ("magnet", "MagSafe compatible"), ("wireless", "15W wireless"),
        ("bolt", "PD 22.5W"), ("battery", "5,000 mAh")]


# ---------------- a figure is a figure, however it is punctuated ----------
#
# Production review found "0 mAh" on ITWC 1302, Maglite 5K - Navy Blue. The
# description read "The 5,000 mAh capacity provides reliable backup power",
# and `\b(\d{3,6})\s*mah\b` could not match across the comma: the scan failed
# at the "5" and matched the "000" three characters later, so a 5,000 mAh
# power bank advertised zero capacity on a customer document. Every numeric
# rule is now built from one figure pattern and one normalization.


@pytest.mark.parametrize("written", [
    "5,000", "5000", "5 000", "5\u00a0000", "5\u202f000",
])
def test_a_grouped_figure_reads_as_the_number_it_is(written):
    """The reported defect, in every separator a supplier might use. NBSP is
    included because `clean_text` turns it into a plain space and the narrow
    one survives untouched — both must land on the same badge."""
    feats = _feat(name="Power Bank",
                  description=f"The {written} mAh capacity provides reliable "
                              "backup power on the move.")
    assert feats == [("battery", "5,000 mAh")], (written, feats)


@pytest.mark.parametrize("text,wanted", [
    ("A 5,000 mAh cell.", "5,000 mAh"),
    ("A 5000 mAh cell.", "5,000 mAh"),
    ("A 10,000 mAh cell.", "10,000 mAh"),
    ("A 10000 mAh cell.", "10,000 mAh"),
    ("A 2,500mAh cell.", "2,500 mAh"),
    ("Holds 1,000 ml.", "1,000 ml"),
    ("Holds 1000 ml.", "1,000 ml"),
    ("Holds 750 ml.", "750 ml"),
    ("A 22.5W charging base.", "22.5W charging"),
    ("A 15W charging base.", "15W charging"),
    ("A 15 W charging base.", "15W charging"),
    ("A 1,500 W fast charging base.", "1,500W charging"),
    ("PD 22.5W over USB-C.", "PD 22.5W"),
    ("PD22.5W over USB-C.", "PD 22.5W"),
    ("PD 1,500W over USB-C.", "PD 1,500W"),
    ("Keeps drinks hot for 12 hours.", "12 hours"),
    ("Burns for 1,200 hours.", "1,200 hours"),
    ("Wireless 15W charging pad.", "15W wireless"),
    ("Wireless 1,500W charging pad.", "1,500W wireless"),
])
def test_every_numeric_badge_prints_the_figure_the_text_carries(text, wanted):
    labels = [t for _, t in _feat(name="Item", description=text)]
    assert wanted in labels, (text, labels)


@pytest.mark.parametrize("text", [
    "The 5,000 mAh capacity provides reliable backup power.",
    "A 1,000 ml flask.",
    "A 1,500 W fast charging base.",
    "Burns for 1,200 hours.",
    "A 10,000 mAh cell.",
])
def test_no_badge_ever_prints_a_smaller_number_than_the_text(text):
    """The failure mode, stated as a rule: the tail of a grouped figure must
    never become a figure of its own. "1,500 W" produced "500W charging"
    before this, which is a different and lower claim about a real product."""
    import re as _re

    biggest = max(int(g.replace(",", "").replace(" ", "").split(".")[0])
                  for g in _re.findall(r"\d[\d, ]*(?:\.\d+)?", text))
    for _, label in _feat(name="Item", description=text):
        for found in _re.findall(r"\d[\d,]*", label):
            assert int(found.replace(",", "")) == biggest, (label, text)


@pytest.mark.parametrize("text", [
    "Model ITGL5000 mAh listed.",      # a part number is not a capacity
    "A 5,00 mAh bank.",                # malformed: better nothing than "0"
    "A 5 00 ml flask.",
])
def test_a_figure_is_not_read_out_of_the_middle_of_something_else(text):
    assert [t for _, t in _feat(name="Item", description=text)
            if "mAh" in t or " ml" in t] == [], text


def test_ordinary_prose_around_a_figure_still_matches():
    """The guard that stops a partial match must not cost a real one: a
    decimal earlier in the sentence, brackets, and a comma straight after."""
    for text, wanted in (
            ("USB 3.0 and a 5000 mAh cell.", "5,000 mAh"),
            ("Capacity (5,000 mAh), in black.", "5,000 mAh"),
            ("Rated 5,000 mAh; charges twice.", "5,000 mAh"),
            ("Version 2 holds 1,000 ml.", "1,000 ml")):
        labels = [t for _, t in _feat(name="Item", description=text)]
        assert wanted in labels, (text, labels)


def test_the_real_maglite_description_is_the_regression():
    """The production record, as reviewed. Both ways of writing the capacity
    give the same badge, and neither gives the one that was reported."""
    for capacity in ("The 5,000 mAh capacity provides reliable backup power "
                     "for a phone or a pair of earbuds.",
                     "The 5000 mAh capacity provides reliable backup power "
                     "for a phone or a pair of earbuds."):
        feats = _feat(name="Maglite 5K - 5000 mAh Magnetic Wireless Power Bank",
                      description=capacity)
        labels = [t for _, t in feats]
        assert "5,000 mAh" in labels, (capacity, labels)
        assert "0 mAh" not in labels, "the reported defect"

    #: and on the finished page, which is where a customer reads it
    text = cat.extract_text(cat.build([{
        "id": "1", "code": "ITWC 1302", "name": "Maglite 5K - Navy Blue",
        "description": ("The 5,000 mAh capacity provides reliable backup "
                        "power on the move."),
        "available": 0, "availableKnown": True}], {}, market="ksa", title="T",
        stock_at=STOCK_AT, stock_is_known=True))
    assert "5,000 mAh" in text
    #: "5,000 mAh" of course contains "0 mAh", so the assertion has to be
    #: that no *standalone* figure of nought reached the page
    assert not re.search(r"(?<![\d,])0 mAh", text), text


# ---------------- a count is not the start of a measurement ----------------
#
# Supporting an ASCII space as a thousands separator is what "5 000 mAh"
# needs and what "Set of 4 750 ml bottles" cannot survive: the second reads
# as 4,750 ml, which is a specification no reader would question and the
# product does not have. A badge is optional; a plausible wrong one is not.


@pytest.mark.parametrize("text,wanted", [
    ("5 000 mAh power bank.", ("battery", "5,000 mAh")),
    ("Capacity 5 000 mAh.", ("battery", "5,000 mAh")),
    ("A 10 000 mAh cell.", ("battery", "10,000 mAh")),
    ("1 500 W charging station.", ("bolt", "1,500W charging")),
    ("A 1 000 ml bottle.", ("droplet", "1,000 ml")),
    ("Lasts 1 200 hours.", ("clock", "1,200 hours")),
    #: the three unambiguous spellings keep working beside the ambiguous one
    ("A 5,000 mAh cell.", ("battery", "5,000 mAh")),
    ("A 5\u00a0000 mAh cell.", ("battery", "5,000 mAh")),
    ("A 5\u202f000 mAh cell.", ("battery", "5,000 mAh")),
    ("A 5000 mAh cell.", ("battery", "5,000 mAh")),
])
def test_a_space_grouped_figure_still_reads_as_one_number(text, wanted):
    assert wanted in _feat(name="Item", description=text), text


#: Every shape this guard exists for, and what the text really says.
COUNTED = [
    ("Set of 4 750 ml bottles.", "4,750 ml"),
    ("A set of 4 750 ml bottles.", "4,750 ml"),
    ("Sets of 4 750 ml bottles.", "4,750 ml"),
    ("Pack of 2 500 ml bottles.", "2,500 ml"),
    ("Box of 6 250 ml cups.", "6,250 ml"),
    ("Case of 12 330 ml cans.", "12,330 ml"),
    ("Carton of 24 500 ml bottles.", "24,500 ml"),
    ("Pair of 2 500 ml flasks.", "2,500 ml"),
    ("Bundle of 2 500 ml flasks.", "2,500 ml"),
    ("Quantity 4 750 ml bottles.", "4,750 ml"),
    ("Qty 4 750 ml bottles.", "4,750 ml"),
    ("Qty: 4 750 ml bottles.", "4,750 ml"),
    ("Units: 4 750 ml bottles.", "4,750 ml"),
    ("Pieces 6 250 ml cups.", "6,250 ml"),
]


@pytest.mark.parametrize("text,misreading", COUNTED)
def test_a_count_is_never_read_as_part_of_the_measurement(text, misreading):
    """The wrong figure must not appear — and since the real one cannot be
    recovered from a number we have just said we cannot read, no badge at
    all is the right answer. Asserted as both: never the misreading, and
    nothing invented in its place."""
    feats = _feat(name="Item", description=text)
    labels = [t for _, t in feats]
    assert misreading not in labels, text
    volume = [t for t in labels if t.endswith(" ml") or t.endswith(" mAh")]
    assert volume == [], (text, volume)


@pytest.mark.parametrize("text,wanted", [
    #: a word between the two figures already separates them, so these never
    #: needed the guard and must not be caught by it
    ("4 pieces 750 ml.", "750 ml"),
    ("4 pcs 750 ml.", "750 ml"),
    ("4 x 750 ml bottles.", "750 ml"),
    ("Bundle of 3 1000 mAh units.", "1,000 mAh"),
    #: a count word that is not immediately in front of the figure says
    #: nothing about it
    ("This set of bottles holds 1 500 ml.", "1,500 ml"),
    ("Pieces of the set hold 1 500 ml.", "1,500 ml"),
    ("Sold in units of 1 500 ml.", "1,500 ml"),
    #: and a rejected reading does not cost a later, honest one
    ("Set of 4 750 ml bottles, each holding 750 ml.", "750 ml"),
    ("Pack of 2 500 ml bottles. The 5,000 mAh bank is included.", "5,000 mAh"),
])
def test_the_count_guard_does_not_suppress_a_real_measurement(text, wanted):
    assert wanted in [t for _, t in _feat(name="Item", description=text)], text


def test_only_an_ascii_space_is_treated_as_ambiguous():
    """A comma is this feed's own grouping convention and a narrow no-break
    space is typography: both say "these digits are one number", so a count
    word in front of one changes nothing.

    A **plain** no-break space is the exception, and not by choice:
    `clean_text` folds U+00A0 to an ordinary space long before the feature
    parser sees the text, so by then it is indistinguishable from language
    and is guarded like one. It still groups — "5\u00a0000 mAh" is 5,000 mAh —
    it simply also gets the benefit of the doubt withdrawn.
    """
    for written in ("4,750", "4\u202f750"):
        labels = [t for _, t in _feat(
            name="Item", description=f"Set of {written} ml bottles.")]
        assert "4,750 ml" in labels, repr(written)

    folded = cat.to_dto({"id": "1", "code": "A", "name": "Item", "available": 5,
                         "availableKnown": True,
                         "description": "Set of 4\u00a0750 ml bottles."})
    assert folded["description"] == "Set of 4 750 ml bottles.", "clean_text folds it"
    assert cat.product_features(folded) == [], "so the guard sees language"
    assert ("battery", "5,000 mAh") in _feat(
        name="Item", description="A 5\u00a0000 mAh cell."), "and it still groups"

    #: the guard's own reading of what is ambiguous
    assert cat._SPACE_GROUPED.search("4 750")
    for unambiguous in ("4,750", "4\u202f750", "4750"):
        assert not cat._SPACE_GROUPED.search(unambiguous), repr(unambiguous)


def test_the_count_words_are_short_and_explicit():
    """A vague word here would suppress a real specification, which is the
    same mistake in the other direction."""
    for word in ("bottle", "capacity", "holds", "with", "and", "of", "each",
                 "size", "volume", "large", "the"):
        labels = [t for _, t in _feat(
            name="Item", description=f"A {word} 1 500 ml flask.")]
        assert "1,500 ml" in labels, word


def test_the_figure_normalizer_is_one_function_for_every_rule():
    """Separately, because every badge's figure goes through it."""
    import re as _re

    def fig(written):
        m = _re.search(cat._FIGURE_IN, f"a {written} x")
        return cat._fig(m) if m else None

    assert fig("5000") == "5,000"
    assert fig("5,000") == "5,000"
    assert fig("5 000") == "5,000"
    assert fig("1,000,000") == "1,000,000"
    assert fig("750") == "750"
    assert fig("22.5") == "22.5"
    assert fig("22.50") == "22.5", "a trailing nought is noise"
    assert fig("22.0") == "22"
    assert fig("1,000.5") == "1,000.5"


def test_a_product_that_says_nothing_specific_gets_no_badges():
    """The row is omitted rather than filled with guesses."""
    assert _feat(name="Product Number 004",
                 description="A well-made corporate gift suited to events.") == []
    assert _feat(name="Tote Bag", description="") == []


def test_a_badge_is_never_inferred_from_a_category_or_a_brand():
    """Being a power bank is not a claim about wireless charging."""
    feats = _feat(name="Pocket Power Bank", brand="MagSafe Co",
                  categories=["Power Banks", "Wireless Chargers"],
                  description="A compact power bank for travel.")
    assert feats == [], feats


def test_a_negated_sentence_is_not_a_feature():
    """"Dishwasher safe parts are not applicable" says the opposite."""
    labels = [t for _, t in _feat(
        name="Bottle", description="Dishwasher safe parts are not applicable. "
                                   "Holds 500 ml.")]
    assert "Dishwasher safe" not in labels
    assert "500 ml" in labels


def test_one_fact_is_not_shown_twice():
    """"PD 22.5W" and "22.5W charging" are the same thing; the second slot
    goes to something the row is not yet saying."""
    labels = [t for _, t in _feat(
        name="Charger", description="PD 22.5W fast charging. 22.5W charging "
                                    "over USB-C. 5000 mAh cell.")]
    assert labels.count("PD 22.5W") == 1
    assert "22.5W charging" not in labels
    assert "5,000 mAh" in labels


def test_at_most_four_badges():
    many = _feat(name="Everything", capacity="500 ml",
                 material="Stainless steel",
                 description=("Double-walled and dishwasher safe, BPA free, "
                              "keeps drinks hot for 12 hours, laser engraved, "
                              "supplied in a gift box, USB-C, bluetooth, "
                              "waterproof, solar, recycled."))
    assert len(many) <= cat.MAX_FEATURES == 4


def test_the_feature_row_is_drawn_and_labelled():
    text = cat.extract_text(cat.build([{
        "id": "1", "code": "ITGL 1455",
        "name": "Maglite 5K - 5000 mAh Magnetic Wireless Power Bank - Black",
        "description": "15W wireless charging over USB-C for MagSafe phones.",
        "capacity": "5000 mAh", "available": 42, "availableKnown": True}],
        {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True))
    for label in ("MagSafe compatible", "15W wireless", "5,000 mAh"):
        assert label in text, label


def test_the_feature_row_never_costs_a_specification(monkeypatch):
    """Content first: the badges are dropped before a spec row is."""
    item = {"id": "1", "code": "A",
            "name": "Maglite 5K - 5000 mAh Magnetic Wireless Power Bank - Black",
            "description": NAPIER_BODY + " 15W wireless charging over USB-C.",
            "brand": "Giftology", "color": "Black", "material": "ABS",
            "size": "104 mm", "capacity": "5000 mAh", "unitsPerCarton": 100,
            "cartonDimensions": "44 x 32 x 26 cm", "cartonWeight": "14.2",
            "cartonVolume": "0.08", "hsCode": "8507.60", "barcode": "629110821",
            "categories": ["Power Banks"], "options": ["Black", "White"],
            "available": 42, "availableKnown": True}
    text = cat.extract_text(cat.build([item], {}, market="ksa", title="T",
                                      stock_at=STOCK_AT, stock_is_known=True))
    for label in ("Brand", "Colour", "Material", "Size", "Capacity",
                  "Units per carton", "Carton size", "Carton weight",
                  "Carton volume", "HS code", "Barcode", "Category", "Options"):
        assert label in text, label
    assert "non-MagSafe smartphones." in text, "and the description is whole"
    assert "Page 2" in text and "Page 3" not in text


def test_a_feature_label_is_built_from_the_matched_text():
    """Never a fixed string where the product gives a figure."""
    assert ("battery", "3,350 mAh") in _feat(
        name="Slim Pack", description="A 3350 mAh pocket battery.")
    assert ("droplet", "750 ml") in _feat(
        name="Flask", description="A 750 ml vacuum flask.")


def test_the_band_and_availability_marks_are_drawn_not_a_font(snapshot):
    """Vector icons on both pages, so nothing can go missing from a deploy.
    The cover's three come from `server/cover.py`; the availability mark on
    a product page is the catalogue's own."""
    from server import cover as cover_master

    page_marks: list[str] = []
    cover_marks: list[str] = []
    real_icon, real_cover = cat._icon, cover_master._draw_icon

    def watched(c, name, cx, cy, r):
        page_marks.append(name)
        real_icon(c, name, cx, cy, r)

    def watched_cover(c, kind, x, top):
        cover_marks.append(kind)
        real_cover(c, kind, x, top)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cat, "_icon", watched)
        mp.setattr(cover_master, "_draw_icon", watched_cover)
        cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 2,
                    "availableKnown": True}], {}, market="ksa", title="T",
                  stock_at=STOCK_AT, stock_is_known=True)
    assert cover_marks == ["cube", "calendar", "clock"], "the cover's three cards"
    assert "check" in page_marks, "the availability mark"
