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


def test_rental_enquiry_with_days():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(items=[{"productId": "rent-display-75", "quantity": 2, "days": 5}]),
                      headers=ORIGIN)
    assert res.status_code == 200, res.text


def test_rental_enquiry_rejects_invalid_days():
    res = client.post("/api/rentals/enquiries",
                      json=rental_payload(items=[{"productId": "rent-display-75", "quantity": 1, "days": 9999}]),
                      headers=ORIGIN)
    assert res.status_code == 422


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


def test_manual_endpoints_are_never_cached_downstream(tmp_path, monkeypatch):
    """A regenerated manual must reach the customer immediately.

    The server already caches generated manuals for 24 hours, so browser and
    CDN caching adds no supplier protection — and it cost real correctness: a
    public, max-age=3600 response kept handing back the old GEN1 PDF for an
    hour after the corrected GEN2 existed. Availability is the same story: a
    cached "no" hides a download button that now works."""
    jasani = _manual_catalog(monkeypatch)
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)

    async def fake_fetch(market, template_id):
        return FAKE_MANUAL_PDF
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", fake_fetch)

    status = client.get("/api/giveaways/manual/status?country=ksa&product_id=24246")
    assert status.status_code == 200 and status.json() == {"available": True}
    assert status.headers["cache-control"] == "no-store"

    pdf = client.get("/api/giveaways/manual?country=ksa&product_id=24246")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert pdf.headers["cache-control"] == "no-store"
    # nothing else may reintroduce a shared cache lifetime
    for header in ("expires", "etag", "last-modified"):
        assert header not in {k.lower() for k in pdf.headers}, header

    # the unavailable answer is equally uncacheable
    async def broken_fetch(market, template_id):
        raise jasani.SupplierUnavailable("down")
    monkeypatch.setattr(jasani, "_fetch_manual_bytes", broken_fetch)
    for name in ("ksa-29453.json", "ksa-29453.pdf"):
        (tmp_path / "manuals" / name).unlink(missing_ok=True)
    unavailable = client.get("/api/giveaways/manual/status?country=ksa&product_id=24246")
    assert unavailable.json() == {"available": False}
    assert unavailable.headers["cache-control"] == "no-store"


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


# ---------------- product videos from the supplier's public page ----------------
# Confirmed live example: ITGL 1291 NAPIER — MagCase Phone Cardholder — Grey is
# id 24246 / parent 29453 with videos: [] from the Product API, while
# https://www.jasani.ae/shop/itgl-1291-…-29453 embeds youtube.com/embed/lFhAiGLjoMo.

# Two shapes of the same gallery. In PAIRED the shop puts the video's own
# product.image record in the same carousel cell as the embed; in UNPAIRED that
# record is never printed, and the poster is whichever of our records the page
# does not show as a photograph. Both are answered from supplier data.
REAL_PAGE = """<!doctype html><html><body><div id="product_detail">
  <img src="https://www.jasani.ae/web/image/product.product/24246/image_1024">
  <div class="carousel-item"><img src="/web/image/product.image/8801/image_1024"></div>
  <div class="carousel-item"><img src="/web/image/product.image/8802/image_1024"></div>
  <div class="carousel-item o_product_video">
    <div class="ratio ratio-16x9">
      <iframe src="https://www.youtube.com/embed/lFhAiGLjoMo?rel=0" allowfullscreen></iframe>
    </div>
    <img class="o_video_thumb" src="/web/image/product.image/8803/image_128">
  </div>
</div>
<div class="alternative_products">
  <a href="/shop/other-product-11111">Another item</a>
  <iframe src="https://www.youtube.com/embed/ZZZZZZZZZZZ"></iframe>
</div></body></html>"""

# same product, a shop that never prints the video record's id
UNPAIRED_PAGE = """<!doctype html><html><body><div id="product_detail">
  <img src="/web/image/product.image/8801/image_1024">
  <img src="/web/image/product.image/8802/image_1024">
  <div class="o_video_container">
    <iframe src="https://www.youtube.com/embed/lFhAiGLjoMo"></iframe>
  </div>
</div></body></html>"""

# the supplier-hosted poster is a completely different URL from the ytimg one —
# which is why matching on the URL could never have worked
GALLERY = ["https://www.jasani.ae/web/image/product.product/24246/image_1024",
           "https://www.jasani.ae/web/image/product.image/8801/image_1024",
           "https://www.jasani.ae/web/image/product.image/8802/image_1024",
           "https://www.jasani.ae/web/image/product.image/8803/image_1024"]
POSTER = "https://www.jasani.ae/web/image/product.image/8803/image_1024"


def _video_product(monkeypatch, tmp_path, **over):
    """A catalogue of one product, with the video cache pointed at tmp_path."""
    from server import jasani, supplier_video

    product = {"id": "24246", "code": "ITGL 1291",
               "name": "NAPIER - MagCase Phone Cardholder - Grey",
               "parentId": "29453", "templateId": None, "videos": [],
               "image": GALLERY[0], "images": list(GALLERY)}
    product.update(over)

    async def fake_catalog(market):
        return ([product], "cache")
    monkeypatch.setattr(jasani, "get_catalog", fake_catalog)
    monkeypatch.setattr(supplier_video, "_CACHE_DIR", tmp_path)
    return supplier_video, product


def test_the_confirmed_product_video_is_found_on_the_public_page(tmp_path, monkeypatch):
    sv, _p = _video_product(monkeypatch, tmp_path)
    asked = []

    async def fake_page(url):
        asked.append(url)
        return REAL_PAGE
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    res = client.get("/api/giveaways/video?country=uae&product_id=24246")
    assert res.status_code == 200
    assert res.json() == {"videos": [{
        "youtubeId": "lFhAiGLjoMo",
        "thumbnail": "https://i.ytimg.com/vi/lFhAiGLjoMo/hqdefault.jpg",
        # the gallery photograph that IS this video — named by supplier record
        # id, so the page can drop it instead of showing the frame twice
        "supplierImageId": "8803", "supplierPoster": POSTER}]}
    # the page is addressed by the template id, on the market's own host
    assert asked == ["https://www.jasani.ae/shop/"
                     "itgl-1291-napier-magcase-phone-cardholder-grey-29453"]
    assert res.headers["cache-control"] == "no-store"


def test_a_video_from_the_related_products_strip_is_not_this_product(tmp_path, monkeypatch):
    """Odoo repeats other items below the product. Their videos are theirs."""
    sv, _p = _video_product(monkeypatch, tmp_path)
    assert [v["youtubeId"] for v in sv.parse_videos(REAL_PAGE)] == ["lFhAiGLjoMo"]


def test_every_supported_youtube_form_is_read_and_nothing_else_is():
    from server import supplier_video as sv

    page = """
      <iframe src="https://www.youtube.com/embed/AAAAAAAAAAA"></iframe>
      <iframe src="https://www.youtube-nocookie.com/embed/BBBBBBBBBBB"></iframe>
      <a href="https://www.youtube.com/watch?v=CCCCCCCCCCC">watch</a>
      <a href="https://www.youtube.com/watch?app=desktop&amp;v=DDDDDDDDDDD">watch</a>
      <a href="https://youtu.be/EEEEEEEEEEE">short link</a>
      <a href="https://www.youtube.com/shorts/FFFFFFFFFFF">shorts</a>
      <a href="https://www.youtube.com/live/GGGGGGGGGGG">live</a>
      <a href="https://www.youtube.com/v/HHHHHHHHHHH">old embed</a>
    """
    got = [v["youtubeId"] for v in sv.parse_videos(page)]
    assert got == ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD"]  # capped at MAX_VIDEOS
    assert sv.MAX_VIDEOS == 4
    # and nothing that is not a YouTube video id
    assert sv.parse_videos('<iframe src="https://vimeo.com/embed/AAAAAAAAAAA"></iframe>') == []
    # a path that merely spells the host is a page on somebody else's server
    assert sv.parse_videos('<a href="https://evil.example/youtube.com/embed/AAAAAAAAAAA">x</a>') == []


