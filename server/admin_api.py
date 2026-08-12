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

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
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
    "analytics.enabled": bool,       # first-party measurement on/off
    "analytics.ga4Id": str,          # optional GA4 measurement id (G-XXXXXXX)
    "analytics.retentionDays": int,  # how long raw events are kept
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
        if expected is None or not isinstance(value, expected) or \
                (expected is int and isinstance(value, bool)) or \
                (expected is bool and not isinstance(value, bool)):
            raise HTTPException(status_code=400, detail=f"Unknown or invalid setting: {key[:60]}")
        if key == "analytics.ga4Id" and value and not re.match(r"^G-[A-Z0-9]{4,16}$", str(value)):
            raise HTTPException(status_code=400,
                                detail="A GA4 measurement id looks like G-XXXXXXXXXX.")
        if key == "analytics.retentionDays":
            value = max(30, min(1000, int(value)))
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
async def admin_requests(request: Request, kind: str = "", status: str = "", q: str = "",
                         limit: int = 30, offset: int = 0):
    session = require_perm(request, "requests.view")
    from . import storage as st

    kinds = [kind] if kind in REQUEST_KINDS else list(REQUEST_KINDS)
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    if status in aa.REQUEST_STATUSES:
        # workflow status lives in admin.db, so filter across the joined view
        all_rows, _ = st.list_records(kinds, limit=1000, q=q[:40])
        meta = aa.request_meta_bulk([r["reference"] for r in all_rows])
        all_rows = [r for r in all_rows
                    if meta.get(r["reference"], {}).get("status", "new") == status]
        total = len(all_rows)
        rows = all_rows[offset:offset + limit]
    else:
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


