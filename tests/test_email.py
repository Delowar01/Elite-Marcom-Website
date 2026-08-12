"""Resend transactional email — all five forms, routing, templates, safety.

The provider call is captured by a stub transport, so the whole pipeline is
exercised end to end without sending anything or needing a real API key.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from server import config, mailer, storage
from server.main import app

client = TestClient(app)
ORIGIN = {"Origin": "http://127.0.0.1:8847"}
SENT: list[dict] = []
FAIL_NEXT: list[bool] = [False]


class _StubResponse:
    def __init__(self, status: int):
        self.status_code = status
        self.text = "stub"

    def json(self):
        return {"error": "stub failure"} if self.status_code >= 400 else {"id": "msg_stub_1"}


class _StubClient:
    """Stands in for httpx.Client inside the mailer only."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        SENT.append({"url": url, "payload": json, "headers": headers})
        return _StubResponse(500 if FAIL_NEXT[0] else 200)


@pytest.fixture(scope="module", autouse=True)
def mail_env(tmp_path_factory):
    from server import adminauth as aa

    d = tmp_path_factory.mktemp("mail")
    old_admin, old_records, old_cv, old_conn = (
        aa._DB_PATH, storage._DB_PATH, storage._CV_DIR, storage._conn)
    old_key, old_runtime = config.RESEND_API_KEY, config.RUNTIME_DIR
    aa._DB_PATH = d / "admin.db"
    if hasattr(aa._local, "conn"):
        del aa._local.conn
    storage._DB_PATH, storage._CV_DIR, storage._conn = d / "data.db", d / "cvs", None
    config.RUNTIME_DIR = d
    config.RESEND_API_KEY = "re_test_key_do_not_use"
    if hasattr(mailer._local, "conn"):
        del mailer._local.conn
    real_client = mailer.httpx.Client
    mailer.httpx.Client = _StubClient
    # deliver inline so assertions are deterministic
    real_send = mailer.send_form_emails
    mailer.send_form_emails = lambda kind, ref, payload, attachment=None: (
        mailer._deliver(mailer.KIND_TO_FORM[kind], kind, ref, payload, attachment)
        if kind in mailer.KIND_TO_FORM else None)
    yield
    mailer.httpx.Client = real_client
    mailer.send_form_emails = real_send
    config.RESEND_API_KEY, config.RUNTIME_DIR = old_key, old_runtime
    aa._DB_PATH, storage._DB_PATH, storage._CV_DIR, storage._conn = (
        old_admin, old_records, old_cv, old_conn)
    if hasattr(mailer._local, "conn"):
        del mailer._local.conn


@pytest.fixture(autouse=True)
def clean_sent():
    SENT.clear()
    FAIL_NEXT[0] = False
    from server import security

    security.limiter._hits.clear()
    yield


def challenge(form: str) -> str:
    return client.get(f"/api/security/challenge?form={form}").json()["challenge"]


def base(form: str) -> dict:
    return {"consent": True, "challenge": challenge(form), "consentVersion": "2026-01"}


def by_recipient(address: str) -> dict | None:
    return next((s["payload"] for s in SENT if address in s["payload"]["to"]), None)


# ---------------- defaults ----------------

def test_default_routing_matches_the_brief():
    expected = {
        "general_inquiry": "info@elitemarcom.com",
        "job_application": "hr@elitemarcom.com",
        "corporate_gifts": "mohammad.hossain@elitemarcom.com",
        "stock_notification": "mohammad.hossain@elitemarcom.com",
        "rental_inquiry": "mohammad.hossain@elitemarcom.com",
    }
    for key, address in expected.items():
        assert mailer.form_settings(key)["recipient"] == address
    general = mailer.general_settings()
    assert general["fromName"] == "Elite Marcom"
    assert general["fromEmail"] == "website@mail.elitemarcom.com"
    assert general["replyTo"] == "info@elitemarcom.com"
    assert general["websiteUrl"] == "https://www.elitemarcom.com"
    assert general["contactEmail"] == "info@elitemarcom.com"


# ---------------- the five forms, end to end ----------------