def test_a_malformed_youtube_url_is_not_a_video():
    """Only an exact 11-character id counts — a truncated or padded one is a
    mis-parse, and a mis-parse is somebody else's video on our product page."""
    from server import supplier_video as sv

    assert sv.parse_videos('<iframe src="https://www.youtube.com/embed/short"></iframe>') == []
    assert sv.parse_videos('<iframe src="https://www.youtube.com/embed/AAAAAAAAAAAAAAA"></iframe>') == []
    assert sv.parse_videos('<a href="https://www.youtube.com/watch?list=PL123">x</a>') == []
    assert sv.parse_videos("") == []
    assert sv.parse_videos("<html>no video here at all</html>") == []


def test_a_declared_thumbnail_is_kept_over_the_generated_one():
    from server import supplier_video as sv

    page = ('<img src="https://i.ytimg.com/vi/lFhAiGLjoMo/maxresdefault.jpg">'
            '<iframe src="https://www.youtube.com/embed/lFhAiGLjoMo"></iframe>')
    assert sv.parse_videos(page) == [
        {"youtubeId": "lFhAiGLjoMo",
         "thumbnail": "https://i.ytimg.com/vi/lFhAiGLjoMo/maxresdefault.jpg",
         "supplierImageId": ""}]


def test_escaped_urls_inside_inline_json_are_still_found():
    from server import supplier_video as sv

    page = '<script>var d = {"video": "https:\\/\\/www.youtube.com\\/embed\\/lFhAiGLjoMo"};</script>'
    assert [v["youtubeId"] for v in sv.parse_videos(page)] == ["lFhAiGLjoMo"]


def test_a_product_without_a_parent_id_never_asks_the_supplier(tmp_path, monkeypatch):
    sv, _p = _video_product(monkeypatch, tmp_path, parentId=None)

    async def boom(url):
        raise AssertionError("no page request may be made without a template id")
    monkeypatch.setattr(sv, "fetch_page", boom)

    assert client.get("/api/giveaways/video?country=uae&product_id=24246").json() == {"videos": []}


def test_videos_from_the_product_api_are_served_without_any_page_request(tmp_path, monkeypatch):
    sv, _p = _video_product(monkeypatch, tmp_path,
                            videos=[{"youtubeId": "Ab3dE5fGh7I", "thumbnail": ""}])

    async def boom(url):
        raise AssertionError("the feed already carried the video")
    monkeypatch.setattr(sv, "fetch_page", boom)

    assert client.get("/api/giveaways/video?country=uae&product_id=24246").json() == {
        "videos": [{"youtubeId": "Ab3dE5fGh7I", "thumbnail": "",
                    "supplierImageId": "", "supplierPoster": ""}]}


def test_a_positive_result_is_cached_and_the_page_is_read_once(tmp_path, monkeypatch):
    sv, _p = _video_product(monkeypatch, tmp_path)
    calls = {"n": 0}

    async def fake_page(url):
        calls["n"] += 1
        return REAL_PAGE
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    for _ in range(3):
        res = client.get("/api/giveaways/video?country=uae&product_id=24246")
        assert [v["youtubeId"] for v in res.json()["videos"]] == ["lFhAiGLjoMo"]
    assert calls["n"] == 1
    assert (tmp_path / "uae-29453.json").exists()


def test_a_product_with_no_video_is_negative_cached(tmp_path, monkeypatch):
    """Without this, every visit to every video-less product is a request to
    the supplier — which is the crawl this must never become."""
    sv, _p = _video_product(monkeypatch, tmp_path)
    calls = {"n": 0}

    async def fake_page(url):
        calls["n"] += 1
        return "<html><div id='product_detail'>photos only</div></html>"
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    for _ in range(3):
        assert client.get("/api/giveaways/video?country=uae&product_id=24246").json() == {"videos": []}
    assert calls["n"] == 1
    assert sv.cache_status() == {"withVideo": 0, "withoutVideo": 1, "entries": 1}


def test_an_unreachable_page_is_retried_sooner_than_a_settled_verdict(tmp_path, monkeypatch):
    """A supplier outage is not evidence that a product has no video, so that
    verdict expires in hours while a real answer stands for weeks."""
    sv, _p = _video_product(monkeypatch, tmp_path)

    async def dead_page(url):
        return None  # 404 / timeout / non-HTML — all the same to the caller
    monkeypatch.setattr(sv, "fetch_page", dead_page)

    assert client.get("/api/giveaways/video?country=uae&product_id=24246").json() == {"videos": []}
    meta = json.loads((tmp_path / "uae-29453.json").read_text(encoding="utf-8"))
    assert meta["ok"] is False and meta["videos"] == []

    # a miss is held for VIDEO_MISS_CACHE_DAYS; an outage only for hours
    meta["checkedAt"] = int(meta["checkedAt"] - config.VIDEO_ERROR_CACHE_HOURS * 3600 - 60)
    (tmp_path / "uae-29453.json").write_text(json.dumps(meta), encoding="utf-8")
    assert sv._read_cache("uae", "29453") is None
    settled = dict(meta, ok=True)
    (tmp_path / "uae-29453.json").write_text(json.dumps(settled), encoding="utf-8")
    assert sv._read_cache("uae", "29453") == {"videos": [], "imageIds": []}


def test_the_search_fallback_only_accepts_the_matching_template_id(tmp_path, monkeypatch):
    """If the slug URL fails we search the public shop — and take the link that
    ends in this product's template id, never a neighbouring result."""
    sv, product = _video_product(monkeypatch, tmp_path)
    listing = ('<a href="/shop/some-other-item-11111">x</a>'
               '<a href="/shop/itgl-1291-napier-magcase-phone-cardholder-grey-29453">this one</a>')
    seen = []

    async def fake_page(url):
        seen.append(url)
        if "/shop?search=" in url:
            return listing
        if url.endswith("-29453") and len(seen) > 1:
            return REAL_PAGE
        return None  # the guessed slug URL did not resolve
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    res = client.get("/api/giveaways/video?country=uae&product_id=24246")
    assert [v["youtubeId"] for v in res.json()["videos"]] == ["lFhAiGLjoMo"]
    assert seen[1] == "https://www.jasani.ae/shop?search=ITGL%201291"
    assert sv.link_for_template(listing, "uae", "11111") == \
        "https://www.jasani.ae/shop/some-other-item-11111"
    assert sv.link_for_template(listing, "uae", "99999") == ""


def test_video_discovery_never_spends_a_supplier_api_call(tmp_path, monkeypatch):
    """The public page is not an API endpoint: no token, no primary call, and
    nothing charged to the five-a-day budget."""
    from server import jasani

    sv, _p = _video_product(monkeypatch, tmp_path)

    async def fake_page(url):
        assert "token" not in url.lower()
        return REAL_PAGE
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    def no_calls(*a, **k):
        raise AssertionError("the supplier API must not be touched for a video")
    monkeypatch.setattr(jasani, "_fetch", no_calls)
    monkeypatch.setattr(jasani, "_budget_ok", no_calls)

    assert client.get("/api/giveaways/video?country=uae&product_id=24246").json()["videos"]


