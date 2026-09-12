"""Bulk import for rental items.

The importer is only allowed to be a faster way of doing what the Add Rental
Item form already does, so these tests care about two things: that a
spreadsheet ends up as exactly the item the form would have saved, and that
an untrusted file cannot talk the server into anything — a path out of a ZIP,
a request to a private address, a formula in a downloaded report.
"""
from __future__ import annotations

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server import adminauth as aa
from server import content, media
from server import rental_import as ri
from server.main import app

client = TestClient(app)

#: the signed-in owner's 2FA secret, so a test may sign out and back in
TOTP: dict[str, str] = {}


def sign_in() -> None:
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    client.post("/api/admin/2fa/verify",
                json={"pending": r["pending"],
                      "code": aa._totp_at(TOTP["secret"], int(time.time() // 30))})


@pytest.fixture(scope="module", autouse=True)
def admin(tmp_path_factory):
    """An isolated admin database, media store and rental file for this module."""
    runtime = tmp_path_factory.mktemp("rental-import")
    # the admin connection is cached per thread, and the import runs on a
    # worker thread — so the cache has to be dropped, not just the path
    # swapped, or the two threads open two different databases
    old_db = aa._DB_PATH
    aa._DB_PATH = runtime / "admin.db"
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    old_media = (media.MEDIA_DIR, media.OVERRIDES_DIR)
    old_rentals = content.RENTAL_RUNTIME
    media.MEDIA_DIR = runtime / "media"
    media.OVERRIDES_DIR = runtime / "overrides"
    content.RENTAL_RUNTIME = runtime / "data" / "rental-inventory.json"
    client.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com", "name": "Owner",
                                              "password": "correct-horse-battery",
                                              "setupCode": ""})
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    TOTP["secret"] = r["secret"]
    client.post("/api/admin/2fa/verify", json={"pending": r["pending"],
                                               "code": aa._totp_at(r["secret"],
                                                                   int(time.time() // 30))})
    yield
    client.post("/api/admin/logout", headers=csrf())
    media.MEDIA_DIR, media.OVERRIDES_DIR = old_media
    content.RENTAL_RUNTIME = old_rentals
    aa._DB_PATH = old_db
    if hasattr(aa._local, "conn"):
        del aa._local.conn


def csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


# ---------------- helpers ----------------

def png_bytes(color="red", size=(80, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def sheet_csv(rows: list[dict], columns: list[str] | None = None) -> bytes:
    cols = columns or ri.COLUMN_NAMES
    out = [",".join(cols)]
    for row in rows:
        out.append(",".join('"' + str(row.get(c, "")).replace('"', '""') + '"' for c in cols))
    return ("\r\n".join(out)).encode("utf-8")


def sheet_xlsx(rows: list[dict]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(ri.COLUMN_NAMES)
    for row in rows:
        ws.append([row.get(c, "") for c in ri.COLUMN_NAMES])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def images_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def validate(sheet: bytes, name="items.csv", zip_bytes: bytes | None = None, **options):
    files = {"file": (name, sheet, "text/csv")}
    if zip_bytes is not None:
        files["images"] = ("images.zip", zip_bytes, "application/zip")
    data = {"onDuplicate": options.get("onDuplicate", "skip"),
            "imageMode": options.get("imageMode", "append"),
            "createCategories": options.get("createCategories", "no")}
    return client.post("/api/admin/rentals/import/validate", files=files, data=data,
                       headers=csrf())


def run_import(token: str) -> dict:
    res = client.post("/api/admin/rentals/import/run", json={"token": token}, headers=csrf())
    assert res.status_code == 200, res.text
    for _ in range(200):
        job = client.get("/api/admin/rentals/import/status",
                         params={"token": token}).json()["job"]
        if job["state"] == "done":
            return job
        time.sleep(0.05)
    raise AssertionError("import did not finish")


def rentals() -> dict[str, dict]:
    return {p["id"]: p for p in client.get("/api/admin/rentals").json()["products"]}


def a_category() -> str:
    return sorted(ri._existing_categories(content.rentals_load()[0]))[0]


def base_row(**over) -> dict:
    row = {"id": "rent-test-1", "name": "Test Item", "category": a_category()}
    row.update(over)
    return row


# ---------------- the template ----------------

def test_the_template_is_built_from_the_rental_item_itself():
    """A column here that the item does not have is a column an admin fills in
    for nothing, so the template is generated rather than typed out."""
    res = client.get("/api/admin/rentals/import/template", params={"format": "xlsx"})
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Items", "Instructions"]
    header = [c.value for c in next(wb["Items"].iter_rows(max_row=1))]
    assert header == ri.COLUMN_NAMES
    assert "id" in header and "name" in header and "category" in header
    assert "image_1" in header and "image_5" in header
    # one example row, and the instructions name the categories that exist
    assert wb["Items"].max_row == 2
    notes = "\n".join(str(c.value or "") for row in wb["Instructions"].iter_rows()
                      for c in row)
    assert a_category() in notes and "image_1" in notes and ri.CLEAR_TOKEN in notes

    csv_res = client.get("/api/admin/rentals/import/template", params={"format": "csv"})
    assert csv_res.status_code == 200 and b"id,code,name,category" in csv_res.content


def test_the_template_round_trips_through_the_parser():
    for fmt, name in (("xlsx", "t.xlsx"), ("csv", "t.csv")):
        body = client.get("/api/admin/rentals/import/template",
                          params={"format": fmt}).content
        rows = ri.parse_sheet(body, name)
        assert len(rows) == 1, fmt
        assert rows[0]["id"] == "rent-led-wall-3x2", fmt


# ---------------- valid imports ----------------

def test_a_csv_row_becomes_exactly_the_item_the_form_would_have_saved():
    row = base_row(id="rent-csv-1", code="EM-R-900", name="CSV Chair",
                   description="A chair.", specifications="Steel frame|Stackable",
                   search_tags="chair, seating", stock_ksa="7", stock_uae="3",
                   featured="yes")
    r = validate(sheet_csv([row])).json()
    assert r["summary"]["create"] == 1 and r["summary"]["errors"] == 0
    job = run_import(r["token"])
    assert job["counts"] == {"created": 1, "updated": 0, "skipped": 0, "failed": 0}
    item = rentals()["rent-csv-1"]
    assert item["name"] == "CSV Chair" and item["code"] == "EM-R-900"
    assert item["specs"] == ["Steel frame", "Stackable"]
    assert item["tags"] == ["chair", "seating"]
    assert item["stockByMarket"] == {"ksa": 7, "uae": 3}
    assert item["featured"] is True
    # the same dict the single-item cleaner produces, field for field
    assert item == content._clean_rental(item)


def test_an_xlsx_row_imports_the_same_way():
    r = validate(sheet_xlsx([base_row(id="rent-xlsx-1", name="XLSX Table")]),
                 name="items.xlsx").json()
    assert r["summary"]["create"] == 1
    run_import(r["token"])
    assert rentals()["rent-xlsx-1"]["name"] == "XLSX Table"


def test_a_mixed_sheet_imports_the_good_rows_and_reports_the_bad_ones():
    rows = [base_row(id="rent-mix-ok", name="Fine"),
            base_row(id="NOT A SLUG", name="Bad id"),
            base_row(id="rent-mix-nocat", name="Bad category", category="Nonexistent Cat"),
            base_row(id="rent-mix-ok2", name="Also fine")]
    r = validate(sheet_csv(rows)).json()
    assert r["summary"]["create"] == 2 and r["summary"]["errors"] == 2
    job = run_import(r["token"])
    assert job["counts"]["created"] == 2 and job["counts"]["failed"] == 2
    got = rentals()
    assert "rent-mix-ok" in got and "rent-mix-ok2" in got and "rent-mix-nocat" not in got


def test_the_result_counts_add_up_to_the_rows_that_were_offered():
    rows = [base_row(id="rent-count-1"), base_row(id="rent-count-2"),
            base_row(id="rent-count-bad", category="Missing Cat")]
    job = run_import(validate(sheet_csv(rows)).json()["token"])
    c = job["counts"]
    assert c["created"] + c["updated"] + c["skipped"] + c["failed"] == len(rows)


# ---------------- images ----------------

def test_images_arrive_from_a_zip_in_order_with_the_first_as_the_card_image():
    z = images_zip({"photos/chair-1.png": png_bytes("red"),
                    "photos/chair-2.png": png_bytes("green"),
                    "photos/chair-3.png": png_bytes("blue")})
    row = base_row(id="rent-zip-1", name="Zipped Chair", image_1="chair-1.png",
                   image_2="chair-2.png", image_3="chair-3.png")
    r = validate(sheet_csv([row]), zip_bytes=z).json()
    assert r["hasZip"] is True and r["rows"][0]["images"] == 3
    run_import(r["token"])
    item = rentals()["rent-zip-1"]
    assert len(item["images"]) == 3
    assert all(p.startswith("/media/") and p.endswith(".webp") for p in item["images"])
    assert item["image"] == item["images"][0], "image_1 is the card image"
    # stored through the library, so they are real rows a person can find again
    files = {m["file"] for m in media.library_list()}
    assert all(p[len("/media/"):] in files for p in item["images"])


def test_a_missing_zip_image_is_an_error_on_that_row_only():
    z = images_zip({"there.png": png_bytes()})
    rows = [base_row(id="rent-zip-ok", image_1="there.png"),
            base_row(id="rent-zip-miss", image_1="absent.png")]
    r = validate(sheet_csv(rows), zip_bytes=z).json()
    verdicts = {x["id"]: x for x in r["rows"]}
    assert verdicts["rent-zip-ok"]["action"] == "create"
    assert verdicts["rent-zip-miss"]["action"] == "error"
    assert "not in the images ZIP" in verdicts["rent-zip-miss"]["errors"][0]["message"]


def test_an_invalid_image_is_refused_by_the_media_validator():
    z = images_zip({"fake.png": b"not an image at all, just bytes"})
    r = validate(sheet_csv([base_row(id="rent-badimg", image_1="fake.png")]),
                 zip_bytes=z).json()
    assert r["rows"][0]["action"] == "error"
    assert r["summary"]["create"] == 0


def test_the_same_picture_named_twice_is_stored_once():
    same = png_bytes("purple", (120, 90))
    z = images_zip({"a.png": same, "b.png": same})
    before = len(media.library_list())
    r = validate(sheet_csv([base_row(id="rent-dedupe", image_1="a.png", image_2="b.png")]),
                 zip_bytes=z).json()
    run_import(r["token"])
    item = rentals()["rent-dedupe"]
    # identical bytes are one library file, so the item holds it once
    assert len(item["images"]) == 1
    assert len(media.library_list()) == before + 1


def test_an_existing_site_path_may_be_reused_and_a_made_up_one_may_not():
    ok = validate(sheet_csv([base_row(id="rent-path-ok",
                                      image_1="/assets/services/led-display.webp")])).json()
    assert ok["rows"][0]["action"] == "create"
    bad = validate(sheet_csv([base_row(id="rent-path-bad",
                                       image_1="/media/does-not-exist.webp")])).json()
    assert bad["rows"][0]["action"] == "error"


def test_an_image_url_is_downloaded_rather_than_hotlinked(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return png_bytes("orange")

    monkeypatch.setattr(ri, "fetch_image_url", fake_fetch)
    r = validate(sheet_csv([base_row(id="rent-url-1",
                                     image_1="https://cdn.example.com/chair.jpg")])).json()
    assert captured["url"] == "https://cdn.example.com/chair.jpg"
    run_import(r["token"])
    stored = rentals()["rent-url-1"]["images"][0]
    assert stored.startswith("/media/") and "example.com" not in stored


def test_a_broken_image_link_is_an_error_not_a_silent_skip(monkeypatch):
    def boom(url):
        raise ri.ImportError_("That image link answered 404.")

    monkeypatch.setattr(ri, "fetch_image_url", boom)
    r = validate(sheet_csv([base_row(id="rent-url-bad",
                                     image_1="https://cdn.example.com/gone.jpg")])).json()
    assert r["rows"][0]["action"] == "error"
    assert "404" in r["rows"][0]["errors"][0]["message"]


# ---------------- duplicates ----------------

def test_an_existing_item_is_skipped_by_default():
    first = base_row(id="rent-dup-1", name="Original Name")
    run_import(validate(sheet_csv([first])).json()["token"])
    again = base_row(id="rent-dup-1", name="Changed Name")
    r = validate(sheet_csv([again])).json()
    assert r["summary"]["duplicates"] == 1 and r["summary"]["skip"] == 1
    job = run_import(r["token"])
    assert job["counts"]["skipped"] == 1 and job["counts"]["created"] == 0
    assert rentals()["rent-dup-1"]["name"] == "Original Name", "nothing overwritten by default"


def test_update_existing_changes_only_the_columns_that_were_filled_in():
    start = base_row(id="rent-dup-2", name="Keep Me", code="EM-KEEP",
                     description="Original description.", stock_ksa="5")
    run_import(validate(sheet_csv([start])).json()["token"])
    # a sheet with only the name filled in
    thin = {"id": "rent-dup-2", "name": "New Name"}
    r = validate(sheet_csv([thin]), onDuplicate="update").json()
    assert r["summary"]["update"] == 1
    run_import(r["token"])
    item = rentals()["rent-dup-2"]
    assert item["name"] == "New Name"
    assert item["code"] == "EM-KEEP", "a blank cell must not erase a value"
    assert item["description"] == "Original description."
    assert item["stockByMarket"]["ksa"] == 5


def test_a_field_is_only_emptied_when_the_sheet_asks_for_it():
    run_import(validate(sheet_csv([base_row(id="rent-clear-1", code="EM-GONE",
                                            description="Bye.")])).json()["token"])
    r = validate(sheet_csv([{"id": "rent-clear-1", "code": ri.CLEAR_TOKEN}]),
                 onDuplicate="update").json()
    run_import(r["token"])
    item = rentals()["rent-clear-1"]
    assert item["code"] == "" and item["description"] == "Bye."


def test_duplicate_rows_inside_one_sheet_are_caught_before_anything_is_written():
    rows = [base_row(id="rent-same", name="First"), base_row(id="rent-same", name="Second")]
    r = validate(sheet_csv(rows)).json()
    assert r["summary"]["create"] == 1 and r["summary"]["errors"] == 1
    assert "row" in r["rows"][1]["errors"][0]["message"]


def test_a_code_already_in_use_is_a_warning_not_a_block():
    run_import(validate(sheet_csv([base_row(id="rent-code-a",
                                            code="EM-SHARED")])).json()["token"])
    r = validate(sheet_csv([base_row(id="rent-code-b", code="EM-SHARED")])).json()
    assert r["rows"][0]["action"] == "create"
    assert any(w["field"] == "code" for w in r["rows"][0]["warnings"])


# ---------------- images on update ----------------

def test_updating_keeps_the_existing_pictures_and_adds_the_new_one_by_default():
    z1 = images_zip({"one.png": png_bytes("red")})
    run_import(validate(sheet_csv([base_row(id="rent-img-merge", image_1="one.png")]),
                        zip_bytes=z1).json()["token"])
    before = rentals()["rent-img-merge"]["images"]
    assert len(before) == 1
    z2 = images_zip({"two.png": png_bytes("green")})
    r = validate(sheet_csv([{"id": "rent-img-merge", "image_1": "two.png"}]),
                 zip_bytes=z2, onDuplicate="update").json()
    run_import(r["token"])
    after = rentals()["rent-img-merge"]["images"]
    assert len(after) == 2 and after[0] == before[0], "the card image stays put"


def test_replace_images_swaps_the_gallery_when_that_is_asked_for():
    z1 = images_zip({"old.png": png_bytes("red")})
    run_import(validate(sheet_csv([base_row(id="rent-img-replace", image_1="old.png")]),
                        zip_bytes=z1).json()["token"])
    old = rentals()["rent-img-replace"]["images"]
    z2 = images_zip({"new.png": png_bytes("blue")})
    r = validate(sheet_csv([{"id": "rent-img-replace", "image_1": "new.png"}]),
                 zip_bytes=z2, onDuplicate="update", imageMode="replace").json()
    run_import(r["token"])
    after = rentals()["rent-img-replace"]["images"]
    assert len(after) == 1 and after[0] != old[0]
    # the picture that was dropped is still in the library — nothing is deleted
    assert old[0][len("/media/"):] in {m["file"] for m in media.library_list()}


# ---------------- categories ----------------

def test_a_category_that_exists_is_mapped_and_an_unknown_one_stops_the_row():
    ok = validate(sheet_csv([base_row(id="rent-cat-ok")])).json()
    assert ok["rows"][0]["action"] == "create"
    bad = validate(sheet_csv([base_row(id="rent-cat-bad",
                                       category="Banquet FurnitureX")])).json()
    assert bad["rows"][0]["action"] == "error"
    assert 'does not exist' in bad["rows"][0]["errors"][0]["message"]


def test_a_new_category_is_only_created_when_the_admin_asks_for_it():
    r = validate(sheet_csv([base_row(id="rent-cat-new", category="Staging & Rigging")]),
                 createCategories="yes").json()
    assert r["rows"][0]["action"] == "create"
    assert any(w["field"] == "category" for w in r["rows"][0]["warnings"])
    run_import(r["token"])
    assert rentals()["rent-cat-new"]["category"] == "Staging & Rigging"
    # ...and now it counts as an existing category for the next import
    nxt = validate(sheet_csv([base_row(id="rent-cat-new2",
                                       category="Staging & Rigging")])).json()
    assert nxt["rows"][0]["action"] == "create"


# ---------------- field validation ----------------

@pytest.mark.parametrize("field,value,word", [
    ("stock_ksa", "many", "whole number"),
    ("stock_ksa", "-4", "between 0 and 100000"),
    ("stock_uae", "999999999", "between 0 and 100000"),
    ("featured", "maybe", "yes or no"),
])
def test_a_bad_value_names_its_own_column(field, value, word):
    r = validate(sheet_csv([base_row(id="rent-bad-value", **{field: value})])).json()
    row = r["rows"][0]
    assert row["action"] == "error"
    assert row["errors"][0]["field"] == field
    assert word in row["errors"][0]["message"]


def test_a_missing_required_field_is_reported_rather_than_guessed():
    r = validate(sheet_csv([{"id": "rent-noname", "category": a_category()}])).json()
    assert r["rows"][0]["action"] == "error"
    assert {e["field"] for e in r["rows"][0]["errors"]} == {"name"}


def test_html_in_a_cell_never_reaches_the_stored_item():
    """A spreadsheet cell is text. The public pages escape what they render, so
    a stored tag was never executable — but it would have shown as literal
    markup on the rental card, and a supplier's sheet is the least trustworthy
    input the panel takes."""
    row = base_row(id="rent-html", name="<script>alert(1)</script>Chair",
                   description="<img src=x onerror=alert(1)>Sturdy.")
    r = validate(sheet_csv([row])).json()
    assert any(w["message"] == "formatting or HTML removed" for w in r["rows"][0]["warnings"]), \
        "the preview says the cell was changed"
    run_import(r["token"])
    item = rentals()["rent-html"]
    assert "<script>" not in item["name"] and "<" not in item["description"]
    assert item["description"] == "Sturdy."
    public = client.get("/api/rentals/products").text
    assert "<script>" not in public and "onerror=" not in public
    assert item == content._clean_rental(item), "still exactly what the form would store"


def test_a_description_that_merely_contains_an_angle_bracket_keeps_its_wording():
    row = base_row(id="rent-angle", name='55" LED display',
                   description="Fits spaces < 3m wide & over 1m deep.")
    run_import(validate(sheet_csv([row])).json()["token"])
    item = rentals()["rent-angle"]
    assert item["name"] == '55" LED display'
    assert item["description"] == "Fits spaces < 3m wide & over 1m deep."


def test_an_over_long_value_is_trimmed_and_the_preview_says_so():
    r = validate(sheet_csv([base_row(id="rent-long", name="N" * 400)])).json()
    row = r["rows"][0]
    assert row["action"] == "create"
    assert any(w["field"] == "name" for w in row["warnings"]), "normalisation is shown"
    run_import(r["token"])
    assert len(rentals()["rent-long"]["name"]) == 160


def test_an_unknown_column_is_ignored_with_a_warning():
    sheet = sheet_csv([{"id": "rent-extra", "name": "Extra", "category": a_category(),
                        "colour": "blue"}],
                      columns=["id", "name", "category", "colour"])
    r = validate(sheet).json()
    assert r["rows"][0]["action"] == "create"
    assert any("colour" in w["field"] for w in r["rows"][0]["warnings"])


# ---------------- malformed files ----------------

def test_a_malformed_workbook_is_refused_with_a_readable_message():
    res = validate(b"PK\x03\x04 this is not really a workbook", name="broken.xlsx")
    assert res.status_code == 400
    assert "workbook" in res.json()["detail"].lower()


def test_a_file_with_no_header_row_is_refused():
    assert validate(b"", name="empty.csv").status_code == 400
    assert validate(b"\n\n\n", name="blank.csv").status_code == 400


def test_an_unsupported_file_type_is_refused():
    res = validate(b"%PDF-1.4 ...", name="catalogue.pdf")
    assert res.status_code == 400 and ".xlsx" in res.json()["detail"]


def test_a_sheet_longer_than_the_ceiling_is_refused():
    rows = [base_row(id=f"rent-many-{i}") for i in range(ri.MAX_ROWS + 5)]
    res = validate(sheet_csv(rows))
    assert res.status_code == 400 and "rows" in res.json()["detail"]


def test_an_oversized_spreadsheet_is_refused_before_it_is_parsed():
    with pytest.raises(ri.ImportError_):
        ri.parse_sheet(b"x" * (ri.MAX_SHEET_BYTES + 1), "big.csv")


# ---------------- ZIP safety ----------------

def test_a_zip_entry_can_only_ever_name_a_file_inside_the_archive():
    """Traversal is not "detected", it is impossible: an entry is addressed by
    its own name with every directory part removed, and nothing is written to
    disk at all."""
    z = images_zip({"../../../etc/passwd.png": png_bytes("red"),
                    "/absolute/root.png": png_bytes("green"),
                    "..\\..\\windows\\win.png": png_bytes("blue")})
    zi = ri.ZipImages(z)
    assert zi.names() == {"passwd.png", "root.png", "win.png"}
    assert zi.read("passwd.png").startswith(b"\x89PNG")
    with pytest.raises(ri.ImportError_):
        zi.read("../../../etc/passwd")
    zi.close()


def test_an_executable_inside_the_zip_is_never_offered_to_a_row():
    z = images_zip({"ok.png": png_bytes(), "payload.sh": b"#!/bin/sh\nrm -rf /",
                    "macro.exe": b"MZ\x90\x00", "notes.txt": b"hello"})
    zi = ri.ZipImages(z)
    assert zi.names() == {"ok.png"}
    zi.close()
    r = validate(sheet_csv([base_row(id="rent-exe", image_1="payload.sh")]),
                 zip_bytes=z).json()
    assert r["rows"][0]["action"] == "error"


def test_a_zip_bomb_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("huge.png", b"\0" * (40 * 1024 * 1024))
    with pytest.raises(ri.ImportError_):
        ri.ZipImages(buf.getvalue())


def test_something_that_is_not_a_zip_is_refused():
    res = validate(sheet_csv([base_row()]), zip_bytes=b"definitely not a zip")
    assert res.status_code == 400 and "ZIP" in res.json()["detail"]


# ---------------- SSRF ----------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x.png", "https://localhost/x.png",
    "http://169.254.169.254/latest/meta-data/x.png",
    "http://10.0.0.5/x.png", "https://192.168.1.10/x.png", "http://[::1]/x.png",
])
def test_an_image_url_may_not_reach_a_private_address(url):
    with pytest.raises(ri.ImportError_):
        ri.fetch_image_url(url)


@pytest.mark.parametrize("url", ["ftp://example.com/a.png", "file:///etc/passwd",
                                 "gopher://example.com/a", "not a url at all"])
def test_only_web_addresses_are_accepted(url):
    with pytest.raises(ri.ImportError_):
        ri.fetch_image_url(url)


def test_a_redirect_is_refused_rather_than_followed(monkeypatch):
    """A permitted host that redirects is the usual way into a private
    network, so the importer stops at the first hop."""
    class FakeResponse:
        status_code = 302
        headers = {"location": "http://169.254.169.254/"}

        def iter_bytes(self):
            return iter(())

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeClient:
        def __init__(self, **kw):
            assert kw.get("follow_redirects") is False, "redirects must stay off"
            assert kw.get("trust_env") is False, "no proxy inheritance"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(ri, "_public_ip", lambda host: None)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(ri.ImportError_) as exc:
        ri.fetch_image_url("https://cdn.example.com/a.png")
    assert "redirect" in str(exc.value)


# ---------------- formula injection ----------------

def test_a_downloaded_report_cannot_carry_a_formula_into_excel():
    assert ri.csv_safe("=cmd|'/c calc'!A1").startswith("'=")
    assert ri.csv_safe("+1+1").startswith("'+")
    assert ri.csv_safe("@SUM(A1)").startswith("'@")
    assert ri.csv_safe("-2+3") .startswith("'-")
    assert ri.csv_safe("Black Chair") == "Black Chair"
    report = ri.error_report_csv([{"row": 3, "id": "=HYPERLINK(1)", "name": "x",
                                   "field": "id", "message": "bad"}])
    assert b",'=HYPERLINK(1)," in report


def test_the_template_example_row_is_not_executable():
    body = client.get("/api/admin/rentals/import/template", params={"format": "csv"}).content
    for line in body.decode("utf-8-sig").splitlines():
        for cell in line.split(","):
            assert not cell.startswith("="), line


# ---------------- the error report ----------------

def test_the_error_report_names_the_row_the_item_the_field_and_the_reason():
    rows = [base_row(id="rent-report-ok"),
            base_row(id="rent-report-bad", name="Round Table",
                     category="Banquet FurnitureX")]
    token = validate(sheet_csv(rows)).json()["token"]
    run_import(token)
    res = client.get("/api/admin/rentals/import/errors", params={"token": token})
    assert res.status_code == 200
    body = res.content.decode("utf-8-sig")
    assert "row,id,name,field,problem" in body
    assert "rent-report-bad" in body and "Round Table" in body
    assert "category" in body and "Banquet FurnitureX" in body
    assert "attachment" in res.headers["content-disposition"]


# ---------------- history and audit ----------------

def test_an_import_is_recorded_in_the_history_and_in_the_audit_log():
    before = client.get("/api/admin/rentals/import/history").json()["imports"]
    token = validate(sheet_csv([base_row(id="rent-hist-1")]), name="my-items.csv").json()["token"]
    run_import(token)
    entries = client.get("/api/admin/rentals/import/history").json()["imports"]
    # newest first, and the listing is capped rather than unbounded
    assert entries and (not before or entries[0]["id"] > before[0]["id"])
    assert len(entries) <= 20
    latest = entries[0]
    assert latest["filename"] == "my-items.csv"
    assert latest["user_email"] == "owner@elitemarcom.com"
    assert latest["created"] == 1 and latest["total"] == 1 and latest["ts"] > 0
    actions = {a["action"] for a in aa.audit_list(40)}
    assert {"rental.import.validated", "rental.import.started"} <= actions


def test_an_old_import_can_still_hand_over_its_error_report():
    token = validate(sheet_csv([base_row(id="rent-hist-bad",
                                         category="No Such Cat")])).json()["token"]
    run_import(token)
    entry = client.get("/api/admin/rentals/import/history").json()["imports"][0]
    assert entry["failed"] == 1
    res = client.get("/api/admin/rentals/import/errors", params={"entry": entry["id"]})
    assert res.status_code == 200 and b"No Such Cat" in res.content


def test_a_staged_upload_does_not_outlive_its_welcome():
    token = validate(sheet_csv([base_row(id="rent-stale")])).json()["token"]
    job = ri.get_job(token, "owner@elitemarcom.com")
    assert job is not None
    job["created"] -= ri.STAGE_TTL_S + 5
    assert ri.get_job(token, "owner@elitemarcom.com") is None, "the staged copy is dropped"
    assert client.post("/api/admin/rentals/import/run", json={"token": token},
                       headers=csrf()).status_code == 404


def test_the_same_import_cannot_be_run_twice_by_a_double_click():
    token = validate(sheet_csv([base_row(id="rent-twice")])).json()["token"]
    run_import(token)
    created_once = rentals()["rent-twice"]
    again = client.post("/api/admin/rentals/import/run", json={"token": token},
                        headers=csrf())
    assert again.status_code == 200 and again.json()["started"] is False
    assert rentals()["rent-twice"] == created_once


# ---------------- permissions and CSRF ----------------

def test_every_import_endpoint_needs_the_rentals_permission():
    """Checked on the server, not merely hidden in the panel."""
    import server.admin_api as api_mod

    paths = [r.path for r in api_mod.router.routes
             if getattr(r, "path", "").startswith("/api/admin/rentals/import")]
    assert len(paths) >= 5
    src = open(api_mod.__file__).read()
    section = src[src.index("# ---------------- rental bulk import"):
                  src.index("# ---------------- site insights")]
    assert section.count('require_perm(request, "rentals.manage")') == len(paths)


def test_a_signed_out_visitor_cannot_import_anything():
    """Every import endpoint, with no session at all — including the two that
    only read, because a template lists the categories and the history lists
    who imported what."""
    assert client.post("/api/admin/logout", headers=csrf()).status_code == 200
    try:
        files = {"file": ("items.csv", sheet_csv([base_row(id="rent-nope")]), "text/csv")}
        assert client.post("/api/admin/rentals/import/validate", files=files,
                           data={"onDuplicate": "skip"}).status_code == 401
        assert client.get("/api/admin/rentals/import/template").status_code == 401
        assert client.get("/api/admin/rentals/import/history").status_code == 401
        assert client.get("/api/admin/rentals/import/status",
                          params={"token": "x"}).status_code == 401
        assert client.post("/api/admin/rentals/import/run",
                           json={"token": "x"}).status_code == 401
        assert client.get("/api/admin/rentals/import/errors",
                          params={"token": "x"}).status_code == 401
    finally:
        sign_in()


def test_an_import_without_the_csrf_header_is_refused():
    files = {"file": ("items.csv", sheet_csv([base_row(id="rent-csrf")]), "text/csv")}
    assert client.post("/api/admin/rentals/import/validate", files=files,
                       data={"onDuplicate": "skip"}).status_code == 403
    assert client.post("/api/admin/rentals/import/run",
                       json={"token": "whatever"}).status_code == 403


def test_one_admin_cannot_run_another_admin_s_staged_import():
    token = validate(sheet_csv([base_row(id="rent-mine")])).json()["token"]
    assert ri.get_job(token, "someone.else@example.com") is None


# ---------------- the single-item workflow is untouched ----------------

def test_the_single_item_form_still_works_exactly_as_before():
    item = {"id": "rent-manual-1", "code": "EM-M-1", "name": "Hand Made",
            "category": a_category(), "description": "Typed in by a person.",
            "images": ["/assets/services/led-display.webp"],
            "image": "/assets/services/led-display.webp",
            "specs": ["One", "Two"], "tags": ["manual"],
            "featured": True, "stockByMarket": {"ksa": 2, "uae": 1}}
    res = client.post("/api/admin/rentals/save", json={"product": item}, headers=csrf())
    assert res.status_code == 200
    saved = res.json()["product"]
    assert saved["name"] == "Hand Made" and saved["stockByMarket"] == {"ksa": 2, "uae": 1}
    assert client.get("/api/admin/rentals").json()["products"]
    # editing and deleting still behave
    item["name"] = "Hand Edited"
    assert client.post("/api/admin/rentals/save", json={"product": item},
                       headers=csrf()).status_code == 200
    assert rentals()["rent-manual-1"]["name"] == "Hand Edited"
    assert client.post("/api/admin/rentals/delete", json={"id": "rent-manual-1"},
                       headers=csrf()).status_code == 200
    assert "rent-manual-1" not in rentals()


def test_an_import_leaves_the_items_that_were_already_there_alone():
    keep = {"id": "rent-bystander", "code": "EM-B", "name": "Bystander",
            "category": a_category(), "images": [], "image": "",
            "description": "Do not touch me.", "specs": [], "tags": [],
            "featured": False, "stockByMarket": {"ksa": 9, "uae": 9}}
    client.post("/api/admin/rentals/save", json={"product": keep}, headers=csrf())
    before = rentals()["rent-bystander"]
    run_import(validate(sheet_csv([base_row(id="rent-neighbour")])).json()["token"])
    assert rentals()["rent-bystander"] == before


def test_imported_items_show_up_on_the_public_rental_feed():
    z = images_zip({"public.png": png_bytes("teal")})
    run_import(validate(sheet_csv([base_row(id="rent-public-1", name="Public Item",
                                            image_1="public.png")]),
                        zip_bytes=z).json()["token"])
    products = client.get("/api/rentals/products").json()["products"]
    mine = [p for p in products if p["id"] == "rent-public-1"]
    assert len(mine) == 1 and mine[0]["name"] == "Public Item"
    assert mine[0]["image"].startswith("/media/")


# ---------------- scale ----------------

def test_a_large_import_is_processed_in_batches_without_losing_a_row():
    rows = [base_row(id=f"rent-bulk-{i:04d}", name=f"Bulk Item {i}", stock_ksa=str(i % 50))
            for i in range(500)]
    r = validate(sheet_csv(rows)).json()
    assert r["summary"]["create"] == 500 and r["summary"]["errors"] == 0
    job = run_import(r["token"])
    assert job["counts"]["created"] == 500 and job["counts"]["failed"] == 0
    got = rentals()
    assert all(f"rent-bulk-{i:04d}" in got for i in range(500))
    assert got["rent-bulk-0499"]["stockByMarket"]["ksa"] == 499 % 50
