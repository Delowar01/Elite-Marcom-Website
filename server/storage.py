"""Elite Marcom website backend — encrypted private storage.

SQLite (WAL) under runtime/, AES-GCM payload encryption, reference IDs,
daily retention cleanup.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import string
import threading
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

_DB_PATH = config.RUNTIME_DIR / "data.db"
_CV_DIR = config.RUNTIME_DIR / "cvs"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _key() -> bytes:
    return hashlib.sha256(("em-data:" + config.EM_DATA_KEY).encode()).digest()


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, data, b"em-v1")


def decrypt(blob: bytes) -> bytes:
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], b"em-v1")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        _CV_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                ip_hash TEXT NOT NULL,
                payload BLOB NOT NULL,
                cv_path TEXT
            )"""
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_records_expiry ON records(expires_at)")
        _conn.commit()
    return _conn


def make_reference(prefix: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{prefix}-{body[:4]}-{body[4:]}"


def save_record(kind: str, payload: dict, ip_hash: str,
                retention_days: int, cv_bytes: bytes | None = None,
                file_ext: str = "pdf") -> str:
    prefix = {
        "contact": "EM", "career": "CA",
        "giveaway_enquiry": "GV", "giveaway_notification": "GN",
        "rental_enquiry": "RN", "rental_notification": "RA",
    }.get(kind, "EM")
    reference = make_reference(prefix)
    now = int(time.time())
    expires = now + retention_days * 86400
    blob = encrypt(json.dumps(payload, ensure_ascii=False).encode())
    cv_path = None
    if cv_bytes is not None:
        _CV_DIR.mkdir(parents=True, exist_ok=True)
        cv_name = f"{reference}-{secrets.token_hex(6)}.{file_ext}.enc"
        cv_file = _CV_DIR / cv_name
        cv_file.write_bytes(encrypt(cv_bytes))
        cv_path = cv_name
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO records (kind, reference, created_at, expires_at, ip_hash, payload, cv_path)"
            " VALUES (?,?,?,?,?,?,?)",
            (kind, reference, now, expires, ip_hash, blob, cv_path),
        )
        conn.commit()
    return reference


def list_records(kinds: list[str] | None = None, limit: int = 50, offset: int = 0,
                 q: str = "") -> tuple[list[dict], int]:
    """Admin inbox listing: rows with the payload still encrypted.

    Returns (rows, total). Decryption happens at the admin layer so every
    decrypt-on-view is an explicit, audited step."""
    sql = "FROM records"
    where, params = [], []
    if kinds:
        where.append(f"kind IN ({','.join('?' * len(kinds))})")
        params.extend(kinds)
    if q:
        where.append("reference LIKE ?")
        params.append(f"%{q.upper()}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _lock:
        conn = _connect()
        total = conn.execute(f"SELECT COUNT(*) {sql}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, kind, reference, created_at, expires_at, payload, cv_path {sql}"
            " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            params + [max(1, min(1000, limit)), max(0, offset)]).fetchall()
    out = []
    for r in rows:
        out.append({"id": r[0], "kind": r[1], "reference": r[2], "createdAt": r[3],
                    "expiresAt": r[4], "payload": r[5], "hasFile": bool(r[6])})
    return out, total


def get_record(reference: str) -> dict | None:
    """One record by reference — payload still encrypted (see list_records)."""
    with _lock:
        row = _connect().execute(
            "SELECT id, kind, reference, created_at, expires_at, payload, cv_path "
            "FROM records WHERE reference=?", (reference,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "kind": row[1], "reference": row[2], "createdAt": row[3],
            "expiresAt": row[4], "payload": row[5], "cvPath": row[6]}


def delete_record(reference: str) -> bool:
    """Remove one record and its encrypted attachment (admin-initiated)."""
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT cv_path FROM records WHERE reference=?",
                           (reference,)).fetchone()
        if row is None:
            return False
        if row[0]:
            try:
                (_CV_DIR / Path(row[0]).name).unlink(missing_ok=True)
            except OSError:
                pass
        conn.execute("DELETE FROM records WHERE reference=?", (reference,))
        conn.commit()
    return True


def read_attachment(cv_path: str) -> bytes | None:
    """Decrypt a stored attachment (CV / logo) by its stored file name."""
    try:
        blob = (_CV_DIR / Path(cv_path).name).read_bytes()
        return decrypt(blob)
    except Exception:
        return None


def cleanup_expired() -> int:
    """Delete expired records (and their encrypted CV files). Returns count removed."""
    now = int(time.time())
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, cv_path FROM records WHERE expires_at < ?", (now,)
        ).fetchall()
        for _rid, cv_path in rows:
            if cv_path:
                try:
                    (_CV_DIR / Path(cv_path).name).unlink(missing_ok=True)
                except OSError:
                    pass
        conn.execute("DELETE FROM records WHERE expires_at < ?", (now,))
        conn.commit()
    # catalog cache retention
    cache_dir = config.RUNTIME_DIR / "cache"
    if cache_dir.exists():
        cutoff = time.time() - config.RETENTION_CATALOG_DAYS * 86400
        for f in cache_dir.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    return len(rows)
