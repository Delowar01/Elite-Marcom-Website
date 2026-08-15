"""Google Analytics 4 reporting — the failure modes, not just the happy path.

Google is never called here. `fake_google` swaps in a transport that answers
the token endpoint and the Data API, so every test states exactly what Google
said and asserts what the panel does with it. The point of most of these is
that a bad answer from Google must leave Site Insights standing.
"""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import contextmanager

import httpx
import pytest

from server import config, ga4

# a throwaway RSA key, generated per test session — no real credential is ever
# needed to test the signing path, and none is ever read from the repository
_KEY_CACHE: dict[str, str] = {}


def _private_key_pem() -> str:
    if "pem" not in _KEY_CACHE:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _KEY_CACHE["pem"] = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()).decode()
    return _KEY_CACHE["pem"]


def write_credentials(tmp_path, email="reader@elite-marcom.iam.gserviceaccount.com"):
    path = tmp_path / "ga4-service-account.json"
    path.write_text(json.dumps({
        "type": "service_account", "project_id": "elite-marcom",
        "private_key_id": "abc123", "private_key": _private_key_pem(),
        "client_email": email, "token_uri": "https://oauth2.googleapis.com/token",
    }), encoding="utf-8")
    return path


class FakeGoogle:
    """Answers the token endpoint and the Data API. `reports` maps the report
    endpoint ("runReport" / "runRealtimeReport") to a list of responses, or a
    callable, so a test can make the second call differ from the first."""

    def __init__(self, reports=None, token_status=200):
        self.reports = reports or {}
        self.token_status = token_status
        self.calls: list[dict] = []
        self.token_calls = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            self.token_calls += 1
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
        endpoint = str(request.url).rsplit(":", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.calls.append({"endpoint": endpoint, "body": body, "url": str(request.url)})
        answer = self.reports.get(endpoint, {"rows": []})
        if callable(answer):
            answer = answer(body, len([c for c in self.calls if c["endpoint"] == endpoint]))
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)


@contextmanager
def fake_google(monkeypatch, tmp_path, google: FakeGoogle, property_id="123456789"):
    """Point the module at a fake Google and a throwaway credential.

    The client factory is replaced rather than httpx itself: patching the
    shared module would change it for every other caller in the process, and
    a second patch would end up wrapping the first one's transport.
    """
    def factory(timeout):
        return httpx.AsyncClient(timeout=timeout,
                                 transport=httpx.MockTransport(google.handler))

    monkeypatch.setattr(config, "GA4_PROPERTY_ID", property_id)
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS",
                        write_credentials(tmp_path))
    monkeypatch.setattr(ga4, "_new_client", factory)
    ga4.reset_state()
    ga4._creds_cache = None
    try:
        yield google
    finally:
        ga4.reset_state()
        ga4._creds_cache = None


def row(dims, metrics):
    return {"dimensionValues": [{"value": d} for d in dims],
            "metricValues": [{"value": str(m)} for m in metrics]}


def run(coro):
    return asyncio.run(coro)


# ---------------- configuration ----------------

def test_without_configuration_every_report_says_so_and_nothing_raises(monkeypatch):
    """A site with no Google set up must still open Site Insights."""
    monkeypatch.setattr(config, "GA4_PROPERTY_ID", "")
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS", None)
    ga4.reset_state()

    assert ga4.configured() is False
    board = run(ga4.dashboard("2026-01-01", "2026-01-30"))
    assert board == {"configured": False, "reason": ga4.NOT_CONFIGURED}
    live = run(ga4.realtime())
    assert live["ok"] is False and live["reason"] == ga4.NOT_CONFIGURED
    test = run(ga4.test_connection())
    assert test["ok"] is False and "property id" in test["reason"]


def test_a_property_id_is_digits_only(monkeypatch):
    """The id goes into a URL path. Anything but digits is not a property."""
    import importlib

    monkeypatch.setenv("GA4_PROPERTY_ID", "properties/123456; rm -rf /")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.GA4_PROPERTY_ID == "123456"
    finally:
        monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)
        importlib.reload(config)


def test_credentials_missing_from_disk_reads_as_not_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GA4_PROPERTY_ID", "123")
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS", tmp_path / "nope.json")
    ga4.reset_state()
    ga4._creds_cache = None
    assert ga4.credentials() == {}
    assert ga4.configured() is False


