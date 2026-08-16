"""Admin panel Phase 0 + 1 — auth, 2FA, roles, audit, requests inbox, Jasani console."""
from __future__ import annotations

import json
import re
from urllib.parse import quote
import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import security, storage
from server.main import app


@pytest.fixture(scope="module", autouse=True)
def admin_db(tmp_path_factory):
    """Fresh admin database for this module; tests run as one sequential flow."""
    aa._DB_PATH = tmp_path_factory.mktemp("admin") / "admin.db"
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    yield
    if hasattr(aa._local, "conn"):
        del aa._local.conn


@pytest.fixture(scope="module", autouse=True)
def records_db(tmp_path_factory):
    """Isolated public-records store so inbox tests never touch runtime/."""
    old = (storage._DB_PATH, storage._CV_DIR, storage._conn)
    d = tmp_path_factory.mktemp("records")
    storage._DB_PATH, storage._CV_DIR, storage._conn = d / "data.db", d / "cvs", None
    yield
    if storage._conn is not None:
        storage._conn.close()
    storage._DB_PATH, storage._CV_DIR, storage._conn = old


@pytest.fixture(scope="module", autouse=True)
def media_dirs(tmp_path_factory):
    """Isolated media/overrides directories for Phase 2 tests."""
    from server import media

    d = tmp_path_factory.mktemp("mediastore")
    old = (media.MEDIA_DIR, media.GLB_DIR, media.OVERRIDES_DIR)
    media.MEDIA_DIR = d / "media"
    media.GLB_DIR = d / "media" / "glb"
    media.OVERRIDES_DIR = d / "overrides"
    yield
    media.MEDIA_DIR, media.GLB_DIR, media.OVERRIDES_DIR = old


@pytest.fixture(scope="module", autouse=True)
def content_dirs(tmp_path_factory):
    """Isolated publish dir + rental runtime file for Phase 3 tests."""
    from server import content

    d = tmp_path_factory.mktemp("contentstore")
    old = (content.PUBLISHED_DIR, content.RENTAL_RUNTIME)
    content.PUBLISHED_DIR = d / "published" / "site"
    content.RENTAL_RUNTIME = d / "data" / "rental-inventory.json"
    yield
    content.PUBLISHED_DIR, content.RENTAL_RUNTIME = old


@pytest.fixture(scope="module", autouse=True)
def analytics_db(tmp_path_factory):
    """Isolated analytics database for Phase 5 tests."""
    from server import analytics

    analytics._DB_PATH = tmp_path_factory.mktemp("insights") / "analytics.db"
    if hasattr(analytics._local, "conn"):
        del analytics._local.conn
    yield
    if hasattr(analytics._local, "conn"):
        del analytics._local.conn


@pytest.fixture(autouse=True)
def reset_limiter():
    security.limiter._hits.clear()
    yield


client = TestClient(app)
OWNER = {"email": "owner@elitemarcom.com", "name": "Site Owner", "password": "correct-horse-battery"}