def test_a_page_request_leaves_the_supplier_hosts_only(monkeypatch):
    """fetch_page is a supplier-host fetcher, not a general URL opener."""
    import anyio

    from server import supplier_video as sv

    monkeypatch.setattr(config, "VIDEO_MIN_INTERVAL_S", 0.0)

    attempts = []

    class Recording:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, headers=None):
            attempts.append(url)
            raise AssertionError("recorded")
    monkeypatch.setattr(sv.httpx, "AsyncClient", Recording)

    for bad in ("http://www.jasani.ae/shop/x-1", "https://evil.example/shop/x-1",
                "https://www.jasani.ae:8080/shop/x-1", ""):
        assert anyio.run(sv.fetch_page, bad) is None
    assert attempts == []  # not "it failed" — it was never dialled


def test_a_timed_out_page_is_not_an_error_the_customer_sees(monkeypatch):
    import anyio

    from server import supplier_video as sv

    monkeypatch.setattr(config, "VIDEO_MIN_INTERVAL_S", 0.0)

    class TimingOut:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, headers=None):
            raise sv.httpx.ReadTimeout("too slow")
    monkeypatch.setattr(sv.httpx, "AsyncClient", TimingOut)

    assert anyio.run(sv.fetch_page, "https://www.jasani.ae/shop/x-29453") is None


def test_the_catalogue_and_an_unknown_product_ask_the_supplier_nothing(tmp_path, monkeypatch):
    sv, _p = _video_product(monkeypatch, tmp_path)

    async def boom(url):
        raise AssertionError("an unknown product has no page to read")
    monkeypatch.setattr(sv, "fetch_page", boom)

    assert client.get("/api/giveaways/video?country=uae&product_id=999999").json() == {"videos": []}
    # the catalogue endpoint itself never reaches into video discovery
    assert client.get("/api/giveaways/products?country=uae").status_code == 200


# --- the video's poster is a gallery photograph too, and looks nothing like it ---
# Supplier poster:  https://www.jasani.ae/web/image/product.image/8803/image_1024
# YouTube thumbnail: https://i.ytimg.com/vi/lFhAiGLjoMo/hqdefault.jpg
# Two URLs, one frame. Matching on the URL can never connect them, which is why
# the same picture appeared twice — once playable, once not.

def test_the_page_pairs_the_poster_record_with_the_embed():
    """The carousel cell holds the video AND its image record. That pairing is
    the supplier's own; nothing here counts positions in the gallery."""
    from server import supplier_video as sv

    found = sv.parse_page(REAL_PAGE)
    assert found["videos"][0]["supplierImageId"] == "8803"
    assert found["imageIds"] == ["8801", "8802"]  # the poster is not an ordinary photo


def test_a_page_that_never_prints_the_poster_record_is_answered_by_subtraction():
    """One video, and exactly one of our image records the page does not show
    as a photograph — that record is the poster, because the page accounts for
    every other one."""
    from server import supplier_video as sv

    found = sv.parse_page(UNPAIRED_PAGE)
    assert found["videos"][0]["supplierImageId"] == ""      # the page paired nothing
    assert found["imageIds"] == ["8801", "8802"]
    out = sv.associate_posters({"images": GALLERY}, found["videos"], found["imageIds"])
    assert out[0]["supplierImageId"] == "8803"
    assert out[0]["supplierPoster"] == POSTER


def test_the_supplier_poster_reaches_the_page_for_both_confirmed_products(tmp_path, monkeypatch):
    """ITGL 1291 (29453) and ITGL 1290 (29452) — the two products checked live."""
    from server import jasani, supplier_video as sv

    items = {"24246": ("ITGL 1291", "29453"), "24245": ("ITGL 1290", "29452")}
    products = [{"id": pid, "code": code, "name": f"{code} NAPIER MagCase",
                 "parentId": tid, "templateId": None, "videos": [],
                 "image": GALLERY[0], "images": list(GALLERY)}
                for pid, (code, tid) in items.items()]

    async def fake_catalog(market):
        return (products, "cache")
    monkeypatch.setattr(jasani, "get_catalog", fake_catalog)
    monkeypatch.setattr(sv, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(sv, "fetch_page", lambda url: _page_for(url))

    async def _page_for(url):
        return REAL_PAGE if url.endswith("-29453") else UNPAIRED_PAGE

    for pid, (_code, tid) in items.items():
        res = client.get(f"/api/giveaways/video?country=uae&product_id={pid}")
        vids = res.json()["videos"]
        assert len(vids) == 1, pid
        assert vids[0]["youtubeId"] == "lFhAiGLjoMo"
        assert vids[0]["supplierPoster"] == POSTER, pid
        assert (tmp_path / f"uae-{tid}.json").exists()


def test_the_poster_identity_survives_in_the_cache(tmp_path, monkeypatch):
    """A second visit must not re-read the supplier page to know which gallery
    image the video already is."""
    sv, _p = _video_product(monkeypatch, tmp_path)
    calls = {"n": 0}

    async def fake_page(url):
        calls["n"] += 1
        return REAL_PAGE
    monkeypatch.setattr(sv, "fetch_page", fake_page)

    first = client.get("/api/giveaways/video?country=uae&product_id=24246").json()
    stored = json.loads((tmp_path / "uae-29453.json").read_text(encoding="utf-8"))
    assert stored["videos"][0]["supplierImageId"] == "8803"
    assert stored["imageIds"] == ["8801", "8802"]
    again = client.get("/api/giveaways/video?country=uae&product_id=24246").json()
    assert again == first and calls["n"] == 1


def test_an_ambiguous_page_leaves_every_photograph_in_place():
    """Two image records in the same cell as the embed, or two of ours missing
    from the page: either way the poster is unknown. Showing one picture twice
    is a blemish; deleting the wrong one loses a product photo."""
    from server import supplier_video as sv

    two_in_a_cell = ("""<div id="product_detail"><div class="carousel-item">"""
                     """<img src="/web/image/product.image/8803/image_128">"""
                     """<img src="/web/image/product.image/8804/image_128">"""
                     """<iframe src="https://www.youtube.com/embed/lFhAiGLjoMo"></iframe>"""
                     """</div></div>""")
    found = sv.parse_page(two_in_a_cell)
    assert found["videos"][0]["supplierImageId"] == ""
    out = sv.associate_posters({"images": GALLERY}, found["videos"], found["imageIds"])
    assert out[0]["supplierPoster"] == "" and out[0]["supplierImageId"] == ""

    # two of ours unaccounted for — subtraction has no single answer either
    thin = sv.parse_page("""<div id="product_detail">"""
                         """<img src="/web/image/product.image/8801/image_1024">"""
                         """<div><iframe src="https://www.youtube.com/embed/lFhAiGLjoMo"></iframe></div>"""
                         """</div>""")
    out = sv.associate_posters({"images": GALLERY}, thin["videos"], thin["imageIds"])
    assert out[0]["supplierPoster"] == ""


def test_a_poster_id_we_do_not_hold_removes_nothing():
    """An id from the page that is not in this product's gallery identifies no
    image to drop, so it must not travel to the browser as if it did."""
    from server import supplier_video as sv

    out = sv.associate_posters(
        {"images": GALLERY},
        [{"youtubeId": "lFhAiGLjoMo", "thumbnail": "", "supplierImageId": "999999"}],
        ["8801", "8802", "8803"])
    assert out[0]["supplierImageId"] == "" and out[0]["supplierPoster"] == ""


def test_two_videos_never_borrow_each_others_poster():
    from server import supplier_video as sv

    page = ("""<div id="product_detail">"""
            """<div class="cell"><iframe src="https://www.youtube.com/embed/AAAAAAAAAAA"></iframe>"""
            """<img src="/web/image/product.image/8803/image_128"></div>"""
            """<div class="cell"><iframe src="https://www.youtube.com/embed/BBBBBBBBBBB"></iframe>"""
            """<img src="/web/image/product.image/8804/image_128"></div>"""
            """<img src="/web/image/product.image/8801/image_1024"></div>""")
    found = sv.parse_page(page)
    assert [v["supplierImageId"] for v in found["videos"]] == ["8803", "8804"]
    assert found["imageIds"] == ["8801"]
    # with more than one video, subtraction is not attempted at all
    out = sv.associate_posters({"images": GALLERY}, [dict(v, supplierImageId="")
                                                     for v in found["videos"]], ["8801"])
    assert [v["supplierPoster"] for v in out] == ["", ""]


def test_image_ids_are_read_from_the_gallery_urls_we_already_hold():
    from server import supplier_video as sv

    assert sv.image_ids(GALLERY) == ["8801", "8802", "8803"]  # product.product is not one
    assert sv.image_ids(["https://evil.example/web/image/product.image/1/x"]) == ["1"]
    assert sv.image_ids([]) == [] and sv.image_ids(None) == []


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
    monkeypatch.setattr(jasani.config, "SUPPLIER_AUTO_BUDGET", 5)
    assert all(jasani._budget_ok("ksa") for _ in range(5))
    assert jasani._budget_ok("ksa") is False
    jasani._budget_exhaust("ksa")
    assert jasani._budget_ok("ksa") is False
    assert jasani._budget_ok("ksa", manual=True) is False   # a 403 stops everything
    assert jasani._budget_ok("uae") is True                 # the other account is untouched


def _png_b64(w=120, h=90, mode="RGB", fmt="PNG"):
    """A branding area view: opaque marks on a transparent ground, the way
    supplier artwork actually arrives."""
    import base64
    import io as _io

    from PIL import Image, ImageDraw

    transparent = mode in ("RGBA", "LA", "P")
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
    ImageDraw.Draw(im).rectangle([w * 0.2, h * 0.2, w * 0.8, h * 0.8], fill=(200, 120, 40, 255))
    buf = _io.BytesIO()
    if mode == "P":
        im.convert("P", palette=Image.ADAPTIVE, colors=32).save(buf, format="PNG", transparency=0)
    elif mode == "L":
        im.convert("L").save(buf, format="PNG")
    elif fmt == "JPEG" or mode == "RGB":
        im.convert("RGB").save(buf, format=fmt)
    else:
        im.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()


def _jpeg_b64(w=240, h=180):
    """A real JPEG, Base64'd the way a supplier would send one."""
    import base64
    import io as _io

    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), (248, 246, 242))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([w * 0.2, h * 0.2, w * 0.8, h * 0.8], radius=8, fill=(38, 46, 66))
    buf = _io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), buf.getvalue()


