"""Elite Marcom website backend — configuration.

Production fails closed: missing independent secrets, origins, Turnstile,
malware scanning or a persistent runtime path abort startup.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

ENV = os.environ.get("EM_ENV", "development").strip().lower()
IS_PROD = ENV == "production"

RUNTIME_DIR = Path(os.environ.get("EM_RUNTIME_DIR", str(BASE_DIR / "runtime"))).resolve()

CONSENT_VERSION = "2026-01"

# --- retention defaults (days) ---
RETENTION_SUBMISSIONS_DAYS = int(os.environ.get("EM_RETENTION_SUBMISSIONS_DAYS", "180"))
RETENTION_CAREERS_DAYS = int(os.environ.get("EM_RETENTION_CAREERS_DAYS", "90"))
RETENTION_CATALOG_DAYS = int(os.environ.get("EM_RETENTION_CATALOG_DAYS", "30"))

# --- supplier (Jasani) ---
JASANI_API_TOKEN = os.environ.get("JASANI_API_TOKEN", "")            # KSA account
JASANI_API_TOKEN_UAE = os.environ.get("JASANI_API_TOKEN_UAE", "")    # UAE account
# One token per market, each with its own daily allowance. Deliberately no
# fallback between them: sending both markets through a single token would put
# ten calls a day on one account, and the supplier answers an over-limit token
# with a 403 that parks it for the rest of the day.
JASANI_TOKENS = {"ksa": JASANI_API_TOKEN.strip(), "uae": JASANI_API_TOKEN_UAE.strip()}
JASANI_HOSTS = {"ksa": "www.giftsksa.com", "uae": "www.jasani.ae"}
# the supplier day rolls over in local time, and the two markets are an hour apart
JASANI_UTC_OFFSET = {"ksa": 3, "uae": 4}
# automatic sync times in each market's own local time: one products refresh at
# midnight, then stock through the trading day. Four calls, leaving the fifth.
JASANI_SCHEDULE = ((0, "products"), (8, "stock"), (13, "stock"), (18, "stock"))
# The UAE products feed is ~4 MB and was measured from the production VPS at
# 24.2s to the last byte, 24.17s of it before the first — a 20s read timeout
# aborts a response that was on its way.
SUPPLIER_TIMEOUT_S = float(os.environ.get("EM_SUPPLIER_TIMEOUT_S", "60"))
# Hard ceiling on an upstream response. The UAE products feed is ~4.17 MB, so
# 5 MB left almost no room for the catalogue to grow before a valid reply was
# rejected as too large; 8 MB keeps the protection strict with headroom.
SUPPLIER_MAX_BYTES = int(os.environ.get("EM_SUPPLIER_MAX_BYTES", str(8 * 1024 * 1024)))
SUPPLIER_MAX_RECORDS = 5000
# Jasani documents at most 5 primary GET calls (products/price/stock) per day,
# measured in UAE time; branding endpoints are documented outside that limit.
SUPPLIER_DAILY_BUDGET = int(os.environ.get("EM_SUPPLIER_DAILY_BUDGET", "5"))
# The last call of the day is held back for a person: background refreshes stop
# at this many so an owner/admin can always force a sync when something is wrong.
# The admin item list marks low stock at the same figure the public catalogue
# uses (public/js/giveaways.js) — two thresholds would disagree in public.
LOW_STOCK_THRESHOLD = int(os.environ.get("EM_LOW_STOCK_THRESHOLD", "20"))
SUPPLIER_AUTO_BUDGET = max(0, min(
    SUPPLIER_DAILY_BUDGET,
    int(os.environ.get("EM_SUPPLIER_AUTO_BUDGET", str(max(0, SUPPLIER_DAILY_BUDGET - 1))))))
# refresh cadence sized to the documented budget: products daily, stock twice daily
PRODUCT_REFRESH_HOURS = float(os.environ.get("EM_PRODUCT_REFRESH_HOURS", "22"))
STOCK_REFRESH_HOURS = float(os.environ.get("EM_STOCK_REFRESH_HOURS", "11"))
BRANDING_CACHE_HOURS = 24
BRANDING_CACHE_MAX_ENTRIES = 500

# --- security secrets (independent) ---
_DEV_PREFIX = "dev-insecure-"


def _secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if IS_PROD:
        _fail(f"{name} is required in production")
    # deterministic-per-process dev secret; never used in production
    return _DEV_PREFIX + secrets.token_hex(16)


def _fail(message: str) -> None:
    print(f"[elite-marcom] REFUSING TO START: {message}", file=sys.stderr)
    raise SystemExit(1)


EM_DATA_KEY = _secret("EM_DATA_KEY")            # AES-GCM data-at-rest key material
EM_CHALLENGE_SECRET = _secret("EM_CHALLENGE_SECRET")  # form-token signing
EM_IP_HASH_SECRET = _secret("EM_IP_HASH_SECRET")      # IP hashing
EM_ADMIN_SESSION_SECRET = _secret("EM_ADMIN_SESSION_SECRET")  # admin pending-token signing

# one-time bootstrap code required to create the FIRST admin account in
# production (any value works in development when unset)
ADMIN_SETUP_CODE = os.environ.get("EM_ADMIN_SETUP_CODE", "").strip()
ADMIN_SESSION_HOURS = float(os.environ.get("EM_ADMIN_SESSION_HOURS", "12"))

# --- transactional email (Resend) ---
# The API key is read from the environment ONLY. It is never stored in the
# admin database, never returned by an endpoint and never sent to a browser.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
# sender addresses are restricted to domains verified with Resend
MAIL_SENDER_DOMAINS = os.environ.get("EM_MAIL_SENDER_DOMAINS", "mail.elitemarcom.com")
# override only for staging/self-hosted relays; defaults to Resend's API
RESEND_ENDPOINT = os.environ.get("EM_RESEND_ENDPOINT", "https://api.resend.com/emails").strip()

TURNSTILE_SECRET = os.environ.get("EM_TURNSTILE_SECRET", "").strip()
TURNSTILE_SITE_KEY = os.environ.get("EM_TURNSTILE_SITE_KEY", "").strip()

# --- origins ---
_default_origins = "http://127.0.0.1:8847,http://localhost:8847"
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("EM_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()
]

# proxy peers allowed to supply X-Forwarded-For
TRUSTED_PROXIES = {
    p.strip() for p in os.environ.get("EM_TRUSTED_PROXIES", "").split(",") if p.strip()
}

HOST = os.environ.get("EM_HOST", "127.0.0.1")
PORT = int(os.environ.get("EM_PORT", "8847"))

# malware scanning (clamd) — mandatory in production, fail closed
CLAMD_SOCKET = os.environ.get("EM_CLAMD_SOCKET", "/var/run/clamav/clamd.ctl")
MALWARE_SCAN_REQUIRED = IS_PROD


def validate_startup() -> None:
    """Fail closed on unsafe production configuration."""
    if not IS_PROD:
        return
    problems = []
    for name, val in (("EM_DATA_KEY", EM_DATA_KEY),
                      ("EM_CHALLENGE_SECRET", EM_CHALLENGE_SECRET),
                      ("EM_IP_HASH_SECRET", EM_IP_HASH_SECRET),
                      ("EM_ADMIN_SESSION_SECRET", EM_ADMIN_SESSION_SECRET)):
        if val.startswith(_DEV_PREFIX) or len(val) < 32:
            problems.append(f"{name} must be set to at least 32 characters")
    if len({EM_DATA_KEY, EM_CHALLENGE_SECRET, EM_IP_HASH_SECRET, EM_ADMIN_SESSION_SECRET}) != 4:
        problems.append("EM_DATA_KEY / EM_CHALLENGE_SECRET / EM_IP_HASH_SECRET / EM_ADMIN_SESSION_SECRET must be distinct")
    if not ADMIN_SETUP_CODE:
        problems.append("EM_ADMIN_SETUP_CODE is required in production until the first admin account exists")
    if not TURNSTILE_SECRET or not TURNSTILE_SITE_KEY:
        problems.append("EM_TURNSTILE_SECRET and EM_TURNSTILE_SITE_KEY are required in production")
    https_origins = [o for o in ALLOWED_ORIGINS if o.startswith("https://")]
    if not https_origins:
        problems.append("EM_ALLOWED_ORIGINS must contain exact https:// origins in production")
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        probe = RUNTIME_DIR / ".probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        problems.append(f"runtime path {RUNTIME_DIR} is not writable/persistent")
    if problems:
        _fail("; ".join(problems))