def totp_now(secret: str) -> str:
    return aa._totp_at(secret, int(time.time() // 30))


def sign_in(c: TestClient, email: str, password: str) -> dict:
    """Password + TOTP (enrolling on first login). Returns /me payload."""
    r = c.post("/api/admin/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    if data["stage"] == "setup":
        secret = data["secret"]
    else:
        user = aa.get_user_by_email(email)
        secret = aa.read_totp_secret(user)
    r = c.post("/api/admin/2fa/verify", json={"pending": data["pending"], "code": totp_now(secret)})
    assert r.status_code == 200, r.text
    me = c.get("/api/admin/me")
    assert me.status_code == 200
    return me.json()


# ---------------- bootstrap ----------------

def test_admin_page_serves_login_before_auth():
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Sign in" in res.text


def test_bootstrap_creates_first_owner_only_once():
    assert client.get("/api/admin/state").json()["needsBootstrap"] is True
    res = client.post("/api/admin/bootstrap", json={**OWNER, "setupCode": ""})
    assert res.status_code == 200, res.text
    # second bootstrap is refused forever
    res = client.post("/api/admin/bootstrap",
                      json={"email": "x@x.com", "name": "X", "password": "y" * 12, "setupCode": ""})
    assert res.status_code == 403


def test_login_requires_totp_enrolment_and_code():
    r = client.post("/api/admin/login", json={"email": OWNER["email"], "password": OWNER["password"]})
    assert r.status_code == 200
    data = r.json()
    assert data["stage"] == "setup" and data["secret"]
    # a wrong code is rejected
    bad = client.post("/api/admin/2fa/verify", json={"pending": data["pending"], "code": "000000"})
    assert bad.status_code == 400
    ok = client.post("/api/admin/2fa/verify",
                     json={"pending": data["pending"], "code": totp_now(data["secret"])})
    assert ok.status_code == 200
    me = client.get("/api/admin/me")
    assert me.status_code == 200 and me.json()["role"] == "owner"
    assert client.get("/admin").text.find("admin-shell") != -1  # app shell now served


def test_wrong_password_and_lockout():
    c = TestClient(app)
    for _ in range(aa.LOCKOUT_ATTEMPTS):
        r = c.post("/api/admin/login", json={"email": OWNER["email"], "password": "wrong-password-x"})
        assert r.status_code == 400
    r = c.post("/api/admin/login", json={"email": OWNER["email"], "password": OWNER["password"]})
    assert r.status_code == 429  # locked
    aa.update_user(aa.get_user_by_email(OWNER["email"])["id"], failed_attempts=0, locked_until=0)


def test_csrf_required_for_mutations():
    me = client.get("/api/admin/me").json()
    no_csrf = client.post("/api/admin/settings",
                          json={"values": {"notify.emails": ["ops@elitemarcom.com"]}})
    assert no_csrf.status_code == 403
    ok = client.post("/api/admin/settings",
                     json={"values": {"notify.emails": ["ops@elitemarcom.com"]}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert client.get("/api/admin/settings").json()["notify.emails"] == ["ops@elitemarcom.com"]


def test_default_language_decides_what_an_unprefixed_url_serves():
    """site.defaultLanguage was writable and read by nothing at all."""
    from server import adminauth as aa, content

    original = (aa.setting_get("site.languages"), aa.setting_get("site.defaultLanguage"))
    try:
        aa.setting_set("site.languages", ["en"])
        aa.setting_set("site.defaultLanguage", "ar")
        # Arabic is not published, so it cannot become the default
        assert content.default_language() == "en"
        aa.setting_set("site.languages", ["en", "ar"])
        assert content.default_language() == "ar"
        aa.setting_set("site.defaultLanguage", "en")
        assert content.default_language() == "en"
    finally:
        aa.setting_set("site.languages", original[0] or ["en"])
        aa.setting_set("site.defaultLanguage", original[1] or "en")


def test_settings_screen_only_offers_settings_that_do_something():
    """A field that stores a value nothing ever reads is worse than no field:
    it reads as configured. notify.whatsapp was one, and is gone."""
    from server import admin_api

    assert "notify.whatsapp" not in admin_api.SETTINGS_KEYS
    rejected = client.post("/api/admin/settings",
                           json={"values": {"notify.whatsapp": "+966500000000"}},
                           headers={"X-CSRF": client.get("/api/admin/me").json()["csrf"]})
    assert rejected.status_code == 400
    data = client.get("/api/admin/settings").json()
    assert "notify.whatsapp" not in data
    # the screen is told whether the legacy SMTP alert route can actually deliver
    assert isinstance(data["notify.smtpConfigured"], bool)


def test_role_permissions_enforced():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/users",
                      json={"email": "sales@elitemarcom.com", "name": "Sales Person",
                            "password": "another-long-pass", "role": "sales"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    sales = TestClient(app)
    sales_me = sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales_me["role"] == "sales"
    assert sales.get("/api/admin/users").status_code == 403      # no users.manage
    assert sales.get("/api/admin/audit").status_code == 403      # no audit.view
    assert sales.get("/api/admin/dashboard").status_code == 200  # shell works


def test_owner_safety_rails():
    me = client.get("/api/admin/me").json()
    owner_id = aa.get_user_by_email(OWNER["email"])["id"]
    res = client.post(f"/api/admin/users/{owner_id}", json={"role": "editor"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 400  # cannot demote the last owner
    res = client.post(f"/api/admin/users/{owner_id}", json={"active": False},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 400  # cannot deactivate yourself


def test_audit_chain_intact_and_populated():
    res = client.get("/api/admin/audit")
    assert res.status_code == 200
    data = res.json()
    assert data["chain"]["ok"] is True and data["chain"]["checked"] > 5
    actions = {e["action"] for e in data["entries"]}
    assert "login.success" in actions and "user.created" in actions and "settings.updated" in actions


def test_sessions_listing_and_revoke_others():
    res = client.get("/api/admin/sessions")
    assert res.status_code == 200
    assert any(s["current"] for s in res.json()["sessions"])
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/sessions/revoke-others", headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200
    assert client.get("/api/admin/me").status_code == 200  # own session survives


def test_logout_destroys_session():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/logout", headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200
    assert client.get("/api/admin/me").status_code == 401
    assert "Sign in" in client.get("/admin").text


def test_totp_algorithm_reference_vector():
    # RFC 6238 SHA-1 test vector: secret "12345678901234567890" at t=59 → 94287082
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert aa._totp_at(secret, int(59 // 30), digits=8) == "94287082"


# ---------------- Phase 1: requests inbox ----------------

def _seed_request(kind: str, payload: dict, cv: bytes | None = None, ext: str = "pdf") -> str:
    return storage.save_record(kind, payload, "test-ip", 180, cv_bytes=cv, file_ext=ext)


def test_requests_inbox_lists_decrypted_summaries():
    me = sign_in(client, OWNER["email"], OWNER["password"])
    ref_gv = _seed_request("giveaway_enquiry", {
        "fullName": "Amira Hassan", "company": "Falcon Events", "email": "amira@falcon.example",
        "market": "ksa", "items": [{"productId": "101", "name": "Notebook", "quantity": 50}]})
    ref_ct = _seed_request("contact", {"fullName": "Omar Aziz", "service": "Branding",
                                       "message": "Hello there, need a stand."})
    res = client.get("/api/admin/requests")
    assert res.status_code == 200
    data = res.json()
    refs = {x["reference"]: x for x in data["requests"]}
    assert ref_gv in refs and ref_ct in refs
    assert refs[ref_gv]["summary"]["fullName"] == "Amira Hassan"
    assert refs[ref_gv]["summary"]["items"] == 1
    assert refs[ref_gv]["status"] == "new"
    # kind filter and reference search both narrow the listing
    only_ct = client.get("/api/admin/requests?kind=contact").json()["requests"]
    assert all(x["kind"] == "contact" for x in only_ct)
    found = client.get(f"/api/admin/requests?q={ref_gv[3:8]}").json()["requests"]
    assert any(x["reference"] == ref_gv for x in found)
    # decrypt-on-view is audited
    actions = {e["action"] for e in aa.audit_list(limit=20)}
    assert "requests.listed" in actions
    globals()["_REF_GV"] = ref_gv


def test_request_detail_workflow_and_notes():
    me = client.get("/api/admin/me").json()
    ref = globals()["_REF_GV"]
    res = client.get(f"/api/admin/requests/{ref}")
    assert res.status_code == 200
    data = res.json()
    assert data["payload"]["email"] == "amira@falcon.example"
    assert data["meta"]["status"] == "new"
    # status + note need CSRF
    no_csrf = client.post(f"/api/admin/requests/{ref}", json={"status": "in_progress"})
    assert no_csrf.status_code == 403
    ok = client.post(f"/api/admin/requests/{ref}",
                     json={"status": "in_progress", "assignee": "Sales Person",
                           "note": "Called the client, awaiting brief."},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    meta = ok.json()["meta"]
    assert meta["status"] == "in_progress" and len(meta["notes"]) == 1
    assert meta["notes"][0]["by"] == OWNER["email"]
    # bad status rejected; unknown reference 404
    bad = client.post(f"/api/admin/requests/{ref}", json={"status": "sideways"},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    assert client.get("/api/admin/requests/GV-XXXX-XXXX").status_code == 404
    actions = {e["action"] for e in aa.audit_list(limit=20)}
    assert "request.viewed" in actions and "request.updated" in actions
    counts = client.get("/api/admin/requests").json()["statusCounts"]
    assert counts.get("in_progress", 0) >= 1


def test_request_attachment_download_decrypts_and_audits():
    logo = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes" * 10
    ref = _seed_request("giveaway_enquiry",
                        {"fullName": "Logo Sender", "logoAttached": True}, cv=logo, ext="png")
    res = client.get(f"/api/admin/requests/{ref}/file")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    assert res.content == logo
    assert "attachment" in res.headers["content-disposition"]
    no_file = _seed_request("contact", {"fullName": "No File"})
    assert client.get(f"/api/admin/requests/{no_file}/file").status_code == 404
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "request.file_downloaded" in actions


def test_requests_permissions_sales_yes_editor_no():
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/users",
                json={"email": "editor@elitemarcom.com", "name": "Site Editor",
                      "password": "editor-long-pass", "role": "editor"},
                headers={"X-CSRF": me["csrf"]})
    sales = TestClient(app)
    sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales.get("/api/admin/requests").status_code == 200
    assert sales.get("/api/admin/jasani").status_code == 403     # no jasani.view
    editor = TestClient(app)
    editor_me = sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.get("/api/admin/requests").status_code == 403  # no requests.view
    assert "requests.view" not in editor_me["permissions"]


def test_requests_status_filter():
    res = client.get("/api/admin/requests?status=in_progress")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert all(x["status"] == "in_progress" for x in data["requests"])
    none = client.get("/api/admin/requests?status=won").json()
    assert none["total"] == 0


def test_requests_export_csv_xlsx_pdf():
    import io
    import zipfile

    res = client.get("/api/admin/requests/export?format=csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    text = res.content.decode("utf-8-sig")
    assert "Reference,Type,Received" in text and "Amira Hassan" in text

    res = client.get("/api/admin/requests/export?format=xlsx")
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "Amira Hassan" in sheet and "Reference" in sheet

    ref = globals()["_REF_GV"]
    res = client.get(f"/api/admin/requests/export?format=pdf&refs={ref}")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")

    # single-request export + filtered export
    res = client.get(f"/api/admin/requests/{ref}/export?format=xlsx")
    assert res.status_code == 200
    res = client.get("/api/admin/requests/export?format=csv&status=in_progress")
    assert res.status_code == 200 and ref.encode() in res.content
    assert client.get("/api/admin/requests/export?format=doc").status_code == 400
    actions = {e["action"] for e in aa.audit_list(limit=15)}
    assert "requests.exported" in actions and "request.exported" in actions


def test_request_delete_removes_record_and_meta():
    me = client.get("/api/admin/me").json()
    ref = _seed_request("contact", {"fullName": "To Be Deleted"},
                        cv=b"%PDF-1.4 tiny", ext="pdf")
    client.post(f"/api/admin/requests/{ref}",
                json={"status": "closed"}, headers={"X-CSRF": me["csrf"]})
    no_csrf = client.post(f"/api/admin/requests/{ref}/delete")
    assert no_csrf.status_code == 403
    ok = client.post(f"/api/admin/requests/{ref}/delete", headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert client.get(f"/api/admin/requests/{ref}").status_code == 404
    assert storage.get_record(ref) is None
    assert aa.request_meta_get(ref)["updatedAt"] is None  # meta row gone
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "request.deleted" in actions
    # sales can delete (requests.manage), editor cannot even see
    sales = TestClient(app)
    sales_me = sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    ref2 = _seed_request("contact", {"fullName": "Sales Deletes"})
    ok2 = sales.post(f"/api/admin/requests/{ref2}/delete",
                     headers={"X-CSRF": sales_me["csrf"]})
    assert ok2.status_code == 200


# ---------------- Phase 1: Jasani console ----------------

def _seed_jasani_cache(cache_dir, market="ksa"):
    products = [
        {"id": "101", "code": "ITGL 1291", "name": "Eco Notebook", "brand": "Jasani",
         "color": "Blue", "image": "https://www.giftsksa.com/img/1.jpg",
         "stock": {"available": 40, "incoming": 10}},
        {"id": "102", "code": "CTEN 2240", "name": "Steel Tumbler", "brand": "",
         "color": "Silver", "image": "", "stock": {"available": 0, "incoming": 0}},
    ]
    (cache_dir / f"giveaways-{market}.json").write_text(json.dumps(
        {"fetchedAt": int(time.time()), "stockAt": int(time.time()), "products": products}),
        encoding="utf-8")
    return products


def _catalog_client():
    """A catalogue-role client: jasani.view but no prices and no visibility."""
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/users",
                json={"email": "catalog@elitemarcom.com", "name": "Catalogue Manager",
                      "password": "catalog-long-pass", "role": "catalog"},
                headers={"X-CSRF": me["csrf"]})
    c = TestClient(app)
    return c, sign_in(c, "catalog@elitemarcom.com", "catalog-long-pass")


def _seed_items_cache(cache_dir, market="ksa"):
    """A snapshot with the internal fields still attached, so _write_cache is
    the thing under test as well as the reader."""
    from server import jasani

    rows = [
        # the last column is website_sequence — the supplier's own website order
        ("2001", "ITGL 1291", "Aluminium Flask", "Santhome", "Black", "Drinkware",
         1840, 0, 120, 38.50, 62.00, 30),
        ("2002", "CTEN 2240", "Cotton Tote Bag", "EcoLine", "Natural", "Bags",
         0, 1500, 90, 11.25, 19.00, 10),
        ("2003", "APRL 4417", "Zip Hoodie", "Elite Collection", "Orange", "Apparel",
         12, 0, 8, 96.00, 165.00, 20),
    ]
    products = []
    for pid, code, name, brand, colour, cat, avail, inc, booked, price, _rtl, seq in rows:
        products.append({
            "id": pid, "code": code, "name": name, "brand": brand, "color": colour,
            "categories": [cat], "market": market, "image": "", "images": [],
            "sequence": seq,
            "description": f"{name} description.", "hsCode": "9617.00",
            "unitsPerCarton": 50, "cartonDimensions": "600 x 400 x 300 mm",
            "stock": {"available": avail, "incoming": inc,
                      "incomingDate": "12 Mar 2026" if inc else None},
            jasani._INT_KEY: {"price": price, "currency": "SAR", "booked": booked},
        })
    jasani._write_cache(market, products, fetched_at=time.time(), stock_at=time.time())
    return products


def test_internal_supplier_fields_never_ride_on_a_product(tmp_path, monkeypatch):
    """blocked_qty and the two prices are internal by supplier policy. They are
    stored beside the catalogue, not on it, so a caller that hands the product
    list to a public response cannot leak what the list never holds."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    raw = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    assert all(jasani._INT_KEY not in p for p in raw["products"])
    for key in ("price", "wholesale", "retail", "booked", "list_price", "blocked_qty"):
        assert all(key not in p for p in raw["products"]), key
    assert raw["internal"]["2001"] == {"price": 38.5, "currency": "SAR", "booked": 120}
    # a stock-only refresh carries no prices; the stored ones must survive it
    products = jasani.all_products("ksa")
    jasani._merge_stock(products, [{"id": "2001", "net_available_qty": 7, "blocked_qty": 3}])
    jasani._write_cache("ksa", products, fetched_at=time.time(), stock_at=time.time())
    after = jasani.internal_map("ksa")["2001"]
    assert after["price"] == 38.5 and after["booked"] == 3


def test_items_list_searches_filters_and_gates_prices(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    res = client.get("/api/admin/jasani/items?market=ksa")
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["totals"] == {"all": 3, "in": 2, "low": 1, "out": 1, "hidden": 0}
    assert d["facets"]["brands"] == ["EcoLine", "Elite Collection", "Santhome"]
    assert d["canSeePrices"] is True and d["currency"] == "SAR"
    assert d["items"][0]["price"] is not None

    # Enter and comma both split, and results match any term
    two = client.get("/api/admin/jasani/items?market=ksa&q=hoodie,CTEN").json()
    assert {i["code"] for i in two["items"]} == {"APRL 4417", "CTEN 2240"}
    # a pasted column arrives with newlines
    pasted = client.get("/api/admin/jasani/items?market=ksa&q=" + quote("ITGL 1291\nAPRL 4417")).json()
    assert {i["code"] for i in pasted["items"]} == {"ITGL 1291", "APRL 4417"}

    band = client.get("/api/admin/jasani/items?market=ksa&priceMin=30&priceMax=70").json()
    assert {i["code"] for i in band["items"]} == {"ITGL 1291"}
    # one price, so the band needs no "which price" to go with it
    assert all("retail" not in i for i in band["items"])

    assert [i["code"] for i in client.get(
        "/api/admin/jasani/items?market=ksa&sort=priceDesc").json()["items"]][0] == "APRL 4417"
    assert {i["code"] for i in client.get(
        "/api/admin/jasani/items?market=ksa&stock=out").json()["items"]} == {"CTEN 2240"}
    assert {i["code"] for i in client.get(
        "/api/admin/jasani/items?market=ksa&hideZero=true").json()["items"]} == {"ITGL 1291", "APRL 4417"}

    # a role without jasani.prices gets a payload with no price in it at all
    cat, _ = _catalog_client()
    lean = cat.get("/api/admin/jasani/items?market=ksa").json()
    assert lean["canSeePrices"] is False
    assert all("price" not in i and "wholesale" not in i and "retail" not in i
               and "booked" not in i for i in lean["items"])
    assert cat.get("/api/admin/jasani/items?market=ksa&priceMin=30").json()["matched"] == 3


def test_items_default_to_the_website_order(tmp_path, monkeypatch):
    """Featured is the list's default, and it means what it means on the site:
    the supplier's website_sequence, lowest first, unsequenced items last."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    d = client.get("/api/admin/jasani/items?market=ksa").json()
    assert [i["code"] for i in d["items"]] == ["CTEN 2240", "APRL 4417", "ITGL 1291"]
    assert d["items"] == client.get(
        "/api/admin/jasani/items?market=ksa&sort=featured").json()["items"]
    # the ordering key is not something the browser needs to be told
    assert all("_seq" not in i and "sequence" not in i for i in d["items"])

    # an item the supplier never sequenced sorts last, not first
    products = jasani.all_products("ksa")
    products.append({**products[0], "id": "2004", "code": "ZZZ 0001",
                     "name": "Unsequenced Item", "sequence": 0})
    jasani._write_cache("ksa", products, fetched_at=time.time(), stock_at=time.time())
    order = [i["code"] for i in client.get("/api/admin/jasani/items?market=ksa").json()["items"]]
    assert order[-1] == "ZZZ 0001"


def test_a_stock_row_without_incoming_keeps_the_quantity_we_already_had(tmp_path, monkeypatch):
    """Absent and zero are different answers. A stock row that simply omits
    incoming_qty must not wipe the figure the products feed gave us."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    products = jasani.all_products("ksa")
    jasani._merge_stock(products, [{"id": "2002", "net_available_qty": 4}])
    tote = next(p for p in products if p["id"] == "2002")
    assert tote["stock"]["available"] == 4 and tote["stock"]["incoming"] == 1500
    # a row that does carry the field still wins
    jasani._merge_stock(products, [{"id": "2002", "net_available_qty": 4, "incoming_qty": 0}])
    assert tote["stock"]["incoming"] == 0


def test_a_snapshot_without_prices_says_so(tmp_path, monkeypatch):
    """A snapshot written before the internal store existed carries no prices.
    The page says they arrive with the next sync rather than showing dashes
    with no explanation."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    assert client.get("/api/admin/jasani/items?market=ksa").json()["pricesPending"] is False

    raw = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    raw["internal"] = {}
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(raw), encoding="utf-8")
    d = client.get("/api/admin/jasani/items?market=ksa").json()
    assert d["pricesPending"] is True and d["items"][0]["price"] is None
    # a role that may not see prices is never told about a price gap
    cat, _ = _catalog_client()
    assert cat.get("/api/admin/jasani/items?market=ksa").json()["pricesPending"] is False


def test_hidden_items_and_zero_stock_rule_reach_the_public_catalogue(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    me = client.get("/api/admin/me").json()
    public = lambda: {p["code"] for p in
                      client.get("/api/giveaways/products?country=ksa").json()["products"]}
    assert public() == {"ITGL 1291", "CTEN 2240", "APRL 4417"}

    hide = client.post("/api/admin/jasani/visibility",
                       json={"market": "ksa", "productId": "2003", "hidden": True},
                       headers={"X-CSRF": me["csrf"]})
    assert hide.status_code == 200, hide.text
    assert public() == {"ITGL 1291", "CTEN 2240"}
    assert client.get("/api/admin/jasani/items?market=ksa").json()["totals"]["hidden"] == 1

    rule = client.post("/api/admin/jasani/zero-stock-rule", json={"market": "ksa", "on": True},
                       headers={"X-CSRF": me["csrf"]})
    assert rule.status_code == 200
    assert public() == {"ITGL 1291"}          # the out-of-stock tote goes too
    rows = {i["code"]: i for i in client.get("/api/admin/jasani/items?market=ksa").json()["items"]}
    assert rows["CTEN 2240"]["hiddenByRule"] is True and rows["CTEN 2240"]["hidden"] is False
    assert rows["APRL 4417"]["hidden"] is True
    assert rows["ITGL 1291"]["live"] is True
    # the admin's own list still shows everything
    assert len(rows) == 3

    state = client.get("/api/admin/jasani/visibility?market=ksa").json()
    assert state["hideZeroStock"] is True and state["zeroStockCount"] == 1
    assert [h["product_id"] for h in state["hiddenItems"]] == ["2003"]

    # changing what the public site sells needs more than jasani.view
    cat, cat_me = _catalog_client()
    denied = cat.post("/api/admin/jasani/visibility",
                      json={"market": "ksa", "productId": "2001", "hidden": True},
                      headers={"X-CSRF": cat_me["csrf"]})
    assert denied.status_code == 403

    client.post("/api/admin/jasani/zero-stock-rule", json={"market": "ksa", "on": False},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/jasani/visibility",
                json={"market": "ksa", "productId": "2003", "hidden": False},
                headers={"X-CSRF": me["csrf"]})
    assert public() == {"ITGL 1291", "CTEN 2240", "APRL 4417"}


def test_item_detail_and_exports(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    detail = client.get("/api/admin/jasani/items/ksa/2001")
    assert detail.status_code == 200, detail.text
    item = detail.json()["item"]
    assert item["code"] == "ITGL 1291" and item["description"]
    assert item["price"] == 38.5 and item["booked"] == 120
    assert "retail" not in item
    assert client.get("/api/admin/jasani/items/ksa/nope").status_code == 404

    csv = client.get("/api/admin/jasani/items-export?format=csv&market=ksa")
    assert csv.status_code == 200
    body = csv.content.decode("utf-8-sig")
    assert body.splitlines()[0] == (
        "SN,SKU,Name,Brand,Colour,Category,Price (SAR),Booked,"
        "Available,Incoming,Incoming date (estimated),On the website")
    assert "ITGL 1291" in body
    xlsx = client.get("/api/admin/jasani/items-export?format=xlsx&market=ksa")
    assert xlsx.content[:2] == b"PK"
    pdf = client.get("/api/admin/jasani/items-export?format=pdf&market=ksa")
    assert pdf.content.startswith(b"%PDF-")

    # a filtered export carries only what is on screen; scope=all ignores filters
    one = client.get("/api/admin/jasani/items-export?format=csv&market=ksa&q=hoodie")
    assert len(one.content.decode("utf-8-sig").strip().splitlines()) == 2
    every = client.get("/api/admin/jasani/items-export?format=csv&market=ksa&q=hoodie&scope=all")
    assert len(every.content.decode("utf-8-sig").strip().splitlines()) == 4

    # an export must not become the way a price leaves the panel
    cat, _ = _catalog_client()
    lean = cat.get("/api/admin/jasani/items-export?format=csv&market=ksa")
    header = lean.content.decode("utf-8-sig").splitlines()[0]
    assert "Price" not in header and "Booked" not in header
    assert "38.5" not in lean.content.decode("utf-8-sig")


ODOO_HOST = "https://www.giftsksa.com"
ODOO_PHOTOS = [f"{ODOO_HOST}/web/image/product.image/{20036 + i}/image_1024" for i in range(2)]
ODOO_POSTER = f"{ODOO_HOST}/web/image/product.image/20045/image_1024"
ODOO_PAGE = (
    '<div id="product_detail"><div class="carousel slide"><div class="carousel-inner">'
    '<div class="carousel-item"><img src="/web/image/product.image/20036/image_1024"></div>'
    '<div class="carousel-item"><img src="/web/image/product.image/20037/image_1024"></div>'
    '<div class="carousel-item"><iframe src="https://www.youtube.com/embed/lFhAiGLjoMo"></iframe></div>'
    '</div><ul class="carousel-indicators">'
    '<li data-bs-slide-to="0"><img src="/web/image/product.image/20036/image_128"></li>'
    '<li data-bs-slide-to="1"><img src="/web/image/product.image/20037/image_128"></li>'
    '<li data-bs-slide-to="2" class="o_product_video_thumb">'
    '<img src="/web/image/product.image/20045/image_128"></li>'
    "</ul></div></div>")


def _seed_item_with_video(tmp_path, monkeypatch):
    from server import jasani, supplier_video

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(supplier_video, "_CACHE_DIR", tmp_path / "videos")
    jasani._write_cache("ksa", [{
        "id": "2001", "code": "ITGL 1290", "name": "MagCase Phone Cardholder",
        "brand": "Jasani", "color": "Black", "categories": ["Tech"], "market": "ksa",
        "image": ODOO_PHOTOS[0], "images": ODOO_PHOTOS + [ODOO_POSTER],
        "parentId": "29452", "templateId": None, "videos": [],
        "description": "Magnetic phone cardholder.",
        "stock": {"available": 5, "incoming": 0, "incomingDate": None},
    }], fetched_at=time.time(), stock_at=time.time())

    async def fake_page(url):
        return ODOO_PAGE
    monkeypatch.setattr(supplier_video, "fetch_page", fake_page)
    return supplier_video


def test_the_admin_item_page_shows_the_video_and_not_its_static_poster(tmp_path, monkeypatch):
    """The panel and the website read the same public page from the same cache,
    so an admin checking an item sees exactly what a customer sees — the video,
    and not the poster sitting in the gallery as a still nobody can play."""
    _seed_item_with_video(tmp_path, monkeypatch)

    item = client.get("/api/admin/jasani/items/ksa/2001").json()["item"]
    assert [v["youtubeId"] for v in item["videos"]] == ["lFhAiGLjoMo"]
    assert item["videos"][0]["supplierImageId"] == "20045"
    assert item["videos"][0]["supplierPoster"] == ODOO_POSTER
    assert item["images"] == ODOO_PHOTOS      # the poster is no longer a photograph
    assert ODOO_POSTER not in item["images"]


def test_the_product_sheet_never_prints_a_video_poster(tmp_path, monkeypatch):
    """A customer document should carry photographs of the product, not a frame
    of a video that cannot be played on paper."""
    supplier_video = _seed_item_with_video(tmp_path, monkeypatch)
    fetched = []

    async def fake_image(url):
        fetched.append(url)
        return None
    from server import jasani
    monkeypatch.setattr(jasani, "_fetch_image_bytes", fake_image)

    res = client.get("/api/admin/jasani/items/ksa/2001/sheet")
    assert res.status_code == 200 and res.content.startswith(b"%PDF-")
    assert fetched == ODOO_PHOTOS
    assert ODOO_POSTER not in fetched
    assert supplier_video.without_posters(
        ODOO_PHOTOS + [ODOO_POSTER],
        [{"supplierImageId": "20045", "supplierPoster": ""}]) == ODOO_PHOTOS


def test_an_unidentified_poster_leaves_the_admin_gallery_alone(tmp_path, monkeypatch):
    from server import supplier_video

    every = ODOO_PHOTOS + [ODOO_POSTER]
    assert supplier_video.without_posters(every, []) == every
    assert supplier_video.without_posters(
        every, [{"youtubeId": "lFhAiGLjoMo", "supplierImageId": "", "supplierPoster": ""}]) == every


def test_product_sheet_pdf_carries_no_price(tmp_path, monkeypatch):
    """The sheet is a customer document, and supplier prices may not travel in
    one — not for an owner either."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_items_cache(tmp_path)
    res = client.get("/api/admin/jasani/items/ksa/2001/sheet")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")
    assert res.headers["cache-control"] == "no-store"
    assert "ITGL-1291" in res.headers["content-disposition"]
    body = res.content.decode("latin-1")
    for forbidden in ("38.5", "62.0", "Price", "Wholesale", "Retail", "SAR"):
        assert forbidden not in body, forbidden
    assert client.get("/api/admin/jasani/items/ksa/nope/sheet").status_code == 404


def test_jasani_console_status_and_search(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)
    res = client.get("/api/admin/jasani")
    assert res.status_code == 200
    data = res.json()
    for market in ("ksa", "uae"):
        assert data["budgets"][market]["limit"] >= 1
        assert data["budgets"][market]["used"] == 0
    assert data["markets"]["ksa"]["products"] == 2
    assert data["markets"]["ksa"]["inStock"] == 1
    assert data["markets"]["uae"]["cached"] is False
    assert set(data["tokensConfigured"]) == {"ksa", "uae"}
    found = client.get("/api/admin/jasani/products?market=ksa&q=tumbler").json()["products"]
    assert len(found) == 1 and found[0]["code"] == "CTEN 2240"
    assert client.get("/api/admin/jasani/products?market=nope").status_code == 400


def test_jasani_refresh_stock_success_and_audit(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)

    async def fake_apply(market, products, manual=False):
        assert manual is True          # an admin pressing refresh is a manual sync
        for p in products:
            p["stock"]["available"] = 77

    monkeypatch.setattr(jasani, "_apply_stock", fake_apply)
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": "stock"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    assert res.json()["refreshed"] == "stock"
    cached = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    assert all(p["stock"]["available"] == 77 for p in cached["products"])
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "jasani.refreshed" in actions


def test_jasani_refresh_targets_and_the_reserved_call(tmp_path, monkeypatch):
    """Four buttons, four targets. The reserve is owner/admin only — a role
    with jasani.refresh but no seniority works against the automatic four."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)
    calls = []

    async def fake_refresh(market, what, manual=True):
        calls.append((market, what, manual))
        return {"refreshed": what, "products": 2, "priced": 2}

    monkeypatch.setattr(jasani, "force_refresh", fake_refresh)
    me = client.get("/api/admin/me").json()
    for what in ("products", "prices", "stock", "full"):
        res = client.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": what},
                          headers={"X-CSRF": me["csrf"]})
        assert res.status_code == 200, (what, res.text)
    assert [c[1] for c in calls] == ["products", "prices", "stock", "full"]
    assert all(c[2] is True for c in calls)        # the owner may use the reserve

    bad = client.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": "branding"},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400

    # a catalogue role has jasani.refresh but is not owner/admin: manual=False,
    # so it can never reach the fifth call
    cat, cat_me = _catalog_client()
    calls.clear()
    ok = cat.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": "prices"},
                  headers={"X-CSRF": cat_me["csrf"]})
    assert ok.status_code == 200 and calls == [("ksa", "prices", False)]


def test_jasani_refresh_blocked_when_budget_exhausted(tmp_path, monkeypatch):
    from server import config as cfg
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)
    monkeypatch.setattr(cfg, "JASANI_TOKENS", {"ksa": "test-token", "uae": "test-token-uae"})
    (tmp_path / "supplier-budget.json").write_text(
        json.dumps({m: {"day": jasani._market_day(m), "count": cfg.SUPPLIER_DAILY_BUDGET}
                    for m in cfg.JASANI_HOSTS}),
        encoding="utf-8")
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": "stock"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 503
    assert "budget" in res.json()["detail"].lower()
    # the cached snapshot is untouched
    cached = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    assert cached["products"][0]["stock"]["available"] == 40
    budgets = client.get("/api/admin/jasani").json()["budgets"]
    assert budgets["ksa"]["remaining"] == 0 and budgets["uae"]["remaining"] == 0
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "jasani.refresh_failed" in actions


# ---------------- Phase 2: media library, brand, GLB ----------------

def _png_bytes(size=(200, 200), color="red") -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_media_upload_converts_to_webp_and_serves():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/media/upload",
                      files={"file": ("photo.png", _png_bytes(), "image/png")},
                      data={"alt": "Red test square"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    item = res.json()["item"]
    assert item["file"].endswith(".webp") and item["alt"] == "Red test square"
    served = client.get(f"/media/{item['file']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.content[:4] == b"RIFF" and served.content[8:12] == b"WEBP"
    # listed with usage stats
    lib = client.get("/api/admin/media").json()
    assert any(m["id"] == item["id"] for m in lib["library"])
    assert lib["usage"]["libraryBytes"] > 0
    # alt update + delete
    ok = client.post(f"/api/admin/media/{item['id']}/alt", json={"alt": "New alt"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    gone = client.post(f"/api/admin/media/{item['id']}/delete", headers={"X-CSRF": me["csrf"]})
    assert gone.status_code == 200
    assert client.get(f"/media/{item['file']}").status_code == 404
    # junk uploads are refused
    bad = client.post("/api/admin/media/upload",
                      files={"file": ("x.png", b"not-an-image-at-all", "image/png")},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400


def test_site_asset_replace_serves_override_and_resets():
    me = client.get("/api/admin/me").json()
    original = client.get("/assets/favicon-64.png").content
    res = client.post("/api/admin/media/replace-asset",
                      data={"path": "assets/favicon-64.png"},
                      files={"file": ("new.png", _png_bytes((64, 64), "blue"), "image/png")},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    replaced = client.get("/assets/favicon-64.png")
    assert replaced.status_code == 200 and replaced.content != original
    assert replaced.content.startswith(b"\x89PNG")
    assets = client.get("/api/admin/media").json()["siteAssets"]
    row = next(a for a in assets if a["path"] == "assets/favicon-64.png")
    assert row["overridden"] is True
    ok = client.post("/api/admin/media/reset-asset", json={"path": "assets/favicon-64.png"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert client.get("/assets/favicon-64.png").content == original
    # traversal and non-asset paths are rejected
    bad = client.post("/api/admin/media/replace-asset",
                      data={"path": "../server/config.py"},
                      files={"file": ("x.png", _png_bytes(), "image/png")},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400


def test_brand_tokens_theme_css_and_warnings():
    me = client.get("/api/admin/me").json()
    assert client.get("/theme-custom.css").text == ""
    res = client.post("/api/admin/brand/tokens",
                      json={"values": {"orange": "#123456", "motion": False}},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    css = client.get("/theme-custom.css")
    assert css.headers["content-type"].startswith("text/css")
    assert "--orange: #123456;" in css.text
    assert "animation-duration" in css.text  # motion off
    bad = client.post("/api/admin/brand/tokens", json={"values": {"orange": "orangeish"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    # near-white orange trips a contrast warning
    warn = client.post("/api/admin/brand/tokens",
                       json={"values": {"orange": "#ffef e0".replace(" ", ""), "motion": True}},
                       headers={"X-CSRF": me["csrf"]})
    assert warn.status_code == 200 and warn.json()["warnings"]
    # reset to defaults
    client.post("/api/admin/brand/tokens", json={"values": {"motion": True}},
                headers={"X-CSRF": me["csrf"]})
    assert client.get("/theme-custom.css").text == ""


def test_the_admin_picks_what_a_first_time_visitor_sees():
    """An admin chooses the default theme; a visitor who has already chosen
    keeps theirs. The choice is baked into the markup because the theme has to
    be settled before the first paint."""
    import re

    from server import content, media

    me = client.get("/api/admin/me").json()

    def html_tag(page="index"):
        return re.search(r"<html[^>]*>", content.bake_page(page)).group(0)

    # shipped state: nothing stamped, so the page follows the visitor's device
    assert media.get_brand_tokens()["theme"] == "auto"
    assert "data-default-theme" not in html_tag()

    res = client.post("/api/admin/brand/tokens", json={"values": {"theme": "dark"}},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    assert client.get("/api/admin/brand").json()["tokens"]["theme"] == "dark"
    # ...and every page carries it, not just the one that was open
    for page in ("index", "about", "giveaways", "contact", "privacy"):
        assert 'data-default-theme="dark"' in html_tag(page), page

    # switching again replaces rather than accumulates
    client.post("/api/admin/brand/tokens", json={"values": {"theme": "light"}},
                headers={"X-CSRF": me["csrf"]})
    tag = html_tag()
    assert 'data-default-theme="light"' in tag
    assert tag.count("data-default-theme") == 1
    # the page's own data-theme is untouched: it is the pre-script fallback
    assert 'data-theme="dark"' in tag

    # back to auto and the attribute goes away entirely
    client.post("/api/admin/brand/tokens", json={"values": {"theme": "auto"}},
                headers={"X-CSRF": me["csrf"]})
    assert "data-default-theme" not in html_tag()

    # anything that is not one of the three is refused
    bad = client.post("/api/admin/brand/tokens", json={"values": {"theme": "midnight"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    assert media.get_brand_tokens()["theme"] == "auto"


def test_changing_the_default_theme_leaves_the_pages_waiting_to_publish():
    """It is baked into the markup, so it is an unpublished change to every
    page. The Pages screen saying "up to date" while the live site still shows
    the old theme is the failure this prevents."""
    import time

    def past_the_second():
        """Both stamps are whole seconds and "waiting to publish" is a strictly
        later comparison, so a test that publishes and edits inside one second
        would read as settled. A real admin takes longer than that."""
        time.sleep(1.05 - time.time() % 1)

    me = client.get("/api/admin/me").json()
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    before = client.get("/api/admin/pages").json()
    assert all(not p["dirty"] for p in before["pages"]), "publish should settle everything"

    past_the_second()
    client.post("/api/admin/brand/tokens", json={"values": {"theme": "dark"}},
                headers={"X-CSRF": me["csrf"]})
    after = client.get("/api/admin/pages").json()
    assert all(p["dirty"] for p in after["pages"]), "every page is waiting again"

    # a colour is live immediately and needs no publish, so it must not
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    past_the_second()
    client.post("/api/admin/brand/tokens",
                json={"values": {"theme": "dark", "orange": "#123456"}},
                headers={"X-CSRF": me["csrf"]})
    colour_only = client.get("/api/admin/pages").json()
    assert not any(p["dirty"] for p in colour_only["pages"])

    client.post("/api/admin/brand/tokens", json={"values": {"theme": "auto"}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


def test_the_published_site_serves_the_chosen_default():
    """End to end: set it, publish, and a real request for a real page carries
    the attribute the browser reads before it paints."""
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/brand/tokens", json={"values": {"theme": "dark"}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    for path in ("/", "/about.html", "/giveaways.html"):
        body = client.get(path).text
        assert 'data-default-theme="dark"' in body, path
        # and the script that reads it is the one we shipped, once
        assert body.count("/js/theme-init.js") == 1, path
    client.post("/api/admin/brand/tokens", json={"values": {"theme": "auto"}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert "data-default-theme" not in client.get("/").text
    # leave the site unpublished, the way this module found it
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


def test_identity_logo_svg_sanitized_and_served():
    me = client.get("/api/admin/me").json()
    evil = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    res = client.post("/api/admin/brand/identity",
                      data={"slot": "logoLight"},
                      files={"file": ("logo.svg", evil, "image/svg+xml")},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 400
    clean = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
             b'<rect width="10" height="10" fill="#123456"/></svg>')
    res = client.post("/api/admin/brand/identity",
                      data={"slot": "logoLight"},
                      files={"file": ("logo.svg", clean, "image/svg+xml")},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    served = client.get("/assets/logo.svg")
    assert served.content == clean
    assert served.headers["content-type"].startswith("image/svg")
    slots = {s["slot"]: s for s in client.get("/api/admin/brand").json()["identity"]}
    assert slots["logoLight"]["overridden"] is True
    ok = client.post("/api/admin/brand/identity/reset", json={"slot": "logoLight"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert client.get("/assets/logo.svg").content != clean


def test_glb_upload_activate_and_reset():
    me = client.get("/api/admin/me").json()
    original_len = len(client.get("/assets/aces-exhibition.glb").content)
    glb = b"glTF" + (2).to_bytes(4, "little") + (120).to_bytes(4, "little") + b"\0" * 108
    res = client.post("/api/admin/glb/upload",
                      files={"file": ("stand.glb", glb, "model/gltf-binary")},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    fname = res.json()["file"]
    ok = client.post("/api/admin/glb/activate", json={"file": fname},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    live = client.get("/assets/aces-exhibition.glb")
    assert live.content == glb
    assert live.headers["content-type"] == "model/gltf-binary"
    state = client.get("/api/admin/brand").json()["glb"]
    assert state["overrideActive"] is True
    assert any(v["file"] == fname and v["active"] for v in state["versions"])
    client.post("/api/admin/glb/reset", headers={"X-CSRF": me["csrf"]})
    assert len(client.get("/assets/aces-exhibition.glb").content) == original_len
    # invalid model rejected
    bad = client.post("/api/admin/glb/upload",
                      files={"file": ("x.glb", b"nope" * 50, "model/gltf-binary")},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400


def test_hero_camera_config_public_endpoint():
    me = client.get("/api/admin/me").json()
    assert client.get("/api/site/hero").json() == {}
    res = client.post("/api/admin/hero",
                      json={"values": {"camz": 6.5, "camy": 1.4, "fov": 42}},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200
    assert client.get("/api/site/hero").json() == {"camz": 6.5, "camy": 1.4, "fov": 42}
    bad = client.post("/api/admin/hero", json={"values": {"camz": 99}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    client.post("/api/admin/hero", json={"values": {}}, headers={"X-CSRF": me["csrf"]})
    assert client.get("/api/site/hero").json() == {}


def test_media_and_brand_permissions():
    sales = TestClient(app)
    sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales.get("/api/admin/media").status_code == 403
    assert sales.get("/api/admin/brand").status_code == 403
    editor = TestClient(app)
    editor_me = sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.get("/api/admin/media").status_code == 200
    assert editor.get("/api/admin/brand").status_code == 200
    assert "media.manage" in editor_me["permissions"]


# ---------------- Phase 3: pages, publish, rollback, rentals ----------------

def test_pages_list_and_editor_originals():
    res = client.get("/api/admin/pages")
    assert res.status_code == 200
    data = res.json()
    assert any(p["page"] == "index" for p in data["pages"])
    assert data["published"] is False
    editor = client.get("/api/admin/pages/index").json()
    fields = {f["key"]: f for f in editor["regions"]}
    assert fields["hero.title1"]["original"] == "Experiences made"
    assert fields["hero.title1"]["value"] == ""
    seo = {f["key"]: f for f in editor["seo"]}
    assert "Elite Marcom" in seo["seo.title"]["original"]
    glob = client.get("/api/admin/pages/_global").json()
    gfields = {f["key"]: f for f in glob["regions"]}
    # the menu labels moved to a managed list; what is left here is the text
    # around the menu, and it still reads its default out of the shipped page
    assert "nav.about" not in gfields
    assert gfields["header.cities"]["original"] == "Riyadh · Dubai · Worldwide"
    assert gfields["footer.email"]["original"] == "info@elitemarcom.com"


def test_content_save_preview_publish_and_rollback():
    me = client.get("/api/admin/me").json()
    ok = client.post("/api/admin/pages/index",
                     json={"lang": "en", "values": {"hero.title1": "Bold experiences",
                                                    "seo.title": "Elite Marcom — New Title"}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    # preview shows the draft; the public site does not (nothing published yet)
    prev = client.get("/admin/preview/index")
    assert prev.status_code == 200
    assert "Bold experiences" in prev.text
    assert "<title>Elite Marcom — New Title</title>" in prev.text
    assert "Bold experiences" not in client.get("/").text
    # publish v1
    pub = client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert pub.status_code == 200 and pub.json()["pages"] >= 11
    v1 = pub.json()["id"]
    assert "Bold experiences" in client.get("/").text
    assert "Bold experiences" in client.get("/index.html").text
    assert client.get("/sitemap.xml").text.startswith("<?xml")
    # second edit + publish v2
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.title1": "Even bolder"}},
                headers={"X-CSRF": me["csrf"]})
    pub2 = client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert pub2.status_code == 200
    assert "Even bolder" in client.get("/").text
    # rollback to v1 restores content and republishes
    rb = client.post("/api/admin/pages-rollback", json={"id": v1},
                     headers={"X-CSRF": me["csrf"]})
    assert rb.status_code == 200, rb.text
    assert "Bold experiences" in client.get("/").text
    editor = client.get("/api/admin/pages/index").json()
    fields = {f["key"]: f for f in editor["regions"]}
    assert fields["hero.title1"]["value"] == "Bold experiences"
    actions = {e["action"] for e in aa.audit_list(limit=15)}
    assert "site.published" in actions and "site.rolledback" in actions


def test_global_header_footer_bake_applies_everywhere():
    me = client.get("/api/admin/me").json()
    ok = client.post("/api/admin/pages/_global",
                     json={"lang": "en", "values": {"footer.email": "hello@elitemarcom.com"}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    # the menu is a managed list now, not eight fixed keys — renaming a link is
    # an edit to the Header list and it has to reach every page
    from server import collections as co

    about_link = [i for i in co.items("header-nav") if i["values"]["link"] == "/about.html"][0]
    renamed = client.post("/api/admin/collections/header-nav/items/" + about_link["id"],
                          headers={"X-CSRF": me["csrf"]},
                          json={"values": dict(about_link["values"], label="Our Story")})
    assert renamed.status_code == 200, renamed.text
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    about = client.get("/about.html").text
    assert ">Our Story</a>" in about
    assert 'href="mailto:hello@elitemarcom.com"' in about
    assert ">hello@elitemarcom.com</a>" in about
    # and it is on a page that is not the one the list was read from
    assert ">Our Story</a>" in client.get("/services.html").text
    co.reset("header-nav", "test")
    # unknown fields are rejected
    bad = client.post("/api/admin/pages/_global",
                      json={"lang": "en", "values": {"nav.evil": "x"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400


def test_arabic_saved_as_draft_english_publishes():
    me = client.get("/api/admin/me").json()
    ok = client.post("/api/admin/pages/index",
                     json={"lang": "ar", "values": {"hero.title1": "تجارب استثنائية"}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    ar = client.get("/api/admin/pages/index?lang=ar").json()
    fields = {f["key"]: f for f in ar["regions"]}
    assert fields["hero.title1"]["value"] == "تجارب استثنائية"
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert "تجارب" not in client.get("/").text  # english publishes, arabic waits


def test_unpublish_restores_original_site():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200
    home = client.get("/").text
    assert "Bold experiences" not in home and "Experiences made" in home


def test_rentals_admin_crud_reflects_on_public_api():
    me = client.get("/api/admin/me").json()
    before = client.get("/api/admin/rentals").json()
    assert before["source"] == "default" and before["products"]
    item = {"id": "rent-test-truss", "code": "EM-R-099", "name": "Test Truss Tower 4m",
            "category": "Staging", "image": "/assets/services/led-display.webp",
            "images": ["/assets/services/led-display.webp", "https://evil.example/x.png"],
            "description": "A test item.", "tags": ["truss"], "specs": ["4 m height"],
            "featured": True, "stockByMarket": {"ksa": "12", "uae": 3}}
    res = client.post("/api/admin/rentals/save", json={"product": item},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    saved = res.json()["product"]
    assert saved["stockByMarket"] == {"ksa": 12, "uae": 3}
    assert saved["images"] == ["/assets/services/led-display.webp"]  # external URL dropped
    pub = client.get("/api/rentals/products").json()["products"]
    assert any(p["id"] == "rent-test-truss" for p in pub)
    assert client.get("/api/admin/rentals").json()["source"] == "custom"
    # bad id rejected
    bad = client.post("/api/admin/rentals/save",
                      json={"product": {**item, "id": "Bad ID!"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    # delete + reset to shipped list
    ok = client.post("/api/admin/rentals/delete", json={"id": "rent-test-truss"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert not any(p["id"] == "rent-test-truss"
                   for p in client.get("/api/rentals/products").json()["products"])
    client.post("/api/admin/rentals/reset", headers={"X-CSRF": me["csrf"]})
    assert client.get("/api/admin/rentals").json()["source"] == "default"
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "rental.saved" in actions and "rental.deleted" in actions


def test_pages_and_rentals_permissions():
    sales = TestClient(app)
    sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales.get("/api/admin/pages").status_code == 403
    assert sales.get("/api/admin/rentals").status_code == 403
    editor = TestClient(app)
    sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.get("/api/admin/pages").status_code == 200   # content.edit
    assert editor.get("/api/admin/rentals").status_code == 403  # no rentals.manage


# ---------------- Phase 4: visual editor ----------------

def test_visual_editor_page_injects_bridge_and_is_frameable():
    res = client.get("/admin/visual/index")
    assert res.status_code == 200
    assert "editor-bridge.js" in res.text
    assert 'data-em="hero.title1"' in res.text
    # drafts appear in the visual preview too
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.eyebrow": "Visual test eyebrow"}},
                headers={"X-CSRF": me["csrf"]})
    assert "Visual test eyebrow" in client.get("/admin/visual/index").text
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.eyebrow": ""}},
                headers={"X-CSRF": me["csrf"]})
    # the ONE frameable page: same-origin only, still CSP-protected
    csp = res.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp
    assert res.headers["x-frame-options"] == "SAMEORIGIN"
    # everything else stays unframeable, including the plain preview
    prev = client.get("/admin/preview/index")
    assert "frame-ancestors 'none'" in prev.headers["content-security-policy"]
    assert prev.headers["x-frame-options"] == "DENY"
    assert "editor-bridge" not in prev.text
    # public pages never carry the bridge
    assert "editor-bridge" not in client.get("/index.html").text
    assert client.get("/admin/visual/nope").status_code == 404


def test_visual_editor_requires_content_permission():
    sales = TestClient(app)
    sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales.get("/admin/visual/index").status_code == 403
    anon = TestClient(app)
    assert anon.get("/admin/visual/index").status_code == 401


# ---------------- Visual editor v2: design overrides ----------------

def test_design_save_validate_and_bake_styles():
    me = client.get("/api/admin/me").json()
    doc = {"elements": {
        "[data-em-sec=s0]>div:nth-of-type(2)>div:nth-of-type(1)>h1:nth-of-type(1)": {
            "styles": {"base": {"font-size": "72px", "color": "#123456"},
                       "mobile": {"font-size": "40px"}},
            "anim": {"type": "blur-in", "delay": 120}},
        "header.site-header": {"styles": {"base": {"background-color": "#101418"}}}
    }}
    res = client.post("/api/admin/design/index", json={"doc": doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/visual/index").text
    assert 'id="em-design"' in baked
    assert "font-size:72px !important" in baked
    assert "@media (max-width: 640px)" in baked and "font-size:40px" in baked
    assert 'data-em-sec="s0"' in baked
    # css payload rejects unknown properties and unsafe values
    bad = client.post("/api/admin/design/index",
                      json={"doc": {"elements": {"main": {"styles": {"base": {"behavior": "url(x)"}}}}}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    bad2 = client.post("/api/admin/design/index",
                       json={"doc": {"elements": {"main": {"styles": {"base": {"color": "red;}</style><script>"}}}}}},
                       headers={"X-CSRF": me["csrf"]})
    assert bad2.status_code == 400
    bad3 = client.post("/api/admin/design/index",
                       json={"doc": {"elements": {"main"[::-1] + "<script>": {}}}},
                       headers={"X-CSRF": me["csrf"]})
    assert bad3.status_code == 400


def test_design_animation_attrs_and_media_swap_bake():
    me = client.get("/api/admin/me").json()
    from server import content as ct
    raw = (ct.config.PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
    # hero eyebrow: p inside section s0 — set new animation + image swap on about page
    doc = {"elements": {
        "[data-em-sec=s0]>div:nth-of-type(2)>div:nth-of-type(1)>p:nth-of-type(1)": {
            "anim": {"type": "slide-left", "delay": 200}}}}
    client.post("/api/admin/design/index", json={"doc": doc}, headers={"X-CSRF": me["csrf"]})
    baked = client.get("/admin/visual/index").text
    assert 'data-reveal="slide-left"' in baked
    assert 'data-reveal-delay="200"' in baked
    # the original fade-up on that element is gone (no double animation)
    import re as _re
    eyebrow = _re.search(r'<p class="eyebrow reveal[^>]*data-em="hero.eyebrow"[^>]*>', baked)
    assert eyebrow and "fade-up" not in eyebrow.group(0)
    # img swap on about page hero figure
    about_doc = {"elements": {
        "[data-em-sec=s0]>div:nth-of-type(2)>div:nth-of-type(1)>figure:nth-of-type(1)>div:nth-of-type(1)>img:nth-of-type(1)": {
            "attrs": {"src": "/media/0123456789abcdef.webp", "alt": "Team at work"}}}}
    res = client.post("/api/admin/design/about", json={"doc": about_doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    about = client.get("/admin/visual/about").text
    assert 'src="/media/0123456789abcdef.webp"' in about
    assert 'alt="Team at work"' in about
    # external src rejected
    bad = client.post("/api/admin/design/about",
                      json={"doc": {"elements": {"main": {"attrs": {"src": "https://evil.example/x.png"}}}}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400


def test_design_sections_reorder_hide_duplicate():
    me = client.get("/api/admin/me").json()
    baked0 = client.get("/admin/visual/services").text
    import re as _re
    ids0 = _re.findall(r'data-em-sec="(s\d+)"', baked0)
    assert ids0 == ["s0", "s1", "s2"]
    doc = {"sections": {"order": ["s0", "s2", "s1"], "removed": ["s1"], "duplicated": ["s2"]},
           "elements": {}}
    res = client.post("/api/admin/design/services", json={"doc": doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/visual/services").text
    ids = _re.findall(r'data-em-sec="(s\d+)"', baked)
    assert ids == ["s0", "s2"]  # s1 hidden; duplicate carries no data-em-sec
    assert baked.count('id="model-h"') == 0            # s1 really is off the page
    assert baked.count('id="sprocess-h"') == 1         # s2 kept its ids
    assert baked.count("Bring us the objective") == 2  # s2 plus its duplicate
    # hiding a section must not take the content that merely sat after it —
    # the ten service cards live in a <div> between s1 and s2
    assert baked.count('class="sc-card ') == 10
    # clear
    client.post("/api/admin/design/services", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})
    restored = client.get("/admin/visual/services").text
    assert _re.findall(r'data-em-sec="(s\d+)"', restored) == ["s0", "s1", "s2"]
    assert restored.count('class="sc-card ') == 10


def test_design_global_scope_restricted_and_hidden_ranges():
    me = client.get("/api/admin/me").json()
    ok = client.post("/api/admin/design/_global",
                     json={"doc": {"elements": {"footer.site-footer": {
                         "hidden": {"mobile": True},
                         "styles": {"base": {"padding": "40px 0"}}}}}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    baked = client.get("/admin/visual/contact").text  # global applies everywhere
    assert "@media (max-width: 640px)" in baked
    assert "footer.site-footer{display:none !important;}" in baked
    bad = client.post("/api/admin/design/_global",
                      json={"doc": {"elements": {"main": {"styles": {"base": {"color": "#fff000"}}}}}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400  # global may only touch header/footer
    client.post("/api/admin/design/_global", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})


def test_design_publish_rollback_and_rich_text():
    me = client.get("/api/admin/me").json()
    # publish with a design + rich text
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.lead": "We make <strong>bold</strong> work<br>worldwide. <script>alert(1)</script>"}},
                headers={"X-CSRF": me["csrf"]})
    pub = client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert pub.status_code == 200
    v_design = pub.json()["id"]
    home = client.get("/").text
    assert "<strong>bold</strong>" in home and "<br>worldwide" in home
    assert "<script>alert(1)</script>" not in home and "alert(1)" in home  # tag stripped, text kept
    assert 'data-reveal="slide-left"' in home  # published design layer
    # remove design + publish, then roll back — design returns
    client.post("/api/admin/design/index", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert 'data-reveal="slide-left"' not in client.get("/").text
    rb = client.post("/api/admin/pages-rollback", json={"id": v_design},
                     headers={"X-CSRF": me["csrf"]})
    assert rb.status_code == 200
    assert 'data-reveal="slide-left"' in client.get("/").text
    # cleanup: unpublish + clear docs
    client.post("/api/admin/design/index", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/design/about", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages/index", json={"lang": "en", "values": {"hero.lead": ""}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


# ---------------- Phase 7: free-form editing, blocks, pages, social ----------------

# the third card's <dt> on About — a plain heading with no data-em key, which
# is exactly the kind of text the editor could not reach before
_CARD_TITLE = ("[data-em-sec=s3]>div:nth-of-type(1)>dl:nth-of-type(1)"
               ">div:nth-of-type(3)>dt:nth-of-type(1)")


def test_untagged_element_text_is_editable_by_path():
    me = client.get("/api/admin/me").json()
    before = client.get("/admin/preview/about").text
    assert "<dt>Personal service</dt>" in before
    res = client.post("/api/admin/design/about",
                      json={"doc": {"elements": {_CARD_TITLE: {
                          "text": "Personal <strong>service</strong>, always"}}}},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/preview/about").text
    assert "<dt>Personal <strong>service</strong>, always</dt>" in baked
    assert "<dt>Personal service</dt>" not in baked
    # the surrounding cards are untouched
    assert "<dt>Excellence</dt>" in baked and "<dt>Creativity</dt>" in baked
    # markup outside the small rich-text whitelist never survives
    evil = client.post("/api/admin/design/about",
                       json={"doc": {"elements": {_CARD_TITLE: {
                           "text": "Ok<script>alert(1)</script><img src=x onerror=y>"}}}},
                       headers={"X-CSRF": me["csrf"]})
    assert evil.status_code == 200
    baked = client.get("/admin/preview/about").text
    assert "<script>" not in baked.split('class="values-grid"')[1][:400]
    assert "onerror" not in baked
    client.post("/api/admin/design/about", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})


def test_text_override_on_a_container_wins_over_one_inside_it():
    """Both edits are legal on their own; applying both would splice the inner
    replacement into offsets the outer one has already moved."""
    from server import design

    raw = "<main><section><div><p>inner</p></div></section></main>"
    out = design._apply_text_ops(raw, {
        "main>section:nth-of-type(1)>div:nth-of-type(1)": {"text": "OUTER"},
        "main>section:nth-of-type(1)>div:nth-of-type(1)>p:nth-of-type(1)": {"text": "INNER"},
    })
    assert out == "<main><section><div>OUTER</div></section></main>"


def test_baking_never_drops_what_sits_between_two_sections():
    """<main> holds more than <section>s — a marquee band, a request drawer, the
    services grid. The bake replaces main's whole inner span, so anything it
    fails to emit is deleted from the published page. This is exactly how the
    services page published as an empty gap."""
    from server import design

    raw = ("<html><head></head><body><main>"
           "<section class='a'>A</section>"
           "<div class='marquee'>MARQUEE-KEPT</div>"
           "<section class='b'>B</section>"
           "<div class='services'>SERVICES-KEPT</div>"
           "<section class='c'>C</section>"
           "</main></body></html>")
    out = design._apply_sections(raw, {})
    assert "MARQUEE-KEPT" in out and "SERVICES-KEPT" in out
    assert out.count("<section") == 3
    # and it stays where it was, between the sections it was written between
    assert out.index("MARQUEE-KEPT") < out.index("class='b'") < out.index("SERVICES-KEPT")

    # taking a section off the page must not delete the content that sat after it
    hidden = design._apply_sections(raw, {"removed": ["s1"]})
    assert "class='b'" not in hidden
    assert "MARQUEE-KEPT" in hidden and "SERVICES-KEPT" in hidden

    # reordering carries each stray child with the section it follows
    flipped = design._apply_sections(raw, {"order": ["s2", "s1", "s0"]})
    assert flipped.index("SERVICES-KEPT") < flipped.index("MARQUEE-KEPT")
    assert "MARQUEE-KEPT" in flipped and "SERVICES-KEPT" in flipped


def test_every_shipped_page_survives_a_bake():
    """A publish must not quietly lose an element from any page in the repo."""
    import pathlib as _p
    import re as _re

    from server import design

    for path in sorted(_p.Path("public").glob("*.html")):
        raw = path.read_text(encoding="utf-8")
        out = design._apply_sections(raw, {})
        before = len(_re.findall(r"<[a-zA-Z][^>]*>", raw))
        after = len(_re.findall(r"<[a-zA-Z][^>]*>", out))
        assert after == before, f"{path.name}: bake dropped {before - after} elements"


def test_section_blocks_add_reorder_hide_and_delete():
    me = client.get("/api/admin/me").json()
    lib = client.get("/api/admin/blocks")
    assert lib.status_code == 200
    ids = {b["id"] for b in lib.json()["blocks"]}
    assert {"cta", "cards-3", "quote"} <= ids
    assert all("__ID__" in b["html"] for b in lib.json()["blocks"])

    doc = {"sections": {"added": [{"id": "a1", "template": "cta"},
                                  {"id": "a2", "template": "quote"}],
                        "order": ["a1", "s0", "s1", "s2", "a2"]}}
    res = client.post("/api/admin/design/careers", json={"doc": doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/preview/careers").text
    assert 'data-em-sec="a1"' in baked and 'data-em-block="cta"' in baked
    assert "Ready to talk about your project?" in baked
    assert baked.index('data-em-sec="a1"') < baked.index('data-em-sec="s0"')
    assert baked.index('data-em-sec="s2"') < baked.index('data-em-sec="a2"')

    # text inside an added block is editable like any other element
    heading = "[data-em-sec=a1]>div:nth-of-type(1)>h2:nth-of-type(1)"
    doc["elements"] = {heading: {"text": "Let us build yours"}}
    client.post("/api/admin/design/careers", json={"doc": doc}, headers={"X-CSRF": me["csrf"]})
    baked = client.get("/admin/preview/careers").text
    assert "Let us build yours" in baked and "Ready to talk about your project?" not in baked

    # hiding an added block keeps it out of the page and lists it as hidden
    doc["sections"]["removed"] = ["a2"]
    client.post("/api/admin/design/careers", json={"doc": doc}, headers={"X-CSRF": me["csrf"]})
    baked = client.get("/admin/preview/careers").text
    assert 'data-em-sec="a2"' not in baked and 'data-em-sec="a1"' in baked
    hidden = client.get("/api/admin/design-hidden").json()["hidden"]
    assert any(h["page"] == "careers" and h["path"] == "a2" for h in hidden)

    # unknown block ids and malformed section ids are refused
    for bad_doc in ({"sections": {"added": [{"id": "a1", "template": "../../etc/passwd"}]}},
                    {"sections": {"added": [{"id": "s1", "template": "cta"}]}},
                    {"sections": {"added": [{"id": "a1", "template": "cta"},
                                            {"id": "a1", "template": "quote"}]}}):
        bad = client.post("/api/admin/design/careers", json={"doc": bad_doc},
                          headers={"X-CSRF": me["csrf"]})
        assert bad.status_code == 400, bad_doc

    client.post("/api/admin/design/careers", json={"doc": {"elements": {}}},
                headers={"X-CSRF": me["csrf"]})
    assert 'data-em-sec="a1"' not in client.get("/admin/preview/careers").text


def test_custom_page_create_edit_publish_and_delete():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/pages-new",
                      json={"slug": "our-team", "label": "Our team",
                            "title": "Our team — Elite Marcom",
                            "description": "The people behind the work.", "nav": True},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    assert res.json()["page"]["slug"] == "our-team"

    listing = {p["page"]: p for p in client.get("/api/admin/pages").json()["pages"]}
    assert listing["our-team"]["custom"] is True and listing["our-team"]["nav"] is True
    assert listing["index"]["custom"] is False

    # it edits like any other page: keyed hero regions, SEO and the design layer
    editor = client.get("/api/admin/pages/our-team").json()
    assert {f["key"] for f in editor["regions"]} == {"hero.eyebrow", "hero.title1", "hero.lead"}
    assert client.get("/admin/visual/our-team").status_code == 200
    client.post("/api/admin/pages/our-team",
                json={"lang": "en", "values": {"hero.title1": "The people behind it"}},
                headers={"X-CSRF": me["csrf"]})
    preview = client.get("/admin/preview/our-team")
    assert preview.status_code == 200
    assert "The people behind it" in preview.text
    assert '<link rel="canonical" href="https://www.elitemarcom.com/our-team.html">' in preview.text
    assert '<footer class="site-footer">' in preview.text  # same shell as the rest of the site

    # not on the public site until it is published
    assert client.get("/our-team.html").status_code == 404
    pub = client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert pub.status_code == 200
    live = client.get("/our-team.html")
    assert live.status_code == 200 and "The people behind it" in live.text
    # and it is linked from the menus of every other page, plus the sitemap
    assert '<li><a href="/our-team.html">Our team</a></li>' in client.get("/about.html").text
    assert "/our-team.html" in client.get("/sitemap.xml").text

    # taking it out of the menus leaves the page reachable by address
    client.post("/api/admin/pages-meta/our-team", json={"nav": False},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert "/our-team.html" not in client.get("/about.html").text
    assert client.get("/our-team.html").status_code == 200

    # reserved and malformed addresses are refused, as are duplicates
    for slug in ("our-team", "admin", "about", "Our Team", "a", "x" * 60):
        bad = client.post("/api/admin/pages-new", json={"slug": slug, "label": "X"},
                          headers={"X-CSRF": me["csrf"]})
        assert bad.status_code in (400, 422), slug
    # built-in pages cannot be deleted
    assert client.post("/api/admin/pages-delete/about",
                       headers={"X-CSRF": me["csrf"]}).status_code == 400

    gone = client.post("/api/admin/pages-delete/our-team", headers={"X-CSRF": me["csrf"]})
    assert gone.status_code == 200
    assert client.get("/our-team.html").status_code == 404
    assert "our-team" not in {p["page"] for p in client.get("/api/admin/pages").json()["pages"]}
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


def test_youtube_icon_draws_an_outlined_body_and_a_filled_play_triangle():
    """The body and the triangle are separate shapes on purpose. As one path
    the triangle was a subpath that needed an even-odd fill rule to punch
    through, and without it the icon rendered as a solid rounded rectangle."""
    from server import blocks

    markup = blocks.render_social({"youtube": "https://www.youtube.com/@elitemarcom"})
    assert '<rect x="2.5" y="5.5" width="19" height="13" rx="4"' in markup
    assert 'fill="none" stroke="currentColor"' in markup      # body is outlined…
    assert '<path d="M10 9l6 3-6 3V9Z" fill="currentColor"/>' in markup  # …triangle filled
    # both shapes take their colour from the icon's own, so hover still works
    assert "#" not in markup.split("<svg")[1]
    for other in ("instagram", "linkedin", "facebook", "x"):
        assert blocks._ICONS[other], other


def test_social_links_render_in_the_footer_of_every_page():
    me = client.get("/api/admin/me").json()
    assert "site-social" not in client.get("/admin/preview/about").text
    ok = client.post("/api/admin/settings",
                     json={"values": {"social.instagram": "https://www.instagram.com/elitemarcom",
                                      "social.linkedin": "https://www.linkedin.com/company/elitemarcom",
                                      "social.facebook": ""}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    baked = client.get("/admin/preview/about").text
    assert '<nav class="site-social"' in baked
    assert baked.count("<svg viewBox=\"0 0 24 24\" fill=\"currentColor\"") == 2
    assert 'href="https://www.instagram.com/elitemarcom"' in baked
    assert 'aria-label="LinkedIn"' in baked
    assert 'rel="me noopener"' in baked
    # an empty field means no icon at all, not a dead link
    assert 'aria-label="Facebook"' not in baked
    # the icons sit in the footer, above the copyright line
    assert baked.index('class="site-social"') < baked.index('class="site-footer__meta"')

    for value in ("javascript:alert(1)", "http://insecure.example/x", "not a url",
                  "https://x.com/\" onmouseover=alert(1)"):
        bad = client.post("/api/admin/settings", json={"values": {"social.x": value}},
                          headers={"X-CSRF": me["csrf"]})
        assert bad.status_code == 400, value
    for key in ("social.instagram", "social.linkedin"):
        client.post("/api/admin/settings", json={"values": {key: ""}},
                    headers={"X-CSRF": me["csrf"]})
    assert "site-social" not in client.get("/admin/preview/about").text


# ---------------- Phase 5: site insights ----------------

def test_insights_config_public_and_beacon_collects():
    cfg = client.get("/api/site/insights-config")
    assert cfg.status_code == 200
    assert cfg.json()["enabled"] is True
    assert cfg.json()["ga4Id"] == ""

    batch = {"events": [
        {"kind": "pageview", "path": "/", "referrer": "https://google.com/search?q=x",
         "session": "sess-aaa"},
        {"kind": "pageview", "path": "/giveaways.html", "session": "sess-aaa"},
        {"kind": "product_view", "path": "/product.html", "session": "sess-aaa",
         "meta": "A5 Eco Notebook"},
        {"kind": "catalog_search", "path": "/giveaways.html", "session": "sess-aaa",
         "meta": "gifts: notebook"},
        {"kind": "add_to_request", "path": "/product.html", "session": "sess-aaa",
         "meta": "A5 Eco Notebook"},
        {"kind": "vital", "metric": "LCP", "value": 2100.5, "path": "/"},
        {"kind": "vital", "metric": "CLS", "value": 0.04, "path": "/"},
        {"kind": "nonsense", "path": "/"},
        {"kind": "vital", "metric": "FAKE", "value": 1, "path": "/"},
    ]}
    res = client.post("/api/insights/collect", json=batch)
    assert res.status_code == 200
    assert res.json()["stored"] == 7  # the two invalid entries are dropped

    # a second visitor from another session
    client.post("/api/insights/collect", json={"events": [
        {"kind": "pageview", "path": "/", "session": "sess-bbb"},
        {"kind": "pageview", "path": "/contact.html", "session": "sess-bbb"},
    ]})
    # unknown fields are refused outright
    assert client.post("/api/insights/collect",
                       json={"events": [{"kind": "pageview", "evil": 1}]}).status_code == 422


def test_insights_stores_no_raw_ip_or_user_agent():
    from server import analytics

    rows = analytics._rows("SELECT * FROM events LIMIT 50")
    blob = json.dumps(rows)
    assert "testclient" not in blob.lower()        # no user-agent
    assert "127.0.0.1" not in blob and "testserver" not in blob  # no raw IP
    assert all(len(r["visitor"]) == 20 for r in rows)
    # the visitor key changes every day, so nobody is trackable across days
    today = analytics.visitor_hash("1.2.3.4", "UA", "2026-08-12")
    tomorrow = analytics.visitor_hash("1.2.3.4", "UA", "2026-08-13")
    assert today != tomorrow and len(today) == 20
    assert analytics.referrer_host("https://www.google.com/x") == "google.com"
    assert analytics.referrer_host("http://127.0.0.1:8847/page") == ""  # own site is not a referrer
    assert analytics.clean_path("javascript:alert(1)") == ""
    assert analytics.device_class("iPhone Mobile Safari") == "mobile"


def test_insights_summary_reports_traffic_and_funnel():
    res = client.get("/api/admin/insights?days=30")
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["totals"]["views"] == 4
    assert d["totals"]["visitors"] == 1     # same test client = one daily visitor key
    assert d["totals"]["sessions"] == 2
    assert len(d["series"]) == 30 and d["series"][-1]["views"] == 4
    labels = {p["label"] for p in d["topPages"]}
    assert "/" in labels and "/giveaways.html" in labels
    assert d["referrers"][0]["label"] == "google.com"
    assert d["devices"] and d["devices"][0]["count"] >= 1
    assert d["entryPages"] and d["exitPages"]
    assert d["products"][0]["label"] == "A5 Eco Notebook"
    assert d["searches"][0]["label"] == "gifts: notebook"
    steps = {f["step"]: f["count"] for f in d["funnel"]}
    assert steps["Product views"] == 1 and steps["Added to request"] == 1
    assert {v["metric"] for v in d["vitals"]} == {"LCP", "CLS"}
    assert d["settings"]["enabled"] is True


def test_enquiry_records_a_server_side_conversion():
    before = client.get("/api/admin/insights?days=7").json()["funnel"][2]["count"]
    challenge = client.get("/api/security/challenge?form=contact").json()["challenge"]
    res = client.post("/api/contact/enquiries", json={
        "enquiryType": "New project", "fullName": "Insights Tester",
        "company": "Test Co", "email": "insights@example.com", "phone": "+966500000000",
        "market": "Saudi Arabia", "service": "Branding",
        "message": "Please send a proposal for our stand.", "consent": True,
        "challenge": challenge, "consentVersion": "2026-01", "sourcePage": "/contact.html"},
        headers={"Origin": "http://127.0.0.1:8847"})
    assert res.status_code == 200, res.text
    after = client.get("/api/admin/insights?days=7").json()
    assert after["funnel"][2]["count"] == before + 1
    assert after["funnel"][2]["rate"] >= 0


def test_insights_permissions_and_settings_validation():
    me = client.get("/api/admin/me").json()
    # analyst may read insights; sales may not
    client.post("/api/admin/users",
                json={"email": "analyst@elitemarcom.com", "name": "Data Analyst",
                      "password": "analyst-long-pass", "role": "analyst"},
                headers={"X-CSRF": me["csrf"]})
    analyst = TestClient(app)
    analyst_me = sign_in(analyst, "analyst@elitemarcom.com", "analyst-long-pass")
    assert analyst.get("/api/admin/insights").status_code == 200
    assert analyst.get("/api/admin/insights").json()["canManage"] is False
    assert analyst.get("/api/admin/insights/export?days=7").status_code == 200
    assert "insights.view" in analyst_me["permissions"]
    sales = TestClient(app)
    sign_in(sales, "sales@elitemarcom.com", "another-long-pass")
    assert sales.get("/api/admin/insights").status_code == 403

    # settings: GA4 id shape enforced, retention clamped, bool kept a bool
    bad = client.post("/api/admin/settings", json={"values": {"analytics.ga4Id": "UA-123"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    ok = client.post("/api/admin/settings",
                     json={"values": {"analytics.ga4Id": "G-ABCD123456",
                                      "analytics.retentionDays": 5,
                                      "analytics.enabled": True}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert aa.setting_get("analytics.retentionDays") == 30  # clamped up from 5
    assert client.get("/api/site/insights-config").json()["ga4Id"] == "G-ABCD123456"
    bad_type = client.post("/api/admin/settings", json={"values": {"analytics.enabled": "yes"}},
                           headers={"X-CSRF": me["csrf"]})
    assert bad_type.status_code == 400


def test_insights_can_be_switched_off_completely():
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/settings", json={"values": {"analytics.enabled": False}},
                headers={"X-CSRF": me["csrf"]})
    assert client.get("/api/site/insights-config").json()["enabled"] is False
    res = client.post("/api/insights/collect",
                      json={"events": [{"kind": "pageview", "path": "/", "session": "off"}]})
    assert res.status_code == 200 and res.json()["stored"] == 0
    client.post("/api/admin/settings", json={"values": {"analytics.enabled": True,
                                                        "analytics.ga4Id": ""}},
                headers={"X-CSRF": me["csrf"]})


def test_insights_retention_prune():
    from server import analytics

    with analytics._lock:
        conn = analytics._connect()
        conn.execute("INSERT INTO events (ts, day, kind, path) VALUES (?,?,?,?)",
                     (1, "2020-01-01", "pageview", "/old"))
        conn.commit()
    assert analytics.prune(30) == 1
    assert not any(r["path"] == "/old" for r in analytics._rows("SELECT path FROM events"))


def test_insights_custom_date_range_and_reports():
    from server import analytics

    # explicit range wins over the rolling window and is echoed back
    res = client.get("/api/admin/insights?start=2026-01-01&end=2026-01-31")
    assert res.status_code == 200
    d = res.json()
    assert d["start"] == "2026-01-01" and d["end"] == "2026-01-31" and d["days"] == 31
    assert len(d["series"]) == 31 and d["totals"]["views"] == 0  # no traffic back then
    # reversed dates are corrected, junk falls back to the rolling window
    assert analytics.parse_range("2026-02-10", "2026-02-01")[0] == "2026-02-01"
    assert analytics.parse_range("not-a-date", "x", 14)[2] == 14
    # today's traffic still shows through an explicit range
    today = analytics._today()
    live = client.get(f"/api/admin/insights?start={today}&end={today}").json()
    assert live["totals"]["views"] >= 1

    # branded PDF, standalone HTML and CSV all cover the same window
    pdf = client.get(f"/api/admin/insights/export?format=pdf&start={today}&end={today}")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-") and len(pdf.content) > 3000
    assert "insights" in pdf.headers["content-disposition"]

    html = client.get(f"/api/admin/insights/export?format=html&start={today}&end={today}")
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    body = html.text
    assert body.startswith("<!DOCTYPE html>") and "Site Insights" in body
    assert "<script" not in body.lower()          # a report is data, never code
    assert "http://" not in body.split("</head>")[0]  # fully self-contained styling
    assert today in body

    csv_res = client.get(f"/api/admin/insights/export?format=csv&start={today}&end={today}")
    assert csv_res.status_code == 200
    assert "Date,Pageviews,Visitors" in csv_res.content.decode("utf-8-sig")
    assert client.get("/api/admin/insights/export?format=exe").status_code == 400

    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "insights.exported" in actions


# ---------------- Phase 6: backups, schedule, announcements, Arabic ----------------

def test_backup_download_inspect_and_restore():
    import io as _io
    import zipfile as _zip

    me = client.get("/api/admin/me").json()
    # put something distinctive in the panel first
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.title1": "Backup marker"}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-new",
                json={"slug": "backup-page", "label": "Backup page", "nav": False},
                headers={"X-CSRF": me["csrf"]})
    res = client.get("/api/admin/backup")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    blob = res.content
    with _zip.ZipFile(_io.BytesIO(blob)) as z:
        names = z.namelist()
        assert "manifest.json" in names and "data.json" in names
        data = json.loads(z.read("data.json"))
    assert any(r["key"] == "hero.title1" and r["value"] == "Backup marker"
               for r in data["content"])
    # a page created in the panel is part of the panel's data, not the code
    assert any(r["slug"] == "backup-page" for r in data["customPages"])
    # customer submissions must never travel in an operational backup
    dump = blob.decode("latin-1")
    assert "Amira Hassan" not in dump and "falconevents" not in dump

    # change content, then restore the backup and watch it come back
    client.post("/api/admin/pages/index",
                json={"lang": "en", "values": {"hero.title1": "Changed after backup"}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-delete/backup-page", headers={"X-CSRF": me["csrf"]})
    fields = {f["key"]: f for f in client.get("/api/admin/pages/index").json()["regions"]}
    assert fields["hero.title1"]["value"] == "Changed after backup"
    assert "backup-page" not in {p["page"] for p in client.get("/api/admin/pages").json()["pages"]}

    inspect = client.post("/api/admin/backup/inspect",
                          files={"file": ("b.zip", blob, "application/zip")},
                          headers={"X-CSRF": me["csrf"]})
    assert inspect.status_code == 200 and inspect.json()["counts"]["content"] >= 1

    no_confirm = client.post("/api/admin/backup/restore",
                             files={"file": ("b.zip", blob, "application/zip")},
                             data={"confirm": "yes"}, headers={"X-CSRF": me["csrf"]})
    assert no_confirm.status_code == 400

    ok = client.post("/api/admin/backup/restore",
                     files={"file": ("b.zip", blob, "application/zip")},
                     data={"confirm": "RESTORE"}, headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    fields = {f["key"]: f for f in client.get("/api/admin/pages/index").json()["regions"]}
    assert fields["hero.title1"]["value"] == "Backup marker"
    assert "backup-page" in {p["page"] for p in client.get("/api/admin/pages").json()["pages"]}
    client.post("/api/admin/pages-delete/backup-page", headers={"X-CSRF": me["csrf"]})

    junk = client.post("/api/admin/backup/restore",
                       files={"file": ("x.zip", b"not a zip at all", "application/zip")},
                       data={"confirm": "RESTORE"}, headers={"X-CSRF": me["csrf"]})
    assert junk.status_code == 400
    actions = {e["action"] for e in aa.audit_list(limit=12)}
    assert "backup.downloaded" in actions and "backup.restored" in actions


def test_scheduled_publish_runs_when_due():
    from server import backup, content

    me = client.get("/api/admin/me").json()
    future = int(time.time()) + 3600
    res = client.post("/api/admin/schedule-publish", json={"at": future},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200 and res.json()["at"] == future
    assert client.get("/api/admin/operations").json()["schedule"]["at"] == future
    assert backup.run_due_publish() is None       # not due yet, nothing published
    past = client.post("/api/admin/schedule-publish", json={"at": int(time.time()) - 600},
                       headers={"X-CSRF": me["csrf"]})
    assert past.status_code == 400                 # the past is refused up front
    aa.setting_set("publish.scheduledAt", int(time.time()) - 5)   # simulate the moment arriving
    result = backup.run_due_publish()
    assert result and result["pages"] >= 11
    assert "Backup marker" in client.get("/").text
    assert backup.get_schedule()["at"] == 0        # fires once, then clears
    actions = {e["action"] for e in aa.audit_list(limit=8)}
    assert "site.published_scheduled" in actions
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


def test_announcement_bar_schedule_window():
    me = client.get("/api/admin/me").json()
    assert client.get("/api/site/announcement").json()["show"] is False
    ok = client.post("/api/admin/settings", json={"values": {
        "announce.enabled": True, "announce.text": "Visit us at Cityscape, stand B21",
        "announce.link": "/contact.html", "announce.linkLabel": "Book a meeting",
        "announce.style": "brand"}}, headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    live = client.get("/api/site/announcement").json()
    assert live["show"] is True and "Cityscape" in live["text"] and live["id"]
    # a future window hides it again
    client.post("/api/admin/settings",
                json={"values": {"announce.startsAt": int(time.time()) + 86400}},
                headers={"X-CSRF": me["csrf"]})
    assert client.get("/api/site/announcement").json()["show"] is False
    client.post("/api/admin/settings", json={"values": {"announce.startsAt": 0,
                                                        "announce.endsAt": int(time.time()) - 10}},
                headers={"X-CSRF": me["csrf"]})
    assert client.get("/api/site/announcement").json()["show"] is False
    # off-site links are refused
    bad = client.post("/api/admin/settings",
                      json={"values": {"announce.link": "javascript:alert(1)"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    client.post("/api/admin/settings", json={"values": {"announce.enabled": False,
                                                        "announce.endsAt": 0}},
                headers={"X-CSRF": me["csrf"]})


def test_arabic_edition_publishes_rtl_pages():
    me = client.get("/api/admin/me").json()
    client.post("/api/admin/pages/index",
                json={"lang": "ar", "values": {"hero.title1": "تجارب استثنائية"}},
                headers={"X-CSRF": me["csrf"]})
    # English only: no Arabic edition, no switch
    client.post("/api/admin/settings", json={"values": {"site.languages": ["en"]}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert client.get("/ar/index.html").status_code == 404
    assert "lang-switch" not in client.get("/").text

    # switch Arabic on and publish
    client.post("/api/admin/settings", json={"values": {"site.languages": ["en", "ar"]}},
                headers={"X-CSRF": me["csrf"]})
    pub = client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert pub.status_code == 200 and pub.json()["pages"] >= 22   # both editions
    ar = client.get("/ar/index.html")
    assert ar.status_code == 200
    assert 'lang="ar"' in ar.text and 'dir="rtl"' in ar.text
    assert "تجارب استثنائية" in ar.text
    assert 'href="/ar/about.html"' in ar.text        # navigation stays in the Arabic edition
    assert 'hreflang="en"' in ar.text                # switch back to English
    assert client.get("/ar/").status_code == 200
    english = client.get("/").text
    assert 'lang="en"' in english and 'hreflang="ar"' in english
    assert "تجارب" not in english
    sitemap = client.get("/sitemap.xml").text
    assert "/ar/about.html" in sitemap
    # turning Arabic off removes the edition on the next publish
    client.post("/api/admin/settings", json={"values": {"site.languages": ["en"]}},
                headers={"X-CSRF": me["csrf"]})
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    assert client.get("/ar/index.html").status_code == 404
    client.post("/api/admin/pages-unpublish", headers={"X-CSRF": me["csrf"]})


def test_security_centre_and_operations_permissions():
    res = client.get("/api/admin/operations")
    assert res.status_code == 200
    d = res.json()
    labels = {c["label"] for c in d["checks"]}
    assert {"HTTPS origin", "Bot protection", "Activity log integrity"} <= labels
    gates = [c for c in d["checks"] if c["weight"] != "info"]
    assert d["total"] == len(gates) and 0 <= d["score"] <= d["total"]
    assert d["advisories"] == sum(1 for c in d["checks"] if c["weight"] == "info" and not c["ok"])
    assert next(c for c in d["checks"] if c["label"] == "Activity log integrity")["ok"] is True
    assert d["users"]["owners"] >= 1 and d["sessions"] >= 1
    # no secret value is ever echoed
    blob = json.dumps(d)
    assert "JASANI" not in blob.upper() or "token is configured" in blob
    for secret in (aa.config.EM_DATA_KEY, aa.config.EM_ADMIN_SESSION_SECRET):
        assert secret not in blob
    # only settings managers may see it
    editor = TestClient(app)
    sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.get("/api/admin/operations").status_code == 403
    assert editor.get("/api/admin/backup").status_code == 403


# ---------------- Email settings in the admin panel ----------------

def test_hidden_index_lists_everything_switched_off_and_restores_it():
    """Hiding lives per element, per breakpoint, deep in the editor's
    inspector. Without one list of what is currently off, something hidden
    months ago on one page at one width is effectively lost."""
    from server import design

    me = client.get("/api/admin/me").json()
    design.set_doc("index", {
        "elements": {"[data-em-sec=s2]>div>a": {"hidden": {"mobile": True, "tablet": True}}},
        "sections": {"removed": ["s3"]},
    }, "owner@elitemarcom.com")

    listed = client.get("/api/admin/design-hidden")
    assert listed.status_code == 200
    rows = listed.json()["hidden"]
    element = next(r for r in rows if r["kind"] == "element")
    section = next(r for r in rows if r["kind"] == "section")
    assert element["page"] == "index"
    assert element["breakpoints"] == ["tablet", "mobile"]      # only where it is off
    assert section["path"] == "s3"

    # putting it back is one call, and needs the same permission plus CSRF
    assert client.post("/api/admin/design-hidden/restore",
                       json={"page": "index", "kind": "element",
                             "path": "[data-em-sec=s2]>div>a"}).status_code == 403
    ok = client.post("/api/admin/design-hidden/restore",
                     json={"page": "index", "kind": "element",
                           "path": "[data-em-sec=s2]>div>a"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    remaining = {r["kind"] for r in ok.json()["hidden"]}
    assert "element" not in remaining and "section" in remaining
    # restoring something already visible is reported, not silently accepted
    again = client.post("/api/admin/design-hidden/restore",
                        json={"page": "index", "kind": "element",
                              "path": "[data-em-sec=s2]>div>a"},
                        headers={"X-CSRF": me["csrf"]})
    assert again.status_code == 404
    design.set_doc("index", {"elements": {}, "sections": {}}, "owner@elitemarcom.com")


def test_hero_model_size_is_admin_controlled_and_clamped():
    """Fitting the camera to the worst rotation stopped the model clipping and
    also stopped anyone making it bigger; size is the control that gives that
    back without letting a value silently reintroduce the crop everywhere."""
    from server import media

    me = client.get("/api/admin/me").json()
    lo, hi = media.HERO_RANGES["size"]
    assert lo < 1.0 < hi                       # 1.0 is the no-clip maximum

    saved = client.post("/api/admin/hero", json={"values": {"size": 1.25}},
                        headers={"X-CSRF": me["csrf"]})
    assert saved.status_code == 200
    assert media.get_hero_config()["size"] == 1.25
    assert client.get("/api/site/hero").json()["size"] == 1.25   # reaches the page

    # out of range is refused with a message, the same as the other camera
    # fields — a saved-but-ignored value is worse than a visible error
    for bad in (99, 0.01, "not a number"):
        res = client.post("/api/admin/hero", json={"values": {"size": bad}},
                          headers={"X-CSRF": me["csrf"]})
        assert res.status_code == 400, bad
        assert media.get_hero_config()["size"] == 1.25, bad   # unchanged
    # the edges of the range are accepted
    for edge in (lo, hi):
        res = client.post("/api/admin/hero", json={"values": {"size": edge}},
                          headers={"X-CSRF": me["csrf"]})
        assert res.status_code == 200 and media.get_hero_config()["size"] == edge

    brand = client.get("/api/admin/brand").json()
    assert "size" in brand["heroRanges"]
    client.post("/api/admin/hero", json={"values": {"size": 1}},
                headers={"X-CSRF": me["csrf"]})


def test_dashboard_reports_real_system_state():
    """Every dashboard figure comes from the live system — no placeholders."""
    res = client.get("/api/admin/dashboard")
    assert res.status_code == 200
    d = res.json()
    for key in ("requests", "requestTotals", "requestSeries", "statusCounts",
                "marketCounts", "supplier", "rentals", "mail", "audit"):
        assert key in d, key
    assert len(d["requestSeries"]) == 14           # one bucket per day, oldest first
    assert d["requestSeries"] == sorted(d["requestSeries"], key=lambda x: x["day"])
    # KSA and UAE are reported separately, never merged
    assert set(d["supplier"]["markets"]) == {"ksa", "uae"}
    assert set(d["marketCounts"]) == {"ksa", "uae", "other"}
    for market in ("ksa", "uae"):
        entry = d["supplier"]["markets"][market]
        assert entry["market"] == market
        assert {"products", "inStock", "fetchedAt", "stockAt",
                "nextProductsAt", "nextStockAt", "lastAttempt"} <= set(entry)
    for market in ("ksa", "uae"):
        budget = d["supplier"]["budgets"][market]
        assert {"used", "remaining", "limit", "resetInSeconds", "day",
                "utcOffset", "schedule", "nextSlot"} <= set(budget)
    # the two markets run on their own clocks and their own allowances
    assert d["supplier"]["budgets"]["ksa"]["utcOffset"] == 3
    assert d["supplier"]["budgets"]["uae"]["utcOffset"] == 4
    # the supplier token is never echoed to the browser, only a boolean
    assert set(d["supplier"]["tokensConfigured"]) == {"ksa", "uae"}
    assert "JASANI" not in json.dumps(d).upper().replace("JASANI_API_TOKEN", "")


def test_untouched_requests_count_as_new():
    """A request nobody has opened has no meta row; the inbox shows it as
    'new', so the totals must say 'new' too."""
    from server import adminauth as aa, storage as st

    before = aa.request_status_counts()
    reference = st.save_record("contact", {"fullName": "Counted", "email": "c@example.com"},
                               "iphash", 30)
    after = aa.request_status_counts()
    assert after["new"] == before["new"] + 1
    assert set(after) == set(aa.REQUEST_STATUSES)
    aa.request_meta_set(reference, "owner@elitemarcom.com", status="won")
    moved = aa.request_status_counts()
    assert moved["new"] == before["new"] and moved["won"] == before.get("won", 0) + 1


def test_market_is_stored_in_the_clear_for_reporting():
    """Market is a routing label, not personal data — it stays queryable so the
    dashboard can split KSA from UAE without decrypting anything."""
    from server import adminauth as aa, storage as st

    before = aa.request_market_counts()
    st.save_record("rental_enquiry", {"fullName": "A", "market": "ksa"}, "iphash", 30)
    st.save_record("giveaway_enquiry", {"fullName": "B", "market": "UAE"}, "iphash", 30)
    st.save_record("contact", {"fullName": "C"}, "iphash", 30)
    after = aa.request_market_counts()
    assert after["ksa"] == before["ksa"] + 1
    assert after["uae"] == before["uae"] + 1          # normalised from "UAE"
    assert after["other"] == before["other"] + 1      # no market on the form
    row = st._connect().execute(
        "SELECT market, payload FROM records ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == ""                                # plaintext column only
    assert b"fullName" not in row[1]                   # the payload is still encrypted


def test_email_settings_screen_and_permissions():
    res = client.get("/api/admin/email")
    assert res.status_code == 200
    d = res.json()
    assert {f["key"] for f in d["forms"]} == {
        "general_inquiry", "job_application", "corporate_gifts",
        "stock_notification", "rental_availability", "rental_inquiry"}
    # the two availability alerts stay separate, with their own recipients
    forms = {f["key"]: f for f in d["forms"]}
    assert forms["stock_notification"]["label"] == "Stock Notification"
    assert forms["rental_availability"]["label"] == "Rental Availability Notification"
    assert forms["rental_availability"]["recipient"] == "mohammad.hossain@elitemarcom.com"
    assert forms["stock_notification"]["customerSubject"] != \
        forms["rental_availability"]["customerSubject"]
    assert "required_from" in forms["rental_availability"]["variables"]
    assert "required_from" not in forms["stock_notification"]["variables"]
    assert isinstance(d["queued"], int)
    # queue health cards: every status the Email screen shows
    stats = d["stats"]
    assert set(stats) == {"pending", "sending", "sent", "failed", "total"}
    assert all(isinstance(v, int) for v in stats.values())
    assert stats["total"] == stats["pending"] + stats["sending"] + stats["sent"] + stats["failed"]
    assert d["general"]["fromEmail"] == "website@mail.elitemarcom.com"
    assert d["senderDomains"] == ["mail.elitemarcom.com"]
    # the provider key is never present in any shape
    blob = json.dumps(d)
    assert "re_" not in blob
    for leak in ("apiKey", "api_key", "resend", "secret"):
        assert leak.lower() not in blob.lower()
    assert isinstance(d["configured"], bool)
    # only settings managers reach it
    editor = TestClient(app)
    sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.get("/api/admin/email").status_code == 403
    assert editor.post("/api/admin/email/test", json={"to": "x@y.com"}).status_code == 403


def test_email_retry_endpoint_is_guarded_and_reports_what_it_requeued():
    me = client.get("/api/admin/me").json()
    assert client.post("/api/admin/email/retry", json={"all": True}).status_code == 403  # no CSRF
    vague = client.post("/api/admin/email/retry", json={},
                        headers={"X-CSRF": me["csrf"]})
    assert vague.status_code == 400
    ok = client.post("/api/admin/email/retry", json={"all": True},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200 and isinstance(ok.json()["requeued"], int)
    one = client.post("/api/admin/email/retry", json={"reference": "EM-0000-0000"},
                      headers={"X-CSRF": me["csrf"]})
    assert one.status_code == 200 and one.json()["requeued"] == 0
    editor = TestClient(app)
    sign_in(editor, "editor@elitemarcom.com", "editor-long-pass")
    assert editor.post("/api/admin/email/retry", json={"all": True}).status_code == 403


def test_email_routing_and_template_editing_through_the_api():
    me = client.get("/api/admin/me").json()
    ok = client.post("/api/admin/email/form/corporate_gifts",
                     json={"values": {"recipient": "gifts@elitemarcom.com",
                                      "customerOn": False,
                                      "heading": "Hello {{customer_name}}"}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    form = ok.json()["form"]
    assert form["recipient"] == "gifts@elitemarcom.com" and form["customerOn"] is False
    # unknown variables and unverified sender domains are refused with a clear message
    bad = client.post("/api/admin/email/form/corporate_gifts",
                      json={"values": {"body": "Salary is {{salary}}"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400 and "salary" in bad.json()["detail"]
    bad_from = client.post("/api/admin/email/general",
                           json={"values": {"fromEmail": "hello@gmail.com"}},
                           headers={"X-CSRF": me["csrf"]})
    assert bad_from.status_code == 400 and "verified" in bad_from.json()["detail"]
    no_csrf = client.post("/api/admin/email/general", json={"values": {"fromName": "X"}})
    assert no_csrf.status_code == 403
    # restore defaults
    client.post("/api/admin/email/form/corporate_gifts",
                json={"values": {"recipient": "mohammad.hossain@elitemarcom.com",
                                 "customerOn": True,
                                 "heading": "Your corporate gifts request is with our team"}},
                headers={"X-CSRF": me["csrf"]})
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "email.form_saved" in actions


def test_email_preview_renders_without_saving():
    me = client.get("/api/admin/me").json()
    before = client.get("/api/admin/email").json()
    res = client.post("/api/admin/email/preview",
                      json={"form": "job_application", "audience": "customer",
                            "values": {"heading": "Draft heading for {{customer_name}}",
                                       "customerSubject": "Draft subject {{position}}"}},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "Draft heading for Amira Hassan" in data["html"]
    assert data["subject"] == "Draft subject Senior 3D Designer"
    assert data["from"] == "Elite Marcom <website@mail.elitemarcom.com>"
    assert data["replyTo"] == "info@elitemarcom.com"
    assert "logo-email.png" in data["html"] and "<script" not in data["html"].lower()
    internal = client.post("/api/admin/email/preview",
                           json={"form": "job_application", "audience": "internal"},
                           headers={"X-CSRF": me["csrf"]}).json()
    assert "New submission" in internal["html"]
    # nothing was persisted by previewing
    after = client.get("/api/admin/email").json()
    assert before["forms"] == after["forms"]
    bad = client.post("/api/admin/email/preview",
                      json={"form": "job_application", "values": {"body": "{{quantity}}"}},
                      headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400          # quantity is not valid for a job application


def test_email_test_send_reports_failure_without_provider_detail(monkeypatch):
    me = client.get("/api/admin/me").json()
    from server import mailer

    monkeypatch.setattr(mailer, "send_test",
                        lambda to, by: (_ for _ in ()).throw(
                            mailer.MailError("The email service rejected the message.")))
    res = client.post("/api/admin/email/test", json={"to": "owner@elitemarcom.com"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail == "The email service rejected the message."
    assert "re_" not in detail and "401" not in detail
    monkeypatch.setattr(mailer, "send_test", lambda to, by: {"ok": True})
    ok = client.post("/api/admin/email/test", json={"to": "owner@elitemarcom.com"},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200 and ok.json()["ok"] is True
    actions = {e["action"] for e in aa.audit_list(limit=10)}
    assert "email.test_sent" in actions and "email.test_failed" in actions


# ---------------- repeatable content: the items inside a section ----------------
# Sections are the design layer's business. This is the other half: adding an
# eleventh service must be a form in the panel, not a deployment.

def _csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


def test_an_untouched_list_is_whatever_the_shipped_page_says():
    """No rows in the database, no divergence: the list follows the git HTML
    until somebody edits it, and baking reproduces the page it came from."""
    from server import collections as co

    assert not co.is_managed("services-spaces")
    shipped = co.items("services-spaces")
    assert [i["values"]["name"] for i in shipped] == ["Exhibition stands", "Fit-out & interiors"]

    baked = client.get("/admin/preview/services").text
    for item in shipped:
        import html as _html
        assert ">" + _html.escape(item["values"]["name"]) + "<" in baked
        assert item["values"]["image"] in baked


def test_every_page_of_the_site_is_managed_section_by_section():
    """The screen is page-first: every page the site has, with the repeatable
    parts it owns. Header and footer are their own groups because they are on
    every page rather than belonging to one."""
    from server import collections as co
    from server import content

    res = client.get("/api/admin/collections")
    assert res.status_code == 200, res.text
    groups = {g["page"]: g for g in res.json()["pages"]}

    # the header and the footer come first and are marked as site-wide
    assert list(groups)[:2] == ["_header", "_footer"]
    assert groups["_header"]["label"] == "Header" and groups["_header"]["global"] is True
    assert groups["_footer"]["label"] == "Footer" and groups["_footer"]["global"] is True

    # every page a visitor can reach and that has repeatable parts is there
    for page in ("index", "about", "services", "projects", "giveaways",
                 "rental", "careers", "contact"):
        assert page in groups, page
        assert groups[page]["lists"], page
        assert groups[page]["items"] > 0, page
        assert groups[page]["global"] is False

    # a group's lists are exactly the schemas that claim that page, and each
    # one really is in that page's markup
    for page, group in groups.items():
        assert set(group["lists"]) == {n for n, sp in co.SCHEMAS.items()
                                       if sp["page"] == page}
        raw = content.page_source(co.source_page(group["lists"][0]))
        for name in group["lists"]:
            assert co._container(raw, name) is not None, (page, name)

    # and every list the site defines belongs to exactly one group
    assert sorted(n for g in groups.values() for n in g["lists"]) == sorted(co.SCHEMAS)
    assert len(content.PAGES) - len(groups) + 2 == 3   # privacy, product, rental-item


def test_the_menu_is_one_list_baked_into_every_page():
    """Header and footer are not a page. They are read from one page's markup
    and baked into all of them, and only the header marks where you are."""
    import re

    from server import collections as co
    from server import content

    in_menu = {i["values"]["link"] for i in co.items("header-nav")}
    for page in content.PAGES:
        out = co.apply_to_page(content.page_source(page), page)
        # the same links on every page...
        assert out.count('<li><a href="/about.html"') >= 2, page
        # ...and where the page is in the menu, the bar and the slide-in panel
        # both say you are here — nothing else does, and the privacy page,
        # which is not a menu destination, is marked nowhere
        current = re.findall(r'<li><a href="([^"]*)"[^>]*aria-current="page"', out)
        want = co.page_href(page)
        assert current == ([want, want] if want in in_menu else []), (page, current)
        # a footer link never claims to be the current page: the header has
        # already said so and a second announcement is noise
        footer = out[out.index("<footer"):]
        assert 'aria-current="page"' not in footer, page


def test_a_page_group_only_ever_shows_that_page_s_lists():
    """The failure this guards against is a list appearing under the wrong page,
    which would have an admin editing the About values from the Contact screen."""
    from server import collections as co

    for group in co.page_groups():
        for name in group["lists"]:
            assert co.public_schema(name)["page"] == group["page"], name
            assert co.public_schema(name)["pageLabel"] == group["label"], name


def test_every_shipped_list_survives_a_round_trip_through_the_renderer():
    """render(parse(page)) has to reproduce the page field for field, or the
    first edit to any list would silently rewrite the ones beside it."""
    from server import collections as co
    from server import content

    for name, spec in co.SCHEMAS.items():
        page = co.source_page(name)
        out = co.apply_to_page(content.page_source(page), page)
        box = co._container(out, name)
        assert box is not None, name
        inner = out[box["contentStart"]:box["contentEnd"]]
        after = [spec["parse"](html) for html in co._shipped_spans(inner, spec)]
        assert after == [i["values"] for i in co.shipped_items(name)], name
        assert after, name


def test_add_a_service_from_the_panel_and_it_reaches_the_page():
    """The whole point: a new service with its name, description and image,
    with no developer involved."""
    res = client.post("/api/admin/collections/services-spaces/items", headers=_csrf(), json={
        "values": {"name": "Wayfinding systems", "eyebrow": "Spaces & fit-out",
                   "description": "Signage and orientation for venues and campuses.",
                   "image": "/assets/services/led-display.webp",
                   "imageAlt": "Illuminated wayfinding panel",
                   "specTitle": "What it includes",
                   "includes": "Survey and route planning\nSign family design\nProduction and install",
                   "linkLabel": "Talk to us about this", "link": "/contact.html",
                   "anchor": "wayfinding"}})
    assert res.status_code == 200, res.text
    new_id = res.json()["item"]["id"]

    listed = client.get("/api/admin/collections/services-spaces").json()
    assert [i["values"]["name"] for i in listed["items"]] == [
        "Exhibition stands", "Fit-out & interiors", "Wayfinding systems"]
    assert listed["managed"] is True     # the first edit takes the list over

    baked = client.get("/admin/preview/services").text
    assert "Wayfinding systems" in baked
    assert 'id="wayfinding"' in baked
    assert "Signage and orientation for venues and campuses." in baked
    assert "<li>Survey and route planning</li>" in baked
    # the two shipped cards are still there, unchanged
    assert "Exhibition stands" in baked and "Fit-out &amp; interiors" in baked
    return new_id


def test_duplicate_edit_reorder_hide_and_delete_one_item():
    """The complete workflow, in the order somebody would actually do it."""
    items = client.get("/api/admin/collections/services-spaces").json()["items"]
    target = [i for i in items if i["values"]["name"] == "Wayfinding systems"][0]

    # --- duplicate: the copy lands directly below the original
    dup = client.post(f"/api/admin/collections/services-spaces/duplicate/{target['id']}",
                      headers=_csrf())
    assert dup.status_code == 200, dup.text
    copy_id = dup.json()["item"]["id"]
    names = [i["values"]["name"] for i in
             client.get("/api/admin/collections/services-spaces").json()["items"]]
    assert names == ["Exhibition stands", "Fit-out & interiors",
                     "Wayfinding systems", "Wayfinding systems (copy)"]
    # an anchor is an address; the copy must not claim the original's
    copy = [i for i in client.get("/api/admin/collections/services-spaces").json()["items"]
            if i["id"] == copy_id][0]
    assert copy["values"]["anchor"] == "wayfinding-copy"

    # --- edit the copy
    values = dict(copy["values"], name="Environmental graphics",
                  description="Large-format graphics for spaces.")
    edit = client.post(f"/api/admin/collections/services-spaces/items/{copy_id}",
                       headers=_csrf(), json={"values": values})
    assert edit.status_code == 200, edit.text
    baked = client.get("/admin/preview/services").text
    assert "Environmental graphics" in baked and "Large-format graphics for spaces." in baked

    # --- reorder: move the copy to the front
    order = [copy_id] + [i["id"] for i in
                         client.get("/api/admin/collections/services-spaces").json()["items"]
                         if i["id"] != copy_id]
    moved = client.post("/api/admin/collections/services-spaces/order",
                        headers=_csrf(), json={"order": order})
    assert moved.status_code == 200, moved.text
    baked = client.get("/admin/preview/services").text
    assert baked.index("Environmental graphics") < baked.index("Exhibition stands")

    # --- hide: off the page, still in the panel
    hide = client.post(f"/api/admin/collections/services-spaces/hidden/{copy_id}",
                       headers=_csrf(), json={"hidden": True})
    assert hide.status_code == 200, hide.text
    baked = client.get("/admin/preview/services").text
    assert "Environmental graphics" not in baked
    assert "Exhibition stands" in baked          # the rest of the list is untouched
    assert [i["hidden"] for i in
            client.get("/api/admin/collections/services-spaces").json()["items"]][0] is True

    # --- show again
    client.post(f"/api/admin/collections/services-spaces/hidden/{copy_id}",
                headers=_csrf(), json={"hidden": False})
    assert "Environmental graphics" in client.get("/admin/preview/services").text

    # --- delete
    gone = client.post(f"/api/admin/collections/services-spaces/delete/{copy_id}",
                       headers=_csrf())
    assert gone.status_code == 200, gone.text
    baked = client.get("/admin/preview/services").text
    assert "Environmental graphics" not in baked
    assert "Wayfinding systems" in baked and "Exhibition stands" in baked


def test_restoring_the_shipped_list_drops_the_panels_copy():
    reset = client.post("/api/admin/collections/services-spaces/reset", headers=_csrf())
    assert reset.status_code == 200, reset.text
    listed = client.get("/api/admin/collections/services-spaces").json()
    assert listed["managed"] is False
    assert [i["values"]["name"] for i in listed["items"]] == [
        "Exhibition stands", "Fit-out & interiors"]
    assert "Wayfinding systems" not in client.get("/admin/preview/services").text


def test_every_managed_list_takes_the_same_operations():
    """Not a services-only feature: each list on the site does the lot."""
    from server import collections as co

    for name, spec in co.SCHEMAS.items():
        fields = co.public_schema(name)["fields"]
        values = {}
        for f in fields:
            if f["type"] == "image":
                values[f["key"]] = "/assets/services/led-display.webp"
            elif f["type"] == "link":
                values[f["key"]] = "/contact.html"
            elif f["type"] == "slug":
                values[f["key"]] = "probe-item"
            elif f["type"] == "select":
                values[f["key"]] = f["options"][0]["value"]
            else:
                # some fields are deliberately short (a one-letter marker,
                # a step number), so the probe has to fit the field
                values[f["key"]] = "Probe item"[:int(f.get("max") or 300)]
        added = client.post(f"/api/admin/collections/{name}/items",
                            headers=_csrf(), json={"values": values})
        assert added.status_code == 200, (name, added.text)
        item_id = added.json()["item"]["id"]
        assert client.post(f"/api/admin/collections/{name}/duplicate/{item_id}",
                           headers=_csrf()).status_code == 200, name
        assert client.post(f"/api/admin/collections/{name}/hidden/{item_id}",
                           headers=_csrf(), json={"hidden": True}).status_code == 200, name
        rows = client.get(f"/api/admin/collections/{name}").json()["items"]
        assert client.post(f"/api/admin/collections/{name}/order", headers=_csrf(),
                           json={"order": [r["id"] for r in reversed(rows)]}).status_code == 200
        page = co.source_page(name)
        baked = client.get(f"/admin/preview/{page}").text
        assert "Probe" in baked                            # the copy is visible
        assert client.post(f"/api/admin/collections/{name}/reset",
                           headers=_csrf()).status_code == 200, name
        assert "Probe" not in client.get(f"/admin/preview/{page}").text


def test_a_hidden_item_leaves_the_page_but_not_the_panel():
    from server import collections as co

    client.post("/api/admin/collections/about-values/items", headers=_csrf(),
                json={"values": {"title": "Curiosity", "text": "We ask before we answer."}})
    rows = client.get("/api/admin/collections/about-values").json()["items"]
    added = rows[-1]["id"]
    assert "Curiosity" in client.get("/admin/preview/about").text
    client.post(f"/api/admin/collections/about-values/hidden/{added}",
                headers=_csrf(), json={"hidden": True})
    assert "Curiosity" not in client.get("/admin/preview/about").text
    assert any(r["id"] == added for r in
               client.get("/api/admin/collections/about-values").json()["items"])
    client.post("/api/admin/collections/about-values/reset", headers=_csrf())
    assert not co.is_managed("about-values")


def test_nothing_an_admin_types_is_ever_treated_as_markup():
    """Every tag in a rendered item is written by us. A field is text, a path
    or a URL — never HTML, and never a way into the page."""
    res = client.post("/api/admin/collections/about-values/items", headers=_csrf(), json={
        "values": {"title": "Ok<script>alert(1)</script>",
                   "text": "<img src=x onerror=alert(1)> and <b>bold</b>"}})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/preview/about").text
    grid = baked.split('class="values-grid"')[1].split("</dl>")[0]
    # the only tags in a rendered list are the ones the renderer writes; the
    # admin's angle brackets came back as text, which is the whole point
    assert set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", grid)) == {"div", "dt", "dd"}
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in grid
    assert "&lt;b&gt;bold&lt;/b&gt;" in grid
    client.post("/api/admin/collections/about-values/reset", headers=_csrf())


def test_an_image_or_link_field_only_takes_something_we_would_serve():
    bad_image = client.post("/api/admin/collections/services-spaces/items", headers=_csrf(),
                            json={"values": {"name": "X", "image": "https://evil.example/x.png"}})
    assert bad_image.status_code == 400
    assert "Media library" in bad_image.json()["detail"]
    bad_link = client.post("/api/admin/collections/services-spaces/items", headers=_csrf(),
                           json={"values": {"name": "X", "link": "javascript:alert(1)"}})
    assert bad_link.status_code == 400
    bad_slug = client.post("/api/admin/collections/services-spaces/items", headers=_csrf(),
                           json={"values": {"name": "X", "anchor": "Not A Slug"}})
    assert bad_slug.status_code == 400
    nameless = client.post("/api/admin/collections/services-spaces/items", headers=_csrf(),
                           json={"values": {"name": ""}})
    assert nameless.status_code == 400
    assert not client.get("/api/admin/collections/services-spaces").json()["managed"]


def test_a_stale_screen_cannot_delete_an_item_by_reordering():
    """An order list that has fallen behind must move what it names and leave
    everything else alone — never drop the items it forgot."""
    from server import collections as co

    client.post("/api/admin/collections/about-values/items", headers=_csrf(),
                json={"values": {"title": "Fifth", "text": "Added after the screen loaded."}})
    rows = client.get("/api/admin/collections/about-values").json()["items"]
    assert len(rows) >= 5
    stale = [r["id"] for r in rows[:2]][::-1]           # a two-item order from before
    client.post("/api/admin/collections/about-values/order", headers=_csrf(),
                json={"order": stale})
    after = client.get("/api/admin/collections/about-values").json()["items"]
    assert len(after) == len(rows)
    assert [a["id"] for a in after[:2]] == stale
    client.post("/api/admin/collections/about-values/reset", headers=_csrf())


def test_editing_a_list_needs_permission_and_a_csrf_token():
    res = client.post("/api/admin/collections/about-values/items",
                      json={"values": {"title": "No token"}})
    assert res.status_code == 403
    lean, lean_me = _catalog_client()
    denied = lean.post("/api/admin/collections/about-values/items",
                       headers={"X-CSRF": lean_me["csrf"]}, json={"values": {"title": "Nope"}})
    assert denied.status_code == 403
    assert lean.get("/api/admin/collections").status_code == 403


def test_an_unknown_list_is_a_404_not_a_crash():
    assert client.get("/api/admin/collections/not-a-list").status_code == 404
    assert client.post("/api/admin/collections/not-a-list/items", headers=_csrf(),
                       json={"values": {}}).status_code == 400


def test_a_visual_editor_edit_inside_a_list_is_not_rebuilt_away():
    """Both layers can touch the same card. Sections, then the items inside
    them, then the per-element overrides — so the last word is the editor's."""
    from server import collections as co

    client.post("/api/admin/collections/about-values/items", headers=_csrf(),
                json={"values": {"title": "Care", "text": "Details matter."}})
    path = ("[data-em-sec=s3]>div:nth-of-type(1)>dl:nth-of-type(1)"
            ">div:nth-of-type(5)>dt:nth-of-type(1)")
    saved = client.post("/api/admin/design/about", headers=_csrf(),
                        json={"doc": {"elements": {path: {"text": "Care, always"}}}})
    assert saved.status_code == 200, saved.text
    baked = client.get("/admin/preview/about").text
    assert "<dt>Care, always</dt>" in baked
    client.post("/api/admin/design/about", headers=_csrf(), json={"doc": {"elements": {}}})
    client.post("/api/admin/collections/about-values/reset", headers=_csrf())
    assert not co.is_managed("about-values")


def test_a_list_edit_marks_its_page_as_needing_publishing():
    client.post("/api/admin/collections/home-services/items", headers=_csrf(),
                json={"values": {"name": "New capability", "hint": "Something we now do",
                                 "link": "/contact.html", "preview": ""}})
    pages = {p["page"]: p for p in client.get("/api/admin/pages").json()["pages"]}
    assert pages["index"]["dirty"] is True
    client.post("/api/admin/collections/home-services/reset", headers=_csrf())


def test_a_backup_carries_the_lists_and_a_restore_puts_them_back():
    from server import backup, collections as co

    client.post("/api/admin/collections/about-presence/items", headers=_csrf(),
                json={"values": {"title": "Jeddah", "text": "Western region support.",
                                 "chip": "Regional", "tone": "chip--violet"}})
    blob, manifest = backup.create()
    assert "collections" in manifest["contains"]
    co.reset("about-presence", "test")
    assert not co.is_managed("about-presence")
    backup.restore(blob, "test")
    assert co.is_managed("about-presence")
    assert any(i["values"]["title"] == "Jeddah" for i in co.items("about-presence"))
    co.reset("about-presence", "test")


# ---------------- visual editor: blank sections, elements, copied sections ----------------
# Sections are added, copied, reordered, hidden and deleted from the editor; a
# blank one is filled from an element library. Everything here is still our
# markup — the panel sends template ids, never HTML.

def test_a_blank_section_carries_the_elements_placed_in_it():
    me = client.get("/api/admin/me").json()
    doc = {"sections": {"added": [{"id": "a1", "template": "blank", "children": [
        {"id": "e1", "template": "heading"},
        {"id": "e2", "template": "text"},
        {"id": "e3", "template": "button"}]}],
        "order": ["s0", "a1"]}}
    res = client.post("/api/admin/design/contact", json={"doc": doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/preview/contact").text
    assert 'data-em-sec="a1"' in baked and 'data-em-block="blank"' in baked
    # each element is stamped, so a style survives the ones around it moving
    for eid in ("e1", "e2", "e3"):
        assert 'data-em-el="' + eid + '"' in baked
    assert baked.index('data-em-el="e1"') < baked.index('data-em-el="e2"') \
        < baked.index('data-em-el="e3"')
    assert "A new headline" in baked and "Start the conversation" in baked


def test_an_element_keeps_its_styling_when_the_ones_around_it_move():
    """The whole reason a placed element has an id: nth-of-type would hand the
    style to whatever ended up in that position instead."""
    me = client.get("/api/admin/me").json()
    path = "[data-em-sec=a1]>[data-em-el=e3]>a:nth-of-type(1)"
    doc = {"sections": {"added": [{"id": "a1", "template": "blank", "children": [
        {"id": "e1", "template": "heading"},
        {"id": "e2", "template": "text"},
        {"id": "e3", "template": "button"}]}], "order": ["s0", "a1"]},
        "elements": {path: {"styles": {"base": {"border-radius": "2px"}},
                            "text": "Talk to us"}}}
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/contact").text
    assert "Talk to us" in baked
    assert "border-radius:2px" in baked

    # now move that element to the front — the style must travel with it
    doc["sections"]["added"][0]["children"] = [
        {"id": "e3", "template": "button"},
        {"id": "e1", "template": "heading"},
        {"id": "e2", "template": "text"}]
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    moved = client.get("/admin/preview/contact").text
    assert "Talk to us" in moved and "border-radius:2px" in moved
    assert moved.index('data-em-el="e3"') < moved.index('data-em-el="e1"')


def test_only_elements_we_ship_can_be_placed():
    me = client.get("/api/admin/me").json()
    bad = client.post("/api/admin/design/contact", json={"doc": {"sections": {"added": [
        {"id": "a1", "template": "blank",
         "children": [{"id": "e1", "template": "<script>alert(1)</script>"}]}]}}},
        headers={"X-CSRF": me["csrf"]})
    assert bad.status_code == 400
    assert "Unknown element" in bad.json()["detail"]
    bad_id = client.post("/api/admin/design/contact", json={"doc": {"sections": {"added": [
        {"id": "a1", "template": "blank", "children": [{"id": "x9", "template": "heading"}]}]}}},
        headers={"X-CSRF": me["csrf"]})
    assert bad_id.status_code == 400


def test_a_section_copied_from_another_page_is_that_pages_own_markup():
    """Copy/paste moves a section between pages without any HTML travelling
    through the panel: we remember which page and which section, and the bake
    lifts the markup out of the git-tracked page itself."""
    me = client.get("/api/admin/me").json()
    doc = {"sections": {"added": [{"id": "a2", "from": {"page": "about", "sec": "s3"}}],
                        "order": ["s0", "a2"]}}
    res = client.post("/api/admin/design/contact", json={"doc": doc},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 200, res.text
    baked = client.get("/admin/preview/contact").text
    assert 'data-em-sec="a2"' in baked
    assert "Excellence" in baked and "Personal service" in baked   # the About values
    # the copy is edited on its own: no keyed regions, no ids taken from the original
    copy = baked.split('data-em-sec="a2"')[1].split("</section>")[0]
    assert "data-em=" not in copy and 'id="mission' not in copy
    assert 'data-em-list' not in copy      # a frozen copy, not a second live list


def test_a_copied_section_carries_the_items_the_page_shows_today():
    """Copy a section after a fifth item was added to its list and the copy has
    five — a copy of the page as it stands, not of the file in git."""
    from server import collections as co

    me = client.get("/api/admin/me").json()
    client.post("/api/admin/collections/about-values/items", headers={"X-CSRF": me["csrf"]},
                json={"values": {"title": "Curiosity", "text": "We ask before we answer."}})
    doc = {"sections": {"added": [{"id": "a3", "from": {"page": "about", "sec": "s3"}}],
                        "order": ["s0", "a3"]}}
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/contact").text
    assert "Curiosity" in baked and "We ask before we answer." in baked
    co.reset("about-values", "test")
    client.post("/api/admin/design/contact", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_a_copy_can_only_name_a_page_of_ours():
    me = client.get("/api/admin/me").json()
    for source in ({"page": "https://evil.example/x", "sec": "s1"},
                   {"page": "about", "sec": "../../etc/passwd"},
                   {"page": "about", "sec": "s999999"}):
        res = client.post("/api/admin/design/contact", json={"doc": {"sections": {
            "added": [{"id": "a4", "from": source}]}}}, headers={"X-CSRF": me["csrf"]})
        assert res.status_code == 400, source
    client.post("/api/admin/design/contact", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_the_element_library_is_offered_with_the_block_library():
    res = client.get("/api/admin/blocks")
    assert res.status_code == 200
    data = res.json()
    ids = {b["id"] for b in data["blocks"]}
    assert "blank" in ids                      # the empty canvas
    el_ids = {e["id"] for e in data["elements"]}
    for wanted in ("heading", "text", "image", "video", "button", "icon",
                   "columns-2", "columns-3", "card", "divider", "spacer-el", "list"):
        assert wanted in el_ids, wanted
    # every element arrives pre-rendered with the id placeholder the panel fills
    for e in data["elements"]:
        assert "__EID__" in e["html"], e["id"]
        assert "<script" not in e["html"]
    assert data["maxElements"] >= 10


def test_the_section_copy_endpoint_serves_our_markup_only():
    res = client.get("/api/admin/section-copy?page=about&sec=s3")
    assert res.status_code == 200
    assert 'data-em-sec="__ID__"' in res.json()["html"]
    assert client.get("/api/admin/section-copy?page=nope&sec=s1").status_code == 404
    assert client.get("/api/admin/section-copy?page=about&sec=s404").status_code == 404
    lean, _ = _catalog_client()
    assert lean.get("/api/admin/section-copy?page=about&sec=s3").status_code == 403


def test_the_new_layout_properties_are_whitelisted_like_every_other():
    from server import design

    ok = design.validate_doc({"elements": {"[data-em-sec=s1]": {"styles": {"base": {
        "display": "flex", "gap": "24px", "justify-content": "space-between",
        "align-items": "center", "min-height": "420px",
        "grid-template-columns": "repeat(3, minmax(0, 1fr))",
        "background-size": "cover", "background-position": "center"}}}}})
    assert ok["elements"]["[data-em-sec=s1]"]["styles"]["base"]["gap"] == "24px"
    for bad in ({"display": "url(javascript:1)"}, {"gap": "expression(1)"},
                {"justify-content": "</style>"}, {"grid-template-columns": "1fr;}body{x"},
                {"background-position": "url(x)"}):
        with pytest.raises(design.DesignError):
            design.validate_doc({"elements": {"[data-em-sec=s1]": {"styles": {"base": bad}}}})


def test_an_element_path_is_still_a_path_and_nothing_else():
    from server import design

    good = "[data-em-sec=a1]>[data-em-el=e2]>a:nth-of-type(1)"
    assert design.validate_doc({"elements": {good: {"styles": {"base": {"opacity": "0.5"}}}}})
    for bad in ("[data-em-el=e1]>div",                      # must start at a section
                "[data-em-sec=a1]>[data-em-el=e1x]",        # not an element id
                "[data-em-sec=a1]>[data-em-el=e1]>[data-em-el=e2]"):
        with pytest.raises(design.DesignError):
            design.validate_doc({"elements": {bad: {"styles": {"base": {"opacity": "0.5"}}}}})


def test_the_editor_page_still_bakes_every_shipped_page():
    """The whole point of the guard: none of this may quietly drop content."""
    from server import content

    for page in content.PAGES:
        baked = client.get("/admin/preview/" + page)
        assert baked.status_code == 200, page
        assert "</html>" in baked.text, page


def test_the_editors_own_chrome_never_reaches_a_baked_page():
    """The toolbar, handles and drop marker are injected into the preview by
    the bridge. Nothing the bake produces may carry them."""
    from server import content

    for page in ("index", "about", "contact", "services"):
        baked = client.get("/admin/preview/" + page).text
        for chrome in ("em-bar", "em-handle", "em-drop", "em-size",
                       "em-selected", "em-hover", "em-off", "em-dragging"):
            assert chrome not in baked, (page, chrome)
    assert "editor-bridge" not in content.bake_page("index")


def test_the_old_duplicate_field_still_works_beside_the_new_one():
    """Documents saved before this change use sections.duplicated. They must
    keep baking exactly as they did."""
    me = client.get("/api/admin/me").json()
    doc = {"sections": {"duplicated": ["s3"],
                        "added": [{"id": "a1", "template": "blank",
                                   "children": [{"id": "e1", "template": "heading"}]}],
                        "order": ["s0", "s1", "s2", "s3", "a1"]}}
    assert client.post("/api/admin/design/about", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/about").text
    assert baked.count("<dt>Excellence</dt>") == 2      # the in-place copy
    assert 'data-em-sec="a1"' in baked and "A new headline" in baked
    client.post("/api/admin/design/about", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_a_duplicated_blank_section_is_independent_of_the_original():
    me = client.get("/api/admin/me").json()
    doc = {"sections": {"added": [
        {"id": "a1", "template": "blank", "children": [{"id": "e1", "template": "heading"}]},
        {"id": "a2", "template": "blank", "children": [{"id": "e1", "template": "heading"}]}],
        "order": ["s0", "a1", "a2"]},
        "elements": {"[data-em-sec=a1]>[data-em-el=e1]": {"text": "Only the first"}}}
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/contact").text
    assert "Only the first" in baked
    assert baked.count("A new headline") == 1      # the copy kept the default
    client.post("/api/admin/design/contact", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_a_backslash_in_alt_text_does_not_break_every_bake():
    """The attribute value used to be a regex replacement template: an alt of
    "AC\\DC" raised re.error on every later bake and aborted Publish part-way
    through, with no way back through the editor."""
    from server import design

    me = client.get("/api/admin/me").json()
    for value in ("AC\\DC", "C:\\photos\\hero.png", "Sara \\1 Ali"):
        res = client.post("/api/admin/design/about", headers={"X-CSRF": me["csrf"]},
                          json={"doc": {"elements": {"main": {"attrs": {"alt": value}}}}})
        assert res.status_code == 200, (value, res.text)
        baked = client.get("/admin/preview/about")
        assert baked.status_code == 200, value
        assert 'alt="' + value.replace("&", "&amp;") + '"' in baked.text, value
    assert design._set_attrs_in_tag('<img src="/x.png"/>', {"alt": "a\\b"}) == \
        '<img src="/x.png" alt="a\\b"/>'
    client.post("/api/admin/design/about", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_a_placed_elements_style_is_a_selector_that_actually_matches():
    """The path is emitted verbatim as CSS. A child combinator between the
    section and the element would resolve on the server and match nothing in a
    browser — a style that looks saved and does nothing."""
    from server import design

    me = client.get("/api/admin/me").json()
    path = "[data-em-sec=a1] [data-em-el=e1]"
    doc = {"sections": {"added": [{"id": "a1", "template": "blank",
                                   "children": [{"id": "e1", "template": "heading"}]}],
                        "order": ["s0", "a1"]},
           "elements": {path: {"styles": {"base": {"color": "#ff0000"}},
                               "hidden": {"mobile": True}}}}
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/contact").text
    assert "[data-em-sec=a1] [data-em-el=e1]{color:#ff0000" in baked
    assert ">[data-em-el=" not in baked        # never the child combinator
    # and the markup really does nest the element below .container > .em-stack
    body = baked.split('data-em-sec="a1"')[1].split("</section>")[0]
    assert 'class="em-stack"' in body and 'data-em-el="e1"' in body
    assert body.index("em-stack") < body.index('data-em-el="e1"')
    # an old path with ">" is normalised on the way in rather than rejected
    fixed = design.validate_doc({"elements": {"[data-em-sec=a1]>[data-em-el=e1]":
                                              {"styles": {"base": {"opacity": "0.5"}}}}})
    assert list(fixed["elements"]) == ["[data-em-sec=a1] [data-em-el=e1]"]
    client.post("/api/admin/design/contact", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})


def test_elements_are_refused_where_a_template_cannot_hold_them():
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/design/contact", headers={"X-CSRF": me["csrf"]},
                      json={"doc": {"sections": {"added": [
                          {"id": "a1", "template": "cta",
                           "children": [{"id": "e1", "template": "heading"}]}]}}})
    assert res.status_code == 400
    assert "Blank section" in res.json()["detail"]


def test_a_copied_section_keeps_its_labels_and_never_carries_a_form():
    """Deleting every id broke label/field pairing and in-block anchors;
    keeping them would put two elements on one id. They are re-prefixed."""
    from server import design

    out = design.section_from_page("about", "s3", "a7")
    assert 'id="a7-mission-h"' in out
    assert 'aria-labelledby="' not in out.split(">")[0]   # the section's own is dropped
    # a section with a form cannot be wired up twice, so saving the copy is
    # refused where the admin can see it — not silently at bake time
    assert "form" in design.copy_refusal("contact", "s1")
    assert design.copy_refusal("about", "s3") == ""
    me = client.get("/api/admin/me").json()
    refused = client.post("/api/admin/design/about", headers={"X-CSRF": me["csrf"]},
                          json={"doc": {"sections": {"added": [
                              {"id": "a1", "from": {"page": "contact", "sec": "s1"}}]}}})
    assert refused.status_code == 400
    assert "form" in refused.json()["detail"]
    # and a page still bakes if such a copy were ever stored some other way
    assert design.section_from_page("contact", "s1", "a9") == ""
    assert client.get("/admin/preview/about").status_code == 200


def test_the_video_element_can_be_pointed_at_a_real_video():
    """It ships with a placeholder clip; the editor must be able to change it,
    and only to a validated id on our privacy host."""
    from server import design

    assert design.ATTRS["src"]("https://www.youtube-nocookie.com/embed/lFhAiGLjoMo?rel=0")
    assert not design.ATTRS["src"]("https://www.youtube.com/embed/lFhAiGLjoMo")
    assert not design.ATTRS["src"]("https://evil.example/embed/lFhAiGLjoMo")
    assert not design.ATTRS["src"]("/media/../admin/secrets")
    assert design.ATTRS["src"]("/assets/portfolio/aces-pavilion-live.webp")

    me = client.get("/api/admin/me").json()
    path = "[data-em-sec=a1] [data-em-el=e1]"
    doc = {"sections": {"added": [{"id": "a1", "template": "blank",
                                   "children": [{"id": "e1", "template": "video"}]}],
                        "order": ["s0", "a1"]},
           "elements": {path: {"attrs": {
               "src": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0"}}}}
    assert client.post("/api/admin/design/contact", json={"doc": doc},
                       headers={"X-CSRF": me["csrf"]}).status_code == 200
    baked = client.get("/admin/preview/contact").text
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in baked
    client.post("/api/admin/design/contact", json={"doc": {}}, headers={"X-CSRF": me["csrf"]})
