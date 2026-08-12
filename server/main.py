"""Elite Marcom website backend — public API + static site.

FastAPI application. Serves the strict public/ webroot and the
website-only API. No admin panel, no CMS, no user accounts.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config, jasani, mailer, notify, security, storage

config.validate_startup()

app = FastAPI(
    title="Elite Marcom Website API",
    docs_url=None if config.IS_PROD else "/api/_docs",
    redoc_url=None,
    openapi_url=None if config.IS_PROD else "/api/_openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,  # explicit allowlist, never wildcard
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

MAX_BODY_BYTES = 8 * 1024 * 1024  # generous cap; CV endpoint enforces 5 MB on the file itself


# ---------------- security headers ----------------

_SUPPLIER_IMG = "https://*.giftsksa.com https://giftsksa.com https://*.jasani.ae https://jasani.ae"
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'wasm-unsafe-eval' https://www.youtube.com https://challenges.cloudflare.com "
    "https://www.googletagmanager.com; "
    "style-src 'self' 'unsafe-inline'; "
    f"img-src 'self' data: blob: https://i.ytimg.com https://www.google-analytics.com "
    f"https://www.googletagmanager.com {_SUPPLIER_IMG}; "
    "font-src 'self'; "
    "connect-src 'self' blob: https://challenges.cloudflare.com "
    "https://www.google-analytics.com https://*.google-analytics.com https://www.googletagmanager.com; "
    "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com https://challenges.cloudflare.com; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "worker-src 'self' blob:"
)

# the visual-editor preview is the ONE page allowed inside a same-origin
# iframe (the admin shell); it still requires an authenticated admin session
CSP_FRAMEABLE = CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request too large."}, status_code=413)
    response = await call_next(request)
    frameable = request.url.path.startswith("/admin/visual/")
    response.headers["Content-Security-Policy"] = CSP_FRAMEABLE if frameable else CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if frameable else "DENY"
    if config.IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if "server" in response.headers:
        del response.headers["server"]
    return response


# ---------------- validation helpers ----------------

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
_PHONE_RE = re.compile(r"^[0-9+().\- ]{7,32}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_text(value: str, max_len: int, min_len: int = 0, field: str = "field") -> str:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    if _CONTROL_RE.search(value):
        raise HTTPException(status_code=400, detail="Invalid characters in submission.")
    if len(value) < min_len or len(value) > max_len:
        raise HTTPException(status_code=400, detail=f"Please check the {field} length.")
    return value


def clean_multiline(value: str, max_len: int, min_len: int = 0, field: str = "field") -> str:
    value = (value or "").replace("\r\n", "\n").strip()
    if _CONTROL_RE.search(value.replace("\n", "").replace("\t", " ")):
        raise HTTPException(status_code=400, detail="Invalid characters in submission.")
    if len(value) < min_len or len(value) > max_len:
        raise HTTPException(status_code=400, detail=f"Please check the {field} length.")
    return value


def clean_email(value: str) -> str:
    value = clean_text(value, 200, 5, "email").lower()
    if not _EMAIL_RE.match(value):
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")
    return value


def clean_phone(value: str) -> str:
    value = clean_text(value, 32, 7, "phone")
    if not _PHONE_RE.match(value):
        raise HTTPException(status_code=400, detail="Please provide a valid phone number.")
    return value


def clean_date(value: str | None, field: str = "date") -> str | None:
    if not value:
        return None
    if not _DATE_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Please provide a valid {field}.")
    return value


def clean_https_url(value: str) -> str:
    value = clean_text(value, 300, 12, "URL")
    if not value.startswith("https://") or " " in value:
        raise HTTPException(status_code=400, detail="Portfolio / LinkedIn URL must start with https://")
    return value


def check_consent(consent: bool, version: str) -> str:
    if not consent:
        raise HTTPException(status_code=400, detail="Privacy consent is required.")
    version = clean_text(version or "", 20, 4, "consent version")
    if version != config.CONSENT_VERSION:
        raise HTTPException(status_code=400, detail="Please reload the page and try again.")
    return version


def check_source_page(value: str | None) -> str:
    value = clean_text(value or "", 100, 1, "source")
    if not re.match(r"^/[A-Za-z0-9./_-]{0,90}$", value):
        raise HTTPException(status_code=400, detail="Invalid submission source.")
    return value


async def guard_submission(request: Request, form_key: str, challenge: str,
                           honeypot: str | None, turnstile_token: str | None,
                           limit: int = 5, window_s: int = 3600) -> str:
    """Shared protections for every state-changing endpoint. Returns ip_hash."""
    security.check_origin(request)
    ip = security.client_ip(request)
    ip_hash = security.hash_ip(ip)
    security.limiter.check(form_key, ip_hash, limit, window_s)
    security.check_honeypot(honeypot)
    security.consume_challenge(challenge, form_key, ip_hash)
    await security.verify_turnstile(turnstile_token, ip)
    return ip_hash


# ---------------- basic endpoints ----------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/security/config")
async def security_config():
    return {
        "consentVersion": config.CONSENT_VERSION,
        "turnstileSiteKey": config.TURNSTILE_SITE_KEY or None,
    }


@app.get("/api/security/challenge")
async def security_challenge(request: Request, form: str = Query(...)):
    ip_hash = security.hash_ip(security.client_ip(request))
    security.limiter.check("challenge", ip_hash, 60, 600)
    return {"challenge": security.issue_challenge(form, ip_hash)}


# ---------------- careers ----------------

_JOBS_FILE = Path(__file__).parent / "data" / "jobs.json"


def load_jobs() -> list[dict]:
    try:
        data = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    jobs = [j for j in data.get("jobs", []) if j.get("published") and j.get("open")]
    jobs.sort(key=lambda j: j.get("sortOrder", 999))
    return jobs


@app.get("/api/careers/jobs")
async def careers_jobs():
    jobs = load_jobs()
    public = [{k: j[k] for k in
               ("id", "title", "department", "track", "location", "employmentType",
                "summary", "requirements", "poster")} for j in jobs]
    return JSONResponse({"jobs": public}, headers={"Cache-Control": "no-store"})


_PDF_MAX = 5 * 1024 * 1024


def validate_pdf(data: bytes) -> None:
    if len(data) > _PDF_MAX:
        raise HTTPException(status_code=400, detail="The CV must be 5 MB or smaller.")
    if len(data) < 100 or not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The CV must be a valid PDF file.")
    if b"%%EOF" not in data[-2048:]:
        raise HTTPException(status_code=400, detail="The CV must be a valid PDF file.")
    if b"/Encrypt" in data:
        raise HTTPException(status_code=400, detail="Encrypted PDFs are not accepted — please export an unencrypted CV.")
    pages = data.count(b"/Type /Page") + data.count(b"/Type/Page")
    pages -= data.count(b"/Type /Pages") + data.count(b"/Type/Pages")
    if pages < 1:
        counts = re.findall(rb"/Count\s+(\d+)", data)
        pages = max((int(c) for c in counts), default=0)
    if pages < 1 or pages > 100:
        raise HTTPException(status_code=400, detail="The CV must contain between 1 and 100 pages.")


def scan_malware(data: bytes) -> None:
    """Mandatory in production; fail closed if the scanner is unavailable."""
    import socket

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(15)
            sock.connect(config.CLAMD_SOCKET)
            sock.sendall(b"zINSTREAM\0")
            sock.sendall(len(data).to_bytes(4, "big") + data)
            sock.sendall((0).to_bytes(4, "big"))
            verdict = sock.recv(512).decode(errors="replace")
        if "OK" not in verdict:
            raise HTTPException(status_code=400, detail="The uploaded file could not be accepted.")
    except HTTPException:
        raise
    except Exception:
        if config.MALWARE_SCAN_REQUIRED:
            raise HTTPException(status_code=503, detail="File scanning is temporarily unavailable — please try again later.")
        # development: scanning optional


@app.post("/api/careers/applications")
async def careers_apply(
    request: Request,
    fullName: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()],
    location: Annotated[str, Form()],
    roleId: Annotated[str, Form()],
    portfolioUrl: Annotated[str, Form()],
    introduction: Annotated[str, Form()],
    consent: Annotated[str, Form()],
    challenge: Annotated[str, Form()],
    consentVersion: Annotated[str, Form()],
    sourcePage: Annotated[str, Form()] = "/careers.html",
    website: Annotated[str, Form()] = "",
    turnstileToken: Annotated[str | None, Form()] = None,
    cv: Annotated[UploadFile | None, File()] = None,
):
    ip_hash = await guard_submission(request, "career", challenge, website, turnstileToken, limit=5)
    jobs = {j["id"]: j for j in load_jobs()}
    role_id = clean_text(roleId, 60, 1, "role")
    if role_id != "general" and role_id not in jobs:
        raise HTTPException(status_code=400, detail="Please choose a valid role.")
    payload = {
        "fullName": clean_text(fullName, 120, 2, "name"),
        "email": clean_email(email),
        "phone": clean_phone(phone),
        "location": clean_text(location, 120, 2, "location"),
        "roleId": role_id,
        "roleTitle": jobs[role_id]["title"] if role_id in jobs else "General application",
        "portfolioUrl": clean_https_url(portfolioUrl),
        "introduction": clean_multiline(introduction, 3000, 10, "introduction"),
        "consentVersion": check_consent(consent == "yes", consentVersion),
        "sourcePage": check_source_page(sourcePage),
    }
    cv_bytes = None
    if cv is not None and cv.filename:
        cv_bytes = await cv.read()
        validate_pdf(cv_bytes)
        scan_malware(cv_bytes)
    reference = storage.save_record("career", payload, ip_hash,
                                    config.RETENTION_CAREERS_DAYS, cv_bytes=cv_bytes)
    notify.notify_new_request("career", reference)
    mailer.enqueue("career", reference)
    track_server_event(request, "enquiry", meta="career application")
    return {"reference": reference}


# ---------------- contact ----------------

class ContactEnquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enquiryType: Literal["New project", "General enquiry", "Partnership", "Supplier"]
    fullName: str
    company: str = ""
    email: str
    phone: str
    market: Literal["Saudi Arabia", "United Arab Emirates", "Worldwide"]
    service: str
    projectDate: str | None = None
    projectCity: str = ""
    message: str
    consent: bool
    challenge: str
    consentVersion: str
    website: str = ""
    sourcePage: str = "/contact.html"
    turnstileToken: str | None = None


ALLOWED_SERVICES = {
    "Exhibition Stands", "Fit-Out / Interior", "Corporate Events", "Outdoor Activities",
    "Branding", "Corporate Gifts", "Event Equipment Rental", "Photo and Videography",
    "Staffing", "Digital Marketing", "Multiple Services / Full Project",
}


@app.post("/api/contact/enquiries")
async def contact_enquiry(request: Request, body: ContactEnquiry):
    ip_hash = await guard_submission(request, "contact", body.challenge, body.website,
                                     body.turnstileToken, limit=6)
    if body.service not in ALLOWED_SERVICES:
        raise HTTPException(status_code=400, detail="Please choose a valid service.")
    payload = {
        "enquiryType": body.enquiryType,
        "fullName": clean_text(body.fullName, 120, 2, "name"),
        "company": clean_text(body.company, 160, 0, "company"),
        "email": clean_email(body.email),
        "phone": clean_phone(body.phone),
        "market": body.market,
        "service": body.service,
        "projectDate": clean_date(body.projectDate, "project date"),
        "projectCity": clean_text(body.projectCity, 160, 0, "city"),
        "message": clean_multiline(body.message, 3000, 10, "message"),
        "consentVersion": check_consent(body.consent, body.consentVersion),
        "sourcePage": check_source_page(body.sourcePage),
    }
    reference = storage.save_record("contact", payload, ip_hash, config.RETENTION_SUBMISSIONS_DAYS)
    notify.notify_new_request("contact", reference)
    mailer.enqueue("contact", reference)
    track_server_event(request, "enquiry", meta="contact")
    return {"reference": reference}


# ---------------- rentals ----------------

def load_rentals() -> list[dict]:
    # admin-managed runtime inventory wins over the shipped default
    from . import content

    return content.rentals_load()[0]


@app.get("/api/rentals/products")
async def rentals_products():
    return JSONResponse({"products": load_rentals()}, headers={"Cache-Control": "no-store"})


class BrandingPreference(BaseModel):
    """Customer's requested printing area/method — a preference only, always
    subject to Elite Marcom technical review."""
    model_config = ConfigDict(extra="forbid")
    area: str = Field(default="", max_length=120)
    method: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=500)


class RequestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    productId: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=100000)
    branding: BrandingPreference | None = None


class RentalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    productId: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=1000)
    days: int = Field(default=1, ge=1, le=365)


class RentalEnquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fullName: str
    company: str
    email: str
    phone: str
    startDate: str
    endDate: str
    eventCity: str
    venue: str
    notes: str = ""
    consent: bool
    market: Literal["ksa", "uae"]
    items: list[RentalItem] = Field(min_length=1, max_length=50)
    challenge: str
    consentVersion: str
    website: str = ""
    sourcePage: str = "/rental.html"
    turnstileToken: str | None = None

    @field_validator("items")
    @classmethod
    def no_duplicates(cls, v):
        ids = [i.productId for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate items")
        return v


def canonical_rental_items(items: list[RentalItem], market: str) -> list[dict]:
    """Re-derive item facts from canonical server data; reject forged posts."""
    inventory = {p["id"]: p for p in load_rentals()}
    out = []
    for item in items:
        p = inventory.get(item.productId)
        if not p:
            raise HTTPException(status_code=400, detail="Your list contains an item that is no longer available — please review it.")
        stock = int(p.get("stockByMarket", {}).get(market, 0))
        if stock <= 0:
            raise HTTPException(status_code=400, detail=f"“{p['name']}” is not currently available in this market.")
        if item.quantity > stock:
            raise HTTPException(status_code=400, detail=f"Only {stock} unit(s) of “{p['name']}” are available — please adjust the quantity.")
        out.append({"productId": p["id"], "code": p["code"], "name": p["name"],
                    "market": market, "quantity": item.quantity, "days": item.days,
                    "stockAtSubmission": stock})
    return out


@app.post("/api/rentals/enquiries")
async def rentals_enquiry(request: Request, body: RentalEnquiry):
    ip_hash = await guard_submission(request, "rental_enquiry", body.challenge, body.website,
                                     body.turnstileToken, limit=5)
    start = clean_date(body.startDate, "start date")
    end = clean_date(body.endDate, "end date")
    if not start or not end:
        raise HTTPException(status_code=400, detail="Rental start and end dates are required.")
    if end < start:
        raise HTTPException(status_code=400, detail="The rental end date cannot be before the start date.")
    payload = {
        "fullName": clean_text(body.fullName, 120, 2, "name"),
        "company": clean_text(body.company, 160, 1, "company"),
        "email": clean_email(body.email),
        "phone": clean_phone(body.phone),
        "startDate": start,
        "endDate": end,
        "eventCity": clean_text(body.eventCity, 120, 1, "city"),
        "venue": clean_text(body.venue, 160, 1, "venue"),
        "notes": clean_multiline(body.notes, 3000, 0, "notes"),
        "market": body.market,
        "items": canonical_rental_items(body.items, body.market),
        "consentVersion": check_consent(body.consent, body.consentVersion),
        "sourcePage": check_source_page(body.sourcePage),
    }
    reference = storage.save_record("rental_enquiry", payload, ip_hash, config.RETENTION_SUBMISSIONS_DAYS)
    notify.notify_new_request("rental_enquiry", reference)
    mailer.enqueue("rental_enquiry", reference)
    track_server_event(request, "enquiry", meta="rental")
    return {"reference": reference}


class RentalNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fullName: str
    company: str
    email: str
    phone: str
    requiredFrom: str | None = None
    requiredUntil: str | None = None
    message: str
    consent: bool
    market: Literal["ksa", "uae"]
    productId: str = Field(min_length=1, max_length=80)
    challenge: str
    consentVersion: str
    website: str = ""
    sourcePage: str = "/rental.html"
    turnstileToken: str | None = None


@app.post("/api/rentals/notifications")
async def rentals_notification(request: Request, body: RentalNotification):
    ip_hash = await guard_submission(request, "rental_notification", body.challenge, body.website,
                                     body.turnstileToken, limit=8)
    inventory = {p["id"]: p for p in load_rentals()}
    product = inventory.get(body.productId)
    if not product:
        raise HTTPException(status_code=400, detail="This item is no longer in the catalog.")
    frm = clean_date(body.requiredFrom, "start date")
    until = clean_date(body.requiredUntil, "end date")
    if frm and until and until < frm:
        raise HTTPException(status_code=400, detail="The end date cannot be before the start date.")
    payload = {
        "fullName": clean_text(body.fullName, 120, 2, "name"),
        "company": clean_text(body.company, 160, 1, "company"),
        "email": clean_email(body.email),
        "phone": clean_phone(body.phone),
        "requiredFrom": frm,
        "requiredUntil": until,
        "message": clean_multiline(body.message, 3000, 10, "message"),
        "market": body.market,
        "productId": product["id"],
        "productName": product["name"],
        "productCode": product["code"],
        "consentVersion": check_consent(body.consent, body.consentVersion),
        "sourcePage": check_source_page(body.sourcePage),
    }
    reference = storage.save_record("rental_notification", payload, ip_hash, config.RETENTION_SUBMISSIONS_DAYS)
    mailer.enqueue("rental_notification", reference)
    return {"reference": reference}


# ---------------- giveaways ----------------

_PREVIEW_FILE = config.PUBLIC_DIR / "data" / "giveaway-preview-products.json"


def load_preview_products(market: str) -> list[dict]:
    try:
        data = json.loads(_PREVIEW_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data.get("products", []) if p.get("market") == market]


async def giveaway_catalog_or_503(market: str) -> tuple[list[dict], str]:
    try:
        return await jasani.get_catalog(market)
    except jasani.SupplierUnavailable:
        raise HTTPException(status_code=503, detail="Catalog temporarily unavailable.")


def catalog_read_guard(request: Request, bucket: str) -> None:
    ip_hash = security.hash_ip(security.client_ip(request))
    security.limiter.check(bucket, ip_hash, 240, 3600)


@app.get("/api/giveaways/products")
async def giveaways_products(request: Request, country: Literal["ksa", "uae"] = Query(...)):
    catalog_read_guard(request, "giveaways_read")
    products, state = await giveaway_catalog_or_503(country)
    return JSONResponse({"state": state, "count": len(products), "products": products},
                        headers={"Cache-Control": "no-store"})


@app.get("/api/giveaways/stock")
async def giveaways_stock(request: Request, country: Literal["ksa", "uae"] = Query(...)):
    catalog_read_guard(request, "giveaways_read")
    products, state = await giveaway_catalog_or_503(country)
    stock = [{"id": p["id"], "stock": p["stock"]} for p in products]
    return JSONResponse({"state": state, "stock": stock}, headers={"Cache-Control": "no-store"})


@app.get("/api/giveaways/branding")
async def giveaways_branding(request: Request, country: Literal["ksa", "uae"] = Query(...),
                             product_id: str = Query(..., min_length=1, max_length=80)):
    catalog_read_guard(request, "giveaways_branding")
    try:
        branding = await jasani.get_branding(country, product_id)
    except jasani.SupplierUnavailable:
        # also allow preview-known products a graceful empty answer
        preview_ids = {p["id"] for p in load_preview_products(country)}
        if product_id in preview_ids:
            return {"branding": []}
        raise HTTPException(status_code=503, detail="Branding details temporarily unavailable.")
    return {"branding": branding}


# ---------------- printing manuals (server-side proxy) ----------------
# Customers download the supplier's printing-manual PDF from an Elite Marcom
# URL only — never a Jasani link. Candidates are validated and cached in
# server/jasani.py before anything is served.

def _manual_filename(code: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", code).strip("-") or "product"
    return f"{safe[:60]}-printing-manual.pdf"


@app.get("/api/giveaways/manual/status")
async def giveaways_manual_status(request: Request, country: Literal["ksa", "uae"] = Query(...),
                                  product_id: str = Query(..., min_length=1, max_length=80)):
    """Cheap availability probe so the UI only shows a working download button."""
    catalog_read_guard(request, "giveaways_manual")
    try:
        await jasani.get_manual(country, product_id)
        return {"available": True}
    except jasani.SupplierUnavailable:
        return {"available": False}


@app.get("/api/giveaways/manual")
async def giveaways_manual(request: Request, country: Literal["ksa", "uae"] = Query(...),
                           product_id: str = Query(..., min_length=1, max_length=80)):
    catalog_read_guard(request, "giveaways_manual")
    try:
        data, code = await jasani.get_manual(country, product_id)
    except jasani.SupplierUnavailable:
        raise HTTPException(status_code=404,
                            detail="The printing manual is not available for this product — contact us for branding assistance.")
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{_manual_filename(code)}"',
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    })


async def canonical_giveaway_items(items: list[RequestItem], market: str) -> list[dict]:
    """Validate against the canonical server-side catalog (live/cache, else preview)."""
    try:
        products, _state = await jasani.get_catalog(market)
    except jasani.SupplierUnavailable:
        products = load_preview_products(market)
    if not products:
        raise HTTPException(status_code=503, detail="Catalog temporarily unavailable — please try again shortly.")
    by_id = {p["id"]: p for p in products}
    out = []
    for item in items:
        p = by_id.get(item.productId)
        if not p:
            raise HTTPException(status_code=400, detail="Your request contains a product that is no longer in the catalog — please review it.")
        available = int(p.get("stock", {}).get("available", 0))
        if available <= 0:
            raise HTTPException(status_code=400, detail=f"“{p['name']}” is currently unavailable — please remove it or ask for a notification.")
        if item.quantity > available:
            raise HTTPException(status_code=400, detail=f"Only {available} unit(s) of “{p['name']}” are available — please adjust the quantity.")
        entry = {"productId": p["id"], "code": p["code"], "name": p["name"],
                 "market": market, "quantity": item.quantity, "stockAtSubmission": available}
        if item.branding and (item.branding.area or item.branding.method or item.branding.note):
            entry["brandingPreference"] = {
                "area": clean_text(item.branding.area, 120, 0, "branding area") if item.branding.area else "",
                "method": clean_text(item.branding.method, 120, 0, "branding method") if item.branding.method else "",
                "note": clean_multiline(item.branding.note, 500, 0, "branding note") if item.branding.note else "",
                "status": "pending_technical_review",
            }
        out.append(entry)
    return out


_LOGO_TYPES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"%PDF-", "pdf"),
)


def validate_logo(data: bytes) -> str:
    """Optional brand logo: PNG/JPG/WEBP/PDF, 5 MB cap. Returns the extension."""
    if len(data) > _PDF_MAX:
        raise HTTPException(status_code=400, detail="The logo must be 5 MB or smaller.")
    if len(data) < 24:
        raise HTTPException(status_code=400, detail="The logo file looks empty — please re-attach it.")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    for magic, ext in _LOGO_TYPES:
        if data.startswith(magic):
            return ext
    raise HTTPException(status_code=400, detail="The logo must be a PNG, JPG, WEBP or PDF file.")


@app.post("/api/giveaways/enquiries")
async def giveaways_enquiry(
    request: Request,
    fullName: Annotated[str, Form()],
    company: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()],
    deliveryCity: Annotated[str, Form()],
    shippingAddress: Annotated[str, Form()],
    market: Annotated[str, Form()],
    items: Annotated[str, Form()],  # JSON: [{"productId": ..., "quantity": ...}]
    consent: Annotated[str, Form()],
    challenge: Annotated[str, Form()],
    consentVersion: Annotated[str, Form()],
    requiredBy: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    sourcePage: Annotated[str, Form()] = "/giveaways.html",
    website: Annotated[str, Form()] = "",
    turnstileToken: Annotated[str | None, Form()] = None,
    logo: Annotated[UploadFile | None, File()] = None,
):
    ip_hash = await guard_submission(request, "giveaway_enquiry", challenge, website,
                                     turnstileToken, limit=5)
    if market not in ("ksa", "uae"):
        raise HTTPException(status_code=400, detail="Please choose a valid market.")
    try:
        raw_items = json.loads(items)
        if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 50:
            raise ValueError
        item_models = [RequestItem(**i) for i in raw_items]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400,
                            detail="Your request list could not be read — please rebuild it and try again.")
    if len({i.productId for i in item_models}) != len(item_models):
        raise HTTPException(status_code=400, detail="Your request contains duplicate products.")
    payload = {
        "fullName": clean_text(fullName, 120, 2, "name"),
        "company": clean_text(company, 160, 1, "company"),
        "email": clean_email(email),
        "phone": clean_phone(phone),
        "requiredBy": clean_date(requiredBy or None, "required-by date"),
        "deliveryCity": clean_text(deliveryCity, 120, 1, "city"),
        "shippingAddress": clean_multiline(shippingAddress, 600, 5, "shipping address"),
        "notes": clean_multiline(notes, 3000, 0, "notes"),
        "market": market,
        "items": await canonical_giveaway_items(item_models, market),
        "consentVersion": check_consent(consent in ("yes", "true", "on"), consentVersion),
        "sourcePage": check_source_page(sourcePage),
    }
    logo_bytes = None
    logo_ext = "pdf"
    if logo is not None and logo.filename:
        logo_bytes = await logo.read()
        logo_ext = validate_logo(logo_bytes)
        scan_malware(logo_bytes)
        payload["logoAttached"] = True
    reference = storage.save_record("giveaway_enquiry", payload, ip_hash,
                                    config.RETENTION_SUBMISSIONS_DAYS,
                                    cv_bytes=logo_bytes, file_ext=logo_ext)
    notify.notify_new_request("giveaway_enquiry", reference)
    mailer.enqueue("giveaway_enquiry", reference)
    track_server_event(request, "enquiry", meta="corporate gifts")
    return {"reference": reference}


class GiveawayNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fullName: str
    company: str
    email: str
    phone: str
    message: str = ""
    consent: bool
    market: Literal["ksa", "uae"]
    productId: str = Field(min_length=1, max_length=80)
    challenge: str
    consentVersion: str
    website: str = ""
    sourcePage: str = "/giveaways.html"
    turnstileToken: str | None = None


@app.post("/api/giveaways/notifications")
async def giveaways_notification(request: Request, body: GiveawayNotification):
    ip_hash = await guard_submission(request, "giveaway_notification", body.challenge, body.website,
                                     body.turnstileToken, limit=8)
    # re-resolve the product server-side
    try:
        products, _state = await jasani.get_catalog(body.market)
    except jasani.SupplierUnavailable:
        products = load_preview_products(body.market)
    product = next((p for p in products if p["id"] == body.productId), None)
    if not product:
        raise HTTPException(status_code=400, detail="This product is no longer in the catalog.")
    payload = {
        "fullName": clean_text(body.fullName, 120, 2, "name"),
        "company": clean_text(body.company, 160, 1, "company"),
        "email": clean_email(body.email),
        "phone": clean_phone(body.phone),
        "message": clean_multiline(body.message, 3000, 0, "message"),
        "market": body.market,
        "productId": product["id"],
        "productName": product["name"],
        "productCode": product["code"],
        "consentVersion": check_consent(body.consent, body.consentVersion),
        "sourcePage": check_source_page(body.sourcePage),
    }
    reference = storage.save_record("giveaway_notification", payload, ip_hash,
                                    config.RETENTION_SUBMISSIONS_DAYS)
    mailer.enqueue("giveaway_notification", reference)
    return {"reference": reference}


# ---------------- retention cleanup ----------------

@app.on_event("startup")
async def start_mail_worker():
    """Durable outbox worker. Emails are queued inside the request and sent
    here; anything left behind by a restart or crash is retried, so delivery
    never depends on a process surviving past the HTTP response."""
    from . import mailer

    try:
        recovered = mailer.recover_stuck(0)
        if recovered:
            print(f"[mail] recovered {recovered} interrupted delivery job(s)", flush=True)
    except Exception:
        pass

    async def loop():
        while True:
            try:
                await asyncio.to_thread(mailer.process_outbox, 10)
                await asyncio.to_thread(mailer.recover_stuck, 300)
            except Exception as exc:
                print(f"[mail] worker error: {exc.__class__.__name__}", flush=True)
            await asyncio.sleep(5)
    asyncio.get_event_loop().create_task(loop())


@app.on_event("startup")
async def start_schedule_task():
    async def loop():
        while True:
            try:
                from . import backup

                backup.run_due_publish()
            except Exception:
                pass
            await asyncio.sleep(60)
    asyncio.get_event_loop().create_task(loop())


@app.on_event("startup")
async def start_cleanup_task():
    async def loop():
        while True:
            try:
                storage.cleanup_expired()
            except Exception:
                pass
            try:
                from . import adminauth, analytics

                analytics.prune(int(adminauth.setting_get(
                    "analytics.retentionDays", analytics.RETENTION_DAYS_DEFAULT) or
                    analytics.RETENTION_DAYS_DEFAULT))
            except Exception:
                pass
            await asyncio.sleep(24 * 3600)
    asyncio.get_event_loop().create_task(loop())


# ---------------- site insights (first-party analytics) ----------------

class InsightEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=24)
    path: str = Field(default="", max_length=140)
    referrer: str = Field(default="", max_length=300)
    session: str = Field(default="", max_length=24)
    meta: str = Field(default="", max_length=120)
    metric: str = Field(default="", max_length=8)
    value: float | None = None


class InsightBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[InsightEvent] = Field(default_factory=list, max_length=20)


@app.get("/api/site/insights-config")
async def insights_config():
    """Public switch read by the beacon: is measuring on, and is GA4 configured?"""
    from . import adminauth, analytics

    try:
        enabled = adminauth.setting_get("analytics.enabled", True)
        ga4 = adminauth.setting_get("analytics.ga4Id", "") or ""
    except Exception:
        enabled, ga4 = True, ""
    return JSONResponse({"enabled": bool(enabled), "ga4Id": str(ga4)[:24],
                         "kinds": list(analytics.EVENT_KINDS)},
                        headers={"Cache-Control": "public, max-age=300"})


@app.post("/api/insights/collect")
async def insights_collect(request: Request, body: InsightBatch):
    """Cookieless beacon intake. Stores no raw IP and no user-agent string."""
    from . import adminauth, analytics

    ip = security.client_ip(request)
    ip_hash = security.hash_ip(ip)
    security.limiter.check("insights", ip_hash, 240, 60)
    try:
        if not adminauth.setting_get("analytics.enabled", True):
            return {"ok": True, "stored": 0}
    except Exception:
        pass
    user_agent = request.headers.get("user-agent", "")
    visitor = analytics.visitor_hash(ip, user_agent)
    device = analytics.device_class(user_agent)
    country = (request.headers.get("cf-ipcountry", "") or "")[:2]
    stored = 0
    for event in body.events[:analytics.MAX_BATCH]:
        if event.kind == "vital":
            if analytics.record_vital(event.metric, event.value or 0.0, event.path, device):
                stored += 1
            continue
        if analytics.record(event.kind, path=event.path, visitor=visitor,
                            session=event.session,
                            referrer=analytics.referrer_host(event.referrer),
                            country=country, device=device, meta=event.meta,
                            value=event.value):
            stored += 1
    return {"ok": True, "stored": stored}


def track_server_event(request: Request, kind: str, meta: str = "", path: str = "") -> None:
    """Server-side event (never blocked by ad blockers or JS-off browsers)."""
    from . import analytics

    try:
        user_agent = request.headers.get("user-agent", "")
        analytics.record(kind, path=path or str(request.url.path),
                         visitor=analytics.visitor_hash(security.client_ip(request), user_agent),
                         device=analytics.device_class(user_agent),
                         country=(request.headers.get("cf-ipcountry", "") or "")[:2],
                         meta=meta)
    except Exception:
        pass  # analytics must never break a customer submission


# ---------------- brand theme, media library & hero config (admin-managed) ----------------

@app.get("/theme-custom.css", include_in_schema=False)
async def theme_custom_css():
    from . import media

    return Response(content=media.theme_css(), media_type="text/css",
                    headers={"Cache-Control": "no-cache"})


@app.get("/media/{name}", include_in_schema=False)
async def media_file(name: str):
    from . import media

    path = media.media_file_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=604800, immutable"})


@app.get("/api/site/announcement")
async def site_announcement():
    """Site-wide notice with an optional schedule window (admin-managed)."""
    from . import adminauth

    try:
        enabled = bool(adminauth.setting_get("announce.enabled", False))
        text = str(adminauth.setting_get("announce.text", "") or "")
        starts = int(adminauth.setting_get("announce.startsAt", 0) or 0)
        ends = int(adminauth.setting_get("announce.endsAt", 0) or 0)
        link = str(adminauth.setting_get("announce.link", "") or "")
        label = str(adminauth.setting_get("announce.linkLabel", "") or "")
        style = str(adminauth.setting_get("announce.style", "brand") or "brand")
    except Exception:
        return JSONResponse({"show": False}, headers={"Cache-Control": "public, max-age=60"})
    now = time.time()
    show = bool(enabled and text and (not starts or now >= starts) and (not ends or now <= ends))
    return JSONResponse(
        {"show": show, "text": text if show else "", "link": link if show else "",
         "linkLabel": label, "style": style,
         "id": str(abs(hash((text, link))) % 10 ** 8) if show else ""},
        headers={"Cache-Control": "public, max-age=60"})


@app.get("/api/site/hero")
async def site_hero_config():
    """Public camera overrides for the 3D hero (set from the admin panel)."""
    from . import media

    return media.get_hero_config()


# ---------------- static site (strict public webroot) ----------------

_BLOCKED_PREFIXES = ("/.", "/server", "/runtime", "/tests")
_BLOCKED_NAMES = {".env", ".env.example", "requirements.txt", "install.sh", "start-local.sh"}


@app.middleware("http")
async def block_private_paths(request: Request, call_next):
    path = request.url.path
    lowered = path.lower()
    if any(lowered.startswith(p) for p in _BLOCKED_PREFIXES) or lowered.lstrip("/") in _BLOCKED_NAMES:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    if "/../" in path or path.endswith("/..") or "\\" in path:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return await call_next(request)


from . import admin_api  # noqa: E402  (registered before the catch-all static mount)

app.include_router(admin_api.router)
app.mount("/admin/assets", StaticFiles(directory=str(admin_api.ADMIN_UI / "assets")), name="admin-assets")


_OVERRIDE_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
                   ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".glb": "model/gltf-binary"}


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        from . import content, media

        published = content.published_file(path)
        if published is not None:
            ctype = "application/xml" if published.suffix == ".xml" else "text/html; charset=utf-8"
            return FileResponse(published, media_type=ctype,
                                headers={"Cache-Control": "no-cache"})
        override = media.override_for(path)
        if override is not None:
            ctype = _OVERRIDE_TYPES.get(override.suffix.lower(), "application/octet-stream")
            response: Response = FileResponse(override, media_type=ctype)
            # admin replacements must show up promptly on the public site
            response.headers["Cache-Control"] = "no-cache"
        else:
            response = await super().get_response(path, scope)
            if path.endswith((".js", ".css")) and "v=" not in path:
                response.headers.setdefault("Cache-Control", "public, max-age=86400")
            elif path.endswith((".webp", ".svg", ".png", ".jpg", ".glb")):
                # short-lived so admin replacements reach returning visitors
                # quickly; ETag revalidation keeps repeat loads cheap
                response.headers.setdefault(
                    "Cache-Control", "public, max-age=300, stale-while-revalidate=600")
        if path.endswith(".glb"):
            response.headers["Content-Type"] = "model/gltf-binary"
        return response


app.mount("/", CachedStaticFiles(directory=str(config.PUBLIC_DIR), html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("server.main:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    run()
