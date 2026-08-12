"""Admin panel Phase 0 — auth, 2FA, sessions, CSRF, roles, audit, settings."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import security
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