def test_a_credential_file_that_is_not_a_service_account_is_refused(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": "world"}', encoding="utf-8")
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS", bad)
    ga4._creds_cache = None
    assert ga4.credentials() == {}
    bad.write_text("not json at all", encoding="utf-8")
    ga4._creds_cache = None
    assert ga4.credentials() == {}


# ---------------- the reports ----------------

OVERVIEW_NOW = {"rows": [row([], [120, 150, 400, 80, 0.62, 9000, 95])]}
OVERVIEW_PREV = {"rows": [row([], [100, 120, 300, 70, 0.55, 7000, 70])]}


def test_overview_returns_kpis_and_a_previous_period_comparison(monkeypatch, tmp_path):
    answers = [OVERVIEW_NOW, OVERVIEW_PREV]
    google = FakeGoogle({"runReport": lambda body, n: answers[n - 1]})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.overview("2026-02-01", "2026-02-28"))

    assert out["ok"] is True
    t = out["totals"]
    assert t["activeUsers"] == 120 and t["sessions"] == 150 and t["pageViews"] == 400
    assert t["newUsers"] == 80 and t["returningUsers"] == 40      # active minus new
    assert t["engagementRate"] == 62.0                            # a rate, as a percentage
    assert t["engagedSessions"] == 95
    assert t["avgEngagementSeconds"] == 60.0                      # 9000s over 150 sessions
    assert out["changes"]["activeUsers"] == 20.0                  # 120 vs 100
    assert out["comparedWith"] == {"start": "2026-01-04", "end": "2026-01-31"}


def test_a_rise_from_nothing_is_not_a_percentage(monkeypatch, tmp_path):
    """Percentage change against zero is undefined, and drawing it as +100%
    or ∞ on a KPI card is a lie an admin would act on."""
    answers = [OVERVIEW_NOW, {"rows": [row([], [0, 0, 0, 0, 0, 0, 0])]}]
    google = FakeGoogle({"runReport": lambda body, n: answers[n - 1]})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.overview("2026-02-01", "2026-02-28"))
    assert out["changes"]["activeUsers"] is None
    assert ga4.change(5, 0) is None and ga4.change(0, 0) is None
    assert ga4.change(150, 100) == 50.0 and ga4.change(50, 100) == -50.0


def test_countries_carry_their_share_of_the_total(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": [
        row(["Saudi Arabia"], [60]), row(["United Arab Emirates"], [30]),
        row(["United Kingdom"], [10])]}})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.countries("2026-02-01", "2026-02-28"))
    assert out["ok"] is True
    assert [r["label"] for r in out["rows"]] == [
        "Saudi Arabia", "United Arab Emirates", "United Kingdom"]
    assert [r["users"] for r in out["rows"]] == [60, 30, 10]
    assert [r["share"] for r in out["rows"]] == [60.0, 30.0, 10.0]
    # the request asked Google for the right thing
    body = google.calls[0]["body"]
    assert body["dimensions"] == [{"name": "country"}]
    assert body["metrics"] == [{"name": "activeUsers"}]
    assert body["dateRanges"] == [{"startDate": "2026-02-01", "endDate": "2026-02-28"}]


def test_a_city_is_always_shown_with_its_country(monkeypatch, tmp_path):
    """"Riyadh" is unambiguous; "Springfield" is not, and several countries
    have a Dubai-sized problem."""
    google = FakeGoogle({"runReport": {"rows": [
        row(["Riyadh", "Saudi Arabia"], [40]),
        row(["Dubai", "United Arab Emirates"], [25]),
        row(["(not set)", "Saudi Arabia"], [5])]}})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.cities("2026-02-01", "2026-02-28"))
    assert [r["display"] for r in out["rows"]] == [
        "Riyadh — Saudi Arabia", "Dubai — United Arab Emirates"]
    assert google.calls[0]["body"]["dimensions"] == [{"name": "city"}, {"name": "country"}]


def test_geography_failing_says_so_in_the_words_the_screen_shows(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.Response(500, text="backend error")})
    with fake_google(monkeypatch, tmp_path, google):
        for report in (ga4.countries, ga4.cities, ga4.regions):
            out = run(report("2026-02-01", "2026-02-28"))
            assert out["ok"] is False
            assert out["reason"] == ga4.GEO_UNAVAILABLE


