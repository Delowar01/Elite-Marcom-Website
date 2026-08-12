"""API, security and workflow tests for the Elite Marcom website backend."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from server import config, storage
from server.main import app

client = TestClient(app, base_url="http://127.0.0.1:8847")
ORIGIN = {"Origin": "http://127.0.0.1:8847"}


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Each test starts with a clean limiter; the limiter itself is covered below."""
    from server import security
    security.limiter._hits.clear()
    yield


def test_rate_limit_enforced():
    from server import security
    security.limiter._hits.clear()
    for _ in range(6):
        payload = contact_payload()
        client.post("/api/contact/enquiries", json=payload, headers=ORIGIN)
    res = client.post("/api/contact/enquiries", json=contact_payload(), headers=ORIGIN)
    assert res.status_code == 429
    assert "retry-after" in {k.lower() for k in res.headers.keys()}


def get_challenge(form: str) -> str:
    res = client.get(f"/api/security/challenge?form={form}")
    assert res.status_code == 200
    return res.json()["challenge"]


def base_fields(form: str) -> dict:
    return {
        "challenge": get_challenge(form),
        "consentVersion": config.CONSENT_VERSION,
        "website": "",
        "sourcePage": "/contact.html",
    }


# ---------------- basics ----------------

def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_security_config():
    data = client.get("/api/security/config").json()
    assert data["consentVersion"] == config.CONSENT_VERSION


def test_pages_load():
    for page in ("/", "/about.html", "/services.html", "/projects.html", "/giveaways.html",
                 "/rental.html", "/careers.html", "/contact.html", "/privacy.html"):
        res = client.get(page)
        assert res.status_code == 200, page
        assert res.headers["content-security-policy"]
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.text.count("<h1") == (1 if page != "/" else 1), page


def test_private_paths_blocked():
    for path in ("/.env", "/.env.example", "/server/main.py", "/runtime/data.db",
                 "/requirements.txt", "/tests/test_api.py", "/server/../server/config.py"):
        res = client.get(path)
        assert res.status_code in (404, 400), path


def test_unknown_challenge_form_rejected():
    assert client.get("/api/security/challenge?form=nope").status_code == 400


# ---------------- contact ----------------

def contact_payload(**overrides) -> dict:
    payload = {
        "enquiryType": "New project",
        "fullName": "Test Person",
        "company": "Test Co",
        "email": "test@example.com",
        "phone": "+966 59 000 0000",
        "market": "Saudi Arabia",
        "service": "Exhibition Stands",
        "projectDate": None,
        "projectCity": "Riyadh",
        "message": "We would like a 100 sqm stand for an upcoming exhibition.",
        "consent": True,
        **base_fields("contact"),
    }
    payload.update(overrides)
    return payload


def test_contact_success_returns_reference():
    res = client.post("/api/contact/enquiries", json=contact_payload(), headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("EM-")


def test_contact_honeypot_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(website="spam"), headers=ORIGIN)
    assert res.status_code == 400


def test_contact_bad_origin_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(),
                      headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_contact_challenge_single_use():
    payload = contact_payload()
    assert client.post("/api/contact/enquiries", json=payload, headers=ORIGIN).status_code == 200
    payload2 = contact_payload(challenge=payload["challenge"])
    assert client.post("/api/contact/enquiries", json=payload2, headers=ORIGIN).status_code == 400


def test_contact_extra_fields_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(hacker="yes"), headers=ORIGIN)
    assert res.status_code == 422


def test_contact_missing_consent_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(consent=False), headers=ORIGIN)
    assert res.status_code == 400


def test_contact_stale_consent_version_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(consentVersion="2000-01"), headers=ORIGIN)
    assert res.status_code == 400


def test_contact_short_message_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(message="hi"), headers=ORIGIN)
    assert res.status_code == 400


def test_contact_bad_phone_rejected():
    res = client.post("/api/contact/enquiries", json=contact_payload(phone="abc"), headers=ORIGIN)
    assert res.status_code == 400


# ---------------- rentals ----------------

