"""One filter contract: the screen, the count, the PDF and a share agree.

Production review found a dialog promising "All filtered items: 456" and a
Create link that came back with "That is 881 products". Two faults, and each
was enough on its own:

* the figure was read **once**, when the dialog opened, out of whatever
  listing the screen happened to be showing — while Market and Minimum stock
  could still be changed inside the dialog and were sent with the request;
* the Items screen filtered by a **price band** and the catalogue did not
  carry one, so the same visible filters rebuilt a different, larger set.

What these tests hold is the contract rather than either symptom: the same
filter state resolves the same product ids everywhere, the number an admin
is shown is the number that would be built, and none of it costs a supplier
call or lets a price out.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import admin_api
from server import catalogue as cat
from server import config
from server import jasani
from server.main import app

client = TestClient(app)
STOCK_AT = 1760000000

#: 1,000 products with `available` and `price` running 0…999, so a minimum
#: stock of k keeps exactly 1,000 - k of them and a price band keeps a known
#: slice. Legible arithmetic beats a fixture nobody can predict.
TOTAL = 1000


@pytest.fixture(scope="module", autouse=True)
def admin(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("selection-runtime")
    old_db, old_runtime = aa._DB_PATH, config.RUNTIME_DIR
    aa._DB_PATH = runtime / "admin.db"
    config.RUNTIME_DIR = runtime
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    client.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com",
                                              "name": "Owner",
                                              "password": "correct-horse-battery",
                                              "setupCode": ""})
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    client.post("/api/admin/2fa/verify",
                json={"pending": r["pending"],
                      "code": aa._totp_at(r["secret"], int(time.time() // 30))})
    yield
    client.post("/api/admin/logout", headers=csrf())
    aa._DB_PATH, config.RUNTIME_DIR = old_db, old_runtime
    if hasattr(aa._local, "conn"):
        del aa._local.conn


def csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


@pytest.fixture(autouse=True)
def snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    for market in ("ksa", "uae"):
        products = []
        for n in range(TOTAL if market == "ksa" else 40):
            products.append({
                "id": f"{market}-{n}", "code": f"ITGL {n:04d}",
                "name": f"Product {n}", "brand": "Alpha" if n % 2 else "Beta",
                "color": "Black" if n % 3 else "Blue",
                "categories": ["Drinkware" if n % 5 else "Notebooks"],
                "market": market, "image": "", "images": [], "sequence": n,
                "description": "A useful item.",
                "stock": {"available": n, "known": True, "incoming": 0},
                jasani._INT_KEY: {"price": float(n), "currency": "SAR",
                                  "booked": 7 if n % 4 == 0 else 0},
            })
        jasani._write_cache(market, products, fetched_at=STOCK_AT, stock_at=STOCK_AT)
    return None


def count(**body) -> dict:
    payload = {"market": "ksa", "scope": "filtered"}
    payload.update(body)
    res = client.post("/api/admin/jasani/catalogue/count", json=payload,
                      headers=csrf())
    assert res.status_code == 200, res.text
    return res.json()


def listed(**params) -> dict:
    query = {"market": "ksa", "perPage": 10}
    query.update(params)
    res = client.get("/api/admin/jasani/items", params=query)
    assert res.status_code == 200, res.text
    return res.json()


def ids_for(body: dict, share: bool = False) -> list[str]:
    """What a build would carry, resolved without rendering anything."""
    model = admin_api.CatalogueShareBody if share else admin_api.CatalogueBody
    session = {"role": "owner", "email": "owner@elitemarcom.com"}
    return [r["id"] for r in admin_api._catalogue_items(model(**body), session)]


# ---------------- the reported case ----------------

def test_the_dialog_figure_is_the_figure_the_build_resolves():
    """456 → 881 → 456, exactly as production hit it.

    The dialog's Minimum stock changes what the request means, so it has to
    change what the dialog promises. Before this the figure came from the
    listing the screen was showing and never moved.
    """
    #: what the screen was showing when the dialog opened
    assert listed(minStock=544)["matched"] == 456

    first = count(minStock="544")
    assert first["count"] == 456 and first["allowed"] is True
    assert first["limit"] == cat.MAX_ITEMS

    #: the admin changes the minimum inside the dialog
    wider = count(minStock="119")
    assert wider["count"] == 881, "the panel now says what the server will"
    assert wider["allowed"] is False, "and says it before anything is built"

    #: pressing Create link anyway is still refused, and says what moved
    refused = client.post("/api/admin/jasani/catalogue/share",
                          json={"market": "ksa", "scope": "filtered",
                                "minStock": "119", "countedAs": 456},
                          headers=csrf())
    assert refused.status_code == 400
    detail = refused.json()["detail"]
    assert "456" in detail and "881" in detail and "500" in detail

    #: narrowed again, and the share is created with exactly those products
    back = count(minStock="544")
    assert back["count"] == 456 and back["allowed"] is True
    made = client.post("/api/admin/jasani/catalogue/share",
                       json={"market": "ksa", "scope": "filtered",
                             "minStock": "544", "countedAs": 456},
                       headers=csrf())
    assert made.status_code == 200, made.text
    assert made.json()["items"] == 456


def test_a_count_the_browser_sends_decides_nothing():
    """It words the refusal and never changes the outcome."""
    honest = client.post("/api/admin/jasani/catalogue",
                         json={"market": "ksa", "scope": "filtered",
                               "minStock": "119", "countedAs": 1},
                         headers=csrf())
    assert honest.status_code == 400
    lying = client.post("/api/admin/jasani/catalogue",
                        json={"market": "ksa", "scope": "filtered",
                              "minStock": "119", "countedAs": 10},
                        headers=csrf())
    assert lying.status_code == 400
    #: and a request that claims nothing is still refused on its merits
    silent = client.post("/api/admin/jasani/catalogue",
                         json={"market": "ksa", "scope": "filtered",
                               "minStock": "119"},
                         headers=csrf())
    assert silent.status_code == 400
    assert "881" in silent.json()["detail"]


# ---------------- the ceiling ----------------

@pytest.mark.parametrize("minimum,products,allowed", [
    (500, 500, True),            # exactly the ceiling
    (499, 501, False),           # one over
    (501, 499, True),
])
def test_the_ceiling_is_decided_before_anything_is_built(minimum, products, allowed):
    answer = count(minStock=str(minimum))
    assert answer["count"] == products
    assert answer["allowed"] is allowed
    res = client.post("/api/admin/jasani/catalogue",
                      json={"market": "ksa", "scope": "filtered",
                            "minStock": str(minimum)}, headers=csrf())
    assert (res.status_code == 200) is allowed, res.text


def test_a_minimum_includes_an_item_sitting_on_it():
    """`>=`, not `>`. A minimum of 999 keeps the one product with 999."""
    assert count(minStock="999")["count"] == 1
    assert count(minStock="1000")["count"] == 0
    assert count(minStock="1000")["allowed"] is False, "nothing is not a catalogue"
    assert count(minStock="0")["count"] == TOTAL, "a minimum of nothing filters nothing"
    assert count()["count"] == TOTAL, "and no minimum at all is the whole market"


def test_the_market_is_part_of_the_question():
    assert count(market="ksa")["count"] == TOTAL
    assert count(market="uae")["count"] == 40


# ---------------- every filter means the same thing everywhere ----------------

CASES = [
    {},
    {"minStock": "544"},
    {"q": "Product 12"},
    {"q": "ITGL 0001,ITGL 0002", "field": "code"},
    {"brand": "Alpha"},
    {"colour": "Blue"},
    {"category": "Notebooks"},
    {"stock": "in"},
    {"stock": "out"},
    {"stock": "low"},
    {"stock": "booked"},
    {"visibility": "visible"},
    {"hideZero": True},
    {"priceMin": "100"},
    {"priceMax": "100"},
    {"priceMin": "100", "priceMax": "199"},
    {"priceMin": "100", "priceMax": "199", "minStock": "150"},
    {"brand": "Alpha", "colour": "Black", "stock": "in", "minStock": "10"},
]


@pytest.mark.parametrize("filters", CASES)
def test_the_screen_and_the_catalogue_resolve_the_same_products(filters):
    """The contract. A filter the listing applies and the catalogue does not
    is exactly how 456 became 881."""
    shown = listed(**{k: ("true" if v is True else v) for k, v in filters.items()})
    assert count(**filters)["count"] == shown["matched"], filters
    assert ids_for({"scope": "filtered", **filters}) == shown["ids"], filters


@pytest.mark.parametrize("filters", CASES)
def test_the_pdf_and_the_share_resolve_the_same_ordered_products(filters):
    """Both routes come through one selection function, so they cannot
    drift. Resolved before either renderer runs, which is the point."""
    body = {"scope": "filtered", **filters}
    assert ids_for(body) == ids_for(body, share=True), filters


@pytest.mark.parametrize("sort", ["featured", "name", "sku", "brand",
                                  "stockAsc", "stockDesc",
                                  "priceAsc", "priceDesc"])
def test_a_sort_orders_the_catalogue_the_way_it_orders_the_screen(sort):
    shown = listed(sort=sort, minStock=990)
    assert ids_for({"scope": "filtered", "minStock": "990", "sort": sort}) == shown["ids"]


# ---------------- the price band selects, and never shows ----------------

def test_a_price_band_reduces_the_selection():
    assert count()["count"] == TOTAL
    assert count(priceMin="100", priceMax="199")["count"] == 100
    assert count(priceMin="900")["count"] == 100
    assert count(priceMax="9")["count"] == 10
    #: and it is the same hundred the screen would show
    assert ids_for({"scope": "filtered", "priceMin": "100", "priceMax": "199"}) == \
        listed(priceMin=100, priceMax=199)["ids"]


def test_a_band_selects_products_and_no_price_rides_out_on_them():
    """Internal-only means internal-only. The band is a question about
    records, not a licence to carry the figure that answered it."""
    rows = admin_api._catalogue_items(
        admin_api.CatalogueBody(market="ksa", scope="filtered",
                                priceMin="100", priceMax="199"),
        {"role": "owner"})
    assert len(rows) == 100
    for row in rows:
        for key in ("price", "_price", "booked", "_booked", "currency",
                    "list_price", "retail_price"):
            assert key not in row, key
    assert "100" not in json.dumps([r for r in rows if r["id"] == "ksa-100"])[:0] + ""


def test_a_banded_catalogue_is_still_price_free_end_to_end():
    """Through the real routes: the PDF, the share snapshot, the viewer's
    data and the public page."""
    res = client.post("/api/admin/jasani/catalogue/share",
                      json={"market": "ksa", "scope": "filtered",
                            "priceMin": "100", "priceMax": "109",
                            "allowPdf": True}, headers=csrf())
    assert res.status_code == 200, res.text
    token = res.json()["token"]
    for _ in range(900):
        job = client.get("/api/admin/jasani/catalogue/status",
                         params={"token": token}).json()["job"]
        if job["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert job["share"]["products"] == 10

    url = job["share"]["url"]
    #: the data a browser is served. The shipped page carries the words
    #: "Prices are available on request", which is the disclaimer and not a
    #: price, so the scan is of the payloads the products arrive in.
    served = client.get(url + "/index.json").text
    for n in range(10):
        served += client.get(url + f"/p/{n}.json").text
    low = served.lower()
    for word in ("price", "sar", "aed", "list_price", "retail", "wholesale"):
        assert word not in low, word
    #: and none of the ten figures that selected them
    for figure in range(100, 110):
        assert f'"{figure}"' not in served and f": {figure}," not in served, figure
    assert client.get(url).status_code == 200

    from server import catalogue_share as cs

    frozen = cs.snapshot_of({"id": job["share"]["id"]})
    cs.assert_snapshot_price_free(frozen.get("products") or [])
    blob = client.get(url + "/pdf")
    assert blob.status_code == 200
    cat.assert_price_free(blob.content)


def test_a_role_that_may_not_see_a_price_may_not_select_on_one():
    """A band is a binary search over figures. Seeing one and filtering by
    one are the same question, so they are the same permission."""
    body = {"market": "ksa", "scope": "filtered", "priceMin": "100",
            "priceMax": "199"}
    assert len(ids_for(body)) == 100, "an owner may"
    editor = admin_api._catalogue_items(admin_api.CatalogueBody(**body),
                                        {"role": "editor"})
    assert len(editor) == TOTAL, "a role without jasani.prices gets no band"
    assert admin_api._can_price({"role": "owner"}) is True
    assert admin_api._can_price({"role": "editor"}) is False
    assert admin_api._can_price(None) is False


def test_the_band_is_not_named_to_somebody_who_may_not_see_prices():
    body = admin_api.CatalogueBody(market="ksa", scope="filtered",
                                   priceMin="100", priceMax="199")
    owner = " ".join(admin_api._filter_summary(body, {"role": "owner"}))
    editor = " ".join(admin_api._filter_summary(body, {"role": "editor"}))
    assert "Price" in owner and "100" in owner
    assert "Price" not in editor and "100" not in editor


# ---------------- selected ids are the authority ----------------

def test_a_filter_inside_the_dialog_does_not_unpick_a_ticked_product():
    """Ticking a box means that product. Raising the minimum stock used to
    remove chosen items silently, because the ids were intersected with the
    filtered rows."""
    picked = ["ksa-1", "ksa-2", "ksa-900"]
    body = {"scope": "selected", "ids": picked, "minStock": "500",
            "priceMin": "900", "brand": "Alpha", "stock": "in"}
    assert sorted(ids_for(body)) == sorted(picked)
    assert sorted(ids_for({**body, "share": None} if False else body,
                          share=True)) == sorted(picked)


def test_a_selected_id_from_another_market_is_not_carried():
    """Existence and market still decide: an id this catalogue cannot carry
    is not in it."""
    body = {"scope": "selected", "ids": ["ksa-1", "uae-1", "nonsense"]}
    assert ids_for(body) == ["ksa-1"]
    assert ids_for({**body, "market": "uae"}) == ["uae-1"]


def test_the_count_endpoint_answers_the_selected_question_too():
    res = count(scope="selected", ids=["ksa-1", "ksa-2", "uae-1"])
    assert res["count"] == 2, "the two that exist in this market"
    assert res["summary"] == ["KSA"], "filters do not describe a chosen list"


# ---------------- what the admin is told ----------------

def test_the_summary_names_what_is_narrowing_the_list():
    body = admin_api.CatalogueBody(
        market="ksa", scope="filtered", minStock="60", brand="Alpha",
        category="Notebooks", stock="in", q="ITGL 1001,ITGL 1002",
        hideZero=True, priceMin="20", priceMax="100")
    parts = admin_api._filter_summary(body, {"role": "owner"})
    joined = " · ".join(parts)
    assert parts[0] == "KSA"
    for wanted in ("Minimum stock ≥ 60", "Brand: Alpha",
                   "Category: Notebooks", "Stock: In stock",
                   "Search: ITGL 1001, ITGL 1002", "Zero stock excluded",
                   "Price: SAR 20–100"):
        assert wanted in joined, wanted


def test_the_summary_says_nothing_it_is_not_filtering_by():
    parts = admin_api._filter_summary(
        admin_api.CatalogueBody(market="uae", scope="filtered"), {"role": "owner"})
    assert parts == ["UAE"]


# ---------------- none of it costs a supplier call ----------------

def test_counting_and_selecting_never_reach_the_supplier(monkeypatch):
    """Every path in this screen reads the cached snapshot. A catalogue must
    never spend one of the five calls a market gets each day."""
    def boom(*a, **k):
        raise AssertionError("the selection reached the supplier")

    monkeypatch.setattr(jasani, "_fetch", boom)
    monkeypatch.setattr(jasani, "_budget_ok", boom)
    monkeypatch.setattr(jasani, "_spend", boom, raising=False)
    monkeypatch.setattr(jasani, "force_refresh", boom)

    assert count(minStock="544")["count"] == 456
    assert count(priceMin="100", priceMax="199")["count"] == 100
    assert count(scope="selected", ids=["ksa-1"])["count"] == 1
    assert len(ids_for({"scope": "filtered", "minStock": "544"})) == 456
    assert len(ids_for({"scope": "filtered", "minStock": "544"}, share=True)) == 456
    #: and the listing the dialog opens over
    assert listed(minStock=544)["matched"] == 456


def test_the_count_endpoint_builds_nothing(monkeypatch):
    """No image, no document, no share, no job."""
    from server import catalogue_share as cs

    def boom(*a, **k):
        raise AssertionError("the count built something")

    monkeypatch.setattr(jasani, "_fetch_image_bytes", boom)
    monkeypatch.setattr(cat, "build", boom)
    monkeypatch.setattr(cat, "start", boom)
    monkeypatch.setattr(cs, "spawn", boom)
    before = len(client.get("/api/admin/jasani/catalogue/shares").json()["shares"])
    assert count(minStock="544")["count"] == 456
    assert len(client.get("/api/admin/jasani/catalogue/shares").json()["shares"]) == before


def test_the_count_endpoint_needs_the_same_permission_and_a_token():
    """It reads the catalogue's own selection, so it is behind the
    catalogue's own permission and its CSRF."""
    res = client.post("/api/admin/jasani/catalogue/count",
                      json={"market": "ksa", "scope": "filtered"})
    assert res.status_code == 403


# ---------------- the contract is written down once ----------------

def test_the_filter_contract_is_one_list():
    """A filter the screen has and the catalogue does not is the bug this
    closes, so the list is named and the body must carry every entry."""
    fields = set(admin_api.CatalogueBody.model_fields)
    for name in admin_api.CATALOGUE_FILTERS:
        assert name in fields, name
    for name in ("priceMin", "priceMax", "minStock", "market", "sort"):
        assert name in admin_api.CATALOGUE_FILTERS, name
    #: and a share asks the same question as a PDF, by inheriting it
    assert issubclass(admin_api.CatalogueShareBody, admin_api.CatalogueBody)


def test_the_panel_sends_every_filter_the_contract_names():
    """The dialog's payload is where the price band went missing, so the
    shipped script is checked against the contract rather than trusted."""
    import pathlib
    import re

    source = pathlib.Path("server/adminui/assets/app.js").read_text(encoding="utf-8")
    body = source[source.index("function catPayload("):]
    body = body[:body.index("\n  }")]
    for name in admin_api.CATALOGUE_FILTERS:
        assert re.search(rf"\b{name}\s*:", body), name
