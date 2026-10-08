"""Shared web catalogues: the link, the viewer's data, and what it cannot do.

Four promises are load-bearing, and each one is tested as a promise rather
than as an implementation detail:

* **No price, ever.** The same guarantee the PDF has, read back out of the
  payload a browser is actually served.
* **No supplier call.** Making a share reads the cached snapshot; opening one
  reads our own database and our own files. A client refreshing a page must
  never cost one of the five calls a market gets each day.
* **The link is the credential.** Only its SHA-256 is stored, so nothing — not
  the database, not the audit log, not the listing endpoint — can hand a
  working link to anybody who did not already have it.
* **Revoked means revoked.** The page, the data, the pictures and the document
  all stop together.
"""
from __future__ import annotations

import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import catalogue as cat
from server import catalogue_share as cs
from server import config
from server import jasani
from server.main import app

client = TestClient(app)
TOTP: dict[str, str] = {}
STOCK_AT = 1760000000


@pytest.fixture(scope="module", autouse=True)
def admin(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("share-runtime")
    old_db, old_runtime = aa._DB_PATH, config.RUNTIME_DIR
    aa._DB_PATH = runtime / "admin.db"
    config.RUNTIME_DIR = runtime
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    client.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com",
                                              "name": "Owner",
                                              "password": "correct-horse-battery",
                                              "setupCode": ""})
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    TOTP["secret"] = r["secret"]
    client.post("/api/admin/2fa/verify",
                json={"pending": r["pending"],
                      "code": aa._totp_at(r["secret"], int(time.time() // 30))})
    yield
    client.post("/api/admin/logout", headers=csrf())
    aa._DB_PATH, config.RUNTIME_DIR = old_db, old_runtime
    if hasattr(aa._local, "conn"):
        del aa._local.conn


def csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    """A small KSA snapshot on disk, with no supplier anywhere near it. One
    product carries a real supplier habit — a recommended price written into
    the middle of otherwise useful prose."""
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = []
    for n in range(6):
        products.append({
            "id": str(2000 + n),
            "code": f"ITGL {2000 + n}",
            "name": f"Sample Product {n}",
            "brand": "Jasani" if n % 2 else "Elite",
            "color": "Blue" if n % 2 else "Black",
            "material": "Stainless steel",
            "size": "104 x 66 x 15 mm",
            "capacity": "500 ml",
            "categories": ["Drinkware" if n % 2 else "Notebooks"],
            "description": ("A well-made corporate gift. RRP: SAR 45. "
                            "Capacity 500 ml." if n == 3 else
                            f"A useful item, number {n}."),
            "image": f"https://www.giftsksa.com/img/{n}.jpg",
            # products 4 and 5 deliberately share one photograph
            "images": [f"https://www.giftsksa.com/img/{min(n, 4)}.jpg"],
            "unitsPerCarton": 24,
            "stock": {"available": 10 * n, "incoming": 0},
        })
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": products}),
        encoding="utf-8")
    return products


def jpeg_bytes(seed=0, w=800, h=800) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), (250, 249, 247))
    d = ImageDraw.Draw(im)
    d.ellipse([w * .2, h * .2, w * .8, h * .8], fill=(40 + seed * 30, 90, 160))
    for i in range(0, w, 70):
        d.line([(i, 0), (i + seed * 9, h)], fill=(200 - i % 60, 120, 70), width=5)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


@pytest.fixture
def photos(monkeypatch):
    """Every image URL answers with a real JPEG, and the reads are counted."""
    made: dict[str, bytes] = {}
    stats = {"fetches": 0}

    async def serve(url):
        stats["fetches"] += 1
        made.setdefault(url, jpeg_bytes(seed=len(made)))
        return made[url]

    monkeypatch.setattr(jasani, "_fetch_image_bytes", serve)
    return stats


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    if "photos" in request.fixturenames:
        return

    async def nothing(url):
        return None

    monkeypatch.setattr(jasani, "_fetch_image_bytes", nothing)


@pytest.fixture(autouse=True)
def clean_store():
    """Each test gets the store to itself, so a sweep in one cannot take a
    picture another is still using."""
    yield
    for path in cs.assets_dir().glob("*.webp"):
        path.unlink(missing_ok=True)
    for path in cs.pdf_dir().glob("*.pdf"):
        path.unlink(missing_ok=True)
    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM catalogue_shares")
        conn.execute("DELETE FROM catalogue_assets")
        conn.commit()
    cs._HASHES.clear()
    cs._SNAPSHOTS.clear()


# ---------------- making a share ----------------

def start_share(**body):
    payload = {"market": "ksa", "scope": "selected"}
    payload.update(body)
    return client.post("/api/admin/jasani/catalogue/share", json=payload,
                       headers=csrf())


def finish(token: str) -> dict:
    for _ in range(600):
        job = client.get("/api/admin/jasani/catalogue/status",
                         params={"token": token}).json()["job"]
        if job["state"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("share did not finish")


def make_share(ids=("2000", "2001"), **body) -> dict:
    res = start_share(ids=list(ids), **body)
    assert res.status_code == 200, res.text
    job = finish(res.json()["token"])
    assert job["state"] == "done", job
    assert job["share"]["url"].startswith("/catalogue/")
    return job["share"]


def test_a_share_is_created_and_its_link_opens(snapshot, photos):
    share = make_share()
    page = client.get(share["url"])
    assert page.status_code == 200
    assert 'data-state="ok"' in page.text
    assert page.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert "noindex,nofollow,noarchive" in page.text


def test_the_link_is_handed_over_once_and_never_stored(snapshot, photos):
    share = make_share()
    token = share["url"].rsplit("/", 1)[-1]
    assert len(token) >= 20
    row = aa._connect().execute("SELECT * FROM catalogue_shares WHERE id=?",
                                (share["id"],)).fetchone()
    blob = " ".join(str(row[k]) for k in row.keys())
    assert token not in blob, "the raw token reached the database"
    assert row["token_hash"] == cs.hash_token(token)
    # nor is it in the listing, nor in the audit trail
    listed = client.get("/api/admin/jasani/catalogue/shares").json()
    assert token not in json.dumps(listed)
    entries = aa.audit_list(20, module="jasani")
    assert token not in json.dumps(entries)
    assert any(e["action"] == "jasani.share_created" for e in entries)


def test_the_payload_carries_the_products_and_no_price(snapshot, photos):
    share = make_share(ids=["2000", "2001", "2003"])
    data = client.get(share["url"] + "/index.json").json()
    assert data["count"] == 3
    assert [i["code"] for i in data["items"]] == ["ITGL 2000", "ITGL 2001", "ITGL 2003"]
    whole = json.dumps(data).lower()
    for word in ("rrp", "sar", "aed", "retail price", "list_price", "wholesale"):
        assert word not in whole, word


def test_the_supplier_price_sentence_is_removed_not_refused(snapshot, photos):
    """A real Jasani description carries "RRP: SAR 45" in the middle of
    useful prose. The sentence goes; the rest of the description stays, and
    the share is published."""
    share = make_share(ids=["2003"])
    product = client.get(share["url"] + "/p/0.json").json()["product"]
    assert "A well-made corporate gift." in product["desc"]
    assert "Capacity 500 ml." in product["desc"]
    assert "rrp" not in product["desc"].lower()


def test_a_snapshot_that_still_carried_a_price_is_refused():
    with pytest.raises(cs.ShareError):
        cs.assert_snapshot_price_free([{"name": "Mug", "desc": "RRP: SAR 45."}])
    with pytest.raises(cs.ShareError):
        cs.assert_snapshot_price_free([{"name": "Mug", "specs": [["Unit price", "45"]]}])
    # and the message names the field, never the figure
    try:
        cs.assert_snapshot_price_free([{"name": "Mug", "desc": "RRP: SAR 45."}])
    except cs.ShareError as exc:
        assert "45" not in str(exc)


def test_one_product_is_read_at_a_time(snapshot, photos):
    share = make_share(ids=["2000"])
    full = client.get(share["url"] + "/p/0.json").json()["product"]
    assert full["name"] == "Sample Product 0"
    # the labels a normalized snapshot really carries, read through the same
    # `spec_rows` the PDF page uses
    assert [row[0] for row in full["specs"]] == ["Brand", "Colour",
                                                 "Units per carton", "Category"]
    assert ("Brand", "Elite") in [tuple(row) for row in full["specs"]]
    # the index is the small record: no specifications, no description
    small = client.get(share["url"] + "/index.json").json()["items"][0]
    assert "specs" not in small and "desc" not in small
    assert client.get(share["url"] + "/p/99.json").status_code == 404
    assert client.get(share["url"] + "/p/-1.json").status_code == 404


def test_a_page_option_that_is_off_is_not_in_the_payload(snapshot, photos):
    share = make_share(ids=["2000"], specs=False, description=False, stockQty=False)
    product = client.get(share["url"] + "/p/0.json").json()["product"]
    assert "specs" not in product
    assert "desc" not in product
    assert "qty" not in product and "stockText" not in product


# ---------------- pictures ----------------

def test_photographs_are_served_from_our_own_store(snapshot, photos):
    share = make_share(ids=["2000"])
    item = client.get(share["url"] + "/index.json").json()["items"][0]
    assert len(item["img"]) == 64
    got = client.get(share["url"] + "/i/" + item["img"] + ".webp")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/webp"
    assert got.content[:4] == b"RIFF" and got.content[8:12] == b"WEBP"


def test_one_photograph_shared_by_two_products_is_stored_once(snapshot, photos):
    share = make_share(ids=["2004", "2005"])
    items = client.get(share["url"] + "/index.json").json()["items"]
    assert items[0]["img"] == items[1]["img"]
    assert len(list(cs.assets_dir().glob("*.webp"))) == 1


def test_a_picture_this_share_does_not_name_is_not_served(snapshot, photos):
    one = make_share(ids=["2000"])
    other = make_share(ids=["2001"])
    mine = client.get(one["url"] + "/index.json").json()["items"][0]["img"]
    theirs = client.get(other["url"] + "/index.json").json()["items"][0]["img"]
    assert mine != theirs
    assert client.get(one["url"] + "/i/" + theirs + ".webp").status_code == 404


def test_a_picture_name_is_a_hash_and_nothing_else(snapshot, photos):
    share = make_share(ids=["2000"])
    for bad in ("../../admin.db", "..%2f..%2fadmin.db", "a" * 64, "x.webp",
                "0123456789abcdef"):
        assert client.get(share["url"] + "/i/" + bad).status_code in (404, 400), bad


# ---------------- no supplier call, ever ----------------

def test_opening_a_share_never_reaches_the_supplier(snapshot, photos, monkeypatch):
    share = make_share(ids=["2000", "2001"])

    def boom(*a, **kw):
        raise AssertionError("a share view reached the supplier")

    monkeypatch.setattr(jasani, "_fetch", boom)
    monkeypatch.setattr(jasani, "_fetch_image_bytes", boom)
    monkeypatch.setattr(jasani, "_budget_ok", boom)
    assert client.get(share["url"]).status_code == 200
    data = client.get(share["url"] + "/index.json").json()
    assert data["count"] == 2
    assert client.get(share["url"] + "/p/0.json").status_code == 200
    img = data["items"][0]["img"]
    assert client.get(share["url"] + "/i/" + img + ".webp").status_code == 200


def test_building_a_share_never_reaches_a_primary_endpoint(snapshot, photos,
                                                           monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a share build charged the supplier budget")

    monkeypatch.setattr(jasani, "_fetch", boom)
    monkeypatch.setattr(jasani, "_budget_ok", boom)
    share = make_share(ids=["2000", "2001", "2002"])
    assert share["products"] == 3


def test_the_share_is_frozen_against_a_later_snapshot(snapshot, photos, tmp_path):
    """The supplier's catalogue moves on; a link already sent does not."""
    share = make_share(ids=["2000"])
    before = client.get(share["url"] + "/index.json").json()["items"][0]
    moved = [dict(p, name="Renamed", stock={"available": 999}) for p in snapshot]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT + 99, "stockAt": STOCK_AT + 99, "products": moved}),
        encoding="utf-8")
    after = client.get(share["url"] + "/index.json").json()["items"][0]
    assert after == before
    assert after["name"] == "Sample Product 0" and after["qty"] == 0


