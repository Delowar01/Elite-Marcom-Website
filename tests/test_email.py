"""Resend transactional email — all six forms, routing, templates, safety.

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
    yield
    mailer.httpx.Client = real_client
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


def drain() -> dict:
    """Run the worker exactly as the server does after a response."""
    return mailer.process_outbox(20)


def by_recipient(address: str) -> dict | None:
    return next((s["payload"] for s in SENT if address in s["payload"]["to"]), None)


# ---------------- defaults ----------------

def test_default_routing_matches_the_brief():
    expected = {
        "general_inquiry": "info@elitemarcom.com",
        "job_application": "hr@elitemarcom.com",
        "corporate_gifts": "mohammad.hossain@elitemarcom.com",
        "stock_notification": "mohammad.hossain@elitemarcom.com",
        "rental_availability": "mohammad.hossain@elitemarcom.com",
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


# ---------------- the six forms, end to end ----------------

def test_general_inquiry_sends_both_emails():
    res = client.post("/api/contact/enquiries", json={
        "enquiryType": "New project", "fullName": "Amira Hassan", "company": "Falcon Events",
        "email": "amira@example.com", "phone": "+966551234567", "market": "Saudi Arabia",
        "service": "Exhibition Stands", "message": "We need a 200 sqm double-deck stand.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    reference = res.json()["reference"]
    assert SENT == []                      # nothing sent during the request
    drain()
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
        "sourcePage": "/careers"},
        files={"cv": ("lina-cv.pdf", pdf, "application/pdf")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    reference = res.json()["reference"]
    drain()

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
        "sourcePage": "/giveaways"}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    drain()
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
        "productId": products[0]["id"], "sourcePage": "/giveaways",
        **base("giveaway_notification")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    drain()
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
        "sourcePage": "/rental", **base("rental_enquiry")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    drain()
    internal = by_recipient("mohammad.hossain@elitemarcom.com")
    customer = by_recipient("bakr@example.com")
    assert internal is not None and customer is not None
    assert "Bakr Holding" in internal["subject"]
    assert "day(s)" in internal["html"]
    assert "rental enquiry" in customer["html"].lower()


def test_rental_availability_is_its_own_notification_type():
    """The sixth type: separate from the gifts stock alert in every respect."""
    from server.main import load_rentals

    rental = load_rentals()[0]
    res = client.post("/api/rentals/notifications", json={
        "fullName": "Nadia Rahman", "company": "Skyline Events",
        "email": "nadia.customer@example.com", "phone": "+966554443322",
        "requiredFrom": "2026-11-02", "requiredUntil": "2026-11-08",
        "message": "We need this for the Riyadh Season activation.",
        "market": "ksa", "productId": rental["id"], "sourcePage": "/rental",
        **base("rental_notification")}, headers=ORIGIN)
    assert res.status_code == 200, res.text
    reference = res.json()["reference"]
    assert SENT == []
    drain()
    assert len(SENT) == 2

    internal = by_recipient("mohammad.hossain@elitemarcom.com")
    assert internal is not None
    assert internal["subject"].startswith("Rental availability alert")
    assert reference in internal["subject"]
    assert "Skyline Events" in internal["html"]
    assert "2026-11-02" in internal["html"] and "2026-11-08" in internal["html"]

    customer = by_recipient("nadia.customer@example.com")
    assert customer is not None
    assert customer["subject"] == "We will confirm availability for you — Elite Marcom"
    assert "Nadia Rahman" in customer["html"]
    assert "2026-11-02" in customer["html"]        # required_from variable resolved
    assert "2026-11-08" in customer["html"]        # required_until variable resolved
    assert rental["name"] in customer["html"]
    assert "{{" not in customer["html"]
    # it is NOT the gifts stock-notification template
    assert "notification list" not in customer["html"]
    assert "rental" in customer["html"].lower()

    # its log rows are tagged with the new form key
    entries = [e for e in mailer.log_entries(20) if e["reference"] == reference]
    assert entries and all(e["form"] == "rental_availability" for e in entries)
    assert {e["kind"] for e in entries} == {"internal", "customer"}


def test_rental_availability_settings_are_independent_of_stock_notification():
    mailer.save_form("rental_availability", {
        "recipient": "rentals-alerts@elitemarcom.com",
        "customerSubject": "Rental availability — Elite Marcom",
        "customerOn": True})
    assert mailer.form_settings("rental_availability")["recipient"] == "rentals-alerts@elitemarcom.com"
    # the gifts stock notification is untouched
    assert mailer.form_settings("stock_notification")["recipient"] == "mohammad.hossain@elitemarcom.com"
    assert mailer.form_settings("stock_notification")["customerSubject"] == \
        "We will let you know when it is available — Elite Marcom"
    # variables are scoped per form
    with pytest.raises(mailer.MailError):
        mailer.save_form("stock_notification", {"body": "From {{required_from}}"})
    with pytest.raises(mailer.MailError):
        mailer.save_form("rental_availability", {"body": "Qty {{quantity}}"})

    # a fresh rental alert honours the new routing
    from server.main import load_rentals

    res = client.post("/api/rentals/notifications", json={
        "fullName": "Route Check", "company": "Route Co", "email": "route.rental@example.com",
        "phone": "+966554443322", "requiredFrom": "2026-12-01", "requiredUntil": "2026-12-05",
        "message": "Routing check for the rental availability alert.",
        "market": "ksa", "productId": load_rentals()[0]["id"], "sourcePage": "/rental",
        **base("rental_notification")}, headers=ORIGIN)
    assert res.status_code == 200
    drain()
    assert by_recipient("rentals-alerts@elitemarcom.com") is not None
    assert by_recipient("mohammad.hossain@elitemarcom.com") is None
    mailer.save_form("rental_availability", {"recipient": "mohammad.hossain@elitemarcom.com"})


# ---------------- admin-controlled behaviour ----------------

def test_routing_change_affects_the_next_submission():
    mailer.save_form("general_inquiry", {"recipient": "newteam@elitemarcom.com"})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Routing Test", "company": "",
        "email": "routing@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Testing the routing change end to end.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    drain()
    assert by_recipient("newteam@elitemarcom.com") is not None
    assert by_recipient("info@elitemarcom.com") is None
    mailer.save_form("general_inquiry", {"recipient": "info@elitemarcom.com"})


def test_on_off_switches_are_respected():
    mailer.save_form("general_inquiry", {"internalOn": False, "customerOn": True})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Switch Test", "company": "",
        "email": "switch@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Only the customer should hear back here.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    drain()
    assert by_recipient("info@elitemarcom.com") is None
    assert by_recipient("switch@example.com") is not None

    SENT.clear()
    mailer.save_form("general_inquiry", {"internalOn": True, "customerOn": False})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Switch Test 2", "company": "",
        "email": "switch2@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "Only the team should hear about this one.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    drain()
    assert by_recipient("info@elitemarcom.com") is not None
    assert by_recipient("switch2@example.com") is None
    mailer.save_form("general_inquiry", {"internalOn": True, "customerOn": True})


def test_template_edits_reach_the_customer_email():
    mailer.save_form("general_inquiry", {
        "customerSubject": "Hello {{customer_name}} — Elite Marcom",
        "heading": "Thanks, {{customer_name}}",
        "body": "We received your note about {{service}}. Reference {{reference_number}}.",
        "closing": "Talk soon.", "buttonText": "Our services",
        "buttonUrl": "https://www.elitemarcom.com/services"})
    client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Template Tester", "company": "",
        "email": "template@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Corporate Events", "message": "Checking the custom template rendering.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    drain()
    customer = by_recipient("template@example.com")
    assert customer["subject"] == "Hello Template Tester — Elite Marcom"
    assert "Thanks, Template Tester" in customer["html"]
    assert "Corporate Events" in customer["html"]
    assert "https://www.elitemarcom.com/services" in customer["html"]
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
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    drain()
    customer = by_recipient("bobby@example.com")
    assert "<script>" not in customer["html"]
    assert "&lt;script&gt;" in customer["html"]


# ---------------- reliability & safety ----------------

def test_failed_send_is_retried_then_recovered_without_duplicates():
    FAIL_NEXT[0] = True
    res = client.post("/api/contact/enquiries", json={
        "enquiryType": "General enquiry", "fullName": "Fail Case", "company": "",
        "email": "fail@example.com", "phone": "+966500000000", "market": "Worldwide",
        "service": "Branding", "message": "The provider will reject this one.",
        "sourcePage": "/contact", **base("contact")}, headers=ORIGIN)
    assert res.status_code == 200          # the visitor's request is still safely stored
    reference = res.json()["reference"]

    drain()                                 # first attempt fails
    entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
    assert entries and all(e["status"] == "pending" for e in entries)   # queued for retry
    assert all(e["attempts"] == 1 for e in entries)
    assert all("stub" not in e["detail"] for e in entries)   # provider text never stored

    # the provider recovers; the queued jobs go out, exactly once each
    FAIL_NEXT[0] = False
    SENT.clear()                                            # count only what happens next
    mailer.retry_failed(reference=reference)                # make them due immediately
    with mailer._log_lock:
        mailer._log_conn().execute(
            "UPDATE sends SET next_attempt_at=0 WHERE reference=?", (reference,))
        mailer._log_conn().commit()
    drain()
    entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
    assert all(e["status"] == "sent" for e in entries)
    assert len([s for s in SENT if "fail@example.com" in s["payload"]["to"]]) == 1

    drain()                                  # a further pass must not resend
    assert len([s for s in SENT if "fail@example.com" in s["payload"]["to"]]) == 1


def test_delivery_survives_a_restart():
    """A process killed mid-send leaves the job recoverable, not lost."""
    payload = {"fullName": "Crash Case", "company": "", "email": "crash@example.com",
               "phone": "+966500000000", "message": "queued before the crash"}
    reference = storage.save_record("contact", payload, "iphash", 180)
    assert mailer.enqueue("contact", reference) == 2
    # simulate: worker claimed the jobs, then the process died
    mailer._claim_due(10)
    assert SENT == []
    assert mailer.recover_stuck(0) == 2       # startup recovery re-queues them
    drain()
    assert by_recipient("crash@example.com") is not None
    entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
    assert all(e["status"] == "sent" for e in entries)


def test_duplicate_submission_cannot_queue_or_send_twice():
    payload = {"fullName": "Repeat Sender", "company": "", "email": "repeat@example.com",
               "phone": "+966500000000", "message": "duplicate check"}
    reference = storage.save_record("contact", payload, "iphash", 180)
    assert mailer.enqueue("contact", reference) == 2
    assert mailer.enqueue("contact", reference) == 0     # double click / retried request
    drain()
    assert len(SENT) == 2
    drain()
    assert len(SENT) == 2


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
        mailer.enqueue("contact", reference)
        assert mailer.process_outbox() == {"sent": 0, "failed": 0, "pending": 0}
        assert SENT == []
    finally:
        config.RESEND_API_KEY = original


# ---------------- queue health (admin KPI cards) ----------------

def _reset_log() -> None:
    """Start from an empty log so the KPI counts can be asserted exactly."""
    with mailer._log_lock:
        mailer._log_conn().execute("DELETE FROM sends")
        mailer._log_conn().commit()


def _due_now() -> None:
    with mailer._log_lock:
        mailer._log_conn().execute("UPDATE sends SET next_attempt_at=0 WHERE status='pending'")
        mailer._log_conn().commit()


def _queue(name: str, address: str) -> str:
    reference = storage.save_record(
        "contact", {"fullName": name, "company": "", "email": address,
                    "phone": "+966500000000", "message": "queue health"}, "iphash", 180)
    assert mailer.enqueue("contact", reference) == 2
    return reference


def test_queue_health_counts_every_status():
    """The Email screen's KPI cards read straight off log_stats()."""
    _reset_log()
    assert mailer.log_stats() == {"pending": 0, "sending": 0, "sent": 0, "failed": 0, "total": 0}

    reference = _queue("Health Check", "health@example.com")
    assert mailer.log_stats() == {"pending": 2, "sending": 0, "sent": 0, "failed": 0, "total": 2}

    mailer._claim_due(10)                                   # in flight
    assert mailer.log_stats()["sending"] == 2
    mailer.recover_stuck(0)
    _due_now()

    drain()
    assert mailer.log_stats() == {"pending": 0, "sending": 0, "sent": 2, "failed": 0, "total": 2}
    entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
    assert len(entries) == 2 and all(e["status"] == "sent" for e in entries)


