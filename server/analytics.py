"""Elite Marcom — first-party, privacy-first site analytics (admin Phase 5).

No cookies, no third-party calls, no raw IP or user-agent storage. Visitors
are counted with a hash that mixes a **daily-rotating salt**, so the same
person is not linkable across days and the data cannot be re-identified.
Optional GA4 forwarding runs in the browser only when an admin configures a
measurement id.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config

_DB_PATH = config.RUNTIME_DIR / "analytics.db"
_lock = threading.Lock()
_local = threading.local()

RETENTION_DAYS_DEFAULT = 400
MAX_BATCH = 20

# what the beacon may report; anything else is dropped
EVENT_KINDS = ("pageview", "product_view", "catalog_search", "filter_use",
               "add_to_request", "enquiry", "manual_download", "outbound", "form_error")
VITAL_METRICS = ("LCP", "CLS", "INP", "FCP", "TTFB")

_PATH_RE = re.compile(r"^/[\w./#?=&%-]{0,120}$")
_CLEAN_RE = re.compile(r"[\x00-\x1f\x7f]")


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            day TEXT NOT NULL,
            kind TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            visitor TEXT NOT NULL DEFAULT '',
            session TEXT NOT NULL DEFAULT '',
            referrer TEXT NOT NULL DEFAULT '',
            country TEXT NOT NULL DEFAULT '',
            device TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL DEFAULT '',
            value REAL
        );
        CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
        CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, day);
        CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            day TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            device TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_vitals_day ON vitals(day, metric);
        """)
        conn.commit()
        _local.conn = conn
    return conn


# ---------------- privacy helpers ----------------

def _today(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def visitor_hash(ip: str, user_agent: str, day: str | None = None) -> str:
    """Daily-salted, truncated. Rotates every UTC day and is never reversible."""
    day = day or _today()
    salt = hmac.new(config.EM_IP_HASH_SECRET.encode(), f"em-analytics:{day}".encode(),
                    hashlib.sha256).digest()
    digest = hmac.new(salt, f"{ip}|{user_agent[:120]}".encode(), hashlib.sha256).hexdigest()
    return digest[:20]


def device_class(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "ipad" in ua or ("tablet" in ua and "mobile" not in ua) or "sm-t" in ua:
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    return "desktop"


def _clean(value: str, limit: int) -> str:
    return _CLEAN_RE.sub("", str(value or "")).strip()[:limit]


def referrer_host(value: str) -> str:
    value = _clean(value, 300)
    if not value:
        return ""
    m = re.match(r"^https?://([^/:?#]{1,100})", value)
    if not m:
        return ""
    host = m.group(1).lower().lstrip("www.")
    own = {o.split("//")[-1].split(":")[0].lstrip("www.") for o in config.ALLOWED_ORIGINS}
    return "" if host in own else host


def clean_path(value: str) -> str:
    value = _clean(value, 140)
    if not value.startswith("/"):
        return ""
    value = value.split("?")[0].split("#")[0]
    return value if _PATH_RE.match(value) else ""


# ---------------- ingestion ----------------

def record(kind: str, *, path: str = "", visitor: str = "", session: str = "",
           referrer: str = "", country: str = "", device: str = "",
           meta: str = "", value: float | None = None) -> bool:
    if kind not in EVENT_KINDS:
        return False
    now = int(time.time())
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO events (ts, day, kind, path, visitor, session, referrer, country,"
            " device, meta, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (now, _today(now), kind, clean_path(path), visitor[:20], _clean(session, 24),
             _clean(referrer, 100), _clean(country, 2).upper(), _clean(device, 10),
             _clean(meta, 120), value))
        conn.commit()
    return True


def record_vital(metric: str, value: float, path: str, device: str) -> bool:
    if metric not in VITAL_METRICS:
        return False
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    if not (0 <= value <= 600000):
        return False
    now = int(time.time())
    with _lock:
        conn = _connect()
        conn.execute("INSERT INTO vitals (ts, day, path, metric, value, device) VALUES (?,?,?,?,?,?)",
                     (now, _today(now), clean_path(path), metric, value, _clean(device, 10)))
        conn.commit()
    return True


def prune(retention_days: int = RETENTION_DAYS_DEFAULT) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(7, retention_days))).strftime("%Y-%m-%d")
    with _lock:
        conn = _connect()
        cur = conn.execute("DELETE FROM events WHERE day < ?", (cutoff,))
        conn.execute("DELETE FROM vitals WHERE day < ?", (cutoff,))
        conn.commit()
        return cur.rowcount