# ---------------- the optional document ----------------

def test_a_pdf_is_not_offered_unless_the_share_allows_one(snapshot, photos):
    share = make_share(ids=["2000"])
    assert share["allowPdf"] is False
    assert client.get(share["url"] + "/index.json").json()["allowPdf"] is False
    assert client.get(share["url"] + "/pdf").status_code == 404


def test_an_allowed_pdf_is_the_same_catalogue_and_is_price_free(snapshot, photos):
    share = make_share(ids=["2000", "2003"], allowPdf=True)
    assert share["allowPdf"] is True and share["pdfBytes"] > 0
    assert client.get(share["url"] + "/index.json").json()["allowPdf"] is True
    got = client.get(share["url"] + "/pdf")
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/pdf"
    assert got.content[:5] == b"%PDF-"
    text = cat.extract_text(got.content)
    assert "Sample Product 0" in text
    cat.assert_price_free(got.content)     # raises if anything leaked


# ---------------- expiry and revocation ----------------

def test_the_default_life_is_thirty_days_and_the_choices_are_honoured(snapshot, photos):
    now = int(time.time())
    default = make_share(ids=["2000"])
    assert 29 * 86400 < default["expiresAt"] - now < 31 * 86400
    for days in (7, 90):
        share = make_share(ids=["2000"], expiryDays=days)
        assert (days - 1) * 86400 < share["expiresAt"] - now < (days + 1) * 86400
    forever = make_share(ids=["2000"], expiryDays=0)
    assert forever["expiresAt"] is None
    odd = make_share(ids=["2000"], expiryDays=4)       # not on the list
    assert 29 * 86400 < odd["expiresAt"] - now < 31 * 86400