def test_branding_artwork_reads_the_python_bytes_repr_jasani_actually_sends():
    """The UAE Branding API returns web_image as a JSON string holding a Python
    bytes repr — b'/9j/…' with the marker and quotes as characters. b64decode
    skips non-alphabet characters rather than failing, so the payload came out
    shifted: JPEG's FF D8 FF arrived as 6F FF 63 FF and Pillow rejected an
    image that was fine on the wire. Confirmed against CTEN 2240 (UAE 24233).
    """
    import base64
    import io as _io

    from PIL import Image

    from server import jasani

    plain, jpeg_bytes = _jpeg_b64()
    assert plain.startswith("/9j/")

    # the failure this reproduces, exactly
    corrupt = base64.b64decode("b'" + plain + "'", validate=False)
    assert corrupt[:4].hex() == "6fff63ff"
    with pytest.raises(Exception):
        Image.open(_io.BytesIO(corrupt)).load()

    # unwrapping recovers the payload byte for byte
    assert base64.b64decode(jasani._unwrap_base64("b'" + plain + "'")) == jpeg_bytes

    for label, value in (("plain", plain),
                         ("bytes repr, single quotes", "b'" + plain + "'"),
                         ("bytes repr, double quotes", 'b"' + plain + '"'),
                         ("data uri", "data:image/jpeg;base64," + plain)):
        assert jasani._area_image_raw({"web_image": value}) == value, label
        data, w, h = jasani._decode_web_image(value)
        assert data, label
        assert (w, h) == (240, 180), label            # dimensions retained
        out = Image.open(_io.BytesIO(data))
        out.load()                                     # fully decodable
        assert out.mode == "RGB" and out.size == (240, 180), label


def test_branding_artwork_rejects_a_malformed_bytes_wrapper():
    """Only a genuine wrapper is removed — never stray quotes."""
    from server import jasani

    plain, _ = _jpeg_b64()
    # unmatched or partial wrappers are not Base64 and must not be guessed at
    for broken in ("b'" + plain,            # no closing quote
                   plain + "'",             # no marker
                   "b'" + plain + '"',      # mismatched quotes
                   "b'not base64 at all'",
                   "b''"):
        assert jasani._decode_web_image(broken) == (None, 0, 0), broken
    # a payload whose length cannot be valid Base64 is refused, not padded blindly
    assert jasani._unwrap_base64("b'" + plain[:-3] + "'") in ("", jasani._unwrap_base64("b'" + plain[:-3] + "'"))
    # and the wrapper is not stripped off something that merely ends in a quote
    assert jasani._unwrap_base64(plain + "'") == ""


def test_generated_manual_shows_the_area_image_for_real_supplier_payload():
    """End to end on the real shape: a b'…' web_image must reach the page as a
    drawn area view, not as the 'Area image unavailable' placeholder."""
    import re

    from server import jasani, manuals

    plain, _ = _jpeg_b64(600, 450)
    data, w, h = jasani._decode_web_image(jasani._area_image_raw({"web_image": "b'" + plain + "'"}))
    assert data and (w, h) == (600, 450)

    areas = [{"name": "Front centre", "methods": ["Screen print"],
              "areaWidthMm": 90, "areaHeightMm": 48,
              "image": {"data": data, "width": w, "height": h},
              "rect": {"left": 150, "top": 120, "width": 300, "height": 160},
              "colorChoices": "Up to 4", "leadTime": "5 days"}]
    pdf = manuals.build_manual({"id": "24233", "code": "CTEN 2240", "name": "Test product",
                                "brand": "Jasani"}, areas, "uae", None)
    assert pdf[:5] == b"%PDF-"
    embedded = {(int(a), int(b2)) for a, b2 in
                zip(re.findall(rb"/Width\s+(\d+)", pdf), re.findall(rb"/Height\s+(\d+)", pdf))}
    assert (600, 450) in embedded, "the area view is missing from the manual"
    assert b"Area image unavailable" not in pdf, \
        "an area that supplied valid web_image still rendered the placeholder"


def test_branding_cache_from_the_old_decoder_is_not_reused():
    """Fixing the decoder does not fix what the broken one already stored, so
    the cache carries the decoder version and a mismatch forces a refetch."""
    import json as _json

    from server import jasani

    assert jasani.BRANDING_DECODER_VERSION >= 2
    assert jasani.GEN_MANUAL_VERSION >= 2      # old PDFs have no area images

    stale = {"fetchedAt": 9999999999, "decoder": 1,
             "areas": [{"name": "Front", "methods": [], "rect": None}]}
    fresh = {**stale, "decoder": jasani.BRANDING_DECODER_VERSION}
    assert stale["decoder"] != jasani.BRANDING_DECODER_VERSION
    assert _json.loads(_json.dumps(fresh))["decoder"] == jasani.BRANDING_DECODER_VERSION