def test_general_inquiry_sends_both_emails():
    res = client.post("/api/contact/enquiries", json={
        "enquiryType": "New project", "fullName": "Amira Hassan", "company": "Falcon Events",
        "email": "amira@example.com", "phone": "+966551234567", "market": "Saudi Arabia",
        "service": "Exhibition Stands", "message": "We need a 200 sqm double-deck stand.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    reference = res.json()["reference"]
    assert len(SENT) == 2

    internal = by_recipient("info@elitemarcom.com")
    assert internal is not None
    assert internal["from"] == "Elite Marcom <website@mail.elitemarcom.com>"
    assert internal["reply_to"] == ["amira@example.com"]        # reply goes to the customer
    assert reference in internal["subject"] and "Amira Hassan" in internal["subject"]
    assert "Falcon Events" in internal["html"] and "200 sqm" in internal["html"]

    customer = by_recipient("amira@example.com")
    assert customer is not None
    assert customer["subject"] == "We have received your enquiry — Elite Marcom"
    assert customer["reply_to"] == ["info@elitemarcom.com"]
    assert "Thank you for contacting Elite Marcom" in customer["html"]
    assert "Amira Hassan" in customer["html"] and reference in customer["html"]
    assert "logo-email.png" in customer["html"]
    assert "www.elitemarcom.com" in customer["html"]
    assert "info@elitemarcom.com" in customer["html"]
    assert 'max-width:600px' in customer["html"]               # mobile-responsive shell
    assert customer["text"].strip()                             # plain-text alternative


def test_job_application_attaches_the_cv():
    import io as _io

    from reportlab.pdfgen import canvas as _canvas

    _buf = _io.BytesIO()
    _c = _canvas.Canvas(_buf)
    _c.drawString(80, 700, "Lina Farouk — Senior 3D Designer")
    _c.save()
    pdf = _buf.getvalue()
    res = client.post("/api/careers/applications", data={
        "fullName": "Lina Farouk", "email": "lina@example.com", "phone": "+971523337788",
        "location": "Dubai", "roleId": "general", "portfolioUrl": "https://portfolio.example.com/lina",
        "introduction": "Eight years designing award-winning exhibition experiences.",
        "consent": "yes", "challenge": challenge("career"), "consentVersion": "2026-01",
        "sourcePage": "/careers.html"},
        files={"cv": ("lina-cv.pdf", pdf, "application/pdf")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    reference = res.json()["reference"]

    internal = by_recipient("hr@elitemarcom.com")
    assert internal is not None
    attachments = internal.get("attachments") or []
    assert len(attachments) == 1
    assert attachments[0]["filename"] == f"{reference}-cv.pdf"
    assert base64.b64decode(attachments[0]["content"]) == pdf   # the real file, intact
    assert "CV is attached" in internal["html"]

    customer = by_recipient("lina@example.com")
    assert customer is not None
    assert "application" in customer["subject"].lower()
    assert "Lina Farouk" in customer["html"]
    assert not customer.get("attachments")                      # never sent back to the applicant


def test_corporate_gifts_request_sends_both_emails():
    res = client.post("/api/giveaways/enquiries", data={
        "fullName": "Yousef Al Marri", "company": "Dune Digital", "email": "yousef@example.com",
        "phone": "+971507654321", "requiredBy": "", "deliveryCity": "Dubai",
        "shippingAddress": "Sheikh Zayed Road, Trade Centre 2, Dubai", "notes": "",
        "consent": "yes", "market": "ksa",
        "items": json.dumps([{"productId": "prev-hoodie-ksa", "quantity": 50}]),
        "challenge": challenge("giveaway_enquiry"), "consentVersion": "2026-01",
        "sourcePage": "/giveaways.html"}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    internal = by_recipient("mohammad.hossain@elitemarcom.com")
    customer = by_recipient("yousef@example.com")
    assert internal is not None and customer is not None
    assert "Dune Digital" in internal["subject"]
    assert "Requested items" in internal["html"] and "qty 50" in internal["html"]
    assert "corporate gifts request" in customer["html"].lower()


def test_stock_notification_sends_both_emails():
    from server.main import load_preview_products

    products = load_preview_products("ksa")
    res = client.post("/api/giveaways/notifications", json={
        "fullName": "Sara Al Qahtani", "company": "Vision Expo", "email": "sara@example.com",
        "phone": "+966542228899", "message": "", "market": "ksa",
        "productId": products[0]["id"], "sourcePage": "/giveaways.html",
        **base("giveaway_notification")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    internal = by_recipient("mohammad.hossain@elitemarcom.com")
    customer = by_recipient("sara@example.com")
    assert internal is not None and customer is not None
    assert "Stock notification request" in internal["subject"]
    assert "notification list" in customer["html"]
    assert products[0]["name"] in customer["html"]              # product variable resolved


def test_rental_inquiry_sends_both_emails():
    rentals = client.get("/api/rentals/products").json()["products"]
    res = client.post("/api/rentals/enquiries", json={
        "fullName": "Mohammed Bakr", "company": "Bakr Holding", "email": "bakr@example.com",
        "phone": "+966509991122", "startDate": "2026-10-02", "endDate": "2026-10-06",
        "eventCity": "Riyadh", "venue": "Riyadh Front", "notes": "Full AV setup.",
        "market": "ksa", "items": [{"productId": rentals[0]["id"], "quantity": 2, "days": 4}],
        "sourcePage": "/rental.html", **base("rental_enquiry")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    internal = by_recipient("mohammad.hossain@elitemarcom.com")
    customer = by_recipient("bakr@example.com")
    assert internal is not None and customer is not None
    assert "Bakr Holding" in internal["subject"]
    assert "day(s)" in internal["html"]
    assert "rental enquiry" in customer["html"].lower()


# ---------------- admin-controlled behaviour ----------------

def test_routing_change_affects_the_next_submission():
    mailer.save_form("general_inquiry", {"recipient": "newteam@elitemarcom.com"})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Routing Test", "company": "",
        "email": "routing@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Testing the routing change end to end.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    assert by_recipient("newteam@elitemarcom.com") is not None
    assert by_recipient("info@elitemarcom.com") is None
    mailer.save_form("general_inquiry", {"recipient": "info@elitemarcom.com"})


def test_on_off_switches_are_respected():
    mailer.save_form("general_inquiry", {"internalOn": False, "customerOn": True})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Switch Test", "company": "",
        "email": "switch@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Only the customer should hear back here.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    assert by_recipient("info@elitemarcom.com") is None
    assert by_recipient("switch@example.com") is not None

    SENT.clear()
    mailer.save_form("general_inquiry", {"internalOn": True, "customerOn": False})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Switch Test 2", "company": "",
        "email": "switch2@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Only the team should hear about this one.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    assert by_recipient("info@elitemarcom.com") is not None
    assert by_recipient("switch2@example.com") is None
    mailer.save_form("general_inquiry", {"internalOn": True, "customerOn": True})


def test_template_edits_reach_the_customer_email():
    mailer.save_form("general_inquiry", {
        "customerSubject": "Hello {{customer_name}} — Elite Marcom",
        "heading": "Thanks, {{customer_name}}",
        "body": "We received your note about {{service}}. Reference {{reference_number}}.",
        "closing": "Talk soon.", "buttonText": "Our services",
        "buttonUrl": "https://www.elitemarcom.com/services.html"})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Template Tester", "company": "",
        "email": "template@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Corporate Events", "message": "Checking the custom template rendering.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    customer = by_recipient("template@example.com")
    assert customer["subject"] == "Hello Template Tester — Elite Marcom"
    assert "Thanks, Template Tester" in customer["html"]
    assert "Corporate Events" in customer["html"]
    assert "https://www.elitemarcom.com/services.html" in customer["html"]
    assert "Our services" in customer["html"]
    assert "{{" not in customer["html"]                       # every variable resolved


def test_templates_reject_unknown_variables_and_bad_addresses():
    with pytest.raises(mailer.MailError):
        mailer.save_form("general_inquiry", {"body": "Hi {{salary}}"})
    with pytest.raises(mailer.MailError):
        mailer.save_form("general_inquiry", {"recipient": "not-an-email"})
    with pytest.raises(mailer.MailError):
        mailer.save_form("general_inquiry", {"buttonUrl": "javascript:alert(1)"})
    with pytest.raises(mailer.MailError):
        mailer.save_general({"fromEmail": "hello@evil.example"})   # unverified sender domain
    with pytest.raises(mailer.MailError):
        mailer.save_general({"websiteUrl": "http://insecure.example"})
    assert mailer.general_settings()["fromEmail"] == "website@mail.elitemarcom.com"


def test_template_values_are_escaped_not_injected():
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Bobby <script>alert(1)</script>",
        "company": "", "email": "bobby@example.com", "phone": "+966500000000",
        "market": "Worldwide", "service": "Branding",
        "message": "Testing that markup in a name cannot break the email.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    customer = by_recipient("bobby@example.com")
    assert "<script>" not in customer["html"]
    assert "&lt;script&gt;" in customer["html"]


# ---------------- reliability & safety ----------------

def test_failed_send_is_logged_as_failed_never_as_sent():
    FAIL_NEXT[0] = True
    res = client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Fail Case", "company": "",
        "email": "fail@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "The provider will reject this one.",
        "sourcePage": "/contact.html", **base("contact")}, headers=ORIGIN)
    assert res.status_code == 200          # the visitor's request is still safely stored
    reference = res.json()["reference"]
    entries = [e for e in mailer.log_entries(20) if e["reference"] == reference]
    assert entries and all(e["status"] == "failed" for e in entries)
    assert all("stub" not in e["detail"] for e in entries)   # provider text never stored


def test_duplicate_submission_cannot_send_twice():
    payload = {"fullName": "Repeat Sender", "company": "", "email": "repeat@example.com",
               "phone": "+966500000000", "message": "duplicate check"}
    reference = storage.save_record("contact", payload, "iphash", 180)
    mailer._deliver("general_inquiry", "contact", reference, payload, None)
    first = len(SENT)
    assert first == 2
    mailer._deliver("general_inquiry", "contact", reference, payload, None)  # retry / double click
    assert len(SENT) == first


def test_api_key_never_leaves_the_server():
    settings = mailer.all_settings()
    blob = json.dumps(settings)
    assert config.RESEND_API_KEY not in blob
    assert "re_" not in blob
    for leak in ("apiKey", "api_key", "resend_api_key", "secret", "token"):
        assert leak.lower() not in blob.lower()
    assert settings["configured"] is True          # only a boolean is exposed
    # the key is not written to any admin setting either
    from server import adminauth as aa

    rows = aa._connect().execute("SELECT key, value FROM settings").fetchall()
    assert all(config.RESEND_API_KEY not in str(r["value"]) for r in rows)
    # every outbound call carries it in the header only, never in the body
    assert SENT == [] or all(config.RESEND_API_KEY not in json.dumps(s["payload"]) for s in SENT)
    assert mailer._mask(f"boom {config.RESEND_API_KEY}") == "boom ***"


def test_test_email_success_and_failure_are_reported_plainly():
    mailer.send_test("owner@elitemarcom.com", "owner@elitemarcom.com")
    assert SENT and "owner@elitemarcom.com" in SENT[-1]["payload"]["to"]
    assert SENT[-1]["payload"]["subject"] == "Elite Marcom — email settings test"
    FAIL_NEXT[0] = True
    with pytest.raises(mailer.MailError) as exc:
        mailer.send_test("owner@elitemarcom.com", "owner@elitemarcom.com")
    assert "stub" not in str(exc.value) and "500" not in str(exc.value)
    with pytest.raises(mailer.MailError):
        mailer.send_test("not-an-email", "owner@elitemarcom.com")


def test_nothing_is_sent_when_the_key_is_missing():
    original = config.RESEND_API_KEY
    config.RESEND_API_KEY = ""
    try:
        payload = {"fullName": "No Key", "email": "nokey@example.com"}
        reference = storage.save_record("contact", payload, "iphash", 180)
        mailer._deliver("general_inquiry", "contact", reference, payload, None)
        assert SENT == []
    finally:
        config.RESEND_API_KEY = original
