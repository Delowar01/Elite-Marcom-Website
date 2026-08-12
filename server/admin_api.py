"""Elite Marcom admin panel — HTTP surface (Phase 0).

Login + mandatory TOTP 2FA, sessions with CSRF, user management, audit log,
settings. Pages are served by the same app; every mutating endpoint requires
a valid session cookie AND the matching X-CSRF header.
"""
from __future__ import annotations

import base64
import io
import re
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import adminauth as aa
from . import config, security

router = APIRouter()

ADMIN_UI = Path(__file__).parent / "adminui"
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")

COOKIE_KW = dict(httponly=True, samesite="strict", path="/")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(aa.SESSION_COOKIE, token, secure=config.IS_PROD,
                        max_age=int(config.ADMIN_SESSION_HOURS * 3600), **COOKIE_KW)


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(aa.SESSION_COOKIE, path="/")


def _ip_hash(request: Request) -> str:
    return security.hash_ip(security.client_ip(request))


def current_session(request: Request) -> sqlite3.Row | None:
    return aa.get_session(request.cookies.get(aa.SESSION_COOKIE, ""))


def require_session(request: Request) -> sqlite3.Row:
    session = current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return session


def require_perm(request: Request, perm: str) -> sqlite3.Row:
    session = require_session(request)
    if not aa.has_perm(session["role"], perm):
        raise HTTPException(status_code=403, detail="You do not have permission for this action.")
    return session


def require_csrf(request: Request, session: sqlite3.Row, x_csrf: str | None) -> None:
    if not x_csrf or x_csrf != session["csrf"]:
        raise HTTPException(status_code=403, detail="Invalid session token — reload the page.")


def _clean(value: str, max_len: int, min_len: int, field: str) -> str:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    if len(value) < min_len or len(value) > max_len:
        raise HTTPException(status_code=400, detail=f"Please check the {field}.")
    return value


def _check_password(pw: str) -> str:
    if len(pw or "") < 12 or len(pw) > 200:
        raise HTTPException(status_code=400, detail="Passwords must be at least 12 characters.")
    return pw


def _qr_data_uri(text: str) -> str | None:
    try:
        import qrcode

        img = qrcode.make(text, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None  # UI falls back to showing the secret for manual entry


# ---------------- pages ----------------

@router.get("/admin", include_in_schema=False)
@router.get("/admin/", include_in_schema=False)
async def admin_page(request: Request):
    page = "app.html" if current_session(request) else "login.html"
    return FileResponse(ADMIN_UI / page, headers={"Cache-Control": "no-store"})


# ---------------- auth flow ----------------

class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/api/admin/login")
async def admin_login(request: Request, body: LoginBody):
    ip = _ip_hash(request)
    security.limiter.check("admin_login", ip, 10, 900)
    user = aa.get_user_by_email(body.email)
    if user is None or not user["active"]:
        aa.audit(None, "login.failed", "auth", {"email": body.email.lower()[:200]}, ip)
        raise HTTPException(status_code=400, detail="Incorrect email or password.")
    if user["locked_until"] > time.time():
        raise HTTPException(status_code=429, detail="Too many attempts — this account is locked for a few minutes.")
    if not aa.verify_password(body.password, user["pass_hash"], user["pass_salt"]):
        aa.register_login_failure(user)
        aa.audit(user, "login.failed", "auth", {"reason": "password"}, ip)
        raise HTTPException(status_code=400, detail="Incorrect email or password.")
    if not user["totp_enabled"]:
        # first sign-in: force 2FA enrolment before any session exists
        secret = aa.totp_new_secret()
        aa.set_totp(user["id"], secret, enabled=False)
        uri = aa.totp_uri(secret, user["email"])
        return {"stage": "setup", "pending": aa.make_pending(user["id"], "setup"),
                "secret": secret, "uri": uri, "qr": _qr_data_uri(uri)}
    return {"stage": "totp", "pending": aa.make_pending(user["id"], "totp")}


class TotpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending: str = Field(max_length=600)
    code: str = Field(max_length=12)


def _finish_login(request: Request, user: sqlite3.Row) -> JSONResponse:
    token, csrf = aa.create_session(user["id"], _ip_hash(request),
                                    request.headers.get("user-agent", ""))
    aa.register_login_success(user)
    aa.audit(user, "login.success", "auth", {}, _ip_hash(request))
    response = JSONResponse({"ok": True})
    _set_session_cookie(response, token)
    return response


@router.post("/api/admin/2fa/verify")
async def admin_2fa_verify(request: Request, body: TotpBody):
    ip = _ip_hash(request)
    security.limiter.check("admin_2fa", ip, 15, 900)
    for purpose in ("totp", "setup"):
        user_id = aa.read_pending(body.pending, purpose)
        if user_id is not None:
            break
    else:
        raise HTTPException(status_code=400, detail="Sign-in expired — start again.")
    user = aa.get_user(user_id)
    if user is None or not user["active"]:
        raise HTTPException(status_code=400, detail="Sign-in expired — start again.")
    secret = aa.read_totp_secret(user)
    if not secret or not aa.totp_verify(secret, body.code):
        aa.audit(user, "login.failed", "auth", {"reason": "totp"}, ip)
        raise HTTPException(status_code=400, detail="That code is not correct — try the current code.")
    if purpose == "setup":
        aa.set_totp(user["id"], secret, enabled=True)
        aa.audit(user, "2fa.enabled", "auth", {}, ip)
    return _finish_login(request, user)


class SetupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=200)
    name: str = Field(max_length=120)
    password: str = Field(max_length=200)
    setupCode: str = Field(default="", max_length=120)