def test_acquisition_reports_use_the_session_scoped_dimensions(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": lambda body, n: (
        {"rows": [row(["Organic Search"], [80, 60]), row(["Direct"], [40, 35])]}
        if body["dimensions"] == [{"name": "sessionDefaultChannelGroup"}]
        else {"rows": [row(["google", "organic"], [80, 60]),
                       row(["", ""], [40, 35])]})})
    with fake_google(monkeypatch, tmp_path, google):
        chan = run(ga4.channels("2026-02-01", "2026-02-28"))
        srcs = run(ga4.sources("2026-02-01", "2026-02-28"))
    assert [r["label"] for r in chan["rows"]] == ["Organic Search", "Direct"]
    assert chan["rows"][0]["sessions"] == 80 and chan["rows"][0]["users"] == 60
    assert [round(r["share"]) for r in chan["rows"]] == [67, 33]
    # an empty source/medium is direct traffic, and it says so rather than "/"
    assert [r["label"] for r in srcs["rows"]] == ["google / organic", "(direct) / (none)"]


def test_page_and_landing_reports_shape_what_the_table_needs(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": lambda body, n: (
        {"rows": [row(["/giveaways.html", "Corporate Gifts"], [200, 90, 3600])]}
        if body["dimensions"] == [{"name": "pagePath"}, {"name": "pageTitle"}]
        else {"rows": [row(["/"], [120, 100, 0.58])]})})
    with fake_google(monkeypatch, tmp_path, google):
        pages = run(ga4.pages("2026-02-01", "2026-02-28"))
        landing = run(ga4.landing_pages("2026-02-01", "2026-02-28"))
    assert pages["rows"][0] == {"label": "/giveaways.html", "title": "Corporate Gifts",
                                "views": 200, "users": 90, "avgSeconds": 18.0}
    assert landing["rows"][0] == {"label": "/", "sessions": 120, "users": 100,
                                  "engagementRate": 58.0}


def test_devices_and_technology(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": lambda body, n: {
        "rows": [row(["mobile"], [70]), row(["desktop"], [30])]}})
    with fake_google(monkeypatch, tmp_path, google):
        dev = run(ga4.devices("2026-02-01", "2026-02-28"))
        tech = run(ga4.technology("2026-02-01", "2026-02-28"))
    assert [r["label"] for r in dev["rows"]] == ["Mobile", "Desktop"]
    assert [r["share"] for r in dev["rows"]] == [70.0, 30.0]
    assert tech["browsers"]["ok"] is True and tech["systems"]["ok"] is True


def test_new_versus_returning(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": [
        row(["new"], [80]), row(["returning"], [20]), row(["(not set)"], [3])]}})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.new_vs_returning("2026-02-01", "2026-02-28"))
    assert [(r["label"], r["users"], r["share"]) for r in out["rows"]] == [
        ("New", 80, 80.0), ("Returning", 20, 20.0)]


def test_the_daily_series_turns_ga4_dates_into_real_ones(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": [
        row(["20260201"], [10, 12, 30]), row(["20260202"], [14, 15, 44]),
        row(["nonsense"], [1, 1, 1])]}})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.series("2026-02-01", "2026-02-28"))
    assert out["series"] == [
        {"day": "2026-02-01", "users": 10, "sessions": 12, "views": 30},
        {"day": "2026-02-02", "users": 14, "sessions": 15, "views": 44}]


def test_realtime_returns_a_live_block(monkeypatch, tmp_path):
    def answer(body, n):
        dims = [d["name"] for d in body.get("dimensions", [])]
        if not dims:
            return {"rows": [row([], [7])]}
        if dims == ["unifiedScreenName"]:
            return {"rows": [row(["Corporate Gifts"], [4])]}
        if dims == ["country"]:
            return {"rows": [row(["Saudi Arabia"], [5])]}
        if dims == ["city", "country"]:
            return {"rows": [row(["Riyadh", "Saudi Arabia"], [3])]}
        return {"rows": [row(["mobile"], [5]), row(["desktop"], [2])]}
    google = FakeGoogle({"runRealtimeReport": answer})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.realtime())
    assert out["ok"] is True and out["activeUsers"] == 7
    assert out["pages"][0]["label"] == "Corporate Gifts"
    assert out["countries"][0]["label"] == "Saudi Arabia"
    assert out["cities"][0]["label"] == "Riyadh — Saudi Arabia"
    assert [(d["label"], d["share"]) for d in out["devices"]] == [
        ("Mobile", 71.4), ("Desktop", 28.6)]
    assert all(c["endpoint"] == "runRealtimeReport" for c in google.calls)