def test_an_expired_link_says_so_and_stops_serving(snapshot, photos):
    share = make_share(ids=["2000"])
    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE catalogue_shares SET expires_at=? WHERE id=?",
                     (int(time.time()) - 60, share["id"]))
        conn.commit()
    page = client.get(share["url"])
    assert page.status_code == 410
    assert 'data-state="expired"' in page.text
    assert "expired" in page.text.lower()
    assert client.get(share["url"] + "/index.json").status_code == 410
    assert client.get(share["url"] + "/pdf").status_code == 410


def test_revoking_stops_the_page_the_data_and_the_document(snapshot, photos):
    share = make_share(ids=["2000"], allowPdf=True)
    img = client.get(share["url"] + "/index.json").json()["items"][0]["img"]
    assert client.get(share["url"] + "/i/" + img + ".webp").status_code == 200
    res = client.post("/api/admin/jasani/catalogue/shares/revoke",
                      json={"id": share["id"]}, headers=csrf())
    assert res.status_code == 200, res.text
    page = client.get(share["url"])
    assert page.status_code == 404
    assert 'data-state="revoked"' in page.text
    assert client.get(share["url"] + "/index.json").status_code == 404
    assert client.get(share["url"] + "/pdf").status_code == 404
    assert client.get(share["url"] + "/i/" + img + ".webp").status_code == 404
    # the row stays — who shared what, and when it stopped — the copy does not
    row = aa._connect().execute("SELECT * FROM catalogue_shares WHERE id=?",
                                (share["id"],)).fetchone()
    assert row["revoked_at"] and row["revoked_by"] == "owner@elitemarcom.com"
    assert row["snapshot"] == "" and row["pdf_file"] == ""
    assert not list(cs.pdf_dir().glob("*.pdf"))
    # the picture is unreachable at once; the file itself is swept once it is
    # past the grace period that protects a build in flight
    assert list(cs.assets_dir().glob("*.webp"))
    cs.cleanup(grace=0)
    assert not list(cs.assets_dir().glob("*.webp"))