_EXPORT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _export_items(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        out.append({"reference": r["reference"], "kind": r["kind"],
                    "createdAt": r["createdAt"], "payload": _decrypt_payload(r),
                    "meta": aa.request_meta_get(r["reference"])})
    return out


def _export_response(items: list[dict], fmt: str, scope: str) -> Response:
    from . import exports

    rows = [exports.request_row(i) for i in items]
    if fmt == "csv":
        data = exports.to_csv(rows)
    elif fmt == "xlsx":
        data = exports.to_xlsx(rows)
    else:
        data = exports.to_pdf(items)
    name = exports.export_filename(fmt, scope)
    return Response(content=data, media_type=_EXPORT_TYPES[fmt], headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# NOTE: declared before /api/admin/requests/{reference} so "export" is never
# swallowed by the reference path parameter.
@router.get("/api/admin/requests/export")
async def admin_requests_export(request: Request, format: str = "csv", kind: str = "",
                                status: str = "", q: str = "", refs: str = ""):
    session = require_perm(request, "requests.view")
    from . import storage as st

    if format not in _EXPORT_TYPES:
        raise HTTPException(status_code=400, detail="Export as csv, xlsx or pdf.")
    if refs:
        wanted = [r.strip().upper()[:20] for r in refs.split(",") if r.strip()][:200]
        records = [rec for rec in (st.get_record(r) for r in wanted)
                   if rec and rec["kind"] in REQUEST_KINDS]
        scope = "selected"
    else:
        kinds = [kind] if kind in REQUEST_KINDS else list(REQUEST_KINDS)
        records, _ = st.list_records(kinds, limit=1000, q=q[:40])
        if status in aa.REQUEST_STATUSES:
            meta = aa.request_meta_bulk([r["reference"] for r in records])
            records = [r for r in records
                       if meta.get(r["reference"], {}).get("status", "new") == status]
        scope = kind or "all"
    if not records:
        raise HTTPException(status_code=404, detail="Nothing to export for this selection.")
    items = _export_items(records)
    aa.audit(session, "requests.exported", "requests",
             {"format": format, "count": len(items), "scope": scope}, _ip_hash(request))
    return _export_response(items, format, scope)


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


@router.get("/api/admin/requests/{reference}/export")
async def admin_request_export(request: Request, reference: str, format: str = "pdf"):
    session = require_perm(request, "requests.view")
    from . import storage as st

    if format not in _EXPORT_TYPES:
        raise HTTPException(status_code=400, detail="Export as csv, xlsx or pdf.")
    record = st.get_record(reference.strip().upper()[:20])
    if record is None or record["kind"] not in REQUEST_KINDS:
        raise HTTPException(status_code=404, detail="Unknown request reference.")
    items = _export_items([record])
    aa.audit(session, "request.exported", "requests",
             {"reference": record["reference"], "format": format}, _ip_hash(request))
    return _export_response(items, format, record["reference"].lower())


@router.post("/api/admin/requests/{reference}/delete")
async def admin_request_delete(request: Request, reference: str,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "requests.manage")
    require_csrf(request, session, x_csrf)
    from . import storage as st

    record = st.get_record(reference.strip().upper()[:20])
    if record is None or record["kind"] not in REQUEST_KINDS:
        raise HTTPException(status_code=404, detail="Unknown request reference.")
    st.delete_record(record["reference"])
    aa.request_meta_delete(record["reference"])
    aa.audit(session, "request.deleted", "requests",
             {"reference": record["reference"], "kind": record["kind"]}, _ip_hash(request))
    return {"ok": True}


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


# ---------------- media library & site assets (Phase 2) ----------------

def _media_err(exc: Exception) -> HTTPException:
    from .media import MediaError

    if isinstance(exc, MediaError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/api/admin/media")
async def admin_media(request: Request):
    require_perm(request, "media.manage")
    from . import media

    return {"library": media.library_list(), "siteAssets": media.site_assets(),
            "usage": media.storage_usage()}


@router.post("/api/admin/media/upload")
async def admin_media_upload(request: Request, file: UploadFile = File(...),
                             alt: str = Form(default=""),
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "media.manage")
    require_csrf(request, session, x_csrf)
    from . import media

    data = await file.read()
    try:
        item = media.ingest_library_image(data, file.filename or "image", alt, session["email"])
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "media.uploaded", "media",
             {"file": item["file"], "name": item["name"], "bytes": item["bytes"]},
             _ip_hash(request))
    return {"item": item}


class MediaAltBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alt: str = Field(max_length=300)


@router.post("/api/admin/media/{media_id}/alt")
async def admin_media_alt(request: Request, media_id: int, body: MediaAltBody,
                          x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "media.manage")
    require_csrf(request, session, x_csrf)
    from . import media

    if media.library_get(media_id) is None:
        raise HTTPException(status_code=404, detail="Unknown media item.")
    media.library_set_alt(media_id, body.alt)
    return {"ok": True}


@router.post("/api/admin/media/{media_id}/delete")
async def admin_media_delete(request: Request, media_id: int,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "media.manage")
    require_csrf(request, session, x_csrf)
    from . import media

    item = media.library_get(media_id)
    if item is None or not media.library_delete(media_id):
        raise HTTPException(status_code=404, detail="Unknown media item.")
    aa.audit(session, "media.deleted", "media", {"file": item["file"]}, _ip_hash(request))
    return {"ok": True}


@router.post("/api/admin/media/replace-asset")
async def admin_media_replace(request: Request, path: str = Form(...),
                              file: UploadFile = File(...),
                              x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "media.manage")
    require_csrf(request, session, x_csrf)
    from . import media

    data = await file.read()
    try:
        result = media.replace_site_asset(path, data, session["email"])
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "asset.replaced", "media", result, _ip_hash(request))
    return result


class AssetPathBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=300)


@router.post("/api/admin/media/reset-asset")
async def admin_media_reset(request: Request, body: AssetPathBody,
                            x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "media.manage")
    require_csrf(request, session, x_csrf)
    from . import media

    try:
        removed = media.reset_site_asset(body.path)
    except Exception as exc:
        raise _media_err(exc)
    if not removed:
        raise HTTPException(status_code=404, detail="This asset has no replacement to remove.")
    aa.audit(session, "asset.reset", "media", {"path": body.path}, _ip_hash(request))
    return {"ok": True}