# ---------------- bad answers ----------------

def test_an_empty_google_response_is_data_not_an_error(monkeypatch, tmp_path):
    """A property with no traffic yet answers with no rows. That is "nothing
    to show", not "something broke" — the difference matters on a new site."""
    google = FakeGoogle({"runReport": {}})
    with fake_google(monkeypatch, tmp_path, google):
        assert run(ga4.countries("2026-02-01", "2026-02-28")) == {"ok": True, "rows": []}
        assert run(ga4.devices("2026-02-01", "2026-02-28")) == {"ok": True, "rows": []}
        over = run(ga4.overview("2026-02-01", "2026-02-28"))
    assert over["ok"] is True and over["totals"]["activeUsers"] == 0
    assert over["totals"]["avgEngagementSeconds"] == 0.0        # no divide by zero


def test_a_malformed_response_is_skipped_row_by_row(monkeypatch, tmp_path):
    """Google is not going to send this, but a proxy in front of it might."""
    google = FakeGoogle({"runReport": {"rows": [
        "not a row", {"dimensionValues": "wrong", "metricValues": None},
        {"dimensionValues": [{"value": "Saudi Arabia"}],
         "metricValues": [{"value": "not-a-number"}]},
        row(["Oman"], [5])]}})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.countries("2026-02-01", "2026-02-28"))
    assert out["ok"] is True
    assert [(r["label"], r["users"]) for r in out["rows"]] == [
        ("(not set)", 0), ("Saudi Arabia", 0), ("Oman", 5)]


def test_a_response_that_is_not_json_does_not_raise(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.Response(200, text="<html>proxy error</html>")})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.channels("2026-02-01", "2026-02-28"))
    assert out == {"ok": False, "reason": ga4.UNAVAILABLE}


def test_a_timeout_is_reported_as_a_timeout(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.ReadTimeout("too slow")})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.pages("2026-02-01", "2026-02-28"))
    assert out["ok"] is False and "in time" in out["reason"]


def test_quota_exhaustion_says_quota_and_permission_says_permission(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.Response(429, text="quota exceeded")})
    with fake_google(monkeypatch, tmp_path, google):
        assert "quota" in run(ga4.pages("2026-02-01", "2026-02-28"))["reason"]
    google = FakeGoogle({"runReport": httpx.Response(403, text="caller lacks permission")})
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.pages("2026-02-01", "2026-02-28"))
    assert "read access" in out["reason"]


def test_a_rejected_service_account_never_shows_googles_words(monkeypatch, tmp_path):
    google = FakeGoogle({}, token_status=400)
    with fake_google(monkeypatch, tmp_path, google):
        out = run(ga4.countries("2026-02-01", "2026-02-28"))
        state = ga4.status()
    assert out["reason"] == ga4.GEO_UNAVAILABLE
    assert "invalid_grant" not in json.dumps(state)
    assert state["lastError"] and "\n" not in state["lastError"]


def test_one_broken_report_leaves_the_others_readable(monkeypatch, tmp_path):
    """The whole point of the per-widget error state."""
    def answer(body, n):
        if body["dimensions"] == [{"name": "country"}]:
            return httpx.Response(500, text="nope")
        return {"rows": [row(["x"], [1, 1, 1])]}
    google = FakeGoogle({"runReport": answer})
    with fake_google(monkeypatch, tmp_path, google):
        board = run(ga4.dashboard("2026-02-01", "2026-02-28"))
    assert board["configured"] is True
    assert board["countries"]["ok"] is False
    assert board["devices"]["ok"] is True and board["channels"]["ok"] is True
    assert board["overview"]["ok"] is True


# ---------------- cache ----------------

