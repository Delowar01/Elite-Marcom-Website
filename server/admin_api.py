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
from typing import Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import adminauth as aa
from . import blocks, config, security

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
    "site.defaultLanguage": str,  # published language (en now, ar later)
    "site.languages": list,
    "analytics.enabled": bool,       # first-party measurement on/off
    "analytics.ga4Id": str,          # optional GA4 measurement id (G-XXXXXXX)
    "analytics.retentionDays": int,  # how long raw events are kept
    "announce.enabled": bool,        # site-wide announcement bar
    "announce.text": str,
    "announce.link": str,
    "announce.linkLabel": str,
    "announce.style": str,
    "announce.startsAt": int,
    "announce.endsAt": int,
}
# one https:// profile URL per network, rendered as an icon in the footer
SETTINGS_KEYS.update({f"social.{key}": str for key in blocks.SOCIAL_KEYS})


@router.get("/api/admin/settings")
async def admin_settings(request: Request):
    require_perm(request, "settings.manage")
    from . import notify

    data = {key: aa.setting_get(key) for key in SETTINGS_KEYS}
    # whether the legacy SMTP alert route can actually deliver, so the screen
    # can say so rather than letting an admin fill in a field that does nothing
    data["notify.smtpConfigured"] = bool(getattr(notify, "SMTP_HOST", ""))
    # the networks the footer can render, so the screen and the bake agree on
    # the list rather than each keeping its own copy
    data["socialNetworks"] = blocks.SOCIAL_NETWORKS
    return data


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
        if key == "announce.link" and value and not re.match(r"^(https://|/|#|mailto:|tel:)", str(value)):
            raise HTTPException(status_code=400,
                                detail="The announcement link must be a site path or an https:// address.")
        if key.startswith("social.") and value and not blocks.SOCIAL_URL_RE.match(str(value)):
            raise HTTPException(
                status_code=400,
                detail="A social link must be a full https:// address, e.g. "
                       "https://www.instagram.com/yourbrand.")
        if key == "announce.style" and value not in ("brand", "quiet"):
            raise HTTPException(status_code=400, detail="Unknown announcement style.")
        if key in ("announce.startsAt", "announce.endsAt"):
            value = max(0, min(4102444800, int(value)))
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

    from . import supplier_video

    return {"budgets": jasani.budget_status_all(),
            "markets": {m: jasani.cache_status(m) for m in config.JASANI_HOSTS},
            "manuals": jasani.manuals_status(),
            # public-page video lookups: no API call, no budget — shown here so
            # the console accounts for every request we make to the supplier
            "videos": supplier_video.cache_status(),
            "refreshHours": {"products": config.PRODUCT_REFRESH_HOURS,
                             "prices": config.PRICE_REFRESH_HOURS,
                             "stock": config.STOCK_REFRESH_HOURS},
            "refreshCost": jasani.REFRESH_COST,
            "tokensConfigured": {m: bool(tok) for m, tok in config.JASANI_TOKENS.items()}}


class JasaniRefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str = Field(max_length=10)
    what: str = Field(max_length=20)  # products | prices | stock (1 call) or full (3)


@router.post("/api/admin/jasani/refresh")
async def admin_jasani_refresh(request: Request, body: JasaniRefreshBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "jasani.refresh")
    require_csrf(request, session, x_csrf)
    from . import jasani

    if body.market not in config.JASANI_HOSTS:
        raise HTTPException(status_code=400, detail="Unknown market.")
    if body.what not in jasani.REFRESH_COST:
        raise HTTPException(status_code=400,
                            detail="Refresh products, prices, stock or run a full sync.")
    # The reserved call exists so a person can always force a sync; only an
    # owner or admin may reach into it. Other roles with jasani.refresh keep
    # working against the automatic allowance.
    privileged = session["role"] in ("owner", "admin")
    try:
        result = await jasani.force_refresh(body.market, body.what, manual=privileged)
    except jasani.SupplierUnavailable as exc:
        aa.audit(session, "jasani.refresh_failed", "jasani",
                 {"market": body.market, "what": body.what, "reason": str(exc)[:200]},
                 _ip_hash(request))
        raise HTTPException(status_code=503, detail=f"Refresh failed: {exc}")
    aa.audit(session, "jasani.refreshed", "jasani",
             {"market": body.market, "what": body.what, "products": result.get("products")},
             _ip_hash(request))
    return {**result, "budgets": jasani.budget_status_all()}


