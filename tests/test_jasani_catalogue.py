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

import json
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
    for _ in range(400):
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
def no_image_downloads(monkeypatch):
    """The catalogue never reaches the network in a test; a product with no
    photograph is also the case the layout has to survive."""
    async def nothing(url):
        return None

    monkeypatch.setattr(jasani, "_fetch_image_bytes", nothing)


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


def test_a_five_hundred_product_catalogue_builds(snapshot):
    ids = [str(1000 + i) for i in range(500)]
    started = time.time()
    blob = pdf_for(ids)
    took = time.time() - started
    text = cat.extract_text(blob)
    assert "Product Number 499" in text
    assert "Page 501" in text and "Page 502" not in text
    assert took < 180, f"took {took:.1f}s"


def test_more_than_five_hundred_is_refused_rather_than_attempted(snapshot):
    res = start_catalogue(scope="filtered", market="ksa")
    assert res.status_code == 400
    assert "at most" in res.json()["detail"]


def test_an_empty_selection_asks_for_one(snapshot):
    res = start_catalogue(ids=[], scope="selected")
    assert res.status_code == 400
    assert "select" in res.json()["detail"].lower()


# ---------------- no prices, ever ----------------

def test_no_price_of_any_kind_reaches_the_catalogue(tmp_path, monkeypatch):
    """The product carries every price field the supplier and our internal
    store can hold. None of them, and no price wording, may appear."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps({
        "fetchedAt": STOCK_AT, "stockAt": STOCK_AT,
        "internal": {"7": {"price": 12.5, "currency": "SAR", "booked": 3}},
        "products": [{
            "id": "7", "code": "EM-MUG-7", "name": "Expensive Mug", "brand": "Jasani",
            "color": "Black", "categories": ["Drinkware"],
            "description": "A mug with a story.",
            "image": "", "images": [], "stock": {"available": 42, "incoming": 0},
            "list_price": 12.5, "retail_price": 19.99, "currency": "SAR",
            "reseller_price": 15.0, "selling_price": 17.5, "vat": 1.875,
            "discount": 10, "unit_price": 12.5,
        }]}), encoding="utf-8")
    blob = pdf_for(["7"])
    text = cat.extract_text(blob).lower()
    assert "expensive mug" in text, "the product really is in the document"
    for value in ("12.5", "19.99", "15.0", "17.5", "1.875", "12,5", "19,99"):
        assert value not in text, value
    for word in cat.PRICE_WORDS:
        assert word not in text, word
    # and the guard, run against the figures this market really holds
    cat.assert_price_free(blob, cat.price_values_of("ksa", ["7"]))


def test_the_price_guard_is_not_a_no_op():
    """A check that reads an empty string passes on everything. This proves
    the extractor really sees the page text."""
    priced = cat.build(
        [{"id": "1", "code": "A", "name": "Mug", "available": 5,
          "description": "Costs 19.99 each."}], {},
        market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    with pytest.raises(cat.CatalogueError):
        cat.assert_price_free(priced, values=["19.99"])
    assert "19.99" in cat.extract_text(priced), "the extractor really reads the page"


def test_a_currency_code_alone_is_enough_to_refuse_a_document():
    doc = cat.build([{"id": "1", "code": "A", "name": "Mug", "available": 5,
                      "description": "Billed in SAR."}], {},
                    market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    with pytest.raises(cat.CatalogueError):
        cat.assert_price_free(doc)


def test_an_honest_description_is_not_mistaken_for_a_price():
    """"Low cost" and "total weight" are things a supplier writes. Refusing a
    whole catalogue over an ordinary English word would be the worse bug."""
    doc = cat.build([{"id": "1", "code": "A", "name": "Low Cost Tote",
                      "available": 5,
                      "description": "A total of 12 colours. Low cost, high quality."}],
                    {}, market="ksa", title="T", stock_at=STOCK_AT, stock_is_known=True)
    cat.assert_price_free(doc)


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


def test_generating_a_catalogue_is_audited(snapshot):
    pdf_for(["1000", "1001"], minStock="")
    entry = [a for a in aa.audit_list(30)
             if a["action"] == "jasani.catalogue_generated"][0]
    detail = json.loads(entry["detail"])
    assert detail["market"] == "ksa" and detail["items"] == 2
    assert entry["user_email"] == "owner@elitemarcom.com"