@router.post("/api/admin/bootstrap")
async def admin_bootstrap(request: Request, body: SetupBody):
    """Create the FIRST Owner account — only while no accounts exist."""
    security.limiter.check("admin_bootstrap", _ip_hash(request), 5, 3600)
    if aa.user_count() > 0:
        raise HTTPException(status_code=403, detail="Setup is already complete.")
    if config.ADMIN_SETUP_CODE and body.setupCode != config.ADMIN_SETUP_CODE:
        raise HTTPException(status_code=403, detail="The setup code is not correct.")
    email = _clean(body.email, 200, 5, "email").lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")
    name = _clean(body.name, 120, 2, "name")
    aa.create_user(email, name, _check_password(body.password), "owner")
    aa.audit(None, "bootstrap.owner_created", "auth", {"email": email}, _ip_hash(request))
    return {"ok": True}


@router.get("/api/admin/state")
async def admin_state(request: Request):
    """Pre-login state for the login page (no secrets)."""
    return {"needsBootstrap": aa.user_count() == 0,
            "setupCodeRequired": bool(config.ADMIN_SETUP_CODE)}


@router.post("/api/admin/logout")
async def admin_logout(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_session(request)
    require_csrf(request, session, x_csrf)
    aa.audit(session, "logout", "auth", {}, _ip_hash(request))
    aa.destroy_session(request.cookies.get(aa.SESSION_COOKIE, ""))
    response = JSONResponse({"ok": True})
    _clear_session_cookie(response)
    return response


@router.get("/api/admin/me")
async def admin_me(request: Request):
    session = require_session(request)
    grants = aa.ROLES.get(session["role"], set())
    return {"email": session["email"], "name": session["name"], "role": session["role"],
            "csrf": session["csrf"],
            "permissions": sorted(aa.PERMISSIONS) if "*" in grants else sorted(grants)}


# ---------------- sessions ----------------

@router.get("/api/admin/sessions")
async def admin_sessions(request: Request):
    session = require_session(request)
    current_hash = aa._token_hash(request.cookies.get(aa.SESSION_COOKIE, ""))
    out = []
    for s in aa.list_sessions(session["user_id"]):
        out.append({"current": s["token_hash"] == current_hash,
                    "createdAt": s["created_at"], "expiresAt": s["expires_at"],
                    "userAgent": s["user_agent"]})
    return {"sessions": out}


@router.post("/api/admin/sessions/revoke-others")
async def admin_sessions_revoke(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_session(request)
    require_csrf(request, session, x_csrf)
    n = aa.destroy_user_sessions(session["user_id"], keep_token=request.cookies.get(aa.SESSION_COOKIE, ""))
    aa.audit(session, "sessions.revoked_others", "auth", {"count": n}, _ip_hash(request))
    return {"revoked": n}


# ---------------- users ----------------

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=200)
    name: str = Field(max_length=120)
    password: str = Field(max_length=200)
    role: str = Field(max_length=30)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=30)
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)
    resetTotp: bool = False