def test_branding_artwork_decodes_from_any_field_and_format():
    """A branding area whose artwork is not read renders as 'Area image
    unavailable' in the printing manual — a missing picture to the customer."""
    from server import jasani

    for key in ("web_image", "image_1920", "branding_image", "view_image"):
        raw = jasani._area_image_raw({"name": "Front", key: _png_b64()})
        assert raw, key
        data, w, h = jasani._decode_web_image(raw)
        assert data and (w, h) == (120, 90), key
        assert data[:8] == b"\x89PNG\r\n\x1a\n"      # normalised for reportlab

    # Formats and colour modes the supplier can send. Every one must come out
    # as flat RGB: alpha survives into the PDF as a soft mask, and a reader
    # that ignores it draws the area view as nothing at all — which is what a
    # customer sees as "the manual has no images".
    import io as _io

    from PIL import Image

    for mode, fmt in (("RGB", "JPEG"), ("RGBA", "PNG"), ("P", "PNG"), ("L", "PNG")):
        data, w, h = jasani._decode_web_image(_png_b64(64, 48, mode, fmt))
        assert data and (w, h) == (64, 48), (mode, fmt)
        out = Image.open(_io.BytesIO(data))
        assert out.mode == "RGB", (mode, fmt, out.mode)
        assert "transparency" not in out.info, (mode, fmt)
        # the artwork itself survived the flatten — not a blank white page
        assert len(set(out.convert("RGB").getdata())) > 1, (mode, fmt)

    # a data: URL prefix is accepted
    assert jasani._decode_web_image("data:image/png;base64," + _png_b64())[0]


def test_printing_manual_embeds_each_area_image():
    """Each area must reach the PDF as its own image, at its own pixel size —
    that is what keeps the highlighted rectangle over the right spot."""
    import re

    from server import jasani, manuals

    sizes = [(600, 450), (500, 500), (640, 360)]
    keys = ["web_image", "image_1920", "branding_image"]
    areas = []
    for (w, h), key in zip(sizes, keys):
        data, dw, dh = jasani._decode_web_image(jasani._area_image_raw({key: _png_b64(w, h)}))
        assert data, key
        areas.append({"name": f"Area {w}", "methods": ["Screen print"],
                      "areaWidthMm": 90, "areaHeightMm": 48,
                      "image": {"data": data, "width": dw, "height": dh},
                      "rect": {"left": 10, "top": 10, "width": w // 3, "height": h // 3},
                      "colorChoices": "Up to 4", "leadTime": "5 days"})
    # one area with no artwork at all still renders, just without a view
    areas.append({"name": "No artwork", "methods": ["Pad print"], "areaWidthMm": 20,
                  "areaHeightMm": 20, "image": None, "rect": None,
                  "colorChoices": "", "leadTime": ""})

    # the product photo at the head of the manual is a separate image from the
    # per-area views, and was never covered until a manual turned up without one
    import base64 as _b64
    photo = _b64.b64decode(_png_b64(512, 384, "RGB", "PNG"))   # a size no area uses

    pdf = manuals.build_manual({"id": "1", "code": "ITGL 1291", "name": "Test product",
                                "brand": "Jasani"}, areas, "uae", photo)
    assert pdf[:5] == b"%PDF-"
    embedded = {(int(w), int(h)) for w, h in
                zip(re.findall(rb"/Width\s+(\d+)", pdf), re.findall(rb"/Height\s+(\d+)", pdf))}
    for size in sizes:
        assert size in embedded, f"{size} missing from the manual"
    assert (512, 384) in embedded, "the product photo is missing from the manual"
    # and a manual generated without a photo still builds, just without one
    no_photo = manuals.build_manual({"id": "1", "code": "ITGL 1291", "name": "Test product",
                                     "brand": "Jasani"}, areas, "uae", None)
    assert no_photo[:5] == b"%PDF-"
    assert (512, 384) not in {(int(w), int(h)) for w, h in
                              zip(re.findall(rb"/Width\s+(\d+)", no_photo),
                                  re.findall(rb"/Height\s+(\d+)", no_photo))}


def test_branding_artwork_rejects_what_cannot_be_drawn():
    """verify() passes on a truncated payload that then fails at draw time, so
    the bytes are decoded here instead — a bad image is caught before the PDF."""
    import base64

    from server import jasani

    good = base64.b64decode(_png_b64(200, 150))
    truncated = base64.b64encode(good[: len(good) // 2]).decode()
    assert jasani._decode_web_image(truncated) == (None, 0, 0)
    assert jasani._decode_web_image("not base64 at all") == (None, 0, 0)
    assert jasani._decode_web_image(base64.b64encode(b"\x00" * 500).decode()) == (None, 0, 0)
    assert jasani._decode_web_image(base64.b64encode(b"tiny").decode()) == (None, 0, 0)
    assert jasani._decode_web_image(None) == (None, 0, 0)
    assert jasani._area_image_raw({"web_image": "false", "name": "Front"}) is None


def test_jasani_recognises_every_youtube_link_shape():
    """A video link the parser does not recognise does not go missing — the
    entry falls through to the gallery and the video renders as a still
    picture, which is exactly the bug this guards."""
    from server import jasani

    ID = "dQw4w9WgXcQ"
    for url in ("https://www.youtube.com/watch?v=" + ID,
                "https://www.youtube.com/watch?app=desktop&v=" + ID,
                "https://m.youtube.com/watch?feature=share&v=" + ID,
                "https://youtu.be/" + ID,
                "https://www.youtube.com/embed/" + ID,
                "https://www.youtube-nocookie.com/embed/" + ID,
                "https://www.youtube.com/shorts/" + ID,
                "https://www.youtube.com/live/" + ID,
                "https://www.youtube.com/v/" + ID):
        assert jasani._youtube_id(url) == ID, url
    for not_a_video in ("https://www.jasani.ae/web/image/product.product/1/image_1024",
                        "https://www.youtube.com/watch", "false", "", None, True):
        assert jasani._youtube_id(not_a_video) == ""


def test_jasani_video_entry_is_never_mistaken_for_a_gallery_image():
    from server import jasani

    ID = "dQw4w9WgXcQ"
    poster = "https://www.jasani.ae/web/image/product.image/9/image_1024"
    # the supplier is not consistent about the key holding the link
    for key in ("video_url", "youtube_url", "video_link", "some_unexpected_key"):
        entry = {"id": 9, "image_url": poster, key: "https://youtu.be/" + ID}
        assert jasani._image_urls([entry]) == [], key      # not a gallery image
        vids = jasani._video_entries([entry])
        assert vids and vids[0]["youtubeId"] == ID, key
        assert vids[0]["thumbnail"] == poster, key         # poster kept for click-to-play
    # a plain image record stays an image
    plain = {"id": 10, "image_url": poster}
    assert jasani._image_urls([plain]) == [poster]
    assert jasani._video_entries([plain]) == []


def test_catalogue_never_makes_a_visitor_wait_for_the_supplier(tmp_path, monkeypatch):
    """A due cache must be served immediately and refreshed behind the request.
    Blocking here is what turns an ordinary page load into a five-second wait
    on every refresh."""
    import asyncio
    import json as _json
    import time as _time

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_API_TOKEN", "tok")
    stale = _time.time() - 10 * 24 * 3600          # long past due
    (tmp_path / "giveaways-uae.json").write_text(_json.dumps({
        "fetchedAt": stale, "stockAt": stale,
        "products": [{"id": "1", "name": "Cached item", "stock": {"available": 5}}]}))

    calls = []

    async def slow_fetch(market, manual=False):
        calls.append(market)
        await asyncio.sleep(3)                     # a supplier that takes its time
        return [{"id": "1", "name": "Fresh item", "stock": {"available": 9}}]

    monkeypatch.setattr(jasani, "_fetch_products", slow_fetch)

    async def scenario():
        started = asyncio.get_running_loop().time()
        products, state = await jasani.get_catalog("uae")
        elapsed = asyncio.get_running_loop().time() - started
        return products, state, elapsed

    products, state, elapsed = asyncio.run(scenario())
    assert products[0]["name"] == "Cached item"    # served from the snapshot
    assert state == "stale"
    assert elapsed < 0.5, f"the visitor waited {elapsed:.1f}s on the supplier"


def test_cold_cache_is_the_only_thing_that_can_block(tmp_path, monkeypatch):
    import asyncio

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok", "uae": "tok"})

    async def fetch(market, manual=False):
        return [{"id": "7", "name": "First sync", "stock": {"available": 2}}]

    async def apply_stock(market, products, manual=False):
        return None

    monkeypatch.setattr(jasani, "_fetch_products", fetch)
    monkeypatch.setattr(jasani, "_apply_stock", apply_stock)
    products, state = asyncio.run(jasani.get_catalog("ksa"))
    assert state == "live" and products[0]["name"] == "First sync"
    # and once cached, the next call is served straight from disk
    products, state = asyncio.run(jasani.get_catalog("ksa"))
    assert state == "cache"


def test_each_market_has_its_own_token_and_allowance(tmp_path, monkeypatch):
    """Two supplier accounts, two allowances. A shared counter would let one
    market spend the other's calls; a shared token would put ten calls a day
    on one account, which the supplier answers with a 403."""
    import asyncio

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "ksa-token", "uae": "uae-token"})
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    monkeypatch.setattr(jasani.config, "SUPPLIER_AUTO_BUDGET", 4)

    assert jasani._token("ksa") == "ksa-token"
    assert jasani._token("uae") == "uae-token"

    for _ in range(4):
        assert jasani._budget_ok("ksa")
    assert jasani._budget_ok("ksa") is False           # KSA automatic work is done
    assert jasani.budget_status("uae")["autoRemaining"] == 4   # UAE untouched
    assert all(jasani._budget_ok("uae") for _ in range(4))
    assert jasani.budget_status("ksa")["used"] == 4
    assert jasani.budget_status("uae")["used"] == 4
    # each keeps its own reserved call
    assert jasani._budget_ok("ksa", manual=True) is True
    assert jasani._budget_ok("uae", manual=True) is True

    # a market with no token never spends anything, and says which one
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "ksa-token", "uae": ""})
    with pytest.raises(jasani.SupplierUnavailable) as exc:
        asyncio.run(jasani._fetch("https://www.jasani.ae/products/all/x", "www.jasani.ae", "uae"))
    assert "UAE" in str(exc.value)