def test_revoking_a_share_leaves_another_shares_pictures_alone(snapshot, photos):
    keep = make_share(ids=["2000"])
    drop = make_share(ids=["2001"])
    kept = client.get(keep["url"] + "/index.json").json()["items"][0]["img"]
    client.post("/api/admin/jasani/catalogue/shares/revoke",
                json={"id": drop["id"]}, headers=csrf())
    assert client.get(keep["url"] + "/i/" + kept + ".webp").status_code == 200
    assert (cs.assets_dir() / f"{kept}.webp").exists()


def test_the_sweep_leaves_a_picture_a_build_may_still_be_writing(snapshot, photos):
    """A build stores its photographs before it has a snapshot to name them
    in, so a sweep landing at that moment must not take them."""
    share = make_share(ids=["2000"])
    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE catalogue_shares SET snapshot='' WHERE id=?",
                     (share["id"],))
        conn.commit()
    files = list(cs.assets_dir().glob("*.webp"))
    assert files
    cs.cleanup()                              # the default grace protects them
    assert list(cs.assets_dir().glob("*.webp")) == files
    cs.cleanup(grace=0)                       # and nothing names them now
    assert not list(cs.assets_dir().glob("*.webp"))


def test_cleanup_drops_an_expired_snapshot_and_sweeps_its_pictures(snapshot, photos):
    share = make_share(ids=["2000"], allowPdf=True)
    assert list(cs.assets_dir().glob("*.webp"))
    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE catalogue_shares SET expires_at=? WHERE id=?",
                     (int(time.time()) - 1, share["id"]))
        conn.commit()
    swept = cs.cleanup(grace=0)
    assert swept["expired"] == 1 and swept["assetsRemoved"] >= 1
    assert not list(cs.assets_dir().glob("*.webp"))
    assert not list(cs.pdf_dir().glob("*.pdf"))
    assert aa._connect().execute(
        "SELECT COUNT(*) FROM catalogue_assets").fetchone()[0] == 0