def test_exhausted_jobs_show_as_failed_and_retry_clears_the_warning():
    _reset_log()
    FAIL_NEXT[0] = True
    reference = _queue("Attention Case", "attention@example.com")

    for _ in range(mailer.MAX_ATTEMPTS):
        _due_now()
        drain()

    stats = mailer.log_stats()
    assert stats == {"pending": 0, "sending": 0, "sent": 0, "failed": 2, "total": 2}
    entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
    assert all(e["attempts"] == mailer.MAX_ATTEMPTS for e in entries)
    assert all("stub" not in e["detail"] and "re_" not in e["detail"] for e in entries)

    FAIL_NEXT[0] = False
    SENT.clear()
    assert mailer.retry_failed(reference=reference) == 2          # per-row Retry
    assert mailer.log_stats()["failed"] == 0                      # warning clears
    assert mailer.log_stats()["pending"] == 2
    drain()
    assert mailer.log_stats() == {"pending": 0, "sending": 0, "sent": 2, "failed": 0, "total": 2}
    assert len([s for s in SENT if "attention@example.com" in s["payload"]["to"]]) == 1
    drain()
    assert len([s for s in SENT if "attention@example.com" in s["payload"]["to"]]) == 1


def test_retry_all_failed_requeues_every_failure():
    _reset_log()
    FAIL_NEXT[0] = True
    references = [_queue("Bulk One", "bulk1@example.com"), _queue("Bulk Two", "bulk2@example.com")]
    for _ in range(mailer.MAX_ATTEMPTS):
        _due_now()
        drain()
    assert mailer.log_stats() == {"pending": 0, "sending": 0, "sent": 0, "failed": 4, "total": 4}

    FAIL_NEXT[0] = False
    SENT.clear()
    assert mailer.retry_failed() == 4                             # "Retry all failed"
    drain()
    assert mailer.log_stats() == {"pending": 0, "sending": 0, "sent": 4, "failed": 0, "total": 4}
    for reference in references:
        entries = [e for e in mailer.log_entries(30) if e["reference"] == reference]
        assert len(entries) == 2 and all(e["status"] == "sent" for e in entries)
    assert len([s for s in SENT if "bulk1@example.com" in s["payload"]["to"]]) == 1
    assert len([s for s in SENT if "bulk2@example.com" in s["payload"]["to"]]) == 1