@router.get("/api/admin/users")
async def admin_users(request: Request):
    require_perm(request, "users.manage")
    return {"users": aa.list_users(), "roles": sorted(aa.ROLES)}


@router.post("/api/admin/users")
async def admin_users_create(request: Request, body: UserCreate,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "users.manage")
    require_csrf(request, session, x_csrf)
    email = _clean(body.email, 200, 5, "email").lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")
    if body.role not in aa.ROLES:
        raise HTTPException(status_code=400, detail="Unknown role.")
    if aa.get_user_by_email(email) is not None:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user_id = aa.create_user(email, _clean(body.name, 120, 2, "name"),
                             _check_password(body.password), body.role)
    aa.audit(session, "user.created", "users", {"id": user_id, "email": email, "role": body.role},
             _ip_hash(request))
    return {"id": user_id}


@router.post("/api/admin/users/{user_id}")
async def admin_users_update(request: Request, user_id: int, body: UserUpdate,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "users.manage")
    require_csrf(request, session, x_csrf)
    user = aa.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown user.")
    changes: dict = {}
    if body.name is not None:
        changes["name"] = _clean(body.name, 120, 2, "name")
    if body.role is not None:
        if body.role not in aa.ROLES:
            raise HTTPException(status_code=400, detail="Unknown role.")
        changes["role"] = body.role
    if body.active is not None:
        if user_id == session["user_id"] and body.active is False:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
        changes["active"] = 1 if body.active else 0
    if body.password:
        pass_hash, salt = aa.hash_password(_check_password(body.password))
        changes["pass_hash"], changes["pass_salt"] = pass_hash, salt
    # never leave the system without an active owner
    if user["role"] == "owner" and (changes.get("role", "owner") != "owner" or changes.get("active") == 0):
        owners = [u for u in aa.list_users() if u["role"] == "owner" and u["active"] and u["id"] != user_id]
        if not owners:
            raise HTTPException(status_code=400, detail="At least one active Owner account is required.")
    aa.update_user(user_id, **changes)
    if body.resetTotp:
        aa.set_totp(user_id, aa.totp_new_secret(), enabled=False)
        changes["resetTotp"] = True
    if body.active is False or body.password or body.resetTotp:
        aa.destroy_user_sessions(user_id)
    aa.audit(session, "user.updated", "users",
             {"id": user_id, "fields": sorted(set(changes) - {"pass_hash", "pass_salt"})},
             _ip_hash(request))
    return {"ok": True}


# ---------------- audit ----------------

@router.get("/api/admin/audit")
async def admin_audit(request: Request, limit: int = 100, offset: int = 0,
                      module: str = "", q: str = ""):
    require_perm(request, "audit.view")
    return {"entries": aa.audit_list(limit, offset, module[:40], q[:80]),
            "chain": aa.audit_verify_chain()}


# ---------------- settings ----------------

SETTINGS_KEYS = {
    "notify.emails": list,       # staff notification recipients
    "notify.whatsapp": str,      # staff WhatsApp number
    "site.defaultLanguage": str,  # published language (en now, ar later)
    "site.languages": list,
}