# ---------------- reporting ----------------

def _rows(sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in _connect().execute(sql, params).fetchall()]


def _one(sql: str, params: tuple = ()) -> dict:
    row = _connect().execute(sql, params).fetchone()
    return dict(row) if row else {}


def _range(days: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _totals(start: str, end: str) -> dict:
    return _one(
        "SELECT COUNT(*) AS views, COUNT(DISTINCT visitor) AS visitors,"
        " COUNT(DISTINCT session) AS sessions FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ?", (start, end))


def _pct(now: float, before: float) -> float | None:
    if not before:
        return None
    return round((now - before) / before * 100, 1)


_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_range(start: str = "", end: str = "", days: int = 30) -> tuple[str, str, int]:
    """Explicit start/end win; otherwise fall back to a rolling window."""
    if _DAY_RE.match(start or "") and _DAY_RE.match(end or ""):
        try:
            s = datetime.strptime(start, "%Y-%m-%d")
            e = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            return (*_range(30), 30)
        if e < s:
            s, e = e, s
        span = (e - s).days + 1
        if span > 1100:
            e = s + timedelta(days=1099)
            span = 1100
        return s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), span
    days = max(1, min(365, days))
    s, e = _range(days)
    return s, e, days


def summary(days: int = 30, start: str = "", end: str = "") -> dict:
    start, end, days = parse_range(start, end, days)
    span = timedelta(days=days)
    prev_start = (datetime.strptime(start, "%Y-%m-%d") - span).strftime("%Y-%m-%d")
    prev_end = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    totals = _totals(start, end)
    previous = _totals(prev_start, prev_end)

    series_rows = {r["day"]: r for r in _rows(
        "SELECT day, COUNT(*) AS views, COUNT(DISTINCT visitor) AS visitors FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ? GROUP BY day", (start, end))}
    series = []
    cursor = datetime.strptime(start, "%Y-%m-%d")
    for _ in range(min(days, 400)):
        key = cursor.strftime("%Y-%m-%d")
        row = series_rows.get(key, {})
        series.append({"day": key, "views": row.get("views", 0), "visitors": row.get("visitors", 0)})
        cursor += timedelta(days=1)

    top_pages = _rows(
        "SELECT path AS label, COUNT(*) AS count, COUNT(DISTINCT visitor) AS visitors FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ? AND path<>''"
        " GROUP BY path ORDER BY count DESC LIMIT 12", (start, end))
    referrers = _rows(
        "SELECT referrer AS label, COUNT(*) AS count FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ? AND referrer<>''"
        " GROUP BY referrer ORDER BY count DESC LIMIT 10", (start, end))
    countries = _rows(
        "SELECT country AS label, COUNT(DISTINCT visitor) AS count FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ? AND country<>''"
        " GROUP BY country ORDER BY count DESC LIMIT 10", (start, end))
    devices = _rows(
        "SELECT device AS label, COUNT(*) AS count FROM events"
        " WHERE kind='pageview' AND day BETWEEN ? AND ? AND device<>''"
        " GROUP BY device ORDER BY count DESC", (start, end))
    entry = _rows(
        "SELECT path AS label, COUNT(*) AS count FROM ("
        "  SELECT session, path, MIN(ts) FROM events WHERE kind='pageview'"
        "  AND day BETWEEN ? AND ? AND session<>'' GROUP BY session"
        ") GROUP BY path ORDER BY count DESC LIMIT 8", (start, end))
    exit_pages = _rows(
        "SELECT path AS label, COUNT(*) AS count FROM ("
        "  SELECT session, path, MAX(ts) FROM events WHERE kind='pageview'"
        "  AND day BETWEEN ? AND ? AND session<>'' GROUP BY session"
        ") GROUP BY path ORDER BY count DESC LIMIT 8", (start, end))

    # catalog intelligence
    products = _rows(
        "SELECT meta AS label, COUNT(*) AS count FROM events"
        " WHERE kind='product_view' AND day BETWEEN ? AND ? AND meta<>''"
        " GROUP BY meta ORDER BY count DESC LIMIT 10", (start, end))
    searches = _rows(
        "SELECT meta AS label, COUNT(*) AS count FROM events"
        " WHERE kind='catalog_search' AND day BETWEEN ? AND ? AND meta<>''"
        " GROUP BY meta ORDER BY count DESC LIMIT 10", (start, end))
    filters = _rows(
        "SELECT meta AS label, COUNT(*) AS count FROM events"
        " WHERE kind='filter_use' AND day BETWEEN ? AND ? AND meta<>''"
        " GROUP BY meta ORDER BY count DESC LIMIT 8", (start, end))
    funnel_counts = {r["kind"]: r["count"] for r in _rows(
        "SELECT kind, COUNT(*) AS count FROM events WHERE day BETWEEN ? AND ?"
        " AND kind IN ('product_view','add_to_request','enquiry','manual_download')"
        " GROUP BY kind", (start, end))}
    funnel = [
        {"step": "Product views", "count": funnel_counts.get("product_view", 0)},
        {"step": "Added to request", "count": funnel_counts.get("add_to_request", 0)},
        {"step": "Enquiry sent", "count": funnel_counts.get("enquiry", 0)},
    ]
    for i, step in enumerate(funnel):
        first = funnel[0]["count"]
        step["rate"] = round(step["count"] / first * 100, 1) if first and i else (100.0 if first else 0.0)

    vitals = []
    for metric in VITAL_METRICS:
        values = [r["value"] for r in _rows(
            "SELECT value FROM vitals WHERE metric=? AND day BETWEEN ? AND ? ORDER BY value",
            (metric, start, end))]
        if values:
            p75 = values[min(len(values) - 1, int(len(values) * 0.75))]
            vitals.append({"metric": metric, "p75": round(p75, 3), "samples": len(values)})
    slow_pages = _rows(
        "SELECT path AS label, ROUND(AVG(value)) AS count FROM vitals"
        " WHERE metric='LCP' AND day BETWEEN ? AND ? AND path<>''"
        " GROUP BY path HAVING COUNT(*) >= 2 ORDER BY AVG(value) DESC LIMIT 6", (start, end))

    manual_downloads = funnel_counts.get("manual_download", 0)
    form_errors = _one("SELECT COUNT(*) AS c FROM events WHERE kind='form_error'"
                       " AND day BETWEEN ? AND ?", (start, end)).get("c", 0)

    alerts = []
    change = _pct(totals.get("views", 0), previous.get("views", 0))
    if change is not None and previous.get("views", 0) >= 50:
        if change <= -35:
            alerts.append({"level": "warn",
                           "text": f"Traffic is down {abs(change)}% versus the previous {days} days."})
        elif change >= 60:
            alerts.append({"level": "good",
                           "text": f"Traffic is up {change}% versus the previous {days} days."})
    if form_errors >= 5:
        alerts.append({"level": "warn",
                       "text": f"{form_errors} form errors were reported by visitors — check the forms."})
    lcp = next((v for v in vitals if v["metric"] == "LCP"), None)
    if lcp and lcp["p75"] > 2500:
        alerts.append({"level": "warn",
                       "text": f"Largest Contentful Paint is {int(lcp['p75'])} ms at the 75th percentile (target: under 2500 ms)."})

    return {
        "days": days, "start": start, "end": end,
        "totals": {
            "views": totals.get("views", 0), "visitors": totals.get("visitors", 0),
            "sessions": totals.get("sessions", 0),
            "viewsChange": change,
            "visitorsChange": _pct(totals.get("visitors", 0), previous.get("visitors", 0)),
        },
        "series": series, "topPages": top_pages, "referrers": referrers,
        "countries": countries, "devices": devices,
        "entryPages": entry, "exitPages": exit_pages,
        "products": products, "searches": searches, "filters": filters,
        "funnel": funnel, "manualDownloads": manual_downloads,
        "vitals": vitals, "slowPages": slow_pages, "alerts": alerts,
        "totalEvents": _one("SELECT COUNT(*) AS c FROM events").get("c", 0),
    }