# ---------------- staff alerts ----------------

def test_staff_alerts_go_through_the_durable_outbox():
    """The alert recipients setting was inert unless legacy SMTP happened to be
    configured — with the mail service in use it sent nothing at all."""
    from server import adminauth as aa, notify

    aa.setting_set("notify.emails", ["ops@elitemarcom.com", "sales@elitemarcom.com"])
    assert mailer.team_recipients() == ["ops@elitemarcom.com", "sales@elitemarcom.com"]

    reference = storage.save_record("contact", {"fullName": "Alerted", "email": "a@example.com"},
                                    "iphash", 30)
    notify.notify_new_request("contact", reference)
    queued = [e for e in mailer.log_entries(80)
              if e["reference"] == reference and e["kind"] == "team"]
    assert len(queued) == 1                       # one broadcast, not one per address
    assert queued[0]["status"] == "pending"       # persisted before anything is sent

    notify.notify_new_request("contact", reference)
    assert len([e for e in mailer.log_entries(80)
                if e["reference"] == reference and e["kind"] == "team"]) == 1

    drain()
    sent = [s for s in SENT if "ops@elitemarcom.com" in s["payload"]["to"]]
    assert len(sent) == 1
    payload = sent[0]["payload"]
    assert payload["to"] == ["ops@elitemarcom.com", "sales@elitemarcom.com"]
    assert reference in payload["subject"]
    # the alert names the request and nothing about the person who sent it
    for personal in ("Alerted", "a@example.com"):
        assert personal not in payload["html"]
    aa.setting_set("notify.emails", [])


def test_no_alert_recipients_means_no_alert():
    from server import adminauth as aa, notify

    aa.setting_set("notify.emails", [])
    reference = storage.save_record("contact", {"fullName": "Quiet", "email": "q@example.com"},
                                    "iphash", 30)
    notify.notify_new_request("contact", reference)
    assert not [e for e in mailer.log_entries(80)
                if e["reference"] == reference and e["kind"] == "team"]