@router.get("/api/admin/settings")
async def admin_settings(request: Request):
    require_perm(request, "settings.manage")
    return {key: aa.setting_get(key) for key in SETTINGS_KEYS}


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/settings")
async def admin_settings_save(request: Request, body: SettingsBody,
                              x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    saved = []
    for key, value in body.values.items():
        expected = SETTINGS_KEYS.get(key)
        if expected is None or not isinstance(value, expected):
            raise HTTPException(status_code=400, detail=f"Unknown or invalid setting: {key[:60]}")
        if isinstance(value, list):
            value = [str(v)[:200] for v in value][:20]
        elif isinstance(value, str):
            value = value[:200]
        aa.setting_set(key, value)
        saved.append(key)
    aa.audit(session, "settings.updated", "settings", {"keys": saved}, _ip_hash(request))
    return {"saved": saved}


# ---------------- requests inbox (Phase 1) ----------------
# The encrypted submissions live in the public records store; decryption is
# an explicit admin action and every view/download lands in the audit log.

REQUEST_KINDS = ("giveaway_enquiry", "rental_enquiry", "contact", "career",
                 "giveaway_notification", "rental_notification")

_LIST_FIELDS = ("fullName", "company", "email", "market", "enquiryType", "service",
                "roleTitle", "eventCity")


def _decrypt_payload(record: dict) -> dict:
    import json as _json

    from . import storage as st
    try:
        return _json.loads(st.decrypt(record["payload"]).decode())
    except Exception:
        return {}


@router.get("/api/admin/requests")
async def admin_requests(request: Request, kind: str = "", q: str = "",
                         limit: int = 30, offset: int = 0):
    session = require_perm(request, "requests.view")
    from . import storage as st

    kinds = [kind] if kind in REQUEST_KINDS else list(REQUEST_KINDS)
    rows, total = st.list_records(kinds, limit=limit, offset=offset, q=q[:40])
    meta = aa.request_meta_bulk([r["reference"] for r in rows])
    out = []
    for r in rows:
        payload = _decrypt_payload(r)
        summary = {k: payload[k] for k in _LIST_FIELDS if payload.get(k)}
        summary["items"] = len(payload.get("items") or [])
        m = meta.get(r["reference"], {})
        out.append({"reference": r["reference"], "kind": r["kind"],
                    "createdAt": r["createdAt"], "hasFile": r["hasFile"],
                    "status": m.get("status", "new"), "assignee": m.get("assignee", ""),
                    "noteCount": m.get("noteCount", 0), "summary": summary})
    aa.audit(session, "requests.listed", "requests",
             {"kind": kind or "all", "count": len(out), "offset": offset}, _ip_hash(request))
    # requests without a workflow row yet are implicitly "new"
    counts = aa.request_status_counts()
    all_total = st.list_records(list(REQUEST_KINDS), limit=1)[1]
    counts["new"] = counts.get("new", 0) + max(0, all_total - sum(counts.values()))
    return {"requests": out, "total": total,
            "statuses": list(aa.REQUEST_STATUSES),
            "statusCounts": counts}


@router.get("/api/admin/requests/{reference}")
async def admin_request_detail(request: Request, reference: str):
    session = require_perm(request, "requests.view")
    from . import storage as st

    record = st.get_record(reference.strip().upper()[:20])
    if record is None or record["kind"] not in REQUEST_KINDS:
        raise HTTPException(status_code=404, detail="Unknown request reference.")
    aa.audit(session, "request.viewed", "requests", {"reference": record["reference"]},
             _ip_hash(request))
    return {"reference": record["reference"], "kind": record["kind"],
            "createdAt": record["createdAt"], "expiresAt": record["expiresAt"],
            "hasFile": bool(record["cvPath"]),
            "payload": _decrypt_payload(record),
            "meta": aa.request_meta_get(record["reference"])}


class RequestMetaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = Field(default=None, max_length=30)
    assignee: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/api/admin/requests/{reference}")
async def admin_request_update(request: Request, reference: str, body: RequestMetaBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "requests.manage")
    require_csrf(request, session, x_csrf)
    from . import storage as st

    record = st.get_record(reference.strip().upper()[:20])
    if record is None or record["kind"] not in REQUEST_KINDS:
        raise HTTPException(status_code=404, detail="Unknown request reference.")
    if body.status is not None and body.status not in aa.REQUEST_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    note = (body.note or "").strip() or None
    meta = aa.request_meta_set(record["reference"], by=session["email"],
                               status=body.status, assignee=body.assignee, note=note)
    aa.audit(session, "request.updated", "requests",
             {"reference": record["reference"], "status": body.status,
              "noteAdded": bool(note)}, _ip_hash(request))
    return {"meta": meta}


_FILE_TYPES = {"pdf": "application/pdf", "png": "image/png",
               "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


@router.get("/api/admin/requests/{reference}/file")
async def admin_request_file(request: Request, reference: str):
    session = require_perm(request, "requests.view")
    from . import storage as st

    record = st.get_record(reference.strip().upper()[:20])
    if record is None or record["kind"] not in REQUEST_KINDS or not record["cvPath"]:
        raise HTTPException(status_code=404, detail="No file attached to this request.")
    data = st.read_attachment(record["cvPath"])
    if data is None:
        raise HTTPException(status_code=404, detail="The attached file is no longer available.")
    # stored name is {reference}-{hex}.{ext}.enc — recover the real extension
    parts = record["cvPath"].split(".")
    ext = parts[-2].lower() if len(parts) >= 3 else "pdf"
    ctype = _FILE_TYPES.get(ext, "application/octet-stream")
    aa.audit(session, "request.file_downloaded", "requests",
             {"reference": record["reference"], "ext": ext}, _ip_hash(request))
    label = "cv" if record["kind"] == "career" else "logo"
    return Response(content=data, media_type=ctype, headers={
        "Content-Disposition": f'attachment; filename="{record["reference"]}-{label}.{ext}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ---------------- Jasani console (Phase 1) ----------------
# Status is read-only; refresh actions consume the documented daily budget
# and are therefore permission-gated, CSRF-protected and audited. The
# supplier token never appears in any response.

@router.get("/api/admin/jasani")
async def admin_jasani(request: Request):
    require_perm(request, "jasani.view")
    from . import jasani

    return {"budget": jasani.budget_status(),
            "markets": {m: jasani.cache_status(m) for m in config.JASANI_HOSTS},
            "manuals": jasani.manuals_status(),
            "refreshHours": {"products": config.PRODUCT_REFRESH_HOURS,
                             "stock": config.STOCK_REFRESH_HOURS},
            "tokenConfigured": bool(config.JASANI_API_TOKEN)}


class JasaniRefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str = Field(max_length=10)
    what: str = Field(max_length=20)  # "products" (2 calls) or "stock" (1 call)


@router.post("/api/admin/jasani/refresh")
async def admin_jasani_refresh(request: Request, body: JasaniRefreshBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "jasani.refresh")
    require_csrf(request, session, x_csrf)
    from . import jasani

    if body.market not in config.JASANI_HOSTS:
        raise HTTPException(status_code=400, detail="Unknown market.")
    if body.what not in ("products", "stock"):
        raise HTTPException(status_code=400, detail="Refresh either products or stock.")
    try:
        result = await jasani.force_refresh(body.market, body.what)
    except jasani.SupplierUnavailable as exc:
        aa.audit(session, "jasani.refresh_failed", "jasani",
                 {"market": body.market, "what": body.what, "reason": str(exc)[:200]},
                 _ip_hash(request))
        raise HTTPException(status_code=503, detail=f"Refresh failed: {exc}")
    aa.audit(session, "jasani.refreshed", "jasani",
             {"market": body.market, "what": body.what, "products": result.get("products")},
             _ip_hash(request))
    return {**result, "budget": jasani.budget_status()}


@router.get("/api/admin/jasani/products")
async def admin_jasani_products(request: Request, market: str = "ksa", q: str = ""):
    require_perm(request, "jasani.view")
    from . import jasani

    if market not in config.JASANI_HOSTS:
        raise HTTPException(status_code=400, detail="Unknown market.")
    return {"products": jasani.search_cached(market, q[:80])}


# ---------------- dashboard ----------------

@router.get("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    session = require_session(request)
    from . import storage as st

    counts: dict = {}
    try:
        conn = st._connect()
        for kind in ("giveaway_enquiry", "rental_enquiry", "contact", "career"):
            counts[kind] = conn.execute(
                "SELECT COUNT(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]
    except Exception:
        counts = {}
    return {"user": {"name": session["name"], "role": session["role"]},
            "requests": counts,
            "adminUsers": aa.user_count(),
            "audit": aa.audit_list(limit=8)}
