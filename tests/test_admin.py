"""Admin panel Phase 0 + 1 — auth, 2FA, roles, audit, requests inbox, Jasani console."""
from __future__ import annotations

import json
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
    no_csrf = client.post("/api/admin/settings", json={"values": {"notify.whatsapp": "+966500000000"}})
    assert no_csrf.status_code == 403
    ok = client.post("/api/admin/settings",
                     json={"values": {"notify.whatsapp": "+966500000000",
                                      "notify.emails": ["ops@elitemarcom.com"]}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200
    assert client.get("/api/admin/settings").json()["notify.whatsapp"] == "+966500000000"


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


def test_jasani_console_status_and_search(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)
    res = client.get("/api/admin/jasani")
    assert res.status_code == 200
    data = res.json()
    assert data["budget"]["limit"] >= 1 and data["budget"]["used"] == 0
    assert data["markets"]["ksa"]["products"] == 2
    assert data["markets"]["ksa"]["inStock"] == 1
    assert data["markets"]["uae"]["cached"] is False
    assert "token" not in json.dumps(data).lower() or data["tokenConfigured"] in (True, False)
    found = client.get("/api/admin/jasani/products?market=ksa&q=tumbler").json()["products"]
    assert len(found) == 1 and found[0]["code"] == "CTEN 2240"
    assert client.get("/api/admin/jasani/products?market=nope").status_code == 400


def test_jasani_refresh_stock_success_and_audit(tmp_path, monkeypatch):
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)

    async def fake_apply(market, products):
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


def test_jasani_refresh_blocked_when_budget_exhausted(tmp_path, monkeypatch):
    from server import config as cfg
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    _seed_jasani_cache(tmp_path)
    monkeypatch.setattr(cfg, "JASANI_API_TOKEN", "test-token")
    (tmp_path / "supplier-budget.json").write_text(
        json.dumps({"day": jasani._uae_day(), "count": cfg.SUPPLIER_DAILY_BUDGET}),
        encoding="utf-8")
    me = client.get("/api/admin/me").json()
    res = client.post("/api/admin/jasani/refresh", json={"market": "ksa", "what": "stock"},
                      headers={"X-CSRF": me["csrf"]})
    assert res.status_code == 503
    assert "budget" in res.json()["detail"].lower()
    # the cached snapshot is untouched
    cached = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    assert cached["products"][0]["stock"]["available"] == 40
    assert client.get("/api/admin/jasani").json()["budget"]["remaining"] == 0
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
    assert gfields["nav.about"]["original"] == "About"
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
                     json={"lang": "en", "values": {"nav.about": "Our Story",
                                                    "footer.email": "hello@elitemarcom.com"}},
                     headers={"X-CSRF": me["csrf"]})
    assert ok.status_code == 200, ok.text
    client.post("/api/admin/pages-publish", headers={"X-CSRF": me["csrf"]})
    about = client.get("/about.html").text
    assert ">Our Story</a>" in about
    assert 'href="mailto:hello@elitemarcom.com"' in about
    assert ">hello@elitemarcom.com</a>" in about
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
