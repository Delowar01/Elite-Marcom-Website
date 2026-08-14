"""Elite Marcom admin panel — accounts, sessions, roles, audit (Phase 0).

Separate SQLite database (runtime/admin.db). Passwords use scrypt (memory-hard,
stdlib). TOTP secrets are AES-GCM encrypted at rest via storage.encrypt. The
audit log is append-only and hash-chained so tampering is detectable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import struct
import threading
import time
from typing import Any

from . import config, storage

_DB_PATH = config.RUNTIME_DIR / "admin.db"
_lock = threading.Lock()
_local = threading.local()

SESSION_COOKIE = "em_admin"
PENDING_TTL_S = 10 * 60
LOCKOUT_ATTEMPTS = 8
LOCKOUT_MINUTES = 15

# ---------------- roles & permissions ----------------
# Fixed matrix for Phase 0; later phases may make this editable (Owner only).

PERMISSIONS = (
    "users.manage", "settings.manage", "audit.view",
    "content.edit", "media.manage", "brand.edit", "seo.edit",
    "rentals.manage", "jasani.view", "jasani.refresh",
    # supplier prices and booked stock are internal, and changing what the
    # public site sells is a bigger decision than reading the catalogue
    "jasani.prices", "jasani.visibility",
    "requests.view", "requests.manage", "insights.view",
)

ROLES: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": set(PERMISSIONS) - {"users.manage"},
    "editor": {"content.edit", "media.manage", "brand.edit", "seo.edit"},
    "catalog": {"rentals.manage", "jasani.view", "jasani.refresh"},
    "sales": {"requests.view", "requests.manage"},
    "analyst": {"insights.view", "audit.view"},
}


def has_perm(role: str, perm: str) -> bool:
    grants = ROLES.get(role, set())
    return "*" in grants or perm in grants


# ---------------- database ----------------

def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(conn)
        _local.conn = conn
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        pass_hash BLOB NOT NULL,
        pass_salt BLOB NOT NULL,
        totp_secret BLOB,
        totp_enabled INTEGER NOT NULL DEFAULT 0,
        role TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL,
        last_login_at INTEGER,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        ip_hash TEXT NOT NULL,
        user_agent TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        user_id INTEGER,
        user_email TEXT NOT NULL,
        action TEXT NOT NULL,
        module TEXT NOT NULL,
        detail TEXT NOT NULL,
        ip_hash TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS request_meta (
        reference TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'new',
        assignee TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '[]',
        updated_at INTEGER NOT NULL,
        updated_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS content (
        page TEXT NOT NULL,
        key TEXT NOT NULL,
        lang TEXT NOT NULL DEFAULT 'en',
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        updated_by TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (page, key, lang)
    );
    CREATE TABLE IF NOT EXISTS designs (
        page TEXT PRIMARY KEY,
        doc TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        updated_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS publishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        by TEXT NOT NULL,
        pages INTEGER NOT NULL,
        snapshot TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS jasani_hidden (
        market TEXT NOT NULL,
        product_id TEXT NOT NULL,
        code TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        hidden_at INTEGER NOT NULL,
        hidden_by TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (market, product_id)
    );
    CREATE TABLE IF NOT EXISTS custom_pages (
        slug TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        nav INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        mime TEXT NOT NULL,
        bytes INTEGER NOT NULL,
        width INTEGER,
        height INTEGER,
        alt TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    );
    """)
    conn.commit()


# ---------------- passwords (scrypt: memory-hard, stdlib) ----------------

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


def hash_password(password: str) -> tuple[bytes, bytes]:
    salt = secrets.token_bytes(16)
    return hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT), salt


def verify_password(password: str, pass_hash: bytes, salt: bytes) -> bool:
    try:
        candidate = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, pass_hash)


# ---------------- TOTP (RFC 6238, stdlib) ----------------

