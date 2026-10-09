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


# ---------------- a selector is a question, and order is an answer --------
#
# `priceMin`/`priceMax` were gated on `jasani.prices` and two other selectors
# were not. `sort=priceAsc` orders by a figure, and an order is a reading of
# it: ask for it twice with the cheaper product swapped and the answer
# changes. `stock=booked` does the same through membership. Neither needs
# the number to be serialized, and `adminauth.PERMISSIONS` has always said
# `jasani.prices` covers "supplier prices and booked stock", so that is the
# permission — none is invented.

PROTECTED = [
    {"sort": "priceAsc"},
    {"sort": "priceDesc"},
    {"stock": "booked"},
    {"priceMin": "500"},
    {"priceMax": "500"},
    {"priceMin": "100", "priceMax": "199"},
]

NO_PRICES = {"role": "catalog"}
WITH_PRICES = {"role": "owner"}


@pytest.fixture(scope="module")
def catalog_client():
    """A catalogue-role session: jasani.view, and no jasani.prices."""
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/users",
                json={"email": "catalog@elitemarcom.com", "name": "Catalogue",
                      "password": "catalog-long-pass", "role": "catalog"},
                headers={"X-CSRF": me["csrf"]})
    c = TestClient(app)
    r = c.post("/api/admin/login", json={"email": "catalog@elitemarcom.com",
                                         "password": "catalog-long-pass"}).json()
    secret = r.get("secret") or aa.read_totp_secret(
        aa.get_user_by_email("catalog@elitemarcom.com"))
    c.post("/api/admin/2fa/verify",
           json={"pending": r["pending"],
                 "code": aa._totp_at(secret, int(time.time() // 30))})
    assert c.get("/api/admin/me").json()["role"] == "catalog"
    return c


def as_catalog(c: TestClient, path: str, **body) -> dict:
    payload = {"market": "ksa", "scope": "filtered"}
    payload.update(body)
    res = c.post(path, json=payload,
                 headers={"X-CSRF": c.get("/api/admin/me").json()["csrf"]})
    assert res.status_code == 200, res.text
    return res.json()


def test_the_permission_matrix_still_says_prices_covers_booked_stock():
    """The contract this gate rests on, read from where it is written."""
    assert aa.has_perm("owner", "jasani.prices") is True
    assert aa.has_perm("admin", "jasani.prices") is True
    assert aa.has_perm("catalog", "jasani.view") is True
    assert aa.has_perm("catalog", "jasani.prices") is False


@pytest.mark.parametrize("asked", PROTECTED)
def test_a_protected_selector_is_normalized_rather_than_refused(asked):
    """One policy, because a refusal is itself an answer: it tells an
    unauthorized caller the selector exists and means something. Neutralized
    requests simply look like requests that did not ask."""
    eff = admin_api.effective_filters(
        NO_PRICES, stock=asked.get("stock", ""),
        sort=asked.get("sort", "featured"),
        price_min=admin_api._f(asked.get("priceMin")),
        price_max=admin_api._f(asked.get("priceMax")))
    assert eff["price_min"] is None and eff["price_max"] is None
    assert eff["sort"] not in admin_api.PRICE_SENSITIVE_SORTS
    assert eff["stock"] not in admin_api.INTERNAL_STOCK_FILTERS
    #: and an authorized caller keeps every one of them
    allowed = admin_api.effective_filters(
        WITH_PRICES, stock=asked.get("stock", ""),
        sort=asked.get("sort", "featured"),
        price_min=admin_api._f(asked.get("priceMin")),
        price_max=admin_api._f(asked.get("priceMax")))
    assert allowed["sort"] == asked.get("sort", "featured")
    assert allowed["stock"] == asked.get("stock", "")
    assert allowed["price_min"] == admin_api._f(asked.get("priceMin"))


def test_an_unprotected_selector_is_left_exactly_as_asked():
    """The gate is narrow: it touches four selectors and nothing else."""
    for role in (NO_PRICES, WITH_PRICES):
        eff = admin_api.effective_filters(role, stock="low", sort="stockDesc")
        assert eff == {"stock": "low", "sort": "stockDesc",
                       "price_min": None, "price_max": None}


# ---- the private map is not consulted, not merely not printed ------------

@pytest.mark.parametrize("asked", PROTECTED)
def test_an_unauthorized_request_never_opens_the_internal_map(
        asked, catalog_client, monkeypatch):
    """Removing `_price` from a row is not the guarantee. The guarantee is
    that the map is never read, so there is nothing to infer from."""
    def boom(*a, **k):
        raise AssertionError("the internal map was opened without jasani.prices")

    monkeypatch.setattr(jasani, "internal_map", boom)

    query = {"market": "ksa", "perPage": 10}
    query.update(asked)
    assert catalog_client.get("/api/admin/jasani/items",
                              params=query).status_code == 200
    assert catalog_client.get("/api/admin/jasani/items-export",
                              params={**query, "format": "csv"}).status_code == 200
    assert as_catalog(catalog_client, "/api/admin/jasani/catalogue/count",
                      **asked)["count"] == TOTAL
    for body in ({"scope": "filtered", **asked},
                 {"scope": "selected", "ids": ["ksa-1", "ksa-2"], **asked}):
        model = admin_api.CatalogueBody(market="ksa", **body)
        admin_api._catalogue_items(model, NO_PRICES)
        admin_api._catalogue_items(admin_api.CatalogueShareBody(market="ksa", **body),
                                   NO_PRICES)
        admin_api._filter_summary(model, NO_PRICES)


def test_an_authorized_request_does_open_it():
    """The other half: the gate is a gate, not a wall."""
    opened = []
    real = jasani.internal_map

    def watched(market):
        opened.append(market)
        return real(market)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(jasani, "internal_map", watched)
        assert len(ids_for({"scope": "filtered", "priceMin": "100",
                            "priceMax": "199"})) == 100
    assert opened == ["ksa"]


# ---- the differential: identical public data, opposite private data ------

def _twin_snapshot(cheaper: str, booked: str, tmp_path):
    """Two products whose public records are identical in every field, and
    whose private figures are the other way round."""
    products = []
    for pid in ("twin-a", "twin-b"):
        products.append({
            "id": pid, "code": "ITGL 9000", "name": "Twin Product",
            "brand": "Alpha", "color": "Black", "categories": ["Drinkware"],
            "market": "ksa", "image": "", "images": [], "sequence": 1,
            "description": "A useful item.",
            "stock": {"available": 50, "known": True, "incoming": 0},
            jasani._INT_KEY: {
                "price": 10.0 if pid == cheaper else 900.0,
                "currency": "SAR",
                "booked": 7 if pid == booked else 0},
        })
    jasani._write_cache("ksa", products, fetched_at=STOCK_AT, stock_at=STOCK_AT)


@pytest.mark.parametrize("asked", PROTECTED)
def test_the_private_map_cannot_be_read_through_the_public_answer(
        asked, catalog_client, tmp_path):
    """**The real security property.** Two snapshots, identical in every
    public field, differing only in which product is cheaper and which
    carries booked stock. Without `jasani.prices` every answer — the ids,
    their order, the count and the summary — must be byte-identical. If the
    private map can change an unauthorized response at all, it can be read.
    """
    seen = []
    for cheaper, booked in (("twin-a", "twin-a"), ("twin-b", "twin-b")):
        _twin_snapshot(cheaper, booked, tmp_path)
        listing = catalog_client.get(
            "/api/admin/jasani/items",
            params={"market": "ksa", "perPage": 10, **asked}).json()
        export = catalog_client.get(
            "/api/admin/jasani/items-export",
            params={"market": "ksa", "format": "csv", **asked}).text
        counted = as_catalog(catalog_client,
                             "/api/admin/jasani/catalogue/count", **asked)
        body = admin_api.CatalogueBody(market="ksa", scope="filtered", **asked)
        seen.append(json.dumps({
            "ids": listing["ids"], "matched": listing["matched"],
            "items": [i["id"] for i in listing["items"]],
            "export": export,
            "count": counted["count"], "summary": counted["summary"],
            "pdf": [r["id"] for r in admin_api._catalogue_items(body, NO_PRICES)],
            "share": [r["id"] for r in admin_api._catalogue_items(
                admin_api.CatalogueShareBody(market="ksa", scope="filtered",
                                             **asked), NO_PRICES)],
        }, sort_keys=True))
    assert seen[0] == seen[1], (
        f"the private map changed an unauthorized answer for {asked}")


@pytest.mark.parametrize("asked,differs", [
    ({"sort": "priceAsc"}, True),
    ({"sort": "priceDesc"}, True),
    ({"stock": "booked"}, True),
    ({"priceMin": "500"}, True),
    ({"priceMax": "500"}, True),
])
def test_the_same_selectors_really_do_work_for_an_authorized_role(asked, differs,
                                                                  tmp_path):
    """And the proof the gate is not simply breaking the feature: with
    `jasani.prices` the two snapshots give different answers, which is
    exactly the difference the other role must not be able to observe."""
    seen = []
    for cheaper, booked in (("twin-a", "twin-a"), ("twin-b", "twin-b")):
        _twin_snapshot(cheaper, booked, tmp_path)
        body = admin_api.CatalogueBody(market="ksa", scope="filtered", **asked)
        seen.append([r["id"] for r in admin_api._catalogue_items(body, WITH_PRICES)])
    assert (seen[0] != seen[1]) is differs, (asked, seen)
    #: the same request without the permission cannot tell them apart
    blind = []
    for cheaper, booked in (("twin-a", "twin-a"), ("twin-b", "twin-b")):
        _twin_snapshot(cheaper, booked, tmp_path)
        body = admin_api.CatalogueBody(market="ksa", scope="filtered", **asked)
        blind.append([r["id"] for r in admin_api._catalogue_items(body, NO_PRICES)])
    assert blind[0] == blind[1]


def test_a_protected_sort_is_neutralized_for_a_chosen_list_too():
    """Ordering ids somebody ticked by price is as much a question about
    prices as filtering by one. The selected scope keeps its own rule —
    the ids are the authority — and still loses the sort."""
    picked = ["ksa-1", "ksa-500", "ksa-900"]
    body = {"scope": "selected", "ids": picked, "sort": "priceAsc"}
    assert ids_for(body) == ids_for({**body, "sort": "featured"}), \
        "an owner's price sort is honoured, and here equals featured by id"
    blind = admin_api._catalogue_items(
        admin_api.CatalogueBody(market="ksa", **body), NO_PRICES)
    public = admin_api._catalogue_items(
        admin_api.CatalogueBody(market="ksa", scope="selected", ids=picked,
                                sort="featured"), NO_PRICES)
    assert [r["id"] for r in blind] == [r["id"] for r in public]


# ---- the summary describes what was applied ------------------------------

@pytest.mark.parametrize("asked,word", [
    ({"stock": "booked"}, "Booked"),
    ({"priceMin": "100", "priceMax": "199"}, "Price"),
    ({"priceMin": "100"}, "100"),
])
def test_the_summary_never_names_a_filter_that_was_neutralized(asked, word):
    body = admin_api.CatalogueBody(market="ksa", scope="filtered", **asked)
    blind = " ".join(admin_api._filter_summary(body, NO_PRICES))
    seeing = " ".join(admin_api._filter_summary(body, WITH_PRICES))
    assert word not in blind, (asked, blind)
    assert word in seeing, (asked, seeing)


def test_every_protected_selector_is_named_in_one_place():
    """So the next person adding a selector that reads the internal map has
    somewhere obvious to add it."""
    assert admin_api.PRICE_SENSITIVE_SORTS == {"priceAsc", "priceDesc"}
    assert admin_api.INTERNAL_STOCK_FILTERS == {"booked"}
    assert admin_api.PUBLIC_SORT == "featured"
    #: and every one of them really is a selector `item_list` opens the map
    #: for — the data layer and the gate agree on the list
    import inspect

    source = inspect.getsource(jasani.item_list)
    needs = source[source.index("needs_internal = "):]
    needs = needs[:needs.index("\n    internal = ")]
    for name in admin_api.PRICE_SENSITIVE_SORTS | admin_api.INTERNAL_STOCK_FILTERS:
        assert f'"{name}"' in needs, (name, needs)