def rental_payload(**overrides) -> dict:
    payload = {
        "fullName": "Test Person",
        "company": "Test Co",
        "email": "test@example.com",
        "phone": "+971 50 000 0000",
        "startDate": "2026-10-01",
        "endDate": "2026-10-03",
        "eventCity": "Riyadh",
        "venue": "REC",
        "notes": "",
        "consent": True,
        "market": "ksa",
        "items": [{"productId": "rent-display-75", "quantity": 2}],
        **base_fields("rental_enquiry"),
    }
    payload.update(overrides)
    return payload


def test_rentals_products():
    data = client.get("/api/rentals/products").json()
    assert len(data["products"]) == 8
    names = {p["name"] for p in data["products"]}
    assert "75-inch 4K Professional Display" in names


def test_rental_enquiry_success():
    res = client.post("/api/rentals/enquiries", json=rental_payload(), headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("RN-")


def test_rental_unknown_product_rejected():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(items=[{"productId": "forged-item", "quantity": 1}]),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_rental_overstock_rejected():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(items=[{"productId": "rent-display-75", "quantity": 999}]),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_rental_cross_market_unavailable_rejected():
    # coffee station has 0 stock in UAE
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(market="uae",
                                          items=[{"productId": "rent-coffee-station", "quantity": 1}]),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_rental_bad_dates_rejected():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(startDate="2026-10-05", endDate="2026-10-01"),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_rental_duplicate_items_rejected():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(items=[{"productId": "rent-display-75", "quantity": 1},
                                                 {"productId": "rent-display-75", "quantity": 2}]),
                      headers=ORIGIN)
    assert res.status_code == 422


def test_rental_notification_end_before_start_rejected():
    payload = {
        "fullName": "Test Person", "company": "Test Co", "email": "t@example.com",
        "phone": "+966590000000", "requiredFrom": "2026-10-05", "requiredUntil": "2026-10-01",
        "message": "Please tell me when available.", "consent": True,
        "market": "uae", "productId": "rent-coffee-station",
        **base_fields("rental_notification"),
    }
    res = client.post("/api/rentals/notifications", json=payload, headers=ORIGIN)
    assert res.status_code == 400


def test_rental_notification_success():
    payload = {
        "fullName": "Test Person", "company": "Test Co", "email": "t@example.com",
        "phone": "+966590000000", "requiredFrom": None, "requiredUntil": None,
        "message": "Please tell me when available.", "consent": True,
        "market": "uae", "productId": "rent-coffee-station",
        **base_fields("rental_notification"),
    }
    res = client.post("/api/rentals/notifications", json=payload, headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("RA-")


# ---------------- giveaways ----------------

def test_giveaways_products_without_supplier_returns_503():
    if config.JASANI_API_TOKEN:
        pytest.skip("supplier token configured")
    res = client.get("/api/giveaways/products?country=ksa")
    assert res.status_code == 503  # frontend then uses the local preview catalog


def test_giveaways_invalid_market_rejected():
    assert client.get("/api/giveaways/products?country=zz").status_code == 422


def enquiry_form(**overrides) -> dict:
    data = {
        "fullName": "Test Person", "company": "Test Co", "email": "t@example.com",
        "phone": "+966590000000", "requiredBy": "", "deliveryCity": "Riyadh",
        "shippingAddress": "Office 12, King Fahd Road, Riyadh 12211",
        "notes": "", "consent": "yes", "market": "ksa",
        "items": json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 50}]),
        **base_fields("giveaway_enquiry"),
    }
    data.update(overrides)
    return data