def _f(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


@router.get("/api/admin/jasani/items")
async def admin_jasani_items(request: Request,
                             market: Literal["ksa", "uae"] = "ksa",
                             q: str = "", field: str = "all", stock: str = "",
                             brand: str = "", colour: str = "", category: str = "",
                             visibility: str = "", hideZero: bool = False,
                             priceMin: str = "", priceMax: str = "",
                             sort: str = "featured", page: int = 1, perPage: int = 25):
    """The Jasani items table. Reads the cached snapshot only — opening this
    page never spends one of the market's five daily supplier calls."""
    session = require_perm(request, "jasani.view")
    from . import jasani

    prices = aa.has_perm(session["role"], "jasani.prices")
    # Enter and comma both split; a pasted column arrives with newlines
    terms = [t.strip() for t in re.split(r"[,\n\t]", q or "") if t.strip()][:20]
    data = jasani.item_list(
        market, terms=terms, field=field, stock=stock, brand=brand, colour=colour,
        category=category, visibility=visibility, hide_zero=bool(hideZero),
        price_min=_f(priceMin), price_max=_f(priceMax),
        sort=sort, with_prices=prices)
    rows = data.pop("rows")
    per = max(10, min(200, perPage))
    pages = max(1, (len(rows) + per - 1) // per)
    page = max(1, min(pages, page))
    status = jasani.cache_status(market)
    return {**data, "market": market, "matched": len(rows), "page": page,
            "pages": pages, "perPage": per, "canSeePrices": prices,
            "canChangeVisibility": aa.has_perm(session["role"], "jasani.visibility"),
            "items": rows[(page - 1) * per: page * per],
            "snapshot": {"fetchedAt": status.get("fetchedAt"), "stockAt": status.get("stockAt"),
                         "productsFresh": status.get("productsFresh"),
                         "stockFresh": status.get("stockFresh"),
                         "cached": status.get("cached")},
            "markets": {m: jasani.cache_status(m).get("products", 0)
                        for m in config.JASANI_HOSTS}}


@router.get("/api/admin/jasani/items-export")
async def admin_jasani_items_export(request: Request, format: str = "csv",
                                    market: Literal["ksa", "uae"] = "ksa",
                                    q: str = "", field: str = "all", stock: str = "",
                                    brand: str = "", colour: str = "", category: str = "",
                                    visibility: str = "", hideZero: bool = False,
                                    priceMin: str = "", priceMax: str = "",
                                    sort: str = "featured", scope: str = "filtered"):
    """The item list as CSV, Excel or a branded PDF table."""
    session = require_perm(request, "jasani.view")
    from . import exports, jasani

    if format not in ("csv", "xlsx", "pdf"):
        raise HTTPException(status_code=400, detail="Unknown export format.")
    prices = aa.has_perm(session["role"], "jasani.prices")
    everything = scope == "all"
    terms = [] if everything else [t.strip() for t in re.split(r"[,\n\t]", q or "") if t.strip()][:20]
    data = jasani.item_list(
        market,
        terms=terms, field=field,
        stock="" if everything else stock,
        brand="" if everything else brand,
        colour="" if everything else colour,
        category="" if everything else category,
        visibility="" if everything else visibility,
        hide_zero=False if everything else bool(hideZero),
        price_min=None if everything else _f(priceMin),
        price_max=None if everything else _f(priceMax),
        sort=sort, with_prices=prices)
    items = data["rows"]
    currency = data["currency"]
    name = exports.export_filename(format, f"{market}-{scope}", prefix="jasani-items")
    if format == "pdf":
        blob = exports.items_to_pdf(items, market=market, with_prices=prices,
                                    currency=currency,
                                    note="whole snapshot" if everything else "filtered")
        media = "application/pdf"
    else:
        rows = exports.item_rows(items, prices, currency)
        blob = (exports.to_csv_rows(rows) if format == "csv"
                else exports.to_xlsx_rows(rows, sheet=f"Jasani {market.upper()}"))
        media = ("text/csv; charset=utf-8" if format == "csv"
                 else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    aa.audit(session, "jasani.items_exported", "jasani",
             {"market": market, "format": format, "scope": scope, "rows": len(items),
              "withPrices": prices}, _ip_hash(request))
    return Response(content=blob, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "no-store"})


def _sheet_specs(item: dict) -> list[tuple[str, str]]:
    """The specification rows a customer sheet carries — no price among them."""
    pairs = [
        ("Supplier code", item.get("code", "")),
        ("Brand", item.get("brand", "")),
        ("Colour", item.get("color", "")),
        ("Category", ", ".join(item.get("categories") or [])),
        ("Units per carton", item.get("unitsPerCarton")),
        ("Carton size", item.get("cartonDimensions")),
        ("Carton weight", f"{item['cartonWeight']} kg" if item.get("cartonWeight") else ""),
        ("Carton volume", f"{item['cartonVolume']} m³" if item.get("cartonVolume") else ""),
        ("HS code", item.get("hsCode", "")),
        ("Barcode", item.get("barcode", "")),
        ("Options", ", ".join(item.get("options") or [])[:80]),
    ]
    return [(k, str(v)) for k, v in pairs if v not in (None, "", [])]


@router.get("/api/admin/jasani/items/{market}/{product_id}/sheet")
async def admin_jasani_item_sheet(request: Request, market: Literal["ksa", "uae"],
                                  product_id: str):
    """A branded one-page product sheet, deliberately without any price."""
    require_perm(request, "jasani.view")
    from . import exports, jasani, supplier_video

    item = jasani.item_detail(market, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That item is not in the cached catalogue.")
    # a video's poster is not a photograph of the product; it does not belong
    # in a document that goes to a customer
    item["images"] = supplier_video.without_posters(
        item.get("images"), await supplier_video.videos_for(market, item))
    photos: list[bytes] = []
    for url in (item.get("images") or [])[:4]:
        blob = await jasani._fetch_image_bytes(url)
        if blob:
            photos.append(blob)
    blob = exports.product_sheet_pdf({**item, "specs": _sheet_specs(item)}, photos)
    code = re.sub(r"[^A-Za-z0-9._-]+", "-", item.get("code") or item["id"]).strip("-")
    return Response(content=blob, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="elite-marcom-{code or "item"}.pdf"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/api/admin/jasani/items/{market}/{product_id}")
async def admin_jasani_item(request: Request, market: Literal["ksa", "uae"], product_id: str):
    session = require_perm(request, "jasani.view")
    from . import jasani, supplier_video

    item = jasani.item_detail(market, product_id,
                              with_prices=aa.has_perm(session["role"], "jasani.prices"))
    if item is None:
        raise HTTPException(status_code=404, detail="That item is not in the cached catalogue.")
    # The same public-page lookup the website uses, off the same cache: an
    # admin looking at an item sees the video the customer sees, and not the
    # poster sitting in the gallery as a still nobody can play.
    item["videos"] = await supplier_video.videos_for(market, item)
    item["images"] = supplier_video.without_posters(item.get("images"), item["videos"])
    return {"item": item, "lowThreshold": config.LOW_STOCK_THRESHOLD,
            "currency": jasani.CURRENCY_BY_MARKET.get(market, ""),
            "canChangeVisibility": aa.has_perm(session["role"], "jasani.visibility")}


class ItemVisibilityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Literal["ksa", "uae"]
    productId: str = Field(max_length=80)
    hidden: bool


@router.post("/api/admin/jasani/visibility")
async def admin_jasani_visibility(request: Request, body: ItemVisibilityBody,
                                  x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "jasani.visibility")
    require_csrf(request, session, x_csrf)
    from . import jasani

    item = jasani.item_detail(body.market, body.productId)
    if item is None:
        raise HTTPException(status_code=404, detail="That item is not in the cached catalogue.")
    jasani.set_item_hidden(body.market, item["id"], body.hidden,
                           code=item["code"], name=item["name"], by=session["email"])
    aa.audit(session, "jasani.item_hidden" if body.hidden else "jasani.item_shown", "jasani",
             {"market": body.market, "id": item["id"], "code": item["code"]}, _ip_hash(request))
    return {"ok": True, "hidden": body.hidden,
            "hiddenItems": jasani.hidden_items(body.market)}


class ZeroStockRuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: Literal["ksa", "uae"]
    on: bool


@router.post("/api/admin/jasani/zero-stock-rule")
async def admin_jasani_zero_rule(request: Request, body: ZeroStockRuleBody,
                                 x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "jasani.visibility")
    require_csrf(request, session, x_csrf)
    from . import jasani

    jasani.set_hide_zero_stock(body.market, body.on)
    aa.audit(session, "jasani.zero_stock_rule", "jasani",
             {"market": body.market, "on": body.on}, _ip_hash(request))
    return {"ok": True, "on": body.on}


@router.get("/api/admin/jasani/visibility")
async def admin_jasani_visibility_state(request: Request,
                                        market: Literal["ksa", "uae"] = "ksa"):
    require_perm(request, "jasani.view")
    from . import jasani

    products = jasani.all_products(market)
    zero = sum(1 for p in products
               if int((p.get("stock") or {}).get("available", 0) or 0) <= 0)
    return {"market": market, "hideZeroStock": jasani.hide_zero_stock(market),
            "zeroStockCount": zero, "cached": len(products),
            "hiddenItems": jasani.hidden_items(market)}


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
            "usage": media.storage_usage(), "placed": media.library_usage()}


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
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown media item.")
    try:
        deleted = media.library_delete(media_id)
    except Exception as exc:
        raise _media_err(exc)
    if not deleted:
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
    from . import collections as collections_mod
    from . import content, design, media

    last = content.last_publish()
    # an item added or reordered on the Sections screen is an unpublished edit
    # to its page too, or the Pages screen would say the site was up to date
    coll_edit = {}
    coll_ts = collections_mod.last_edit_ts()
    if coll_ts:
        for spec in collections_mod.SCHEMAS.values():
            if spec["page"] in collections_mod.GLOBAL_PAGES:
                # the header and the footer are on every page, so editing one
                # leaves every page waiting to be published
                for page in content.all_pages():
                    coll_edit[page] = coll_ts
            else:
                coll_edit[spec["page"]] = coll_ts
    # the default theme is baked into the markup, so changing it leaves every
    # page waiting to publish in exactly the way a text edit does
    theme_ts = media.theme_changed_at()
    pages = []
    for page, cfg in content.all_pages().items():
        edited = max(content.last_edit_ts(page), design.last_design_edit(page),
                     coll_edit.get(page, 0), theme_ts)
        pages.append({"page": page, "label": cfg["label"], "file": cfg["file"],
                      "regions": len(cfg["regions"]),
                      "custom": bool(cfg.get("custom")), "nav": bool(cfg.get("nav")),
                      "title": cfg.get("title", ""), "description": cfg.get("description", ""),
                      "dirty": bool(edited and (last is None or edited > last["ts"]))})
    published = content.PUBLISHED_DIR.joinpath("index.html").is_file()
    return {"pages": pages,
            "staleBuild": bool(published and last and content.source_mtime() > last["ts"]),
            "globalRegions": len(content.GLOBAL_REGIONS),
            "lastPublish": last, "history": content.publish_history(),
            "keepVersions": content.KEEP_PUBLISHES,
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
    else:
        cfg = content.page_config(page)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Unknown page.")
        regions, seo, label = cfg["regions"], content.SEO_FIELDS, cfg["label"]
        originals = content.original_values(page)
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

    if content.page_config(page) is None or lang not in content.LANGS:
        raise HTTPException(status_code=404, detail="Unknown page.")
    return Response(content=content.bake_page(page, lang),
                    media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/api/admin/design/{page}")
async def admin_design_get(request: Request, page: str):
    require_perm(request, "content.edit")
    from . import content, design

    if page != "_global" and content.page_config(page) is None:
        raise HTTPException(status_code=404, detail="Unknown page.")
    return {"page": page, "doc": design.get_doc(page),
            "globalDoc": design.get_doc("_global") if page != "_global" else None,
            "animations": list(design.ANIMATIONS),
            "breakpoints": list(design.BREAKPOINTS)}


@router.get("/api/admin/design-hidden")
async def admin_design_hidden(request: Request):
    """Everything currently hidden anywhere on the site."""
    require_perm(request, "content.edit")
    from . import design

    return {"hidden": design.hidden_index(), "breakpoints": list(design.BREAKPOINTS)}


class UnhideBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: str = Field(max_length=60)
    kind: str = Field(max_length=12)
    path: str = Field(max_length=300)


@router.post("/api/admin/design-hidden/restore")
async def admin_design_unhide(request: Request, body: UnhideBody,
                              x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import design

    if body.kind not in ("element", "section"):
        raise HTTPException(status_code=400, detail="Unknown kind.")
    if not design.unhide(body.page, body.kind, body.path, session["email"]):
        raise HTTPException(status_code=404, detail="That item is no longer hidden.")
    aa.audit(session, "design.unhidden", "content",
             {"page": body.page, "kind": body.kind, "path": body.path}, _ip_hash(request))
    return {"ok": True, "hidden": design.hidden_index()}


class DesignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc: dict


@router.post("/api/admin/design/{page}")
async def admin_design_save(request: Request, page: str, body: DesignBody,
                            x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content, design

    if page != "_global" and content.page_config(page) is None:
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

    if content.page_config(page) is None or lang not in content.LANGS:
        raise HTTPException(status_code=404, detail="Unknown page.")
    baked = content.bake_page(page, lang)
    bridge = '<script src="/admin/assets/editor-bridge.js?v=5" defer></script></body>'
    baked = baked.replace("</body>", bridge, 1)
    return Response(content=baked, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/api/admin/section-copy")
async def admin_section_copy(request: Request, page: str, sec: str):
    """The markup of one of our sections, restamped — what the editor shows as
    a live preview of a pasted copy. Rendering stays server-side so the preview
    and the published page are produced by the same code."""
    require_perm(request, "content.edit")
    from . import content, design

    if content.page_config(page) is None:
        raise HTTPException(status_code=404, detail="Unknown page.")
    html = design.section_from_page(page, sec, "__ID__")
    if not html:
        raise HTTPException(status_code=404, detail="That section is no longer on the page.")
    return {"html": html}


@router.get("/api/admin/blocks")
async def admin_blocks(request: Request):
    """The section templates the editor can drop into a page."""
    require_perm(request, "content.edit")

    # the editor needs the markup itself so an added block appears in the live
    # preview before the draft is saved; __ID__ is swapped for the section id
    return {"blocks": [{**b, "html": blocks.render_section(b["id"], "__ID__")}
                       for b in blocks.template_list()],
            # the element library for a blank section: the editor drops these
            # in and then edits their text, picture and styling like any other
            "elements": [{**e, "html": blocks.render_element(e["id"], "__EID__")}
                         for e in blocks.element_list()],
            "max": 30, "maxElements": 40}


class NewPageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(max_length=60)
    label: str = Field(max_length=80)
    title: str = Field(default="", max_length=220)
    description: str = Field(default="", max_length=400)
    nav: bool = True


@router.post("/api/admin/pages-new")
async def admin_page_new(request: Request, body: NewPageBody,
                         x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    try:
        created = content.page_create(body.slug, body.label, body.title,
                                      body.description, body.nav, session["email"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "page.created", "pages", created, _ip_hash(request))
    return {"page": created}


class PageMetaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=220)
    description: str | None = Field(default=None, max_length=400)
    nav: bool | None = None


@router.post("/api/admin/pages-meta/{page}")
async def admin_page_meta(request: Request, page: str, body: PageMetaBody,
                          x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    try:
        updated = content.page_update(page, body.label, body.title, body.description, body.nav)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "page.updated", "pages", updated, _ip_hash(request))
    return {"page": updated}


@router.post("/api/admin/pages-delete/{page}")
async def admin_page_delete(request: Request, page: str,
                            x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import content

    if page in content.PAGES:
        raise HTTPException(status_code=400,
                            detail="Built-in pages cannot be deleted — hide their sections instead.")
    if not content.page_delete(page):
        raise HTTPException(status_code=404, detail="Unknown page.")
    aa.audit(session, "page.deleted", "pages", {"page": page}, _ip_hash(request))
    return {"deleted": page}


# ---------------- repeatable content: the items inside a section ----------------
# Sections are the design layer's business; the items inside one are this.
# Everything an admin sends is a field value — never markup — and the renderer
# in collections.py writes every tag.

def _collection_err(exc: Exception) -> HTTPException:
    from . import collections as collections_mod

    if isinstance(exc, collections_mod.CollectionError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/api/admin/collections")
async def admin_collections(request: Request):
    require_perm(request, "content.edit")
    from . import collections as collections_mod

    return {"collections": collections_mod.summary(),
            "pages": collections_mod.page_groups()}


@router.get("/api/admin/collections/{name}")
async def admin_collection(request: Request, name: str):
    require_perm(request, "content.edit")
    from . import collections as collections_mod

    try:
        spec = collections_mod.public_schema(name)
        rows = collections_mod.items(name)
    except collections_mod.CollectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"collection": spec, "items": rows,
            "managed": collections_mod.is_managed(name)}


class CollectionItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/collections/{name}/items")
async def admin_collection_add(request: Request, name: str, body: CollectionItemBody,
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        item = collections_mod.add_item(name, body.values, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    aa.audit(session, "collection.item.added", "content",
             {"collection": name, "item": item["id"]}, _ip_hash(request))
    return {"item": item}


@router.post("/api/admin/collections/{name}/items/{item_id}")
async def admin_collection_save(request: Request, name: str, item_id: str,
                                body: CollectionItemBody,
                                x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        item = collections_mod.update_item(name, item_id, body.values, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    aa.audit(session, "collection.item.saved", "content",
             {"collection": name, "item": item_id}, _ip_hash(request))
    return {"item": item}


@router.post("/api/admin/collections/{name}/duplicate/{item_id}")
async def admin_collection_duplicate(request: Request, name: str, item_id: str,
                                     x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        item = collections_mod.duplicate_item(name, item_id, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    aa.audit(session, "collection.item.duplicated", "content",
             {"collection": name, "from": item_id, "item": item["id"]}, _ip_hash(request))
    return {"item": item}


class CollectionHiddenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hidden: bool


@router.post("/api/admin/collections/{name}/hidden/{item_id}")
async def admin_collection_hidden(request: Request, name: str, item_id: str,
                                  body: CollectionHiddenBody,
                                  x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        ok = collections_mod.set_hidden(name, item_id, body.hidden, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    if not ok:
        raise HTTPException(status_code=404, detail="That item is no longer in the list.")
    aa.audit(session, "collection.item.visibility", "content",
             {"collection": name, "item": item_id, "hidden": body.hidden}, _ip_hash(request))
    return {"hidden": body.hidden}


class CollectionOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[str] = Field(default_factory=list, max_length=200)


@router.post("/api/admin/collections/{name}/order")
async def admin_collection_order(request: Request, name: str, body: CollectionOrderBody,
                                 x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        rows = collections_mod.reorder(name, [str(i)[:40] for i in body.order], session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    aa.audit(session, "collection.reordered", "content",
             {"collection": name, "order": [r["id"] for r in rows]}, _ip_hash(request))
    return {"items": rows}


@router.post("/api/admin/collections/{name}/delete/{item_id}")
async def admin_collection_delete(request: Request, name: str, item_id: str,
                                  x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        gone = collections_mod.delete_item(name, item_id, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    if not gone:
        raise HTTPException(status_code=404, detail="That item is no longer in the list.")
    aa.audit(session, "collection.item.deleted", "content",
             {"collection": name, "item": item_id}, _ip_hash(request))
    return {"deleted": item_id}


@router.post("/api/admin/collections/{name}/reset")
async def admin_collection_reset(request: Request, name: str,
                                 x_csrf: str | None = Header(default=None)):
    """Hand the list back to the shipped page — the panel's copy is dropped."""
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import collections as collections_mod

    try:
        rows = collections_mod.reset(name, session["email"])
    except Exception as exc:
        raise _collection_err(exc)
    aa.audit(session, "collection.reset", "content", {"collection": name}, _ip_hash(request))
    return {"items": rows}


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
async def admin_insights(request: Request, days: int = 30, start: str = "", end: str = ""):
    session = require_perm(request, "insights.view")
    from . import analytics, ga4

    data = analytics.summary(days, start[:10], end[:10])
    data["settings"] = {
        "enabled": bool(aa.setting_get("analytics.enabled", True)),
        "ga4Id": aa.setting_get("analytics.ga4Id", "") or "",
        "retentionDays": int(aa.setting_get("analytics.retentionDays",
                                            analytics.RETENTION_DAYS_DEFAULT) or
                             analytics.RETENTION_DAYS_DEFAULT),
    }
    data["canManage"] = aa.has_perm(session["role"], "settings.manage")
    # the reporting integration's own state, so the settings panel can say
    # whether Google is connected without making a Google call to find out
    data["ga4Status"] = ga4.status()
    return data


@router.get("/api/admin/insights/ga4")
async def admin_insights_ga4(request: Request, days: int = 30, start: str = "", end: str = ""):
    """Everything the dashboard reads from Google, in one request. Loaded
    separately from the first-party payload so a slow or broken Google leaves
    the rest of Site Insights on screen and interactive."""
    require_perm(request, "insights.view")
    from . import analytics, ga4

    start, end, days = analytics.parse_range(start[:10], end[:10], days)
    data = await ga4.dashboard(start, end)
    # the connection state *after* these reports ran: read before them it would
    # say "never" on the very load that just succeeded
    return {"days": days, **data, "status": ga4.status()}


@router.get("/api/admin/insights/realtime")
async def admin_insights_realtime(request: Request):
    require_perm(request, "insights.view")
    from . import ga4

    return await ga4.realtime()


@router.post("/api/admin/insights/ga4-test")
async def admin_insights_ga4_test(request: Request):
    """One live report, cache bypassed. Owner/admin only: it is the action
    that proves a credential works, so it belongs with the settings."""
    session = require_perm(request, "settings.manage")
    from . import ga4

    result = await ga4.test_connection()
    aa.audit(session, "insights.ga4_test", "analytics",
             {"ok": bool(result.get("ok"))}, _ip_hash(request))
    return result


_INSIGHT_TYPES = {"csv": "text/csv; charset=utf-8",
                  "pdf": "application/pdf",
                  "html": "text/html; charset=utf-8"}


@router.get("/api/admin/insights/export")
async def admin_insights_export(request: Request, days: int = 30, start: str = "",
                                end: str = "", format: str = "csv"):
    """The same report as the dashboard, as CSV, a branded PDF or a
    self-contained HTML file that can be emailed or printed."""
    session = require_perm(request, "insights.view")
    from . import analytics, exports, reports

    if format not in _INSIGHT_TYPES:
        raise HTTPException(status_code=400, detail="Export as csv, pdf or html.")
    data = analytics.summary(days, start[:10], end[:10])
    if format == "pdf":
        payload = reports.insights_pdf(data)
    elif format == "html":
        payload = reports.insights_html(data).encode("utf-8")
    else:
        buf = ["\ufeff" + ",".join(("Date", "Pageviews", "Visitors"))]
        buf.extend(f'{r["day"]},{r["views"]},{r["visitors"]}' for r in data["series"])
        payload = "\r\n".join(buf).encode("utf-8")
    aa.audit(session, "insights.exported", "insights",
             {"format": format, "start": data["start"], "end": data["end"]}, _ip_hash(request))
    name = exports.export_filename(format, f'{data["start"]}-to-{data["end"]}',
                                   prefix="insights")
    return Response(content=payload, media_type=_INSIGHT_TYPES[format],
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


# ---------------- operations: backups, schedule, security (Phase 6) ----------------

@router.get("/api/admin/operations")
async def admin_operations(request: Request):
    require_perm(request, "settings.manage")
    from . import analytics, backup, content

    users = aa.list_users()
    audit_recent = aa.audit_list(limit=400)
    week_ago = time.time() - 7 * 86400
    failed = [e for e in audit_recent if e["action"] == "login.failed" and e["ts"] >= week_ago]
    sessions = sum(len(aa.list_sessions(u["id"])) for u in users if u["active"])
    owners = [u for u in users if u["role"] == "owner" and u["active"]]
    no_2fa = [u["email"] for u in users if u["active"] and not u["totp_enabled"]]
    never = [u["email"] for u in users if u["active"] and not u["last_login_at"]]

    checks = []

    def check(ok, label, detail, weight="high"):
        checks.append({"ok": bool(ok), "label": label, "detail": detail, "weight": weight})

    check(config.IS_PROD, "Production mode",
          "Running in production." if config.IS_PROD
          else "Development mode — fine while testing, switch EM_ENV=production when live.",
          "info")
    check(any(o.startswith("https://") for o in config.ALLOWED_ORIGINS), "HTTPS origin",
          "An https:// origin is configured." if any(o.startswith("https://") for o in config.ALLOWED_ORIGINS)
          else "No https:// origin configured yet — required before going live.")
    check(bool(config.TURNSTILE_SECRET and config.TURNSTILE_SITE_KEY), "Bot protection",
          "Cloudflare Turnstile is configured." if config.TURNSTILE_SECRET
          else "Turnstile keys are not set — public forms lose their bot check in production.")
    check(not no_2fa, "Two-factor authentication",
          "Every active account has completed 2FA." if not no_2fa
          else f"Waiting for first sign-in / 2FA setup: {', '.join(no_2fa[:4])}", "info")
    chain = aa.audit_verify_chain()
    check(chain["ok"], "Activity log integrity",
          f"{chain['checked']} entries verified, chain intact." if chain["ok"]
          else f"Chain broken at entry {chain['brokenAt']} — investigate immediately.")
    check(len(owners) >= 2, "Owner accounts",
          f"{len(owners)} active owner account{'' if len(owners) == 1 else 's'}." +
          ("" if len(owners) >= 2 else " Consider a second owner so access is never lost."), "info")
    check(len(failed) < 20, "Failed sign-ins (7 days)",
          f"{len(failed)} failed attempt{'' if len(failed) == 1 else 's'} in the last 7 days.")
    check(bool(config.JASANI_API_TOKEN), "Supplier token",
          "Jasani token is configured (never shown here)." if config.JASANI_API_TOKEN
          else "No supplier token set — the gifts catalog serves cached data only.", "info")
    last_backup = int(aa.setting_get("backup.lastAt", 0) or 0)
    check(last_backup and last_backup > time.time() - 30 * 86400, "Recent backup",
          f"Last backup {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(last_backup))}."
          if last_backup else "No backup has been downloaded yet.", "info")

    gates = [c for c in checks if c["weight"] != "info"]
    return {
        "checks": checks,
        "score": sum(1 for c in gates if c["ok"]),
        "total": len(gates),
        "advisories": sum(1 for c in checks if c["weight"] == "info" and not c["ok"]),
        "sessions": sessions,
        "users": {"total": len(users), "active": sum(1 for u in users if u["active"]),
                  "owners": len(owners), "neverSignedIn": never},
        "failedLogins": [{"ts": e["ts"], "email": e["user_email"], "detail": e["detail"][:80]}
                         for e in failed[:10]],
        "schedule": backup.get_schedule(),
        "lastPublish": content.last_publish(),
        "lastBackup": last_backup,
        "announcement": {key: aa.setting_get(key, "" if key not in
                                             ("announce.enabled", "announce.startsAt", "announce.endsAt")
                                             else (False if key == "announce.enabled" else 0))
                         for key in ("announce.enabled", "announce.text", "announce.link",
                                     "announce.linkLabel", "announce.style",
                                     "announce.startsAt", "announce.endsAt")},
        "retention": {"submissions": config.RETENTION_SUBMISSIONS_DAYS,
                      "careers": config.RETENTION_CAREERS_DAYS,
                      "insights": int(aa.setting_get("analytics.retentionDays",
                                                     analytics.RETENTION_DAYS_DEFAULT) or 0)},
        "languages": aa.setting_get("site.languages") or ["en"],
    }


@router.get("/api/admin/backup")
async def admin_backup_download(request: Request):
    session = require_perm(request, "settings.manage")
    from . import backup, exports

    blob, manifest = backup.create()
    aa.setting_set("backup.lastAt", int(time.time()))
    aa.audit(session, "backup.downloaded", "operations",
             {"bytes": manifest["bytes"], "mediaFiles": manifest["mediaFiles"]}, _ip_hash(request))
    name = exports.export_filename("zip", manifest["createdAtHuman"][:10], prefix="backup")
    return Response(content=blob, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Cache-Control": "no-store"})


@router.post("/api/admin/backup/restore")
async def admin_backup_restore(request: Request, file: UploadFile = File(...),
                               confirm: str = Form(default=""),
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import backup

    if confirm != "RESTORE":
        raise HTTPException(status_code=400,
                            detail='Type RESTORE to confirm — this replaces the current content.')
    blob = await file.read()
    try:
        info = backup.restore(blob, session["email"])
    except backup.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "backup.restored", "operations",
             {"counts": info["counts"], "files": info.get("restoredFiles", 0)}, _ip_hash(request))
    return info


@router.post("/api/admin/backup/inspect")
async def admin_backup_inspect(request: Request, file: UploadFile = File(...),
                               x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import backup

    try:
        return backup.inspect(await file.read())
    except backup.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ScheduleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: int = 0


@router.post("/api/admin/schedule-publish")
async def admin_schedule_publish(request: Request, body: ScheduleBody,
                                 x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "content.edit")
    require_csrf(request, session, x_csrf)
    from . import backup

    try:
        schedule = backup.set_schedule(body.at, session["email"])
    except backup.BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "publish.scheduled" if body.at else "publish.schedule_cleared",
             "pages", {"at": body.at}, _ip_hash(request))
    return schedule


# ---------------- email settings & notifications (Resend) ----------------
# The Resend API key is environment-only: it is never read into, stored in or
# returned by any of these endpoints.

@router.get("/api/admin/email")
async def admin_email(request: Request):
    require_perm(request, "settings.manage")
    from . import mailer

    data = mailer.all_settings()
    data["log"] = mailer.log_entries(30)
    data["stats"] = mailer.log_stats()
    data["queued"] = mailer.outbox_pending()
    return data


class EmailGeneralBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/email/general")
async def admin_email_general(request: Request, body: EmailGeneralBody,
                              x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import mailer

    try:
        saved = mailer.save_general(body.values)
    except mailer.MailError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "email.settings_saved", "email",
             {"fields": sorted(body.values)}, _ip_hash(request))
    return {"general": saved}


class EmailFormBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


@router.post("/api/admin/email/form/{form_key}")
async def admin_email_form(request: Request, form_key: str, body: EmailFormBody,
                           x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import mailer

    try:
        saved = mailer.save_form(form_key, body.values)
    except mailer.MailError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    aa.audit(session, "email.form_saved", "email",
             {"form": form_key, "fields": sorted(body.values)}, _ip_hash(request))
    return {"form": saved}


class EmailPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: str = Field(max_length=40)
    values: dict = Field(default_factory=dict)
    audience: str = Field(default="customer", max_length=10)


@router.post("/api/admin/email/preview")
async def admin_email_preview(request: Request, body: EmailPreviewBody,
                              x_csrf: str | None = Header(default=None)):
    """Render the template with sample data — nothing is saved or sent."""
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import mailer

    if body.form not in mailer.FORMS:
        raise HTTPException(status_code=404, detail="Unknown form.")
    settings = mailer.form_settings(body.form)
    for field in ("customerSubject", "internalSubject", "heading", "body",
                  "closing", "buttonText", "buttonUrl"):
        if field in body.values:
            text = str(body.values[field] or "")[:4000]
            try:
                mailer._check_variables(text, body.form)
            except mailer.MailError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            settings[field] = text
    general = mailer.general_settings()
    sample = {
        "fullName": "Amira Hassan", "company": "Falcon Corporate Events",
        "email": "amira@example.com", "phone": "+966 55 123 4567", "market": "ksa",
        "service": "Exhibition Stands", "roleTitle": "Senior 3D Designer",
        "location": "Riyadh", "enquiryType": "New project",
        "items": [{"name": "A5 Eco Notebook", "code": "ITGL 1291", "quantity": 250}],
    }
    reference = "GV-SAMPLE-01"
    values = mailer.variables_for(body.form, sample, reference)
    if body.audience == "internal":
        html = mailer.internal_html(body.form, general, sample, reference)
        subject = mailer.render(settings["internalSubject"], values, escape=False)
    else:
        html = mailer.customer_html(body.form, settings, general, values)
        subject = mailer.render(settings["customerSubject"], values, escape=False)
    # the preview is rendered inside the admin origin, where an absolute
    # elitemarcom.com image is blocked by our own CSP — swap it for the local
    # copy so the preview looks exactly like the delivered email
    html = html.replace(f'{general["websiteUrl"]}/assets/logo-email.png',
                        "/assets/logo-email.png")
    return {"subject": subject, "html": html,
            "from": f'{general["fromName"]} <{general["fromEmail"]}>',
            "replyTo": general["replyTo"]}


class EmailRetryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(default="", max_length=20)
    all: bool = False


@router.post("/api/admin/email/retry")
async def admin_email_retry(request: Request, body: EmailRetryBody,
                            x_csrf: str | None = Header(default=None)):
    """Put failed deliveries back in the queue — never duplicates a send that
    already succeeded, and never re-creates the customer's submission."""
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    from . import mailer

    if not body.all and not body.reference:
        raise HTTPException(status_code=400, detail="Choose a delivery to retry.")
    requeued = mailer.retry_failed(reference=body.reference.strip().upper())
    aa.audit(session, "email.retried", "email",
             {"reference": body.reference or "all", "requeued": requeued}, _ip_hash(request))
    return {"requeued": requeued}


class EmailTestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str = Field(max_length=200)


@router.post("/api/admin/email/test")
async def admin_email_test(request: Request, body: EmailTestBody,
                           x_csrf: str | None = Header(default=None)):
    session = require_perm(request, "settings.manage")
    require_csrf(request, session, x_csrf)
    security.limiter.check("email_test", _ip_hash(request), 10, 600)
    from . import mailer

    try:
        mailer.send_test(body.to.strip(), session["email"])
    except mailer.MailError as exc:
        aa.audit(session, "email.test_failed", "email", {"to": body.to[:120]}, _ip_hash(request))
        # friendly wording only — provider detail stays in the server log
        raise HTTPException(status_code=502, detail=str(exc))
    aa.audit(session, "email.test_sent", "email", {"to": body.to[:120]}, _ip_hash(request))
    return {"ok": True}


# ---------------- dashboard ----------------

@router.get("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    session = require_session(request)
    from . import storage as st

    import time as _time

    from . import content, jasani, mailer

    KINDS = ("giveaway_enquiry", "giveaway_notification", "rental_enquiry",
             "rental_notification", "contact", "career")
    now = int(_time.time())
    day = 86400
    counts: dict = {}
    series: list[dict] = []
    totals = {"last30": 0, "prev30": 0, "last7": 0, "prev7": 0}
    try:
        conn = st._connect()
        for kind in KINDS:
            counts[kind] = conn.execute(
                "SELECT COUNT(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]
        # 14 day trend, one bucket per UTC day, oldest first
        start = now - 13 * day
        rows = conn.execute(
            "SELECT kind, created_at FROM records WHERE created_at >= ?", (start,)).fetchall()
        buckets: dict[int, dict[str, int]] = {}
        for i in range(14):
            buckets[(start + i * day) // day] = {"enquiries": 0, "notifications": 0}
        for kind, created in rows:
            slot = buckets.get(created // day)
            if slot is None:
                continue
            slot["notifications" if kind.endswith("notification") else "enquiries"] += 1
        series = [{"day": (d * day), **v} for d, v in sorted(buckets.items())]
        totals["last30"] = conn.execute(
            "SELECT COUNT(*) FROM records WHERE created_at >= ?", (now - 30 * day,)).fetchone()[0]
        totals["prev30"] = conn.execute(
            "SELECT COUNT(*) FROM records WHERE created_at >= ? AND created_at < ?",
            (now - 60 * day, now - 30 * day)).fetchone()[0]
        totals["last7"] = conn.execute(
            "SELECT COUNT(*) FROM records WHERE created_at >= ?", (now - 7 * day,)).fetchone()[0]
        totals["prev7"] = conn.execute(
            "SELECT COUNT(*) FROM records WHERE created_at >= ? AND created_at < ?",
            (now - 14 * day, now - 7 * day)).fetchone()[0]
    except Exception:
        counts = {}

    # workload by status, and the KSA/UAE split — both from plaintext admin columns
    status_counts = aa.request_status_counts()
    market_counts = aa.request_market_counts()

    markets = {m: jasani.cache_status(m) for m in config.JASANI_HOSTS}
    for key, entry in markets.items():
        fetched = entry.get("fetchedAt") or 0
        stocked = entry.get("stockAt") or 0
        entry["nextProductsAt"] = int(fetched + config.PRODUCT_REFRESH_HOURS * 3600) if fetched else None
        entry["nextStockAt"] = int(stocked + config.STOCK_REFRESH_HOURS * 3600) if stocked else None
    try:
        rentals, rentals_source = content.rentals_load()
    except Exception:
        rentals, rentals_source = [], "unknown"

    mail = mailer.log_stats()
    budgets = jasani.budget_status_all()
    return {"user": {"name": session["name"], "role": session["role"]},
            "requests": counts,
            "requestTotals": totals,
            "requestSeries": series,
            "statusCounts": status_counts,
            "marketCounts": market_counts,
            "adminUsers": aa.user_count(),
            "supplier": {"budgets": budgets, "markets": markets,
                         "tokensConfigured": {m: bool(tok)
                                              for m, tok in config.JASANI_TOKENS.items()}},
            "rentals": {"count": len(rentals), "source": rentals_source},
            "mail": {**mail, "configured": bool(config.RESEND_API_KEY)},
            "audit": aa.audit_list(limit=8)}