def test_market_day_follows_each_markets_own_clock(monkeypatch):
    """KSA is UTC+3 and the UAE UTC+4, so a single clock rolls one market's
    allowance over an hour early or late."""
    import time as _time

    from server import jasani

    # 22:30 UTC — already tomorrow in the UAE, still today in Saudi Arabia
    fixed = _time.mktime(_time.strptime("2026-05-10 22:30:00", "%Y-%m-%d %H:%M:%S")) \
        - _time.timezone
    monkeypatch.setattr(jasani.time, "time", lambda: fixed)
    assert jasani._market_day("ksa") == "2026-05-11"      # 01:30 local
    assert jasani._market_day("uae") == "2026-05-11"      # 02:30 local
    assert jasani._market_local("ksa")[1] == 1
    assert jasani._market_local("uae")[1] == 2
    # 21:30 UTC: 00:30 in Riyadh, 01:30 in Dubai — both already the next day
    fixed2 = fixed - 3600
    monkeypatch.setattr(jasani.time, "time", lambda: fixed2)
    assert jasani._market_local("ksa")[1] == 0
    assert jasani._market_local("uae")[1] == 1


def test_scheduled_slots_run_once_each_and_cost_one_call(tmp_path, monkeypatch):
    """Four automatic calls a day per market: products at midnight, prices at
    01:00, then stock at 08:00 and 18:00 local. Each slot is one call and runs
    once, and four slots is exactly the automatic allowance."""
    import asyncio
    import time as _time

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok", "uae": ""})
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    monkeypatch.setattr(jasani.config, "SUPPLIER_AUTO_BUDGET", 4)

    calls = []

    async def fake_products(market, manual=False):
        calls.append(("products", market))
        jasani._budget_ok(market, manual)          # a real fetch spends one
        return [{"id": "1", "name": "Item", "stock": {"available": 3}}]

    async def fake_stock(market, products, manual=False):
        calls.append(("stock", market))
        jasani._budget_ok(market, manual)
        for p in products:
            p["stock"] = {"available": 9}

    async def fake_prices(market, products, manual=False):
        calls.append(("price", market))
        jasani._budget_ok(market, manual)
        for p in products:
            p.setdefault(jasani._INT_KEY, {}).update({"price": 4.0, "currency": "SAR"})
        return {"rows": len(products), "matched": len(products), "unmatched": 0,
                "codeMismatch": 0, "currencies": ["SAR"]}

    monkeypatch.setattr(jasani, "_fetch_products", fake_products)
    monkeypatch.setattr(jasani, "_apply_stock", fake_stock)
    monkeypatch.setattr(jasani, "_apply_prices", fake_prices)

    # the schedule may never outgrow the automatic allowance: the fifth call is
    # the one a person needs when a catalogue is visibly wrong
    assert len(jasani.config.JASANI_SCHEDULE) <= jasani.config.SUPPLIER_AUTO_BUDGET
    assert [w for _, w in jasani.config.JASANI_SCHEDULE].count("price") == 1

    # 09:00 in Riyadh: midnight products and the 08:00 stock slot are both due
    base = _time.mktime(_time.strptime("2026-05-10 06:00:00", "%Y-%m-%d %H:%M:%S")) - _time.timezone
    monkeypatch.setattr(jasani.time, "time", lambda: base)
    assert jasani._market_local("ksa")[1] == 9

    ran = asyncio.run(jasani.run_due_slots())
    assert ran == ["ksa:00:products"]              # one slot per tick, in order
    ran += asyncio.run(jasani.run_due_slots())
    assert ran[-1] == "ksa:01:price"
    ran += asyncio.run(jasani.run_due_slots())
    assert ran[-1] == "ksa:08:stock"
    assert asyncio.run(jasani.run_due_slots()) == []   # 18:00 has not arrived

    assert calls == [("products", "ksa"), ("price", "ksa"), ("stock", "ksa")]
    used = jasani.budget_status("ksa")["used"]
    assert used == 3, f"three slots must cost three calls, spent {used}"
    # UAE has no token, so nothing was scheduled for it at all
    assert not [c for c in calls if c[1] == "uae"]
    assert jasani.budget_status("ksa")["nextSlot"]["hour"] == 18


