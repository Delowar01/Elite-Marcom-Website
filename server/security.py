"""Elite Marcom website backend — form protection.

Signed one-time challenges, origin checks, IP hashing, rate limits,
honeypot, Turnstile verification.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

import httpx
from fastapi import HTTPException, Request

from . import config

ALLOWED_FORMS = {
    "contact", "career",
    "giveaway_enquiry", "giveaway_notification",
    "rental_enquiry", "rental_notification",
}

CHALLENGE_TTL_S = 15 * 60

_used_nonces: dict[str, float] = {}
_nonce_lock = threading.Lock()


def _prune_nonces(now: float) -> None:
    stale = [n for n, exp in _used_nonces.items() if exp < now]
    for n in stale:
        _used_nonces.pop(n, None)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "0.0.0.0"
    if peer in config.TRUSTED_PROXIES:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return peer


def hash_ip(ip: str) -> str:
    return hmac.new(config.EM_IP_HASH_SECRET.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def issue_challenge(form: str, ip_hash: str) -> str:
    if form not in ALLOWED_FORMS:
        raise HTTPException(status_code=400, detail="Unknown form.")
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    body = f"{form}.{ts}.{nonce}.{ip_hash}"
    sig = hmac.new(config.EM_CHALLENGE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def consume_challenge(token: str, form: str, ip_hash: str) -> None:
    generic = HTTPException(status_code=400, detail="This form session expired — please try again.")
    parts = (token or "").split(".")
    if len(parts) != 5:
        raise generic
    t_form, t_ts, t_nonce, t_ip, t_sig = parts
    body = f"{t_form}.{t_ts}.{t_nonce}.{t_ip}"
    expected = hmac.new(config.EM_CHALLENGE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, t_sig):
        raise generic
    if t_form != form or t_ip != ip_hash:
        raise generic
    now = time.time()
    try:
        issued = int(t_ts)
    except ValueError:
        raise generic
    if now - issued > CHALLENGE_TTL_S or issued - now > 60:
        raise generic
    with _nonce_lock:
        _prune_nonces(now)
        if t_nonce in _used_nonces:
            raise generic
        _used_nonces[t_nonce] = now + CHALLENGE_TTL_S


def check_origin(request: Request) -> None:
    """Exact Origin validation for state-changing requests."""
    origin = request.headers.get("origin")
    if origin is None:
        # Same-origin non-CORS requests may omit Origin; require a same-host Referer then.
        referer = request.headers.get("referer", "")
        if any(referer.startswith(o + "/") or referer == o for o in config.ALLOWED_ORIGINS):
            return
        raise HTTPException(status_code=403, detail="Request origin not allowed.")
    if origin not in config.ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Request origin not allowed.")


def check_honeypot(value: str | None) -> None:
    if value:
        # Bots fill the zero-size field; humans never see it.
        raise HTTPException(status_code=400, detail="Submission rejected.")


async def verify_turnstile(token: str | None, ip: str) -> None:
    if not config.TURNSTILE_SECRET:
        if config.IS_PROD:
            raise HTTPException(status_code=503, detail="Verification unavailable.")
        return  # optional for controlled local development
    if not token:
        raise HTTPException(status_code=400, detail="Verification required — please retry.")
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            res = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": config.TURNSTILE_SECRET, "response": token, "remoteip": ip},
            )
        ok = bool(res.json().get("success"))
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=400, detail="Verification failed — please retry.")


# ---------------- rate limiting ----------------

class RateLimiter:
    """Simple in-memory sliding-window limiter keyed by (bucket, ip_hash)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def check(self, bucket: str, ip_hash: str, limit: int, window_s: int) -> None:
        now = time.time()
        key = (bucket, ip_hash)
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_s]
            if len(hits) >= limit:
                self._hits[key] = hits
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests — please wait a moment and try again.",
                    headers={"Retry-After": str(window_s)},
                )
            hits.append(now)
            self._hits[key] = hits
            # opportunistic prune
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                    self._hits.pop(k, None)


limiter = RateLimiter()

# global concurrency cap for expensive endpoints
_global_semaphore = threading.BoundedSemaphore(int(64))


def acquire_global_slot() -> None:
    if not _global_semaphore.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server busy — please retry shortly.")


def release_global_slot() -> None:
    try:
        _global_semaphore.release()
    except ValueError:
        pass