def totp_new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _totp_at(secret_b32: str, counter: int, digits: int = 6) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32 + pad, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[19] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def totp_verify(secret_b32: str, code: str, at: float | None = None, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int((at if at is not None else time.time()) // 30)
    return any(hmac.compare_digest(_totp_at(secret_b32, counter + off), code)
               for off in range(-window, window + 1))


def totp_uri(secret_b32: str, email: str) -> str:
    from urllib.parse import quote

    label = quote(f"Elite Marcom Admin:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote('Elite Marcom')}&digits=6&period=30"


# ---------------- pending tokens (between password and 2FA steps) ----------------

def make_pending(user_id: int, purpose: str) -> str:
    payload = f"{purpose}:{user_id}:{int(time.time()) + PENDING_TTL_S}:{secrets.token_hex(8)}"
    sig = hmac.new(config.EM_ADMIN_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def read_pending(token: str, purpose: str) -> int | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 5:
            return None
        p, user_id, expires, nonce, sig = parts
        expect = hmac.new(config.EM_ADMIN_SESSION_SECRET.encode(),
                          f"{p}:{user_id}:{expires}:{nonce}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        if p != purpose or int(expires) < time.time():
            return None
        return int(user_id)
    except (ValueError, UnicodeDecodeError):
        return None


# ---------------- users ----------------

def user_count() -> int:
    return _connect().execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


def get_user(user_id: int) -> sqlite3.Row | None:
    return _connect().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    return _connect().execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()


def create_user(email: str, name: str, password: str, role: str) -> int:
    if role not in ROLES:
        raise ValueError("unknown role")
    pass_hash, salt = hash_password(password)
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO users (email, name, pass_hash, pass_salt, role, created_at) VALUES (?,?,?,?,?,?)",
            (email.lower().strip(), name.strip(), pass_hash, salt, role, int(time.time())))
        conn.commit()
        return int(cur.lastrowid)


def update_user(user_id: int, **fields: Any) -> None:
    allowed = {"name", "role", "active", "failed_attempts", "locked_until",
               "last_login_at", "totp_secret", "totp_enabled", "pass_hash", "pass_salt"}
    keys = [k for k in fields if k in allowed]
    if not keys:
        return
    with _lock:
        conn = _connect()
        conn.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in keys)} WHERE id=?",
                     [fields[k] for k in keys] + [user_id])
        conn.commit()


def list_users() -> list[dict]:
    rows = _connect().execute(
        "SELECT id, email, name, role, active, totp_enabled, created_at, last_login_at "
        "FROM users ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def register_login_failure(user: sqlite3.Row) -> None:
    attempts = user["failed_attempts"] + 1
    locked_until = int(time.time() + LOCKOUT_MINUTES * 60) if attempts >= LOCKOUT_ATTEMPTS else user["locked_until"]
    update_user(user["id"], failed_attempts=attempts, locked_until=locked_until)


def register_login_success(user: sqlite3.Row) -> None:
    update_user(user["id"], failed_attempts=0, locked_until=0, last_login_at=int(time.time()))


def set_totp(user_id: int, secret_b32: str, enabled: bool) -> None:
    update_user(user_id, totp_secret=storage.encrypt(secret_b32.encode()), totp_enabled=1 if enabled else 0)


def read_totp_secret(user: sqlite3.Row) -> str | None:
    if not user["totp_secret"]:
        return None
    try:
        return storage.decrypt(user["totp_secret"]).decode()
    except Exception:
        return None


# ---------------- sessions ----------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, ip_hash: str, user_agent: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = int(time.time())
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf, created_at, expires_at, ip_hash, user_agent) "
            "VALUES (?,?,?,?,?,?,?)",
            (_token_hash(token), user_id, csrf, now,
             now + int(config.ADMIN_SESSION_HOURS * 3600), ip_hash, user_agent[:200]))
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.commit()
    return token, csrf


def get_session(token: str) -> sqlite3.Row | None:
    if not token:
        return None
    row = _connect().execute(
        "SELECT s.*, u.email, u.role, u.name, u.active FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token_hash=?",
        (_token_hash(token),)).fetchone()
    if row is None or row["expires_at"] < time.time() or not row["active"]:
        return None
    return row


def destroy_session(token: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
        conn.commit()


def destroy_user_sessions(user_id: int, keep_token: str | None = None) -> int:
    with _lock:
        conn = _connect()
        if keep_token:
            cur = conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?",
                               (user_id, _token_hash(keep_token)))
        else:
            cur = conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.commit()
        return cur.rowcount


def list_sessions(user_id: int) -> list[dict]:
    rows = _connect().execute(
        "SELECT token_hash, created_at, expires_at, ip_hash, user_agent FROM sessions "
        "WHERE user_id=? AND expires_at > ? ORDER BY created_at DESC",
        (user_id, int(time.time()))).fetchall()
    return [dict(r) for r in rows]


# ---------------- audit (append-only, hash-chained) ----------------