def test_a_repeated_report_is_served_from_cache(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": [row(["Saudi Arabia"], [5])]}})
    with fake_google(monkeypatch, tmp_path, google):
        run(ga4.countries("2026-02-01", "2026-02-28"))
        run(ga4.countries("2026-02-01", "2026-02-28"))
        assert len(google.calls) == 1
        # a different window is a different report
        run(ga4.countries("2026-01-01", "2026-01-31"))
        assert len(google.calls) == 2
        # and the token is fetched once, not per report
        assert google.token_calls == 1


def test_the_cache_expires(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": [row(["Saudi Arabia"], [5])]}})
    with fake_google(monkeypatch, tmp_path, google):
        monkeypatch.setattr(config, "GA4_CACHE_TTL_S", 0.05)
        run(ga4.countries("2026-02-01", "2026-02-28"))
        time.sleep(0.06)
        run(ga4.countries("2026-02-01", "2026-02-28"))
    assert len(google.calls) == 2


def test_two_callers_wanting_the_same_report_make_one_request(monkeypatch, tmp_path):
    """A page load fires a dozen widgets. They must not become a dozen calls
    for the same thing, and neither must two admins on the same screen."""
    slow = FakeGoogle({})

    async def answer(request):
        if "oauth2" in str(request.url):
            slow.token_calls += 1
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        slow.calls.append({"endpoint": "runReport", "body": {}, "url": str(request.url)})
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"rows": [row(["Saudi Arabia"], [5])]})

    slow.handler = answer
    with fake_google(monkeypatch, tmp_path, slow):
        async def both():
            return await asyncio.gather(ga4.countries("2026-02-01", "2026-02-28"),
                                        ga4.countries("2026-02-01", "2026-02-28"))
        a, b = asyncio.run(both())
    assert a == b and len(slow.calls) == 1


def test_a_failure_is_cached_briefly_so_a_broken_key_is_not_hammered(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.Response(500, text="nope")})
    with fake_google(monkeypatch, tmp_path, google):
        run(ga4.countries("2026-02-01", "2026-02-28"))
        run(ga4.countries("2026-02-01", "2026-02-28"))
    assert len(google.calls) == 1


def test_realtime_has_its_own_much_shorter_cache(monkeypatch, tmp_path):
    google = FakeGoogle({"runRealtimeReport": {"rows": [row([], [3])]}})
    with fake_google(monkeypatch, tmp_path, google):
        assert config.GA4_REALTIME_TTL_S < config.GA4_CACHE_TTL_S
        run(ga4.realtime())
        first = len(google.calls)
        run(ga4.realtime())
        assert len(google.calls) == first          # inside the realtime window
        monkeypatch.setattr(config, "GA4_REALTIME_TTL_S", 0.01)
        time.sleep(0.02)
        run(ga4.realtime())
    assert len(google.calls) > first


# ---------------- dates ----------------