def test_jasani_reserves_the_last_call_for_a_manual_sync(tmp_path, monkeypatch):
    """Background refreshes stop one short of the limit so a person can always
    force a sync; only an explicitly manual call may use the reserve."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    monkeypatch.setattr(jasani.config, "SUPPLIER_AUTO_BUDGET", 4)

    assert all(jasani._budget_ok("uae") for _ in range(4))   # automatic work
    assert jasani._budget_ok("uae") is False                 # reserve is off limits
    status = jasani.budget_status("uae")
    assert status == {**status, "used": 4, "remaining": 1, "autoLimit": 4,
                      "autoRemaining": 0, "reserved": 1, "limit": 5}
    assert jasani._budget_ok("uae", manual=True) is True     # the person gets it
    assert jasani._budget_ok("uae", manual=True) is False    # and no more
    assert jasani.budget_status("uae")["remaining"] == 0
    assert jasani.budget_status("ksa")["remaining"] == 5     # separate account


def test_jasani_refuses_two_syncs_of_one_market_at_once(tmp_path, monkeypatch):
    """A double-click, or two admins pressing refresh together, must not spend
    two calls doing identical work."""
    import asyncio

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok", "uae": "tok"})

    async def scenario():
        held = jasani._refresh_lock("uae")
        async with held:                       # pretend a sync is already running
            with pytest.raises(jasani.SupplierUnavailable) as exc:
                await jasani.force_refresh("uae", "stock")
            return str(exc.value)

    assert "already running" in asyncio.run(scenario())
    # each market has its own lock, so KSA is unaffected
    assert jasani._refresh_lock("ksa") is not jasani._refresh_lock("uae")


def test_jasani_refunds_calls_the_supplier_never_served(tmp_path, monkeypatch):
    """A call is spent before the request leaves; if the supplier was never
    reached it must be given back, or a few failed attempts silently exhaust
    the day for BOTH markets and look like a dead API."""
    import asyncio

    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok-ksa", "uae": "tok-uae"})

    # our own host allowlist rejects it — nothing ever went out
    with pytest.raises(jasani.SupplierUnavailable):
        asyncio.run(jasani._fetch("https://evil.example.com/x", "www.jasani.ae", "uae"))
    assert jasani.budget_status("uae")["used"] == 0

    # transport failure (DNS/TLS/connect/timeout) — the supplier served nothing
    with pytest.raises(jasani.SupplierUnavailable) as exc:
        asyncio.run(jasani._fetch("https://www.jasani.ae/products/all/tok",
                                  "www.jasani.ae", "uae"))
    assert "transport" in str(exc.value)
    assert jasani.budget_status("uae")["used"] == 0

    # a served response still counts, and a 403 still parks that market's day
    jasani._budget_ok("uae")
    assert jasani.budget_status("uae")["used"] == 1
    jasani._budget_exhaust("uae")
    assert jasani._budget_ok("uae") is False


def test_jasani_remembers_why_a_market_failed(tmp_path, monkeypatch):
    """'Nothing cached yet' cannot be told apart from 'every refresh failed',
    so the last attempt is persisted per market and shown in the console."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS",
                        {"ksa": "ksa-secret-token", "uae": "super-secret-token"})

    assert jasani.cache_status("uae")["lastAttempt"] is None
    jasani.record_attempt("uae", "products", False,
                          "transport: ConnectError super-secret-token")
    entry = jasani.cache_status("uae")["lastAttempt"]
    assert entry["ok"] is False and entry["what"] == "products"
    assert "super-secret-token" not in entry["reason"]      # never leak the token
    assert entry["ts"] > 0
    # the other market keeps its own record
    assert jasani.cache_status("ksa")["lastAttempt"] is None
    jasani.record_attempt("ksa", "stock", True, "40 products")
    assert jasani.cache_status("ksa")["lastAttempt"]["ok"] is True
    assert jasani.cache_status("uae")["lastAttempt"]["ok"] is False


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


# ---------------- Price API (docs section 22) ----------------
# Prices are NOT in the Product API. They have their own primary endpoint, and
# forgetting that is exactly how a catalogue of 1,778 products ends up with
# zero prices no matter how often it is synced.

def _price_stub(monkeypatch, jasani, *, products=None, prices=None, stock=None,
                fail=()):
    """Fake the one transport function, so every URL the client builds is
    observable and the daily budget is still spent the way it really is."""
    seen = []

    async def fake_fetch(url, expected_host, market, primary=True, manual=False):
        seen.append(url)
        kind = ("products" if "/products/all/" in url
                else "price" if "/products/price/" in url
                else "stock")
        if primary and not jasani._budget_ok(market, manual):
            raise jasani.SupplierUnavailable("daily supplier budget exhausted")
        if kind in fail:
            raise jasani.SupplierUnavailable(f"upstream 500 ({kind})")
        payload = {"products": products, "price": prices, "stock": stock}[kind]
        return json.dumps(payload.get(market, [])).encode(), "application/json"

    monkeypatch.setattr(jasani, "_fetch", fake_fetch)
    return seen


_PRODUCTS = {
    "ksa": [{"id": 2001, "default_code": "ITGL 1291", "name": "Aluminium Flask",
             "brand_id": [3, "Santhome"], "website_sequence": 4},
            {"id": 2002, "default_code": "CTEN 2240", "name": "Cotton Tote",
             "brand_id": [4, "EcoLine"], "website_sequence": 9}],
    "uae": [{"id": 3001, "default_code": "ITGL 1291", "name": "Aluminium Flask",
             "brand_id": [3, "Santhome"], "website_sequence": 4}],
}
_PRICES = {
    "ksa": [{"id": 2001, "default_code": "ITGL 1291", "currency": "SAR",
             "list_price": 38.5, "retail_price": 62.0},
            {"id": 2002, "default_code": "CTEN 2240", "currency": "SAR",
             "list_price": 11.25, "retail_price": 19.0}],
    "uae": [{"id": 3001, "default_code": "ITGL 1291", "currency": "AED",
             "list_price": 41.0, "retail_price": 66.0}],
}
_STOCK = {
    "ksa": [{"id": 2001, "net_available_qty": 1840, "blocked_qty": 120, "incoming_qty": 0},
            {"id": 2002, "net_available_qty": 0, "blocked_qty": 90, "incoming_qty": 1500}],
    "uae": [{"id": 3001, "net_available_qty": 12, "blocked_qty": 3}],
}


def _price_env(tmp_path, monkeypatch, jasani, **kw):
    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok-ksa", "uae": "tok-uae"})
    monkeypatch.setattr(jasani.config, "SUPPLIER_DAILY_BUDGET", 5)
    monkeypatch.setattr(jasani.config, "SUPPLIER_AUTO_BUDGET", 4)
    return _price_stub(monkeypatch, jasani, products=_PRODUCTS, prices=_PRICES,
                       stock=_STOCK, **kw)


def test_price_api_url_is_the_documented_one_per_market(tmp_path, monkeypatch):
    """/products/price/{token} on that market's own host — never the other's."""
    import asyncio

    from server import jasani

    seen = _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))
    asyncio.run(jasani.force_refresh("uae", "full"))
    price_urls = [u for u in seen if "/products/price/" in u]
    assert price_urls == ["https://www.giftsksa.com/products/price/tok-ksa",
                          "https://www.jasani.ae/products/price/tok-uae"]