def test_an_unknown_link_is_a_closed_door_not_an_error(snapshot):
    page = client.get("/catalogue/" + "z" * 22)
    assert page.status_code == 404
    assert 'data-state="unknown"' in page.text
    assert "not available" in page.text.lower()
    assert page.headers["x-robots-tag"] == "noindex, nofollow, noarchive"


# ---------------- what is recorded about a visit ----------------

def test_a_view_is_a_counter_and_nothing_else(snapshot, photos):
    share = make_share(ids=["2000"])
    for _ in range(3):
        client.get(share["url"], headers={"User-Agent": "Mozilla/5.0 (secret)",
                                          "X-Forwarded-For": "203.0.113.9"})
    row = aa._connect().execute("SELECT * FROM catalogue_shares WHERE id=?",
                                (share["id"],)).fetchone()
    assert row["views"] == 3
    assert row["last_viewed_at"] >= int(time.time()) - 60
    blob = " ".join(str(row[k]) for k in row.keys())
    assert "Mozilla" not in blob and "203.0.113" not in blob
    assert "user_agent" not in row.keys() and "ip" not in row.keys()
    listed = client.get("/api/admin/jasani/catalogue/shares").json()["shares"]
    mine = [s for s in listed if s["id"] == share["id"]][0]
    assert mine["views"] == 3 and mine["state"] == "live"


def test_reading_the_data_does_not_count_as_another_view(snapshot, photos):
    share = make_share(ids=["2000"])
    client.get(share["url"])
    client.get(share["url"] + "/index.json")
    client.get(share["url"] + "/p/0.json")
    row = aa._connect().execute("SELECT views FROM catalogue_shares WHERE id=?",
                                (share["id"],)).fetchone()
    assert row["views"] == 1


# ---------------- who may do this ----------------

def test_sharing_needs_an_authenticated_admin(snapshot):
    other = TestClient(app)
    assert other.post("/api/admin/jasani/catalogue/share",
                      json={"market": "ksa"}).status_code in (401, 403)
    assert other.get("/api/admin/jasani/catalogue/shares").status_code in (401, 403)
    assert other.post("/api/admin/jasani/catalogue/shares/revoke",
                      json={"id": 1}).status_code in (401, 403)


def test_a_share_without_the_csrf_header_is_refused(snapshot):
    assert client.post("/api/admin/jasani/catalogue/share",
                       json={"market": "ksa", "ids": ["2000"]}).status_code == 403