def audit(user: sqlite3.Row | None, action: str, module: str, detail: dict | str,
          ip_hash: str = "") -> None:
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    with _lock:
        conn = _connect()
        prev = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev["hash"] if prev else "genesis"
        ts = int(time.time())
        user_id = user["user_id"] if user is not None and "user_id" in user.keys() else (
            user["id"] if user is not None else None)
        email = (user["email"] if user is not None else "system")
        body = f"{ts}|{user_id}|{email}|{action}|{module}|{detail}|{ip_hash}|{prev_hash}"
        entry_hash = hashlib.sha256(body.encode()).hexdigest()
        conn.execute(
            "INSERT INTO audit (ts, user_id, user_email, action, module, detail, ip_hash, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, user_id, email, action, module, detail[:4000], ip_hash, prev_hash, entry_hash))
        conn.commit()


def audit_list(limit: int = 100, offset: int = 0, module: str = "", q: str = "") -> list[dict]:
    sql = "SELECT id, ts, user_email, action, module, detail, ip_hash FROM audit"
    where, params = [], []
    if module:
        where.append("module=?")
        params.append(module)
    if q:
        where.append("(user_email LIKE ? OR action LIKE ? OR detail LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([max(1, min(500, limit)), max(0, offset)])
    return [dict(r) for r in _connect().execute(sql, params).fetchall()]


def audit_verify_chain() -> dict:
    """Recompute the hash chain; returns {ok, checked, brokenAt}."""
    rows = _connect().execute("SELECT * FROM audit ORDER BY id").fetchall()
    prev_hash = "genesis"
    for row in rows:
        body = (f"{row['ts']}|{row['user_id']}|{row['user_email']}|{row['action']}|"
                f"{row['module']}|{row['detail']}|{row['ip_hash']}|{prev_hash}")
        if row["prev_hash"] != prev_hash or hashlib.sha256(body.encode()).hexdigest() != row["hash"]:
            return {"ok": False, "checked": len(rows), "brokenAt": row["id"]}
        prev_hash = row["hash"]
    return {"ok": True, "checked": len(rows), "brokenAt": None}


# ---------------- request workflow metadata ----------------
# Status/assignee/notes for customer requests live here (admin.db); the
# encrypted submissions themselves stay in the public records store untouched.

REQUEST_STATUSES = ("new", "in_progress", "quoted", "won", "lost", "closed")


def request_meta_get(reference: str) -> dict:
    row = _connect().execute(
        "SELECT * FROM request_meta WHERE reference=?", (reference,)).fetchone()
    if row is None:
        return {"reference": reference, "status": "new", "assignee": "",
                "notes": [], "updatedAt": None, "updatedBy": ""}
    try:
        notes = json.loads(row["notes"])
    except ValueError:
        notes = []
    return {"reference": row["reference"], "status": row["status"],
            "assignee": row["assignee"], "notes": notes,
            "updatedAt": row["updated_at"], "updatedBy": row["updated_by"]}


def request_meta_bulk(references: list[str]) -> dict[str, dict]:
    """Status + note count for a page of references (list view)."""
    if not references:
        return {}
    marks = ",".join("?" * len(references))
    rows = _connect().execute(
        f"SELECT reference, status, assignee, notes FROM request_meta WHERE reference IN ({marks})",
        references).fetchall()
    out = {}
    for r in rows:
        try:
            n = len(json.loads(r["notes"]))
        except ValueError:
            n = 0
        out[r["reference"]] = {"status": r["status"], "assignee": r["assignee"], "noteCount": n}
    return out


def request_market_counts() -> dict:
    """KSA / UAE split, read from the plaintext market column on records."""
    from . import storage as st

    out = {"ksa": 0, "uae": 0, "other": 0}
    try:
        for market, n in st._connect().execute(
                "SELECT market, COUNT(*) FROM records GROUP BY market"):
            out[market if market in ("ksa", "uae") else "other"] += n
    except Exception:
        pass
    return out


def request_meta_set(reference: str, by: str, status: str | None = None,
                     assignee: str | None = None, note: str | None = None) -> dict:
    if status is not None and status not in REQUEST_STATUSES:
        raise ValueError("unknown status")
    with _lock:
        conn = _connect()
        current = request_meta_get(reference)
        if status is not None:
            current["status"] = status
        if assignee is not None:
            current["assignee"] = assignee[:200]
        if note:
            current["notes"] = (current["notes"] + [
                {"ts": int(time.time()), "by": by[:200], "text": note[:2000]}])[-100:]
        conn.execute(
            "INSERT INTO request_meta (reference, status, assignee, notes, updated_at, updated_by) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(reference) DO UPDATE SET "
            "status=excluded.status, assignee=excluded.assignee, notes=excluded.notes, "
            "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (reference, current["status"], current["assignee"],
             json.dumps(current["notes"], ensure_ascii=False), int(time.time()), by[:200]))
        conn.commit()
    return request_meta_get(reference)


def request_meta_delete(reference: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM request_meta WHERE reference=?", (reference,))
        conn.commit()


def request_status_counts() -> dict[str, int]:
    """Workload by status. A request nobody has opened yet has no meta row at
    all, and request_meta_get() reports those as 'new' — so they are counted
    as 'new' here rather than vanishing from the totals."""
    from . import storage as st

    rows = _connect().execute(
        "SELECT status, COUNT(*) AS c FROM request_meta GROUP BY status").fetchall()
    counts = {s: 0 for s in REQUEST_STATUSES}
    tracked = 0
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + r["c"]
        tracked += r["c"]
    try:
        total = st._connect().execute("SELECT COUNT(*) FROM records").fetchone()[0]
    except Exception:
        total = tracked
    counts["new"] += max(0, total - tracked)
    return counts


# ---------------- settings ----------------

def setting_get(key: str, default: Any = None) -> Any:
    row = _connect().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return default


def setting_set(key: str, value: Any) -> None:
    with _lock:
        conn = _connect()
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                     (key, json.dumps(value, ensure_ascii=False), int(time.time())))
        conn.commit()