def test_giveaway_enquiry_with_preview_catalog():
    res = client.post("/api/giveaways/enquiries", data=enquiry_form(), headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("GV-")


def test_giveaway_enquiry_with_logo_upload():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    res = client.post("/api/giveaways/enquiries", data=enquiry_form(),
                      files={"logo": ("logo.png", png, "image/png")}, headers=ORIGIN)
    assert res.status_code == 200, res.text


def test_giveaway_enquiry_bad_logo_rejected():
    res = client.post("/api/giveaways/enquiries", data=enquiry_form(),
                      files={"logo": ("logo.exe", b"MZ" + b"\x00" * 64, "application/octet-stream")},
                      headers=ORIGIN)
    assert res.status_code == 400


def test_giveaway_enquiry_missing_shipping_address_rejected():
    form = enquiry_form()
    del form["shippingAddress"]
    res = client.post("/api/giveaways/enquiries", data=form, headers=ORIGIN)
    assert res.status_code == 422


def test_giveaway_enquiry_unknown_product_rejected():
    res = client.post("/api/giveaways/enquiries",
                      data=enquiry_form(items=json.dumps([{"productId": "forged-product", "quantity": 5}])),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_giveaway_enquiry_cross_market_rejected():
    res = client.post("/api/giveaways/enquiries",
                      data=enquiry_form(market="uae", deliveryCity="Dubai",
                                        items=json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 5}])),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_giveaway_enquiry_unavailable_product_rejected():
    res = client.post("/api/giveaways/enquiries",
                      data=enquiry_form(items=json.dumps([{"productId": "prev-ramadan-box-ksa", "quantity": 1}])),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_giveaway_enquiry_overstock_quantity_rejected():
    res = client.post("/api/giveaways/enquiries",
                      data=enquiry_form(items=json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 99999}])),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_giveaway_notification_success():
    payload = {
        "fullName": "Test Person", "company": "Test Co", "email": "t@example.com",
        "phone": "+966590000000", "message": "", "consent": True,
        "market": "ksa", "productId": "prev-ramadan-box-ksa",
        **base_fields("giveaway_notification"),
    }
    res = client.post("/api/giveaways/notifications", json=payload, headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("GN-")


# ---------------- careers ----------------

def make_pdf(pages: int = 1, size: int = 2000) -> bytes:
    body = b"%PDF-1.4\n"
    for _ in range(pages):
        body += b"1 0 obj << /Type /Page >> endobj\n"
    body += b"x" * max(0, size - len(body) - 20)
    body += b"\n%%EOF"
    return body


def careers_form(form_key: str = "career", **overrides) -> dict:
    fields = {
        "fullName": "Test Person",
        "email": "cv@example.com",
        "phone": "+966590000000",
        "location": "Riyadh",
        "roleId": "2d-designer",
        "portfolioUrl": "https://example.com/portfolio",
        "introduction": "I design brand systems and want to build extraordinary things.",
        "consent": "yes",
        "challenge": get_challenge(form_key),
        "consentVersion": config.CONSENT_VERSION,
        "sourcePage": "/careers.html",
        "website": "",
    }
    fields.update(overrides)
    return fields


def test_careers_jobs():
    data = client.get("/api/careers/jobs").json()
    assert [j["id"] for j in data["jobs"]] == ["2d-designer", "3d-exhibition-designer", "sales-executive"]
    assert all("poster" in j for j in data["jobs"])


def test_careers_application_with_pdf():
    res = client.post("/api/careers/applications", data=careers_form(),
                      files={"cv": ("cv.pdf", io.BytesIO(make_pdf()), "application/pdf")},
                      headers=ORIGIN)
    assert res.status_code == 200, res.text
    assert res.json()["reference"].startswith("CA-")


def test_careers_application_without_cv():
    res = client.post("/api/careers/applications", data=careers_form(), headers=ORIGIN)
    assert res.status_code == 200, res.text


def test_careers_rejects_non_pdf():
    res = client.post("/api/careers/applications", data=careers_form(),
                      files={"cv": ("cv.pdf", io.BytesIO(b"MZ not a pdf" * 20), "application/pdf")},
                      headers=ORIGIN)
    assert res.status_code == 400


def test_careers_rejects_oversize_pdf():
    big = make_pdf(size=6 * 1024 * 1024)
    res = client.post("/api/careers/applications", data=careers_form(),
                      files={"cv": ("cv.pdf", io.BytesIO(big), "application/pdf")},
                      headers=ORIGIN)
    assert res.status_code in (400, 413)


def test_careers_rejects_encrypted_pdf():
    pdf = make_pdf().replace(b"endobj", b"/Encrypt endobj", 1)
    res = client.post("/api/careers/applications", data=careers_form(),
                      files={"cv": ("cv.pdf", io.BytesIO(pdf), "application/pdf")},
                      headers=ORIGIN)
    assert res.status_code == 400


def test_careers_rejects_http_portfolio():
    res = client.post("/api/careers/applications",
                      data=careers_form(portfolioUrl="http://example.com"),
                      headers=ORIGIN)
    assert res.status_code == 400


def test_careers_rejects_unknown_role():
    res = client.post("/api/careers/applications",
                      data=careers_form(roleId="ceo"), headers=ORIGIN)
    assert res.status_code == 400


# ---------------- storage / encryption / retention ----------------

def test_encryption_roundtrip_and_ciphertext_opacity():
    secret = b'{"name": "Sensitive Person"}'
    blob = storage.encrypt(secret)
    assert secret not in blob
    assert storage.decrypt(blob) == secret


def test_retention_cleanup_removes_expired():
    ref = storage.save_record("contact", {"probe": True}, "iphash", retention_days=-1)
    removed = storage.cleanup_expired()
    assert removed >= 1
    conn = storage._connect()
    row = conn.execute("SELECT COUNT(*) FROM records WHERE reference=?", (ref,)).fetchone()
    assert row[0] == 0


# ---------------- supplier parsing ----------------

def test_jasani_parses_json_and_xml():
    from server import jasani

    json_raw = json.dumps({"products": [
        {"id": "p1", "code": "C1", "name": "Mug", "stock": "15", "image": "https://www.giftsksa.com/img/mug.jpg"},
        {"bad": "record"},
    ]}).encode()
    recs = jasani._parse_records(json_raw, "application/json")
    assert len(recs) == 2
    norm = [p for p in (jasani.normalize_product(r, "ksa") for r in recs) if p]
    assert len(norm) == 1
    assert norm[0]["stock"]["available"] == 15
    assert norm[0]["image"] == "https://www.giftsksa.com/img/mug.jpg"

    xml_raw = (b"<?xml version='1.0'?><products>"
               b"<product><id>x1</id><name>Pen</name><code>PX</code><net_stock>7</net_stock>"
               b"<image>http://www.giftsksa.com/insecure.jpg</image></product>"
               b"</products>")
    recs = jasani._parse_records(xml_raw, "application/xml")
    norm = [p for p in (jasani.normalize_product(r, "ksa") for r in recs) if p]
    assert len(norm) == 1
    assert norm[0]["stock"]["available"] == 7
    assert norm[0]["image"] == ""  # http image rejected


def test_jasani_normalizes_real_odoo_record():
    """Shape observed in the live KSA feed: boolean false for empty fields,
    float artifacts in carton weight, Odoo field names, one image per product."""
    from server import jasani

    rec = {
        "Id": 4821,
        "Default_Code": "LAM-PEN-01",
        "ItemName": "Lamborghini Metal Pen",
        "description_sale": "Premium <b>metal pen</b> with laser engraving.<br>Gift boxed.",
        "color": False,
        "barcode": False,
        "hs_code": False,
        "incoming_date": False,
        "brand": "",
        "categories": [],
        "carton_weight": 14.200000000000001,
        "carton_volume": 0.05400000001,
        "qty_available": "36",
        "website_sequence": 7,
        "brand_id": [3, "Giftology"],
        "public_categ_ids": [[9, "Writing Instruments"], [12, "Executive Gifts"]],
        "product_template_tags": [{"display_name": "New Arrivals"}],
        "product_template_attribute_value_ids": [{"display_name": "Size: M"}, {"display_name": "Color: Grey"}],
        "configurable": False,
        "parent_id": 4800,
        "color_options": [4822, 4823],
        "image": "https://www.jasani.ae/web/image/product.product/4821/image_1024?unique=abc123",
        "images": ["https://www.jasani.ae/web/image/product.image/91/image_1024",
                   "https://www.jasani.ae/web/image/product.product/4821/image_1024?unique=abc123"],
    }
    p = jasani.normalize_product(rec, "ksa")
    assert p is not None
    assert p["id"] == "4821"
    assert p["code"] == "LAM-PEN-01"
    assert p["brand"] == "Giftology"
    assert p["categories"] == ["Writing Instruments", "Executive Gifts"]
    assert p["tags"] == ["New Arrivals"] and p["isNew"] is True
    assert p["options"] == ["Size: M", "Color: Grey"]
    assert p["cartonVolume"] == "0.054"
    assert p["sequence"] == 7
    assert p["templateId"] is None  # parent_id only groups when configurable
    assert p["parentId"] == "4800"  # retained as the printing-manual candidate
    assert "blocked" not in p["stock"]
    assert p["_colorOptionIds"] == ["4822", "4823"]
    assert p["color"] == ""          # Odoo false must not surface as "False"
    assert p["barcode"] == ""
    assert p["hsCode"] == ""
    assert p["stock"]["incomingDate"] is None
    assert p["cartonWeight"] == "14.2"
    assert p["stock"]["available"] == 36
    assert "metal pen" in p["description"] and "<b>" not in p["description"]
    # primary image first, additional images after, duplicates removed
    assert p["images"] == ["https://www.jasani.ae/web/image/product.product/4821/image_1024?unique=abc123",
                           "https://www.jasani.ae/web/image/product.image/91/image_1024"]


def test_jasani_flattens_nested_images_array():
    """Live feed shape: images is a nested 2-D array of {id, image_url} dicts."""
    from server import jasani

    rec = {
        "id": 4502, "code": "6311", "name": "XDDESIGN Komo Travel Wallet",
        "configurable": True,
        "parent_id": [4400, "XDDESIGN Komo Travel Wallet"],
        "image_url": "https://www.jasani.ae/web/image/product.product/4502/image_1024",
        "images": [[
            {"id": 1954, "image_url": "https://www.jasani.ae/web/image/product.image/1954/image_1024"},
            {"id": 1955, "image_url": "https://www.jasani.ae/web/image/product.image/1955/image_1024"},
            {"id": 1956, "image_url": "https://www.jasani.ae/web/image/product.product/4502/image_1024"},
        ]],
    }
    p = jasani.normalize_product(rec, "uae")
    assert p is not None
    assert p["templateId"] == "4400"
    assert p["images"] == [
        "https://www.jasani.ae/web/image/product.product/4502/image_1024",
        "https://www.jasani.ae/web/image/product.image/1954/image_1024",
        "https://www.jasani.ae/web/image/product.image/1955/image_1024",
    ]
    assert p["image"] == "https://www.jasani.ae/web/image/product.product/4502/image_1024"


def test_jasani_splits_video_entries_from_images():
    """Image records carrying a video_url are YouTube slides, not gallery
    images — the thumbnail must not appear as a static image."""
    from server import jasani

    rec = {
        "id": 7001, "code": "ITWC 1279", "name": "TRIODE 4 in 1 Charging Station",
        "image_url": "https://www.jasani.ae/web/image/product.product/7001/image_1024",
        "images": [[
            {"id": 1, "image_url": "https://www.jasani.ae/web/image/product.image/1/image_1024", "video_url": False},
            {"id": 2, "image_url": "https://www.jasani.ae/web/image/product.image/2/image_1024",
             "video_url": "https://www.youtube.com/shorts/Ab3dE5fGh7I"},
        ]],
    }
    p = jasani.normalize_product(rec, "uae")
    assert p is not None
    assert p["videos"] == [{"youtubeId": "Ab3dE5fGh7I",
                            "thumbnail": "https://www.jasani.ae/web/image/product.image/2/image_1024"}]
    assert p["images"] == ["https://www.jasani.ae/web/image/product.product/7001/image_1024",
                           "https://www.jasani.ae/web/image/product.image/1/image_1024"]
    # watch/short/embed/youtu.be forms all resolve; foreign hosts never do
    assert jasani._youtube_id("https://youtu.be/Ab3dE5fGh7I") == "Ab3dE5fGh7I"
    assert jasani._youtube_id("https://www.youtube.com/watch?v=Ab3dE5fGh7I") == "Ab3dE5fGh7I"
    assert jasani._youtube_id("https://evil.example/watch?v=x") == ""


def test_jasani_resolves_color_options_as_template_ids():
    """color_options carries product TEMPLATE ids (parent_id), not variant ids."""
    from server import jasani

    red = jasani.normalize_product(
        {"id": 1, "code": "C1", "name": "Mug Red", "color": "Red",
         "parent_id": 10, "color_options": [20, 30],  # 30 is unknown → dropped
         "image": "https://www.giftsksa.com/img/1.jpg"}, "ksa")
    blue = jasani.normalize_product(
        {"id": 2, "code": "C2", "name": "Mug Blue", "color": "Blue",
         "parent_id": 20, "color_options": [10],
         "image": "https://www.giftsksa.com/img/2.jpg"}, "ksa")
    products = [red, blue]
    jasani._resolve_color_options(products)
    assert "_colorOptionIds" not in products[0]
    assert [o["id"] for o in products[0]["colorOptions"]] == ["2"]  # template 20 → variant 2
    assert products[0]["colorOptions"][0]["color"] == "Blue"
    assert [o["id"] for o in products[1]["colorOptions"]] == ["1"]


FAKE_MANUAL_PDF = (b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n" + b"x" * 1200 + b"\n%%EOF")


def _manual_catalog(monkeypatch):
    from server import jasani

    async def fake_catalog(market):
        return ([{"id": "24246", "code": "ITGL 1291", "name": "NAPIER MagCase",
                  "parentId": "29453", "templateId": None}], "cache")
    monkeypatch.setattr(jasani, "get_catalog", fake_catalog)
    return jasani


def test_manual_pdf_validation():
    from server import jasani

    assert jasani._valid_manual_pdf(FAKE_MANUAL_PDF) is True
    assert jasani._valid_manual_pdf(b"<html>error page</html>") is False
    assert jasani._valid_manual_pdf(b"%PDF-1.4 tiny") is False  # too small / no page


def test_manual_proxy_serves_validated_pdf(tmp_path, monkeypatch):
    jasani = _manual_catalog(monkeypatch)
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)

    async def fake_fetch(market, template_id):
        assert template_id == "29453"
        return FAKE_MANUAL_PDF
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", fake_fetch)

    res = client.get("/api/giveaways/manual/status?country=ksa&product_id=24246")
    assert res.json() == {"available": True}
    res = client.get("/api/giveaways/manual?country=ksa&product_id=24246")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert 'filename="ITGL-1291-printing-manual.pdf"' in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF-")

    # supplier outage after validation → last-known-good copy still served
    async def broken_fetch(market, template_id):
        raise jasani.SupplierUnavailable("down")
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", broken_fetch)
    (tmp_path / "manuals" / "ksa-29453.json").write_text(
        json.dumps({"checkedAt": 0, "valid": True, "size": len(FAKE_MANUAL_PDF)}))
    res = client.get("/api/giveaways/manual?country=ksa&product_id=24246")
    assert res.status_code == 200 and res.content.startswith(b"%PDF-")


def test_manual_proxy_rejects_non_pdf_candidate(tmp_path, monkeypatch):
    jasani = _manual_catalog(monkeypatch)
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    calls = {"n": 0}

    async def fake_fetch(market, template_id):
        calls["n"] += 1
        return b"<html>not a manual</html>"
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", fake_fetch)

    assert client.get("/api/giveaways/manual/status?country=ksa&product_id=24246").json() == {"available": False}
    assert client.get("/api/giveaways/manual?country=ksa&product_id=24246").status_code == 404
    assert calls["n"] == 1  # the failed verdict is cached — no refetch


def _fake_area_image() -> bytes:
    import io as _io

    from PIL import Image as _Image

    im = _Image.new("RGB", (400, 300), (240, 240, 236))
    buf = _io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_generated_manual_is_valid_pdf():
    from server import jasani, manuals

    product = {"id": "24246", "code": "ITGL 1291", "name": "NAPIER MagCase Phone Cardholder",
               "color": "Grey"}
    areas = [{"name": "FRONT TOP", "methods": ["Laser Engraving", "Digital (UV) Print"],
              "areaWidthMm": "40", "areaHeightMm": "10",
              "image": {"data": _fake_area_image(), "width": 400, "height": 300},
              "rect": {"left": 120, "top": 90, "width": 160, "height": 60},
              "colorChoices": "", "leadTime": ""}]
    pdf = manuals.build_manual(product, areas, "ksa", None)
    assert jasani._valid_manual_pdf(pdf)
    assert b"Elite Marcom" in pdf or pdf.startswith(b"%PDF-")


def test_manual_endpoint_prefers_generated_manual(tmp_path, monkeypatch):
    jasani = _manual_catalog(monkeypatch)
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)

    async def fake_areas(market, product_id):
        assert product_id == "24246"
        return [{"name": "FRONT TOP", "methods": ["Laser Engraving"],
                 "areaWidthMm": "40", "areaHeightMm": "10",
                 "image": {"data": _fake_area_image(), "width": 400, "height": 300},
                 "rect": {"left": 10, "top": 10, "width": 100, "height": 50},
                 "colorChoices": "", "leadTime": ""}]
    monkeypatch.setattr(jasani, "get_branding_areas", fake_areas)

    async def no_image(url):
        return None
    monkeypatch.setattr(jasani, "_fetch_image_bytes", no_image)

    async def never_called(market, template_id):
        raise AssertionError("supplier proxy should not be needed")
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", never_called)

    res = client.get("/api/giveaways/manual?country=ksa&product_id=24246")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-")
    # second call comes from the generated-manual cache
    assert client.get("/api/giveaways/manual?country=ksa&product_id=24246").status_code == 200