# ---------------- website & brand (Phase 2) ----------------

@router.get("/api/admin/brand")
async def admin_brand(request: Request):
    require_perm(request, "brand.edit")
    from . import media

    tokens = media.get_brand_tokens()
    return {"tokens": tokens, "defaults": {k: v["default"] for k, v in media.TOKEN_DEFS.items()},
            "labels": {k: v["label"] for k, v in media.TOKEN_DEFS.items()},
            "warnings": media.contrast_warnings(tokens),
            "identity": media.identity_status(),
            "hero": media.get_hero_config(), "heroRanges": media.HERO_RANGES,
            "glb": media.glb_versions()}


class BrandTokensBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/brand/tokens")
async def admin_brand_tokens(request: Request, body: BrandTokensBody,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    try:
        saved = media.save_brand_tokens(body.values)
    except Exception as exc:
        raise _media_err(exc)
    warnings = media.contrast_warnings(media.get_brand_tokens())
    aa.audit(session, "brand.tokens_saved", "brand", {"keys": sorted(saved)}, _ip_hash(request))
    return {"saved": saved, "warnings": warnings}


@router.post("/api/admin/brand/identity")
async def admin_brand_identity(request: Request, slot: str = Form(...),
                               file: UploadFile = File(...),
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    data = await file.read()
    try:
        media.set_identity(slot, data, session["email"])
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "brand.identity_replaced", "brand", {"slot": slot}, _ip_hash(request))
    return {"ok": True}


class IdentitySlotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: str = Field(max_length=30)


@router.post("/api/admin/brand/identity/reset")
async def admin_brand_identity_reset(request: Request, body: IdentitySlotBody,
                                     x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    try:
        media.reset_identity(body.slot)
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "brand.identity_reset", "brand", {"slot": body.slot}, _ip_hash(request))
    return {"ok": True}


# ---------------- 3D hero / GLB manager (Phase 2) ----------------

@router.post("/api/admin/glb/upload")
async def admin_glb_upload(request: Request, file: UploadFile = File(...),
                           x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    data = await file.read()
    try:
        result = media.glb_upload(data, file.filename or "model.glb")
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "glb.uploaded", "brand", result, _ip_hash(request))
    return result


class GlbFileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str = Field(max_length=120)


@router.post("/api/admin/glb/activate")
async def admin_glb_activate(request: Request, body: GlbFileBody,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    try:
        media.glb_activate(body.file)
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "glb.activated", "brand", {"file": body.file}, _ip_hash(request))
    return {"ok": True}


@router.post("/api/admin/glb/reset")
async def admin_glb_reset(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    media.glb_reset()
    aa.audit(session, "glb.reset", "brand", {}, _ip_hash(request))
    return {"ok": True}


@router.post("/api/admin/glb/delete")
async def admin_glb_delete(request: Request, body: GlbFileBody,
                           x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    if not media.glb_delete_version(body.file):
        raise HTTPException(status_code=404, detail="Unknown model version.")
    aa.audit(session, "glb.version_deleted", "brand", {"file": body.file}, _ip_hash(request))
    return {"ok": True}


class HeroBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/hero")
async def admin_hero_save(request: Request, body: HeroBody,
                          x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "brand.edit")
    require_csrf(request, session, x_csrf)
    from . import media

    try:
        saved = media.save_hero_config(body.values)
    except Exception as exc:
        raise _media_err(exc)
    aa.audit(session, "hero.camera_saved", "brand", saved, _ip_hash(request))
    return {"saved": saved}


# ---------------- pages, SEO & publishing (Phase 3) ----------------

def _content_err(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/api/admin/pages")
async def admin_pages(request: Request):
    require_perm(request, "content.edit")
    from . import content

    from . import design

    last = content.last_publish()
    pages = []
    for page, cfg in content.PAGES.items():
        edited = max(content.last_edit_ts(page), design.last_design_edit(page))
        pages.append({"page": page, "label": cfg["label"], "file": cfg["file"],
                      "regions": len(cfg["regions"]),
                      "dirty": bool(edited and (last is None or edited > last["ts"]))})
    published = content.PUBLISHED_DIR.joinpath("index.html").is_file()
    return {"pages": pages,
            "staleBuild": bool(published and last and content.source_mtime() > last["ts"]),
            "globalRegions": len(content.GLOBAL_REGIONS),
            "lastPublish": last, "history": content.publish_history(),
            "published": content.PUBLISHED_DIR.joinpath("index.html").is_file(),
            "languages": aa.setting_get("site.languages") or ["en"]}


@router.get("/api/admin/pages/{page}")
async def admin_page_get(request: Request, page: str, lang: str = "en"):
    require_perm(request, "content.edit")
    from . import content

    if lang not in content.LANGS:
        raise HTTPException(status_code=400, detail="Unknown language.")
    if page == "_global":
        regions, seo, label = content.GLOBAL_REGIONS, [], "Header & Footer"
        originals = content.original_values("index")
    elif page in content.PAGES:
        cfg = content.PAGES[page]
        regions, seo, label = cfg["regions"], content.SEO_FIELDS, cfg["label"]
        originals = content.original_values(page)
    else:
        raise HTTPException(status_code=404, detail="Unknown page.")
    values = content.get_values(page, lang)
    return {"page": page, "label": label, "lang": lang,
            "regions": [{**r, "original": originals.get(r["key"], ""),
                         "value": values.get(r["key"], "")} for r in regions],
            "seo": [{**f, "original": originals.get(f["key"], ""),
                     "value": values.get(f["key"], "")} for f in seo]}


class PageSaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str = Field(default="en", max_length=5)
    values: dict


@router.post("/api/admin/pages/{page}")
async def admin_page_save(request: Request, page: str, body: PageSaveBody,
                          x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    try:
        saved = content.set_values(page, body.values, body.lang, session["email"])
    except Exception as exc:
        raise _content_err(exc)
    aa.audit(session, "content.saved", "pages",
             {"page": page, "lang": body.lang, "keys": sorted(saved)}, _ip_hash(request))
    return {"saved": saved}


@router.get("/admin/preview/{page}", include_in_schema=False)
async def admin_page_preview(request: Request, page: str, lang: str = "en"):
    require_perm(request, "content.edit")
    from . import content

    if page not in content.PAGES or lang not in content.LANGS:
        raise HTTPException(status_code=404, detail="Unknown page.")
    return Response(content=content.bake_page(page, lang),
                    media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/api/admin/design/{page}")
async def admin_design_get(request: Request, page: str):
    require_perm(request, "content.edit")
    from . import content, design

    if page != "_global" and page not in content.PAGES:
        raise HTTPException(status_code=404, detail="Unknown page.")
    return {"page": page, "doc": design.get_doc(page),
            "globalDoc": design.get_doc("_global") if page != "_global" else None,
            "animations": list(design.ANIMATIONS),
            "breakpoints": list(design.BREAKPOINTS)}


class DesignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc: dict


@router.post("/api/admin/design/{page}")
async def admin_design_save(request: Request, page: str, body: DesignBody,
                            x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content, design

    if page != "_global" and page not in content.PAGES:
        raise HTTPException(status_code=404, detail="Unknown page.")
    try:
        clean = design.set_doc(page, body.doc, session["email"])
    except design.DesignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "design.saved", "pages",
             {"page": page, "elements": len(clean["elements"]),
              "sections": bool(clean.get("sections"))}, _ip_hash(request))
    return {"doc": clean}


@router.get("/admin/visual/{page}", include_in_schema=False)
async def admin_page_visual(request: Request, page: str, lang: str = "en"):
    """The visual editor's iframe document: the draft-baked page with the
    click-to-edit bridge script injected (same-origin framing only)."""
    require_perm(request, "content.edit")
    from . import content

    if page not in content.PAGES or lang not in content.LANGS:
        raise HTTPException(status_code=404, detail="Unknown page.")
    baked = content.bake_page(page, lang)
    bridge = '<script src="/admin/assets/editor-bridge.js?v=2" defer></script></body>'
    baked = baked.replace("</body>", bridge, 1)
    return Response(content=baked, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.post("/api/admin/pages-publish")
async def admin_pages_publish(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    result = content.publish_all(session["email"])
    aa.audit(session, "site.published", "pages", result, _ip_hash(request))
    return result


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int


@router.post("/api/admin/pages-rollback")
async def admin_pages_rollback(request: Request, body: RollbackBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    try:
        result = content.rollback(body.id, session["email"])
    except Exception as exc:
        raise _content_err(exc)
    aa.audit(session, "site.rolledback", "pages", {"to": body.id, **result}, _ip_hash(request))
    return result


@router.post("/api/admin/pages-unpublish")
async def admin_pages_unpublish(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    removed = content.unpublish_all()
    aa.audit(session, "site.unpublished", "pages", {"removed": removed}, _ip_hash(request))
    return {"ok": True, "removed": removed}


# ---------------- rental inventory (Phase 3) ----------------

@router.get("/api/admin/rentals")
async def admin_rentals(request: Request):
    require_perm(request, "rentals.manage")
    from . import content

    products, source = content.rentals_load()
    return {"products": products, "source": source}


class RentalSaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: dict


@router.post("/api/admin/rentals/save")
async def admin_rentals_save(request: Request, body: RentalSaveBody,
                             x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "rentals.manage")
    require_csrf(request, session, x_csrf)
    from . import content

    try:
        item = content.rentals_save_item(body.product)
    except Exception as exc:
        raise _content_err(exc)
    aa.audit(session, "rental.saved", "rentals", {"id": item["id"], "name": item["name"]},
             _ip_hash(request))
    return {"product": item}


class RentalIdBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(max_length=80)


@router.post("/api/admin/rentals/delete")
async def admin_rentals_delete(request: Request, body: RentalIdBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "rentals.manage")
    require_csrf(request, session, x_csrf)
    from . import content

    if not content.rentals_delete_item(body.id):
        raise HTTPException(status_code=404, detail="Unknown rental item.")
    aa.audit(session, "rental.deleted", "rentals", {"id": body.id}, _ip_hash(request))
    return {"ok": True}


@router.post("/api/admin/rentals/reset")
async def admin_rentals_reset(request: Request, x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "rentals.manage")
    require_csrf(request, session, x_csrf)
    from . import content

    removed = content.rentals_reset()
    aa.audit(session, "rentals.reset", "rentals", {"removed": removed}, _ip_hash(request))
    return {"ok": True, "removed": removed}


# ---------------- site insights (Phase 5) ----------------

@router.get("/api/admin/insights")
async def admin_insights(request: Request, days: int = 30):
    session = require_perm(request, "insights.view")
    from . import analytics

    data = analytics.summary(days)
    data["settings"] = {
        "enabled": bool(aa.setting_get("analytics.enabled", True)),
        "ga4Id": aa.setting_get("analytics.ga4Id", "") or "",
        "retentionDays": int(aa.setting_get("analytics.retentionDays",
                                            analytics.RETENTION_DAYS_DEFAULT) or
                             analytics.RETENTION_DAYS_DEFAULT),
    }
    data["canManage"] = aa.has_perm(session["role"], "settings.manage")
    return data


@router.get("/api/admin/insights/export")
async def admin_insights_export(request: Request, days: int = 30):
    """Daily traffic table as CSV — for board decks and offline analysis."""
    session = require_perm(request, "insights.view")
    from . import analytics, exports

    data = analytics.summary(days)
    rows = [[r["day"], str(r["views"]), str(r["visitors"])] for r in data["series"]]
    header = ("Date", "Pageviews", "Visitors")
    buf = ["\ufeff" + ",".join(header)]
    buf.extend(",".join(r) for r in rows)
    aa.audit(session, "insights.exported", "insights", {"days": days}, _ip_hash(request))
    name = exports.export_filename("csv", f"traffic-{days}d")
    return Response(content="\r\n".join(buf).encode("utf-8"),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store"})


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