def test_the_date_range_reaches_every_report(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": {"rows": []}})
    with fake_google(monkeypatch, tmp_path, google):
        run(ga4.dashboard("2026-03-05", "2026-03-19"))
    windows = {tuple(c["body"]["dateRanges"][0].values()) for c in google.calls}
    # every report asked for the window, plus one previous period for the KPIs
    assert ("2026-03-05", "2026-03-19") in windows
    assert ("2026-02-18", "2026-03-04") in windows      # the 15 days before
    assert len(windows) == 2


def test_the_previous_period_is_the_equivalent_window_before_this_one():
    # 1-30 March is 30 days, so the 30 days before it end on 28 February
    assert ga4.previous_period("2026-03-01", "2026-03-30") == ("2026-01-30", "2026-02-28")
    assert ga4.previous_period("2026-03-15", "2026-03-15") == ("2026-03-14", "2026-03-14")
    assert ga4.previous_period("2026-01-01", "2026-01-07") == ("2025-12-25", "2025-12-31")


def test_a_custom_range_is_carried_through_the_admin_endpoint(monkeypatch, tmp_path):
    """The endpoint parses the range with the same function the first-party
    side uses, so the two halves of the dashboard can never disagree."""
    from server import analytics

    start, end, days = analytics.parse_range("2026-03-05", "2026-03-19", 30)
    assert (start, end, days) == ("2026-03-05", "2026-03-19", 15)


# ---------------- security ----------------

def test_no_part_of_the_credential_reaches_a_caller(monkeypatch, tmp_path):
    """The one test that matters most: whatever an admin can see must not
    contain the key, the token or the file's contents."""
    google = FakeGoogle({"runReport": {"rows": [row(["Saudi Arabia"], [5])]}})
    with fake_google(monkeypatch, tmp_path, google):
        payloads = json.dumps([
            run(ga4.dashboard("2026-02-01", "2026-02-28")),
            run(ga4.realtime()), ga4.status(), run(ga4.test_connection()),
        ])
    secret = _private_key_pem()
    assert "BEGIN PRIVATE KEY" not in payloads
    assert secret.split("\n")[1][:40] not in payloads
    assert "tok-123" not in payloads and "access_token" not in payloads
    assert "private_key" not in payloads
    # the service-account address is deliberately visible: an admin has to
    # paste it into the GA4 property to grant access
    assert "reader@elite-marcom.iam.gserviceaccount.com" in payloads


def test_status_is_safe_to_render_even_after_a_failure(monkeypatch, tmp_path):
    google = FakeGoogle({"runReport": httpx.Response(403, text="PERMISSION_DENIED: "
                                                     "caller does not have access to "
                                                     "properties/123456789")})
    with fake_google(monkeypatch, tmp_path, google):
        run(ga4.countries("2026-02-01", "2026-02-28"))
        state = ga4.status()
    assert "PERMISSION_DENIED" not in state["lastError"]
    assert state["lastError"] == ("Google refused the request — check that the service "
                                  "account has read access to this property.")
    assert state["lastErrorAt"] > 0


def test_the_signed_assertion_asks_only_for_read_access(monkeypatch, tmp_path):
    import base64 as b64

    creds = json.loads(write_credentials(tmp_path).read_text(encoding="utf-8"))
    token = ga4._signed_assertion(creds, 1_700_000_000)
    header, claims, signature = token.split(".")
    def decode(part):
        return json.loads(b64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    assert decode(header)["alg"] == "RS256"
    body = decode(claims)
    assert body["scope"] == "https://www.googleapis.com/auth/analytics.readonly"
    assert body["iss"] == "reader@elite-marcom.iam.gserviceaccount.com"
    assert body["exp"] - body["iat"] == 3600
    assert signature                      # and it is actually signed


# ---------------- the admin endpoints ----------------

@pytest.fixture(scope="module")
def admin():
    """A signed-in owner against an isolated admin database, so this file
    stands on its own rather than depending on another module having logged
    in first."""
    from fastapi.testclient import TestClient

    from server import adminauth as aa
    from server.main import app
    from tests.test_admin import sign_in

    import tempfile
    import pathlib

    old_path = aa._DB_PATH
    aa._DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "admin.db"
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    c = TestClient(app, base_url="http://127.0.0.1:8847")
    c.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com", "name": "Owner",
                                         "password": "correct-horse-battery", "setupCode": ""})
    sign_in(c, "owner@elitemarcom.com", "correct-horse-battery")
    yield c
    aa._DB_PATH = old_path
    if hasattr(aa._local, "conn"):
        del aa._local.conn


def csrf(c):
    return {"X-CSRF": c.get("/api/admin/me").json()["csrf"]}


def test_the_admin_endpoints_answer_without_google(monkeypatch, admin):
    """Site Insights, its GA4 block and realtime all reachable, and the
    first-party half complete, with no Google configured at all."""
    client = admin

    monkeypatch.setattr(config, "GA4_PROPERTY_ID", "")
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS", None)
    ga4.reset_state()

    res = client.get("/api/admin/insights?days=30")
    assert res.status_code == 200
    body = res.json()
    assert body["ga4Status"]["configured"] is False
    for key in ("totals", "series", "products", "searches", "vitals", "funnel",
                "productFlow", "manuals", "addToRequest"):
        assert key in body, key

    block = client.get("/api/admin/insights/ga4?days=30")
    assert block.status_code == 200 and block.json()["configured"] is False
    live = client.get("/api/admin/insights/realtime")
    assert live.status_code == 200 and live.json()["ok"] is False
    test = client.post("/api/admin/insights/ga4-test", headers=csrf(client))
    assert test.status_code == 200 and test.json()["ok"] is False
    assert "private" not in json.dumps(body).lower().replace("private mode", "")


def test_the_insights_payload_never_carries_a_credential(monkeypatch, tmp_path, admin):
    client = admin

    monkeypatch.setattr(config, "GA4_PROPERTY_ID", "123456789")
    monkeypatch.setattr(config, "GOOGLE_APPLICATION_CREDENTIALS",
                        write_credentials(tmp_path))
    ga4._creds_cache = None
    ga4.reset_state()
    body = client.get("/api/admin/insights?days=7").text
    assert "BEGIN PRIVATE KEY" not in body and "private_key" not in body
    # the path is shown so an admin can check the file is where they put it
    assert json.loads(body)["ga4Status"]["propertyId"] == "123456789"
    ga4._creds_cache = None
    ga4.reset_state()