def test_enquiry_accepts_branding_preference():
    items = json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 10,
                         "branding": {"area": "Front Top", "method": "Silk Screen Printing",
                                      "note": "Centre the logo"}}])
    res = client.post("/api/giveaways/enquiries", data=enquiry_form(items=items), headers=ORIGIN)
    assert res.status_code == 200, res.text


def test_enquiry_rejects_unknown_branding_fields():
    items = json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 10,
                         "branding": {"area": "Front", "price": "1"}}])
    res = client.post("/api/giveaways/enquiries", data=enquiry_form(items=items), headers=ORIGIN)
    assert res.status_code == 400


def test_manual_proxy_unknown_product_404(tmp_path, monkeypatch):
    jasani = _manual_catalog(monkeypatch)
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    assert client.get("/api/giveaways/manual?country=ksa&product_id=nope").status_code == 404


def test_jasani_primary_budget_capped_per_uae_day(tmp_path, monkeypatch):
    """At most SUPPLIER_DAILY_BUDGET primary calls per UAE day; a 403 parks
    the budget until the day resets."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    assert all(jasani._budget_ok() for _ in range(5))
    assert jasani._budget_ok() is False
    jasani._budget_exhaust()
    assert jasani._budget_ok() is False


def test_jasani_stock_merge_matches_on_any_identifier():
    from server import jasani

    products = [jasani.normalize_product(
        {"id": "9", "default_code": "SKU-9", "name": "Notebook",
         "image": "https://www.giftsksa.com/img/n.jpg"}, "ksa")]
    jasani._merge_stock(products, [
        {"Default_Code": "SKU-9", "net_available_qty": "120", "total_qty": "200",
         "blocked_qty": "80", "incoming_qty": "40", "incoming_date": False},
    ])
    assert products[0]["stock"]["available"] == 120  # net_available_qty, never total_qty
    assert "blocked" not in products[0]["stock"]     # blocked_qty stays internal
    assert products[0]["stock"]["incoming"] == 40
    assert products[0]["stock"]["incomingDate"] is None


def test_jasani_cache_roundtrips_non_ascii_names(tmp_path, monkeypatch):
    """Windows' locale codec can't encode e.g. the 'ﬃ' ligature seen in the
    live feed — the cache must be UTF-8 and never fail the request."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    p = jasani.normalize_product(
        {"id": "77", "code": "OF-1", "name": "Oﬃce Desk Set — Arabic هدية",
         "image": "https://www.giftsksa.com/img/o.jpg"}, "ksa")
    jasani._write_cache("ksa", [p], fetched_at=1000, stock_at=1000)
    cached = jasani._read_cache("ksa")
    assert cached and cached["products"][0]["name"] == "Oﬃce Desk Set — Arabic هدية"


def test_jasani_rejects_foreign_image_hosts():
    from server import jasani

    assert jasani._safe_image("https://evil.example/x.jpg", "www.jasani.ae") == ""
    assert jasani._safe_image("https://www.jasani.ae:8443/x.jpg", "www.jasani.ae") == ""
    assert jasani._safe_image("https://user:pw@www.jasani.ae/x.jpg", "www.jasani.ae") == ""
    assert jasani._safe_image("https://www.jasani.ae/x.jpg", "www.jasani.ae") != ""


def test_token_never_in_public_payloads(tmp_path):
    """The supplier token must not appear in anything served to the browser."""
    for path in ("/", "/giveaways.html", "/js/giveaways.js", "/api/security/config"):
        res = client.get(path)
        assert "JASANI" not in res.text or path == "/js/giveaways.js" and "JASANI" not in res.text
        assert "token" not in res.headers.get("set-cookie", "")
