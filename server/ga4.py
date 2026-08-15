"""Elite Marcom — Google Analytics 4 reporting, server side only.

The website's GA4 tag is loaded once by `public/js/insights.js` and nothing
here touches it: this module only *reads* aggregated reports back out of the
GA4 Data API so the admin panel can show geography, acquisition, engagement,
devices and realtime without any of it passing through a browser.

Why raw REST rather than google-analytics-data
----------------------------------------------
The official SDK drags in grpc, protobuf and google-api-core for what is two
JSON endpoints. `httpx` and `cryptography` are already pinned for the supplier
integration, so the service-account flow is done here: build an RS256 JWT,
swap it for an access token, call the API. That also means the same discipline
the Jasani module has — an explicit timeout, a byte cap, one in-flight request
per report, and a cache — instead of whatever the SDK does by default.

Rules this module keeps
-----------------------
* **The credential never leaves the server.** The service-account JSON is read
  from a path outside the repository, its contents are never logged, never
  returned by an API and never rendered. `status()` reports the client email
  and nothing else that is secret, because an admin needs it to grant access.
* **A Google failure is never a panel failure.** Every entry point returns
  ``{"ok": False, "reason": <one safe sentence>}`` rather than raising, so a
  widget can say what happened while the rest of Site Insights carries on.
  The technical detail is logged server-side at most once per minute.
* **Google is not called on every render.** Reports are cached for
  ``GA4_CACHE_TTL_S`` and realtime for ``GA4_REALTIME_TTL_S``, keyed on the
  property, the report and its date window; concurrent callers asking for the
  same report wait on the first one rather than making a second call.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from . import config

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API = "https://analyticsdata.googleapis.com/v1beta"
_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

# an admin sees these; they carry no technical detail and no Google wording
NOT_CONFIGURED = "GA4 reporting is not configured."
UNAVAILABLE = "Analytics data is temporarily unavailable."
GEO_UNAVAILABLE = "Geographic data temporarily unavailable"


class _State:
    """The cached reports, the access token and the last-seen status.

    Plain process state: a cached report is data and has nothing to do with
    which event loop asked for it. Only the in-flight locks below are
    loop-bound, because an asyncio.Lock belongs to the loop that awaits it.
    """

    def __init__(self) -> None:
        self.token = ""
        self.token_expires = 0.0
        self.cache: dict[str, tuple[float, dict]] = {}
        self.last_ok = 0
        self.last_error = ""
        self.last_error_at = 0
        self.logged_at = 0.0


_shared = _State()

# Locks are per loop and the loop object is held beside them on purpose: an
# id() alone is recycled once a loop is closed, so a later run could be handed
# a lock belonging to a loop that no longer exists.
_locks: dict[int, tuple[object, dict[str, asyncio.Lock]]] = {}


def _state() -> _State:
    return _shared


def _lock_for(key: str) -> asyncio.Lock:
    try:
        loop: object | None = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    slot = id(loop)
    hit = _locks.get(slot)
    if hit is None or hit[0] is not loop:
        if len(_locks) > 8:                  # a test suite makes a loop per run
            _locks.clear()
        hit = _locks[slot] = (loop, {})
    return hit[1].setdefault(key, asyncio.Lock())


def reset_state() -> None:
    """Drop every cached token and report. Used by the tests and by a manual
    "Test connection", so a stale credential is never held after it changes."""
    global _shared
    _shared = _State()
    _locks.clear()


# ---------------- credentials ----------------

_creds_cache: tuple[str, float, dict] | None = None


def credentials() -> dict:
    """The service-account JSON, read from disk and cached by (path, mtime).

    Returns {} when it is not configured or not readable — never raises, and
    never puts the file's contents anywhere but this function's return value.
    """
    global _creds_cache
    path = config.GOOGLE_APPLICATION_CREDENTIALS
    if not path:
        return {}
    try:
        stat = path.stat()
    except OSError:
        return {}
    if _creds_cache and _creds_cache[0] == str(path) and _creds_cache[1] == stat.st_mtime:
        return _creds_cache[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not data.get("private_key") or not data.get("client_email"):
        return {}
    _creds_cache = (str(path), stat.st_mtime, data)
    return data


def configured() -> bool:
    return bool(config.GA4_PROPERTY_ID and credentials())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _signed_assertion(creds: dict, now: int) -> str:
    """A service-account JWT, signed RS256 with the key on disk."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    header = {"alg": "RS256", "typ": "JWT"}
    if creds.get("private_key_id"):
        header["kid"] = creds["private_key_id"]
    claims = {
        "iss": creds["client_email"],
        "scope": _SCOPE,
        "aud": creds.get("token_uri") or _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = (_b64(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     _b64(json.dumps(claims, separators=(",", ":")).encode())).encode()
    key = serialization.load_pem_private_key(creds["private_key"].encode(), password=None)
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return signing_input.decode() + "." + _b64(signature)


async def _access_token(client: httpx.AsyncClient) -> str:
    """A cached OAuth access token, refreshed a minute before it expires."""
    st = _state()
    now = time.time()
    if st.token and now < st.token_expires - 60:
        return st.token
    creds = credentials()
    if not creds:
        raise _Unavailable(NOT_CONFIGURED)
    assertion = _signed_assertion(creds, int(now))
    res = await client.post(
        creds.get("token_uri") or _TOKEN_URL,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
              "assertion": assertion},
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    if res.status_code != 200:
        # the body can name the service account; keep it out of the admin's view
        raise _Unavailable("Google rejected the service account credentials.",
                           f"token {res.status_code}: {res.text[:300]}")
    body = res.json()
    token = str(body.get("access_token") or "")
    if not token:
        raise _Unavailable("Google returned no access token.")
    st.token = token
    st.token_expires = now + float(body.get("expires_in") or 3600)
    return token


def _new_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    """The one place an HTTP client is made, so a test can answer as Google
    without reaching into the shared httpx module and changing it for
    everything else in the process."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


class _Unavailable(Exception):
    """Something went wrong upstream. `safe` is what an admin may read."""

    def __init__(self, safe: str, detail: str = "") -> None:
        super().__init__(detail or safe)
        self.safe = safe
        self.detail = detail or safe


# ---------------- the API call ----------------

def _property_path() -> str:
    return f"properties/{config.GA4_PROPERTY_ID}"


async def _call(endpoint: str, body: dict) -> dict:
    """One Data API request. Raises _Unavailable with a safe message."""
    if not config.GA4_PROPERTY_ID:
        raise _Unavailable(NOT_CONFIGURED)
    if not credentials():
        raise _Unavailable(NOT_CONFIGURED)
    url = f"{_API}/{_property_path()}:{endpoint}"
    timeout = httpx.Timeout(config.GA4_TIMEOUT_S, connect=10.0)
    try:
        async with _new_client(timeout) as client:
            token = await _access_token(client)
            res = await client.post(url, json=body,
                                    headers={"Authorization": f"Bearer {token}",
                                             "Content-Type": "application/json"})
    except _Unavailable:
        raise
    except httpx.TimeoutException:
        raise _Unavailable("Google did not answer in time.", f"timeout on {endpoint}")
    except Exception as exc:                                  # network, DNS, TLS
        raise _Unavailable(UNAVAILABLE, f"{type(exc).__name__} on {endpoint}")
    if res.status_code == 401 or res.status_code == 403:
        _state().token = ""      # a stale token must not be reused
        raise _Unavailable("Google refused the request — check that the service account "
                           "has read access to this property.",
                           f"{res.status_code}: {res.text[:300]}")
    if res.status_code == 400:
        # a dimension or metric Google will not accept: it will fail the same
        # way in an hour, so it must not read as a passing glitch
        raise _Unavailable("Google could not run this report.",
                           f"400: {res.text[:400]}")
    if res.status_code == 429:
        raise _Unavailable("Google's reporting quota is exhausted for now.",
                           f"429: {res.text[:200]}")
    if res.status_code != 200:
        raise _Unavailable(UNAVAILABLE, f"{res.status_code}: {res.text[:300]}")
    try:
        data = res.json()
    except ValueError:
        raise _Unavailable(UNAVAILABLE, "response was not JSON")
    if not isinstance(data, dict):
        raise _Unavailable(UNAVAILABLE, "response was not an object")
    return data


def _log(detail: str) -> None:
    """Server-side only, and at most once a minute so a broken credential
    cannot fill a disk. Never carries the key or the token."""
    st = _state()
    now = time.time()
    if now - st.logged_at < 60:
        return
    st.logged_at = now
    print(f"[ga4] {detail}", flush=True)


# ---------------- cache + single flight ----------------

def _cache_key(name: str, body: dict) -> str:
    return json.dumps([config.GA4_PROPERTY_ID, name, body], sort_keys=True, default=str)


async def _cached(name: str, endpoint: str, body: dict, ttl: float) -> dict:
    """Run a report, or serve one that is still fresh. Two callers asking for
    the same report at the same time make one request, not two."""
    st = _state()
    key = _cache_key(name, body)
    hit = st.cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    async with _lock_for(key):
        hit = st.cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]                       # filled while we waited
        try:
            data = await _call(endpoint, body)
        except _Unavailable as exc:
            _log(exc.detail)
            st.last_error = exc.safe
            st.last_error_at = int(time.time())
            out = {"ok": False, "reason": exc.safe}
            # a failure is cached briefly too, or a broken credential means one
            # Google round trip per widget per render
            st.cache[key] = (time.time(), out)
            return out
        st.last_ok = int(time.time())
        st.last_error = ""
        out = {"ok": True, **data}
        st.cache[key] = (time.time(), out)
        if len(st.cache) > 200:                 # a date picker cannot grow it forever
            for old in sorted(st.cache, key=lambda k: st.cache[k][0])[:80]:
                st.cache.pop(old, None)
        return out


# ---------------- shaping ----------------

def _rows(data: dict) -> list[dict]:
    """GA4's row shape flattened to {dims: [...], metrics: [...]}. Anything
    that is not the shape we asked for is skipped rather than trusted."""
    out = []
    for row in (data.get("rows") or []):
        if not isinstance(row, dict):
            continue
        dims = [str((d or {}).get("value", "")) for d in (row.get("dimensionValues") or [])
                if isinstance(d, dict)]
        mets = []
        for m in (row.get("metricValues") or []):
            if not isinstance(m, dict):
                continue
            try:
                mets.append(float(m.get("value") or 0))
            except (TypeError, ValueError):
                mets.append(0.0)
        out.append({"dims": dims, "metrics": mets})
    return out


def _num(row: dict, i: int) -> float:
    mets = row.get("metrics") or []
    return mets[i] if i < len(mets) else 0.0


def _dim(row: dict, i: int) -> str:
    dims = row.get("dims") or []
    return dims[i] if i < len(dims) else ""


UNKNOWN = "Unknown"


def _named(value: str) -> str:
    """What GA4 sends when it could not resolve a dimension, in our words.

    These rows are kept rather than dropped: they are real users, and removing
    them would leave every percentage beside them describing a subset while
    looking like a share of the whole.
    """
    value = (value or "").strip()
    return UNKNOWN if not value or value in ("(not set)", "(none)", "(other)") else value


def _share(rows: list[dict], key: str = "users") -> list[dict]:
    """Add each row's percentage of the total, rounded once so a column of
    shares adds up to something an admin can read."""
    total = sum(r.get(key) or 0 for r in rows)
    for r in rows:
        r["share"] = round((r.get(key) or 0) / total * 100, 1) if total else 0.0
    return rows


def _report(dimensions: list[str], metrics: list[str], start: str, end: str,
            limit: int = 10, order_metric: str = "", keep_empty: bool = False) -> dict:
    body: dict = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
        "keepEmptyRows": keep_empty,
    }
    if order_metric:
        body["orderBys"] = [{"metric": {"metricName": order_metric}, "desc": True}]
    return body


def previous_period(start: str, end: str) -> tuple[str, str]:
    """The equivalent window immediately before this one — the comparison the
    dashboard shows, and the only one it ever shows."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    span = (e - s).days + 1
    return (s - timedelta(days=span)).isoformat(), (s - timedelta(days=1)).isoformat()


def change(now: float, before: float) -> float | None:
    """None when there is nothing to compare against. A jump from zero is not
    an infinite rise and must not be drawn as a percentage."""
    if not before:
        return None
    return round((now - before) / before * 100, 1)


# ---------------- reports ----------------

_OVERVIEW_METRICS = ["activeUsers", "sessions", "screenPageViews", "newUsers",
                     "engagementRate", "userEngagementDuration", "engagedSessions"]


async def overview(start: str, end: str) -> dict:
    """The executive KPI row, with the previous equivalent period beside it."""
    p_start, p_end = previous_period(start, end)
    now, before = await asyncio.gather(
        _cached("overview", "runReport", _report([], _OVERVIEW_METRICS, start, end, 1),
                config.GA4_CACHE_TTL_S),
        _cached("overview", "runReport", _report([], _OVERVIEW_METRICS, p_start, p_end, 1),
                config.GA4_CACHE_TTL_S))
    if not now.get("ok"):
        return now
    def totals(payload: dict) -> dict:
        rows = _rows(payload)
        row = rows[0] if rows else {"metrics": []}
        vals = {name: _num(row, i) for i, name in enumerate(_OVERVIEW_METRICS)}
        users = vals["activeUsers"]
        sessions = vals["sessions"]
        return {
            "activeUsers": int(users), "sessions": int(sessions),
            "pageViews": int(vals["screenPageViews"]), "newUsers": int(vals["newUsers"]),
            # GA4 has no "returning users" metric: it is active minus new, and
            # it cannot be negative even when the two come from different rows
            "returningUsers": max(0, int(users) - int(vals["newUsers"])),
            "engagementRate": round(vals["engagementRate"] * 100, 1),
            "engagedSessions": int(vals["engagedSessions"]),
            # GA4 reports total engagement seconds; per session is the readable one
            "avgEngagementSeconds": round(vals["userEngagementDuration"] / sessions, 1)
                                    if sessions else 0.0,
        }
    current = totals(now)
    prior = totals(before) if before.get("ok") else {}
    return {"ok": True, "totals": current, "previous": prior,
            "changes": {k: change(current[k], prior.get(k, 0))
                        for k in current} if prior else {},
            "comparedWith": {"start": p_start, "end": p_end}}


async def series(start: str, end: str) -> dict:
    """The daily figures behind the sparklines and the trend chart, including
    the engagement metrics the trend can switch to — one report, not four."""
    body = _report(["date"], ["activeUsers", "sessions", "screenPageViews",
                              "engagementRate", "userEngagementDuration",
                              "engagedSessions"],
                   start, end, limit=400, keep_empty=True)
    body["orderBys"] = [{"dimension": {"dimensionName": "date"}}]
    data = await _cached("series", "runReport", body, config.GA4_CACHE_TTL_S)
    if not data.get("ok"):
        return data
    out = []
    for row in _rows(data):
        raw = _dim(row, 0)
        if len(raw) != 8 or not raw.isdigit():
            continue
        sessions = _num(row, 1)
        out.append({"day": f"{raw[:4]}-{raw[4:6]}-{raw[6:]}",
                    "users": int(_num(row, 0)), "sessions": int(sessions),
                    "views": int(_num(row, 2)),
                    "engagementRate": round(_num(row, 3) * 100, 1),
                    "engagedSessions": int(_num(row, 5)),
                    "avgEngagementSeconds": round(_num(row, 4) / sessions, 1)
                                            if sessions else 0.0})
    return {"ok": True, "series": out}


async def _ranked(name: str, dims: list[str], start: str, end: str, limit: int,
                  metrics: list[str] | None = None) -> dict:
    metrics = metrics or ["activeUsers"]
    data = await _cached(name, "runReport",
                         _report(dims, metrics, start, end, limit, metrics[0]),
                         config.GA4_CACHE_TTL_S)
    if not data.get("ok"):
        return data
    return {"ok": True, "rows": _rows(data)}


async def countries(start: str, end: str, limit: int = 10) -> dict:
    data = await _ranked("countries", ["country"], start, end, limit)
    if not data.get("ok"):
        return {"ok": False, "reason": GEO_UNAVAILABLE}
    rows = [{"label": _named(_dim(r, 0)), "users": int(_num(r, 0))}
            for r in data["rows"]]
    return {"ok": True, "rows": _share(rows)}


async def cities(start: str, end: str, limit: int = 10) -> dict:
    """City *and* country: "Riyadh" alone is ambiguous, and several countries
    have one."""
    data = await _ranked("cities", ["city", "country"], start, end, limit)
    if not data.get("ok"):
        return {"ok": False, "reason": GEO_UNAVAILABLE}
    rows = []
    for r in data["rows"]:
        city, country = _named(_dim(r, 0)), _named(_dim(r, 1))
        rows.append({"label": city, "country": country,
                     "display": f"{city} — {country}" if country != UNKNOWN else city,
                     "users": int(_num(r, 0))})
    return {"ok": True, "rows": _share(rows)}


async def regions(start: str, end: str, limit: int = 8) -> dict:
    data = await _ranked("regions", ["region", "country"], start, end, limit)
    if not data.get("ok"):
        return {"ok": False, "reason": GEO_UNAVAILABLE}
    rows = []
    for r in data["rows"]:
        region, country = _named(_dim(r, 0)), _named(_dim(r, 1))
        rows.append({"label": region, "country": country,
                     "display": f"{region} — {country}" if country != UNKNOWN else region,
                     "users": int(_num(r, 0))})
    return {"ok": True, "rows": _share(rows)}


async def channels(start: str, end: str) -> dict:
    data = await _ranked("channels", ["sessionDefaultChannelGroup"], start, end, 12,
                         ["sessions", "activeUsers"])
    if not data.get("ok"):
        return data
    rows = [{"label": _named(_dim(r, 0)), "sessions": int(_num(r, 0)),
             "users": int(_num(r, 1))} for r in data["rows"]]
    return {"ok": True, "rows": _share(rows, "sessions")}


async def sources(start: str, end: str, limit: int = 10) -> dict:
    data = await _ranked("sources", ["sessionSource", "sessionMedium"], start, end, limit,
                         ["sessions", "activeUsers"])
    if not data.get("ok"):
        return data
    def part(value: str, direct: str) -> str:
        value = (value or "").strip()
        return direct if not value or value == "(not set)" else value
    rows = [{"label": f"{part(_dim(r, 0), '(direct)')} / {part(_dim(r, 1), '(none)')}",
             "sessions": int(_num(r, 0)), "users": int(_num(r, 1))}
            for r in data["rows"]]
    return {"ok": True, "rows": _share(rows, "sessions")}


async def pages(start: str, end: str, limit: int = 12) -> dict:
    data = await _ranked("pages", ["pagePath", "pageTitle"], start, end, limit,
                         ["screenPageViews", "activeUsers", "userEngagementDuration"])
    if not data.get("ok"):
        return data
    rows = []
    for r in data["rows"]:
        views = int(_num(r, 0))
        path = (_dim(r, 0) or "").strip()
        rows.append({"label": path if path and path != "(not set)" else UNKNOWN,
                     "title": _named(_dim(r, 1)),
                     "views": views, "users": int(_num(r, 1)),
                     "avgSeconds": round(_num(r, 2) / views, 1) if views else 0.0})
    return {"ok": True, "rows": rows}


async def landing_pages(start: str, end: str, limit: int = 10) -> dict:
    data = await _ranked("landing", ["landingPage"], start, end, limit,
                         ["sessions", "activeUsers", "engagementRate"])
    if not data.get("ok"):
        return data
    def path(value: str) -> str:
        value = (value or "").strip()
        return value if value and value != "(not set)" else UNKNOWN
    rows = [{"label": path(_dim(r, 0)), "sessions": int(_num(r, 0)),
             "users": int(_num(r, 1)), "engagementRate": round(_num(r, 2) * 100, 1)}
            for r in data["rows"]]
    return {"ok": True, "rows": rows}


async def devices(start: str, end: str) -> dict:
    data = await _ranked("devices", ["deviceCategory"], start, end, 6)
    if not data.get("ok"):
        return data
    rows = [{"label": _named(_dim(r, 0)).title(), "users": int(_num(r, 0))}
            for r in data["rows"]]
    return {"ok": True, "rows": _share(rows)}


async def technology(start: str, end: str) -> dict:
    browsers, systems = await asyncio.gather(
        _ranked("browsers", ["browser"], start, end, 8),
        _ranked("os", ["operatingSystem"], start, end, 8))
    def shape(payload: dict) -> dict:
        if not payload.get("ok"):
            return payload
        rows = [{"label": _named(_dim(r, 0)), "users": int(_num(r, 0))}
                for r in payload["rows"]]
        return {"ok": True, "rows": _share(rows)}
    return {"browsers": shape(browsers), "systems": shape(systems)}


def new_vs_returning(overview_payload: dict) -> dict:
    """Split straight out of the overview totals rather than from its own
    report: activeUsers − newUsers is what "returning" means, and deriving it
    twice from two different reports is how one screen ends up showing two
    different numbers for the same thing."""
    if not overview_payload.get("ok"):
        return {"ok": False, "reason": overview_payload.get("reason") or UNAVAILABLE}
    t = overview_payload.get("totals") or {}
    rows = [{"label": "New", "users": int(t.get("newUsers") or 0)},
            {"label": "Returning", "users": int(t.get("returningUsers") or 0)}]
    if not sum(r["users"] for r in rows):
        return {"ok": True, "rows": []}
    return {"ok": True, "rows": _share(rows)}


async def key_events(start: str, end: str, limit: int = 8) -> dict:
    """GA4's own conversion counts. Shown beside our server-side enquiry
    records for comparison — never instead of them."""
    data = await _ranked("keyEvents", ["eventName"], start, end, limit, ["keyEvents"])
    if not data.get("ok"):
        return data
    rows = [{"label": _dim(r, 0), "count": int(_num(r, 0))}
            for r in data["rows"] if _num(r, 0) > 0]
    return {"ok": True, "rows": rows}


# ---------------- realtime ----------------

async def realtime() -> dict:
    """The live section. One cache for the whole block, refreshed at most
    every GA4_REALTIME_TTL_S however many admins have the screen open."""
    async def block(name: str, dims: list[str], limit: int) -> dict:
        body: dict = {"metrics": [{"name": "activeUsers"}], "limit": limit}
        if dims:
            body["dimensions"] = [{"name": d} for d in dims]
            body["orderBys"] = [{"metric": {"metricName": "activeUsers"}, "desc": True}]
        return await _cached("rt:" + name, "runRealtimeReport", body,
                             config.GA4_REALTIME_TTL_S)

    total, pages_rt, countries_rt, cities_rt, devices_rt = await asyncio.gather(
        block("total", [], 1), block("pages", ["unifiedScreenName"], 8),
        block("countries", ["country"], 8), block("cities", ["city", "country"], 8),
        block("devices", ["deviceCategory"], 4))
    if not total.get("ok"):
        return {"ok": False, "reason": total.get("reason") or UNAVAILABLE}
    rows = _rows(total)
    def simple(payload: dict, join: bool = False) -> list[dict]:
        if not payload.get("ok"):
            return []
        out = []
        for r in _rows(payload):
            label = _named(_dim(r, 0))
            if join:
                country = _named(_dim(r, 1))
                if country != UNKNOWN:
                    label = f"{label} — {country}"
            out.append({"label": label, "users": int(_num(r, 0))})
        return out
    return {
        "ok": True,
        "activeUsers": int(_num(rows[0], 0)) if rows else 0,
        "pages": simple(pages_rt),
        "countries": simple(countries_rt),
        "cities": simple(cities_rt, join=True),
        "devices": _share([{**d, "label": d["label"].title()}
                           for d in simple(devices_rt)]),
        "fetchedAt": int(time.time()),
    }


# ---------------- everything the dashboard needs, in one pass ----------------

async def dashboard(start: str, end: str) -> dict:
    """Every non-realtime report, run concurrently. Each one carries its own
    ok/reason, so one broken report leaves the others readable."""
    if not configured():
        return {"configured": False, "reason": NOT_CONFIGURED}
    (over, ser, ctry, city, regs, chan, srcs, pgs, land, dev, tech,
     keys) = await asyncio.gather(
        overview(start, end), series(start, end), countries(start, end),
        cities(start, end), regions(start, end), channels(start, end),
        sources(start, end), pages(start, end), landing_pages(start, end),
        devices(start, end), technology(start, end), key_events(start, end))
    return {"configured": True, "start": start, "end": end,
            "overview": over, "series": ser, "countries": ctry, "cities": city,
            "regions": regs, "channels": chan, "sources": srcs, "pages": pgs,
            "landingPages": land, "devices": dev, "technology": tech,
            "newVsReturning": new_vs_returning(over), "keyEvents": keys}


# ---------------- connection status ----------------

def status() -> dict:
    """What the Analytics settings screen shows. Everything here is safe to
    render: the client email is an address an admin has to grant access to,
    and the error is the sentence we wrote, never Google's."""
    st = _state()
    creds = credentials()
    return {
        "configured": configured(),
        "propertyId": config.GA4_PROPERTY_ID,
        "credentialsFound": bool(creds),
        "serviceAccount": str(creds.get("client_email") or ""),
        "credentialsPath": str(config.GOOGLE_APPLICATION_CREDENTIALS or ""),
        "lastSuccessAt": st.last_ok,
        "lastError": st.last_error,
        "lastErrorAt": st.last_error_at,
        "cacheSeconds": config.GA4_CACHE_TTL_S,
        "realtimeSeconds": config.GA4_REALTIME_TTL_S,
    }


async def test_connection() -> dict:
    """One small live report, ignoring the cache — the "Test connection"
    button. Returns a safe verdict either way."""
    if not config.GA4_PROPERTY_ID:
        return {"ok": False, "reason": "No GA4 property id is set on the server."}
    if not credentials():
        return {"ok": False, "reason": "No service-account credentials were found on the server."}
    reset_state()
    today = date.today()
    body = _report([], ["activeUsers"], (today - timedelta(days=7)).isoformat(),
                   today.isoformat(), 1)
    try:
        data = await _call("runReport", body)
    except _Unavailable as exc:
        _log(f"test connection: {exc.detail}")
        st = _state()
        st.last_error = exc.safe
        st.last_error_at = int(time.time())
        return {"ok": False, "reason": exc.safe}
    st = _state()
    st.last_ok = int(time.time())
    st.last_error = ""
    rows = _rows(data)
    users = int(_num(rows[0], 0)) if rows else 0
    return {"ok": True, "reason": f"Connected. {users} active users in the last 7 days.",
            "propertyId": config.GA4_PROPERTY_ID,
            "serviceAccount": str(credentials().get("client_email") or "")}