def test_nothing_to_share_is_a_clear_refusal(snapshot):
    res = start_share(ids=[])
    assert res.status_code == 400
    assert "select" in res.json()["detail"].lower()


def test_a_share_is_capped_at_the_catalogue_ceiling(snapshot, monkeypatch):
    monkeypatch.setattr(cat, "MAX_ITEMS", 2)
    res = start_share(ids=["2000", "2001", "2002"])
    assert res.status_code == 400
    assert "at most 2" in res.json()["detail"]


# ---------------- what a client actually downloads ----------------

@pytest.fixture
def big_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = [{
        "id": str(3000 + n), "code": f"ITGL {3000 + n}",
        "name": f"Corporate Gift Number {n:03d} - Black",
        "brand": "Jasani" if n % 2 else "Elite",
        "color": "Blue" if n % 3 else "Black", "material": "Stainless steel",
        "size": "104 x 66 x 15 mm", "capacity": "500 ml",
        "categories": ["Drinkware" if n % 2 else "Notebooks"],
        "description": "A well-made corporate gift suited to events and "
                       "giveaways, supplied in branded cartons." * 3,
        "image": f"https://www.giftsksa.com/img/{n}.jpg",
        "images": [f"https://www.giftsksa.com/img/{n}.jpg"],
        "unitsPerCarton": 24, "stock": {"available": n, "incoming": 0},
    } for n in range(120)]
    (tmp_path / "giveaways-ksa.json").write_text(json.dumps(
        {"fetchedAt": STOCK_AT, "stockAt": STOCK_AT, "products": products}),
        encoding="utf-8")
    return products


def test_the_first_request_is_small_however_long_the_catalogue(big_snapshot, photos):
    """The two-stage load is the point. A hundred and twenty products with
    long descriptions and a dozen specifications each would be hundreds of
    kilobytes in one payload; the index is a fraction of that, and the rest
    arrives one product at a time."""
    share = make_share(ids=[str(3000 + n) for n in range(120)])
    assert share["products"] == 120
    index = client.get(share["url"] + "/index.json")
    assert index.status_code == 200
    assert len(index.content) < 40_000, len(index.content)
    data = index.json()
    assert data["count"] == 120 and len(data["items"]) == 120
    one = client.get(share["url"] + "/p/60.json").json()["product"]
    assert len(one["desc"]) > 100 and len(one["specs"]) >= 4
    # the whole catalogue's detail is never sent in one go
    assert len(index.content) < len(json.dumps(one).encode()) * 120


def test_a_picture_is_prepared_once_per_distinct_photograph(big_snapshot, photos):
    share = make_share(ids=[str(3000 + n) for n in range(120)])
    assert photos["fetches"] == 120, "one read per distinct URL, no more"
    assert len(list(cs.assets_dir().glob("*.webp"))) == 120
    again = make_share(ids=[str(3000 + n) for n in range(120)])
    assert photos["fetches"] == 120, "re-sharing re-reads nothing"
    assert again["products"] == 120


# ---------------- the viewer's own assets ----------------

def test_the_viewer_shell_is_shipped_and_self_contained():
    html = (config.PUBLIC_DIR / "catalogue-view.html").read_text(encoding="utf-8")
    assert "noindex,nofollow,noarchive" in html
    # CSP has no 'unsafe-inline' for scripts, so the viewer's JS must be a file
    assert "<script" in html and "/js/catalogue-view.js" in html
    assert "<script>" not in html
    js = (config.PUBLIC_DIR / "js" / "catalogue-view.js").read_text(encoding="utf-8")
    # every product string reaches the page as text, never as markup
    assert "innerHTML" not in js
    assert "textContent" in js


def test_the_viewer_is_not_offered_to_search_engines():
    from server import content

    assert "catalogue-view" in content.SITEMAP_SKIP
    xml = content._sitemap_xml()
    assert "catalogue-view" not in xml
    robots = (config.PUBLIC_DIR / "robots.txt").read_text(encoding="utf-8")
    # never Disallow it: a page that is never fetched is a page whose noindex
    # is never read
    assert "catalogue" not in robots.lower()