def test_price_records_parse_into_one_price_and_a_currency(tmp_path, monkeypatch):
    """list_price only. retail_price is the supplier's suggested selling price,
    not ours, and it is deliberately not carried anywhere."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    rec = jasani.normalize_price(
        {"id": 2001, "default_code": "ITGL 1291", "currency": "sar",
         "list_price": "38.50", "retail_price": 62}, "ksa")
    assert rec == {"id": "2001", "code": "ITGL 1291", "price": 38.5, "currency": "SAR"}
    # a row with no usable list_price is not a row, whatever else it carries
    assert jasani.normalize_price({"id": 9, "list_price": 0, "retail_price": 62}, "ksa") is None
    assert jasani.normalize_price({"id": 9, "retail_price": 19.0}, "uae") is None
    assert jasani.normalize_price({"list_price": 5}, "ksa") is None
    # the market supplies the currency when the supplier leaves it out
    assert jasani.normalize_price({"id": 7, "list_price": 19.0}, "uae")["currency"] == "AED"


def test_prices_join_on_product_id_and_report_code_mismatches(tmp_path, monkeypatch):
    """The id is the key. default_code is reconciliation only — matching on it
    would let a renamed or duplicated code move a price onto another product."""
    from server import jasani

    monkeypatch.setattr(jasani, "_CACHE_DIR", tmp_path)
    products = [{"id": "2001", "code": "ITGL 1291"}, {"id": "2002", "code": "CTEN 2240"},
                {"id": "2003", "code": "APRL 4417"}]
    report = jasani._merge_prices(products, [
        {"id": 2001, "default_code": "ITGL 1291", "list_price": 38.5, "currency": "SAR"},
        {"id": 2002, "default_code": "RENAMED 0001", "list_price": 11.25, "currency": "SAR"},
        {"id": 9999, "default_code": "APRL 4417", "list_price": 96.0, "currency": "SAR"},
    ], "ksa")
    assert report["matched"] == 2 and report["unmatched"] == 1
    assert report["codeMismatch"] == 1 and report["currencies"] == ["SAR"]
    # 2002 took its price despite the code disagreeing; 2003 took none, even
    # though a price row carried its code
    assert products[1][jasani._INT_KEY]["price"] == 11.25
    assert jasani._INT_KEY not in products[2]


def test_price_sync_keeps_the_two_markets_apart(tmp_path, monkeypatch):
    """Separate accounts, separate hosts, separate caches. A KSA price must
    never reach a UAE product — the two catalogues share codes, not ids."""
    import asyncio

    from server import jasani

    _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))
    asyncio.run(jasani.force_refresh("uae", "full"))
    ksa, uae = jasani.internal_map("ksa"), jasani.internal_map("uae")
    assert ksa["2001"]["price"] == 38.5 and ksa["2001"]["currency"] == "SAR"
    assert uae["3001"]["price"] == 41.0 and uae["3001"]["currency"] == "AED"
    assert set(ksa) & set(uae) == set()
    assert "2001" not in uae and "3001" not in ksa


def test_synced_prices_never_ride_on_a_product_or_reach_the_public_api(tmp_path, monkeypatch):
    import asyncio

    from server import jasani

    _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))
    raw = json.loads((tmp_path / "giveaways-ksa.json").read_text(encoding="utf-8"))
    for product in raw["products"]:
        assert jasani._INT_KEY not in product
        for key in ("price", "wholesale", "retail", "list_price", "blocked_qty"):
            assert key not in product, key
    assert raw["internal"]["2001"]["price"] == 38.5
    # the supplier's retail price is not stored at all, on the product or beside it
    assert all("retail" not in rec for rec in raw["internal"].values())

    public = client.get("/api/giveaways/products?country=ksa")
    body = public.text
    for needle in ("38.5", "62.0", "list_price", "retail_price", "price"):
        assert needle not in body, needle


def test_a_stock_refresh_keeps_the_prices_already_synced(tmp_path, monkeypatch):
    import asyncio

    from server import jasani

    _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))
    priced_at = jasani._read_cache("ksa")["priceAt"]
    assert priced_at

    asyncio.run(jasani.force_refresh("ksa", "stock"))
    after = jasani.internal_map("ksa")
    assert after["2001"]["price"] == 38.5
    assert after["2001"]["booked"] == 120          # the stock call adds its own field
    assert jasani._read_cache("ksa")["priceAt"] == priced_at   # not restamped


def test_a_product_refresh_keeps_last_known_good_prices(tmp_path, monkeypatch):
    """Both when the products call runs alone and when a full sync's price leg
    fails: yesterday's prices are better than none, and nothing else can supply
    them until the next successful price call."""
    import asyncio

    from server import jasani

    _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))
    assert jasani.internal_map("ksa")["2001"]["price"] == 38.5

    asyncio.run(jasani.force_refresh("ksa", "products"))
    assert jasani.internal_map("ksa")["2001"]["price"] == 38.5

    # the next day, with a full sync whose price leg fails upstream
    (tmp_path / "supplier-budget.json").unlink(missing_ok=True)
    _price_stub(monkeypatch, jasani, products=_PRODUCTS, prices=_PRICES, stock=_STOCK,
                fail=("price",))
    result = asyncio.run(jasani.force_refresh("ksa", "full"))
    assert result["pricesApplied"] is False and result["stockApplied"] is True
    assert jasani.internal_map("ksa")["2001"]["price"] == 38.5
    assert jasani.cache_status("ksa")["withPrice"] == 2


def test_full_sync_calls_products_price_and_stock(tmp_path, monkeypatch):
    import asyncio

    from server import jasani

    seen = _price_env(tmp_path, monkeypatch, jasani)
    result = asyncio.run(jasani.force_refresh("ksa", "full"))
    assert [u.rsplit("/", 2)[1] for u in seen] == ["all", "price", "stock"]
    assert result == {"refreshed": "full", "products": 2, "priced": 2,
                      "pricesApplied": True, "stockApplied": True}
    assert jasani.budget_status("ksa")["used"] == 3
    status = jasani.cache_status("ksa")
    assert status["withPrice"] == 2
    assert status["priceAt"] and status["pricesFresh"] is True
    assert status["currencies"] == ["SAR"]


def test_full_sync_checks_the_budget_before_spending_any_of_it(tmp_path, monkeypatch):
    """Three calls or none. Spending one on products and then running dry
    leaves a fresh catalogue joined to yesterday's prices and no way to finish."""
    import asyncio

    from server import jasani

    seen = _price_env(tmp_path, monkeypatch, jasani)
    for _ in range(3):                      # 2 automatic calls left, full needs 3
        jasani._budget_ok("ksa", manual=True)
    seen.clear()

    with pytest.raises(jasani.SupplierUnavailable) as exc:
        asyncio.run(jasani.force_refresh("ksa", "full", manual=False))
    assert "budget" in str(exc.value) and "needs 3" in str(exc.value)
    assert seen == []                       # nothing left for the supplier at all
    assert jasani.budget_status("ksa")["used"] == 3

    # the reserve makes the difference: an owner/admin sync still has 2 of 5,
    # which is still short of three, and a single-call target goes through
    with pytest.raises(jasani.SupplierUnavailable):
        asyncio.run(jasani.force_refresh("ksa", "full", manual=True))
    assert seen == []


def test_the_reserved_fifth_call_stays_out_of_automatic_reach(tmp_path, monkeypatch):
    """Automatic work stops at four; only a manual sync — which the API grants
    to owner and admin alone — may spend the fifth."""
    import asyncio

    from server import jasani

    _price_env(tmp_path, monkeypatch, jasani)
    asyncio.run(jasani.force_refresh("ksa", "full"))       # 3 of 5
    asyncio.run(jasani.force_refresh("ksa", "prices"))     # 4 of 5
    assert jasani.budget_status("ksa") == {**jasani.budget_status("ksa"),
                                           "used": 4, "autoRemaining": 0, "remaining": 1}
    with pytest.raises(jasani.SupplierUnavailable):
        asyncio.run(jasani.force_refresh("ksa", "prices", manual=False))
    assert jasani.budget_status("ksa")["used"] == 4        # the failed try spent nothing
    asyncio.run(jasani.force_refresh("ksa", "prices", manual=True))
    assert jasani.budget_status("ksa")["used"] == 5


def test_startup_warm_up_spends_one_call_and_hands_over_to_the_schedule(tmp_path, monkeypatch):
    """A cold market gets its catalogue at boot, but not by doing the day's
    products slot twice: the warm-up marks that slot as its own."""
    import asyncio

    from server import jasani

    seen = _price_env(tmp_path, monkeypatch, jasani)
    monkeypatch.setattr(jasani.config, "JASANI_TOKENS", {"ksa": "tok-ksa", "uae": ""})
    asyncio.run(jasani.warm_catalogues())
    assert [u.rsplit("/", 2)[1] for u in seen] == ["all"]     # one call, products
    assert jasani.budget_status("ksa")["used"] == 1
    assert 0 in jasani.budget_status("ksa")["slotsDone"]

    # a warm cache is left alone entirely
    seen.clear()
    asyncio.run(jasani.warm_catalogues())
    assert seen == []
