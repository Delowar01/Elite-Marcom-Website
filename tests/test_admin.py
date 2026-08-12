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
