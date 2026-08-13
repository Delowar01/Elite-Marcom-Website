"""Elite Marcom — transactional email via Resend (admin-configurable).

The API key lives ONLY in the server environment (RESEND_API_KEY). It is
never written to the database, never returned by any endpoint and never
reaches the browser. Everything an admin can change — sender identity,
routing, on/off switches, subjects and customer templates — lives in the
admin settings store.

Every submission sends at most two emails: an internal notification with the
submitted details, and a branded confirmation to the customer. Both are
recorded in an email log with their real outcome, so a failure is never
reported as a success.
"""
from __future__ import annotations

import base64
import html as html_mod
import json
import re
import sqlite3
import threading
import time

import httpx

from . import config

SEND_TIMEOUT_S = 15.0
MAX_ATTACHMENT_BYTES = 6 * 1024 * 1024

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
_VAR_RE = re.compile(r"\{\{\s*([a-z_]{1,40})\s*\}\}")


class MailError(Exception):
    """Safe, user-facing mail problem (never carries provider detail)."""


# ---------------- form registry ----------------
# `kinds` ties each admin-facing form to the stored record kinds it covers.

FORMS: dict[str, dict] = {
    "general_inquiry": {
        "label": "General Inquiry",
        "kinds": ("contact",),
        "recipient": "info@elitemarcom.com",
        "internalSubject": "New website enquiry — {{customer_name}} ({{reference_number}})",
        "customerSubject": "We have received your enquiry — Elite Marcom",
        "heading": "Thank you for contacting Elite Marcom",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for reaching out to Elite Marcom. We have received your enquiry "
                 "and a member of our team will get back to you shortly.\n\n"
                 "Your reference number is {{reference_number}} — please quote it in any "
                 "follow-up correspondence."),
        "closing": "We look forward to speaking with you.",
        "buttonText": "Explore our work",
        "buttonUrl": "https://www.elitemarcom.com/projects.html",
        "variables": ("customer_name", "company_name", "email", "phone", "service",
                      "market", "reference_number"),
    },
    "job_application": {
        "label": "Job Application",
        "kinds": ("career",),
        "recipient": "hr@elitemarcom.com",
        "internalSubject": "New job application — {{position}} ({{reference_number}})",
        "customerSubject": "Your application has been received — Elite Marcom",
        "heading": "Thank you for applying to Elite Marcom",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for your interest in joining Elite Marcom. We have received your "
                 "application for {{position}} and our people team will review it carefully.\n\n"
                 "If your experience matches what we are looking for, we will contact you to "
                 "arrange the next step. Your reference number is {{reference_number}}."),
        "closing": "Thank you for considering a career with us.",
        "buttonText": "See our latest work",
        "buttonUrl": "https://www.elitemarcom.com/projects.html",
        "variables": ("customer_name", "email", "phone", "position", "location",
                      "reference_number"),
    },
    "corporate_gifts": {
        "label": "Corporate Gifts Request",
        "kinds": ("giveaway_enquiry",),
        "recipient": "mohammad.hossain@elitemarcom.com",
        "internalSubject": "New corporate gifts request — {{company_name}} ({{reference_number}})",
        "customerSubject": "Your corporate gifts request — Elite Marcom",
        "heading": "Your corporate gifts request is with our team",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for your corporate gifts request. Our team is preparing your "
                 "proposal, including availability, branding options and delivery timelines.\n\n"
                 "Requested items: {{product_name}}\n"
                 "Reference number: {{reference_number}}"),
        "closing": "We will be in touch shortly with your private proposal.",
        "buttonText": "Browse the collection",
        "buttonUrl": "https://www.elitemarcom.com/giveaways.html",
        "variables": ("customer_name", "company_name", "email", "phone", "product_name",
                      "quantity", "market", "reference_number"),
    },
    "stock_notification": {
        "label": "Stock Notification",
        "kinds": ("giveaway_notification",),
        "recipient": "mohammad.hossain@elitemarcom.com",
        "internalSubject": "Stock notification request — {{product_name}} ({{reference_number}})",
        "customerSubject": "We will let you know when it is available — Elite Marcom",
        "heading": "You are on the notification list",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for your interest in {{product_name}}. We have added you to the "
                 "notification list and will email you as soon as this item is available "
                 "again.\n\n"
                 "Your reference number is {{reference_number}}."),
        "closing": "If you need something sooner, simply reply to this email and we will "
                   "suggest an alternative.",
        "buttonText": "See similar items",
        "buttonUrl": "https://www.elitemarcom.com/giveaways.html",
        "variables": ("customer_name", "company_name", "email", "phone", "product_name",
                      "market", "reference_number"),
    },
    "rental_availability": {
        "label": "Rental Availability Notification",
        "kinds": ("rental_notification",),
        "recipient": "mohammad.hossain@elitemarcom.com",
        "internalSubject": "Rental availability alert — {{product_name}} ({{reference_number}})",
        "customerSubject": "We will confirm availability for you — Elite Marcom",
        "heading": "We will let you know the moment it is free",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for your interest in renting {{product_name}}. The item is currently "
                 "reserved for your dates, so we have added you to the availability list.\n\n"
                 "Required from: {{required_from}}\n"
                 "Required until: {{required_until}}\n"
                 "Reference number: {{reference_number}}\n\n"
                 "As soon as it becomes free — or if we can offer an equivalent unit — we will "
                 "contact you straight away."),
        "closing": "If your dates are flexible, reply to this email and we will find the closest "
                   "match from our fleet.",
        "buttonText": "Browse rental items",
        "buttonUrl": "https://www.elitemarcom.com/rental.html",
        "variables": ("customer_name", "company_name", "email", "phone", "product_name",
                      "required_from", "required_until", "market", "reference_number"),
    },
    "rental_inquiry": {
        "label": "Rental Items Inquiry",
        "kinds": ("rental_enquiry",),
        "recipient": "mohammad.hossain@elitemarcom.com",
        "internalSubject": "New rental enquiry — {{company_name}} ({{reference_number}})",
        "customerSubject": "Your rental enquiry — Elite Marcom",
        "heading": "Your rental enquiry has been received",
        "body": ("Dear {{customer_name}},\n\n"
                 "Thank you for your rental enquiry. Our team is checking availability for "
                 "your dates and will send you a detailed quotation, including delivery, "
                 "installation and collection.\n\n"
                 "Requested items: {{product_name}}\n"
                 "Reference number: {{reference_number}}"),
        "closing": "We will confirm availability shortly.",
        "buttonText": "View rental items",
        "buttonUrl": "https://www.elitemarcom.com/rental.html",
        "variables": ("customer_name", "company_name", "email", "phone", "product_name",
                      "quantity", "market", "reference_number"),
    },
}

KIND_TO_FORM = {kind: key for key, cfg in FORMS.items() for kind in cfg["kinds"]}

GENERAL_DEFAULTS = {
    "fromName": "Elite Marcom",
    "fromEmail": "website@mail.elitemarcom.com",
    "replyTo": "info@elitemarcom.com",
    "websiteUrl": "https://www.elitemarcom.com",
    "contactEmail": "info@elitemarcom.com",
    "footerText": "Elite Marcom — Experiential marketing, exhibitions and events. "
                  "Riyadh · Dubai · Worldwide.",
}

GENERAL_FIELDS = tuple(GENERAL_DEFAULTS)
FORM_FIELDS = ("recipient", "internalOn", "customerOn", "internalSubject",
               "customerSubject", "heading", "body", "closing", "buttonText", "buttonUrl")


# ---------------- settings ----------------

def allowed_sender_domains() -> list[str]:
    raw = config.MAIL_SENDER_DOMAINS
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _setting(key: str, default):
    from . import adminauth as aa

    value = aa.setting_get(key, None)
    return default if value is None else value


def general_settings() -> dict:
    return {field: str(_setting(f"email.{field}", GENERAL_DEFAULTS[field]))
            for field in GENERAL_FIELDS}


def form_settings(form_key: str) -> dict:
    cfg = FORMS[form_key]
    out = {
        "key": form_key,
        "label": cfg["label"],
        "variables": list(cfg["variables"]),
        "internalOn": bool(_setting(f"email.form.{form_key}.internalOn", True)),
        "customerOn": bool(_setting(f"email.form.{form_key}.customerOn", True)),
    }
    for field in ("recipient", "internalSubject", "customerSubject", "heading",
                  "body", "closing", "buttonText", "buttonUrl"):
        out[field] = str(_setting(f"email.form.{form_key}.{field}", cfg.get(field, "")))
    return out


def all_settings() -> dict:
    return {"general": general_settings(),
            "forms": [form_settings(key) for key in FORMS],
            "senderDomains": allowed_sender_domains(),
            "configured": bool(config.RESEND_API_KEY)}


def _valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match((value or "").strip()))


def save_general(values: dict) -> dict:
    from . import adminauth as aa

    clean = {}
    for field in GENERAL_FIELDS:
        if field not in values:
            continue
        value = re.sub(r"[\r\n\t]", " ", str(values[field] or "")).strip()[:300]
        if field in ("fromEmail", "replyTo", "contactEmail"):
            if not _valid_email(value):
                raise MailError(f"Please provide a valid email address for {field}.")
            if field == "fromEmail":
                domain = value.split("@")[1].lower()
                if domain not in allowed_sender_domains():
                    raise MailError(
                        "The sender address must use a domain verified with Resend: "
                        + ", ".join(allowed_sender_domains()))
        if field == "websiteUrl":
            if not re.match(r"^https://[\w.-]{3,120}(/[\w./-]*)?$", value):
                raise MailError("The website address must start with https://")
            value = value.rstrip("/")
        if field == "fromName" and not value:
            raise MailError("The sender name cannot be empty.")
        clean[field] = value
    for field, value in clean.items():
        aa.setting_set(f"email.{field}", value)
    return general_settings()


def save_form(form_key: str, values: dict) -> dict:
    from . import adminauth as aa

    if form_key not in FORMS:
        raise MailError("Unknown form.")
    for field in FORM_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if field in ("internalOn", "customerOn"):
            aa.setting_set(f"email.form.{form_key}.{field}", bool(value))
            continue
        text = str(value or "")
        if field == "recipient":
            text = text.strip()
            if not _valid_email(text):
                raise MailError("Please provide a valid internal recipient address.")
        elif field == "buttonUrl":
            text = text.strip()
            if text and not re.match(r"^(https://|mailto:|tel:)", text):
                raise MailError("The button link must be an https:// address.")
            text = text[:300]
        elif field in ("internalSubject", "customerSubject"):
            text = re.sub(r"[\r\n]", " ", text).strip()[:200]
            if not text:
                raise MailError("Subjects cannot be empty.")
        else:
            text = text.replace("\r\n", "\n")[:4000]
        _check_variables(text, form_key)
        aa.setting_set(f"email.form.{form_key}.{field}", text)
    return form_settings(form_key)


def _check_variables(text: str, form_key: str) -> None:
    allowed = set(FORMS[form_key]["variables"])
    unknown = {name for name in _VAR_RE.findall(text or "") if name not in allowed}
    if unknown:
        raise MailError("These variables are not available for this form: "
                        + ", ".join(sorted(unknown)[:5]))


# ---------------- variable extraction ----------------

def _items_summary(payload: dict) -> tuple[str, str]:
    items = payload.get("items") or []
    names = []
    total = 0
    for item in items:
        names.append(str(item.get("name") or item.get("productId") or item.get("id") or "item"))
        try:
            total += int(item.get("quantity") or 0)
        except (TypeError, ValueError):
            pass
    if not names:
        return str(payload.get("productName") or payload.get("productId") or ""), ""
    text = ", ".join(names[:4])
    if len(names) > 4:
        text += f" and {len(names) - 4} more"
    return text, str(total or "")


def variables_for(form_key: str, payload: dict, reference: str) -> dict[str, str]:
    product, quantity = _items_summary(payload)
    values = {
        "customer_name": str(payload.get("fullName") or "there"),
        "company_name": str(payload.get("company") or ""),
        "email": str(payload.get("email") or ""),
        "phone": str(payload.get("phone") or ""),
        "service": str(payload.get("service") or payload.get("enquiryType") or ""),
        "market": str(payload.get("market") or ""),
        "position": str(payload.get("roleTitle") or "the role you applied for"),
        "location": str(payload.get("location") or ""),
        "product_name": product or "the item you selected",
        "quantity": quantity,
        "required_from": str(payload.get("requiredFrom") or payload.get("startDate") or "not specified"),
        "required_until": str(payload.get("requiredUntil") or payload.get("endDate") or "not specified"),
        "reference_number": reference,
    }
    return {name: values.get(name, "") for name in FORMS[form_key]["variables"]}


def render(text: str, values: dict[str, str], escape: bool = True) -> str:
    def swap(match):
        value = values.get(match.group(1), "")
        return html_mod.escape(value) if escape else value

    return _VAR_RE.sub(swap, text or "")


# ---------------- branded HTML ----------------

BRAND_ORANGE = "#ed6c26"
BRAND_INK = "#14181f"


def _paragraphs(text: str) -> str:
    blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
    return "".join(
        '<p style="margin:0 0 16px;font-size:16px;line-height:1.65;color:#3f4650;">'
        + b.replace("\n", "<br>") + "</p>" for b in blocks)


def _shell(general: dict, title: str, preheader: str, inner: str) -> str:
    website = general["websiteUrl"]
    website_label = re.sub(r"^https?://", "", website)
    logo = f"{website}/assets/logo-email.png"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{html_mod.escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f6f2ec;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html_mod.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
 style="background:#f6f2ec;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
 style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;
 border:1px solid #e8e4de;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<tr><td style="padding:26px 32px 0;">
<img src="{logo}" alt="Elite Marcom" width="168" height="57"
 style="display:block;border:0;width:168px;height:auto;">
</td></tr>
<tr><td style="padding:18px 32px 0;">
<div style="height:3px;background:linear-gradient(90deg,{BRAND_ORANGE},#8f77d6);
 border-radius:2px;"></div></td></tr>
{inner}
<tr><td style="padding:26px 32px 30px;border-top:1px solid #eee9e2;">
<p style="margin:0 0 10px;font-size:13px;line-height:1.6;color:#8a8f98;">
{html_mod.escape(general['footerText'])}</p>
<p style="margin:0;font-size:13px;line-height:1.7;color:#8a8f98;">
<a href="{website}" style="color:{BRAND_ORANGE};text-decoration:none;">{html_mod.escape(website_label)}</a>
&nbsp;·&nbsp;
<a href="mailto:{html_mod.escape(general['contactEmail'])}"
 style="color:{BRAND_ORANGE};text-decoration:none;">{html_mod.escape(general['contactEmail'])}</a>
</p></td></tr>
</table>
<p style="margin:14px 0 0;font-size:11px;color:#a6abb4;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
This message was sent by Elite Marcom because you contacted us through {html_mod.escape(website_label)}.</p>
</td></tr></table></body></html>"""


def customer_html(form_key: str, settings: dict, general: dict, values: dict) -> str:
    heading = render(settings["heading"], values) or html_mod.escape(FORMS[form_key]["heading"])
    body = _paragraphs(render(settings["body"], values))
    closing = render(settings["closing"], values)
    button_text = render(settings["buttonText"], values).strip()
    button_url = render(settings["buttonUrl"], values, escape=False).strip()
    button = ""
    if button_text and button_url.startswith(("https://", "mailto:", "tel:")):
        button = (f'<tr><td style="padding:4px 32px 8px;">'
                  f'<a href="{html_mod.escape(button_url, quote=True)}" '
                  f'style="display:inline-block;background:{BRAND_ORANGE};color:#ffffff;'
                  f'text-decoration:none;font-weight:700;font-size:15px;padding:13px 26px;'
                  f'border-radius:999px;">{button_text}</a></td></tr>')
    closing_block = (f'<tr><td style="padding:6px 32px 0;">'
                     f'<p style="margin:0;font-size:16px;line-height:1.65;color:#3f4650;">'
                     f'{closing}</p></td></tr>') if closing else ""
    inner = (f'<tr><td style="padding:24px 32px 6px;">'
             f'<h1 style="margin:0 0 14px;font-size:23px;line-height:1.3;color:{BRAND_INK};'
             f'font-weight:800;">{heading}</h1>{body}</td></tr>'
             f'{closing_block}{button}'
             f'<tr><td style="padding:22px 32px 6px;">'
             f'<p style="margin:0;font-size:15px;line-height:1.6;color:{BRAND_INK};">'
             f'Warm regards,<br><strong>The Elite Marcom Team</strong></p></td></tr>')
    subject = render(settings["customerSubject"], values, escape=False)
    return _shell(general, subject, heading, inner)


_INTERNAL_LABELS = {
    "fullName": "Name", "company": "Company", "email": "Email", "phone": "Phone",
    "market": "Market", "enquiryType": "Enquiry type", "service": "Service",
    "roleTitle": "Role", "location": "Location", "portfolioUrl": "Portfolio",
    "introduction": "Introduction", "message": "Message", "notes": "Notes",
    "projectDate": "Project date", "projectCity": "City", "eventDate": "Event date",
    "startDate": "Start date", "endDate": "End date", "eventCity": "Event city",
    "venue": "Venue", "shippingAddress": "Shipping address", "productName": "Product",
    "productCode": "Product code", "productId": "Product id",
    "requiredFrom": "Required from", "requiredUntil": "Required until",
    "deliveryCity": "Delivery city", "requiredBy": "Required by",
}


def internal_html(form_key: str, general: dict, payload: dict, reference: str,
                  attachment_note: str = "") -> str:
    rows = []
    for key, label in _INTERNAL_LABELS.items():
        value = payload.get(key)
        if not value or not isinstance(value, (str, int, float)):
            continue
        rows.append(
            f'<tr><td style="padding:8px 0;font-size:14px;color:#8a8f98;width:150px;'
            f'vertical-align:top;">{html_mod.escape(label)}</td>'
            f'<td style="padding:8px 0;font-size:14px;color:{BRAND_INK};font-weight:600;">'
            f'{html_mod.escape(str(value)).replace(chr(10), "<br>")}</td></tr>')
    items = payload.get("items") or []
    items_block = ""
    if items:
        lines = []
        for item in items:
            bits = [html_mod.escape(str(item.get("name") or item.get("productId") or "item"))]
            if item.get("code"):
                bits.append(html_mod.escape(str(item["code"])))
            if item.get("quantity"):
                bits.append(f"qty {html_mod.escape(str(item['quantity']))}")
            if item.get("days"):
                bits.append(f"{html_mod.escape(str(item['days']))} day(s)")
            pref = item.get("brandingPreference") or {}
            branding = " · ".join(html_mod.escape(str(pref[k])) for k in ("area", "method", "note")
                                  if pref.get(k))
            line = " · ".join(bits)
            if branding:
                line += (f'<br><span style="color:#8a8f98;font-weight:400;">'
                         f'Branding preference: {branding}</span>')
            lines.append(f'<li style="margin:0 0 8px;font-size:14px;color:{BRAND_INK};">{line}</li>')
        items_block = (f'<tr><td colspan="2" style="padding:14px 0 0;">'
                       f'<p style="margin:0 0 8px;font-size:13px;color:#8a8f98;text-transform:uppercase;'
                       f'letter-spacing:0.08em;">Requested items ({len(items)})</p>'
                       f'<ul style="margin:0;padding-inline-start:18px;">{"".join(lines)}</ul></td></tr>')
    note = ""
    if attachment_note:
        note = (f'<tr><td colspan="2" style="padding:14px 0 0;font-size:14px;color:#3f4650;">'
                f'{html_mod.escape(attachment_note)}</td></tr>')
    customer_email = str(payload.get("email") or "")
    reply = ""
    if customer_email:
        reply = (f'<tr><td style="padding:18px 32px 4px;">'
                 f'<a href="mailto:{html_mod.escape(customer_email, quote=True)}" '
                 f'style="display:inline-block;background:{BRAND_ORANGE};color:#fff;'
                 f'text-decoration:none;font-weight:700;font-size:14px;padding:11px 22px;'
                 f'border-radius:999px;">Reply to {html_mod.escape(customer_email)}</a></td></tr>')
    inner = (f'<tr><td style="padding:24px 32px 4px;">'
             f'<p style="margin:0 0 6px;font-size:12px;letter-spacing:0.12em;text-transform:uppercase;'
             f'color:{BRAND_ORANGE};font-weight:700;">{html_mod.escape(FORMS[form_key]["label"])}</p>'
             f'<h1 style="margin:0 0 4px;font-size:21px;color:{BRAND_INK};font-weight:800;">'
             f'New submission — {html_mod.escape(reference)}</h1>'
             f'<p style="margin:0 0 12px;font-size:13px;color:#8a8f98;">Received '
             f'{time.strftime("%d %B %Y, %H:%M UTC", time.gmtime())}</p>'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
             f'{"".join(rows)}{items_block}{note}</table></td></tr>{reply}')
    return _shell(general, f"New {FORMS[form_key]['label']}", f"Reference {reference}", inner)


def to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|h1|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html_mod.unescape(text)).strip()


# ---------------- delivery log ----------------

_local = threading.local()
_log_lock = threading.Lock()


def _log_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.RUNTIME_DIR / "maillog.db"))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            form TEXT NOT NULL,
            kind TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '',
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            provider_id TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sends_once
            ON sends(reference, kind) WHERE reference <> '';
        """)
        # migrate databases created before the durable queue existed, then
        # build the index that depends on the new columns
        for ddl in ("ALTER TABLE sends ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE sends ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0"):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # column already present
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sends_due ON sends(status, next_attempt_at)")
        conn.commit()
        _local.conn = conn
    return conn


def log_entries(limit: int = 40) -> list[dict]:
    rows = _log_conn().execute(
        "SELECT id, ts, form, kind, reference, recipient, subject, status, detail,"
        " attempts FROM sends ORDER BY id DESC LIMIT ?",
        (max(1, min(200, limit)),)).fetchall()
    return [dict(r) for r in rows]


def log_stats() -> dict:
    """Queue health. Counted over the whole log, not a rolling window: a job
    stuck pending for weeks still needs to show up as pending."""
    row = _log_conn().execute(
        "SELECT SUM(status='pending') AS pending, SUM(status='sending') AS sending,"
        " SUM(status='sent') AS sent, SUM(status='failed') AS failed,"
        " COUNT(*) AS total FROM sends").fetchone()
    return {"pending": row["pending"] or 0, "sending": row["sending"] or 0,
            "sent": row["sent"] or 0, "failed": row["failed"] or 0,
            "total": row["total"] or 0}


# ---------------- transport ----------------

def _mask(detail: str) -> str:
    """Never let a provider message carry the key or a full address."""
    key = config.RESEND_API_KEY
    if key:
        detail = detail.replace(key, "***")
    return re.sub(r"re_[A-Za-z0-9_]{6,}", "***", detail)[:300]


def send_email(*, to: str | list[str], subject: str, html: str, reply_to: str = "",
               attachments: list[dict] | None = None, general: dict | None = None) -> str:
    """POST one message to Resend. Returns the provider id; raises MailError."""
    if not config.RESEND_API_KEY:
        raise MailError("Email sending is not configured on the server.")
    general = general or general_settings()
    recipients = to if isinstance(to, list) else [to]
    if not recipients or not all(_valid_email(r) for r in recipients):
        raise MailError("The recipient address is not valid.")
    payload = {
        "from": f'{general["fromName"]} <{general["fromEmail"]}>',
        "to": recipients,
        "subject": subject[:200],
        "html": html,
        "text": to_text(html),
    }
    if reply_to or general.get("replyTo"):
        payload["reply_to"] = [reply_to or general["replyTo"]]
    if attachments:
        payload["attachments"] = attachments
    try:
        with httpx.Client(timeout=SEND_TIMEOUT_S, trust_env=False) as client:
            res = client.post(config.RESEND_ENDPOINT, json=payload, headers={
                "Authorization": f"Bearer {config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            })
    except Exception as exc:
        raise MailError("The email service could not be reached.") from exc
    if res.status_code >= 400:
        try:
            body = json.dumps(res.json())[:200]
        except Exception:
            body = res.text[:200]
        # technical detail is logged, never returned to a caller
        print(f"[mail] resend {res.status_code}: {_mask(body)}", flush=True)
        raise MailError("The email service rejected the message.")
    try:
        return str(res.json().get("id", ""))[:80]
    except Exception:
        return ""


def _attachment(cv_bytes: bytes, filename: str) -> list[dict]:
    if not cv_bytes or len(cv_bytes) > MAX_ATTACHMENT_BYTES:
        return []
    return [{"filename": filename[:80],
             "content": base64.b64encode(cv_bytes).decode()}]


# ---------------- durable outbox ----------------

MAX_ATTEMPTS = 5
BACKOFF_S = (30, 120, 600, 1800)      # 30s, 2m, 10m, 30m, then give up


def enqueue(kind: str, reference: str) -> int:
    """Persist the intent to send BEFORE the HTTP response returns.

    Nothing is sent here: the rows survive a restart, a crash or a deploy,
    and the worker picks them up. The unique (reference, kind) index means a
    repeated submit or a retry can never queue the same email twice.
    """
    form_key = KIND_TO_FORM.get(kind)
    if form_key is None or not reference:
        return 0
    settings = form_settings(form_key)
    queued = 0
    now = int(time.time())
    with _log_lock:
        conn = _log_conn()
        for audience, recipient, enabled in (
                ("internal", settings["recipient"], settings["internalOn"]),
                ("customer", "", settings["customerOn"])):
            if not enabled:
                continue
            try:
                conn.execute(
                    "INSERT INTO sends (ts, form, kind, reference, recipient, status,"
                    " next_attempt_at) VALUES (?,?,?,?,?, 'pending', ?)",
                    (now, form_key, audience, reference, recipient[:200], now))
                queued += 1
            except sqlite3.IntegrityError:
                pass  # already queued for this submission
        conn.commit()
    return queued


def team_recipients() -> list[str]:
    """The staff broadcast list from Settings → Alert recipients."""
    from . import adminauth as aa

    raw = aa.setting_get("notify.emails") or []
    return [e.strip() for e in raw
            if isinstance(e, str) and _valid_email(e.strip())][:20]


def enqueue_team_alert(kind: str, reference: str) -> int:
    """Queue the terse staff alert for a new submission.

    Deliberately carries only the reference and the kind of request — never a
    name, address or message — so a compromised team mailbox leaks nothing
    personal. It rides the same durable outbox as everything else, so it
    survives a restart and is retried and visible in the delivery log."""
    if not team_recipients():
        return 0
    form_key = KIND_TO_FORM.get(kind, "")
    now = int(time.time())
    with _log_lock:
        conn = _log_conn()
        try:
            conn.execute(
                "INSERT INTO sends (ts, form, kind, reference, recipient, status,"
                " next_attempt_at) VALUES (?,?,?,?,?, 'pending', ?)",
                (now, form_key or "team", "team", reference, "", now))
        except sqlite3.IntegrityError:
            return 0        # already queued for this submission
        conn.commit()
    return 1


def _team_alert_body(form_key: str, reference: str) -> tuple[str, str]:
    general = general_settings()
    label = (FORMS.get(form_key) or {}).get("label", "Website request")
    site = str(general.get("websiteUrl") or "").rstrip("/")
    link = f"{site}/admin#requests" if site.startswith("https://") else ""
    subject = f"New {label.lower()} — {reference}"
    button = ""
    if link:
        button = (f'<tr><td style="padding:4px 32px 20px;">'
                  f'<a href="{html_mod.escape(link, quote=True)}" '
                  f'style="display:inline-block;background:{BRAND_ORANGE};color:#ffffff;'
                  f'text-decoration:none;font-weight:700;font-size:15px;padding:13px 26px;'
                  f'border-radius:999px;">Open the requests inbox</a></td></tr>')
    inner = (f'<tr><td style="padding:24px 32px 6px;">'
             f'<h1 style="margin:0 0 14px;font-size:23px;line-height:1.3;color:{BRAND_INK};'
             f'font-weight:800;">New website request</h1>'
             f'<p style="margin:0 0 12px;font-size:16px;line-height:1.65;color:#3f4650;">'
             f'A new {html_mod.escape(label.lower())} came in on the website.</p>'
             f'<p style="margin:0 0 12px;font-size:16px;line-height:1.65;color:#3f4650;">'
             f'Reference: <strong>{html_mod.escape(reference)}</strong></p>'
             f'<p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#6b7280;">'
             f'The customer details are not in this email — they stay encrypted. '
             f'Open the request in the admin panel to read it.</p></td></tr>' + button)
    return subject, _shell(general, subject, "New website request", inner)


def _claim_due(limit: int = 10) -> list[dict]:
    """Atomically take pending jobs whose time has come."""
    now = int(time.time())
    taken = []
    with _log_lock:
        conn = _log_conn()
        rows = conn.execute(
            "SELECT id, form, kind, reference, attempts FROM sends"
            " WHERE status='pending' AND next_attempt_at <= ? ORDER BY id LIMIT ?",
            (now, max(1, min(50, limit)))).fetchall()
        for row in rows:
            cur = conn.execute(
                "UPDATE sends SET status='sending', ts=? WHERE id=? AND status='pending'",
                (now, row["id"]))
            if cur.rowcount:
                taken.append(dict(row))
        conn.commit()
    return taken


def _finish(job_id: int, status: str, *, subject: str = "", recipient: str = "",
            detail: str = "", provider_id: str = "", attempts: int = 0,
            next_attempt_at: int = 0) -> None:
    with _log_lock:
        conn = _log_conn()
        conn.execute(
            "UPDATE sends SET status=?, subject=COALESCE(NULLIF(?,''), subject),"
            " recipient=COALESCE(NULLIF(?,''), recipient), detail=?, provider_id=?,"
            " attempts=?, next_attempt_at=?, ts=? WHERE id=?",
            (status, subject[:200], recipient[:200], detail[:300], provider_id[:80],
             attempts, next_attempt_at, int(time.time()), job_id))
        conn.commit()


def recover_stuck(older_than_s: int = 300) -> int:
    """A process that died mid-send leaves rows in 'sending'; make them due again."""
    cutoff = int(time.time()) - older_than_s
    with _log_lock:
        conn = _log_conn()
        cur = conn.execute(
            "UPDATE sends SET status='pending', next_attempt_at=? WHERE status='sending' AND ts <= ?",
            (int(time.time()), cutoff))
        conn.commit()
        return cur.rowcount


def retry_failed(reference: str = "", job_id: int = 0) -> int:
    """Admin action: put failed deliveries back in the queue."""
    with _log_lock:
        conn = _log_conn()
        if job_id:
            cur = conn.execute(
                "UPDATE sends SET status='pending', next_attempt_at=?, attempts=0"
                " WHERE id=? AND status='failed'", (int(time.time()), job_id))
        elif reference:
            cur = conn.execute(
                "UPDATE sends SET status='pending', next_attempt_at=?, attempts=0"
                " WHERE reference=? AND status='failed'", (int(time.time()), reference))
        else:
            cur = conn.execute(
                "UPDATE sends SET status='pending', next_attempt_at=?, attempts=0"
                " WHERE status='failed'", (int(time.time()),))
        conn.commit()
        return cur.rowcount


def _load_submission(reference: str) -> tuple[dict, tuple[bytes, str] | None]:
    """Read the stored submission at send time — no second copy of personal
    data is kept in the queue, and the CV never leaves the encrypted store."""
    from . import storage

    record = storage.get_record(reference)
    if record is None:
        raise MailError("The submission is no longer available.")
    try:
        payload = json.loads(storage.decrypt(record["payload"]).decode())
    except Exception:
        raise MailError("The submission could not be read.")
    attachment = None
    if record.get("cvPath"):
        data = storage.read_attachment(record["cvPath"])
        if data:
            attachment = (data, f"{reference}-cv.pdf")
    return payload, attachment


def _send_job(job: dict) -> None:
    form_key, audience, reference = job["form"], job["kind"], job["reference"]
    attempts = int(job["attempts"]) + 1

    if audience == "team":
        recipients = team_recipients()
        if not recipients:
            _finish(job["id"], "failed", detail="no alert recipients configured",
                    attempts=attempts)
            return
        subject, html = _team_alert_body(form_key, reference)
        general = general_settings()
        try:
            provider_id = send_email(to=recipients, subject=subject, html=html, general=general)
        except MailError as exc:
            if attempts >= MAX_ATTEMPTS:
                _finish(job["id"], "failed", subject=subject, recipient=", ".join(recipients),
                        detail=f"{exc} (gave up after {attempts} attempts)", attempts=attempts)
            else:
                delay = BACKOFF_S[min(attempts - 1, len(BACKOFF_S) - 1)]
                _finish(job["id"], "pending", subject=subject, recipient=", ".join(recipients),
                        detail=f"{exc} — retrying", attempts=attempts,
                        next_attempt_at=int(time.time()) + delay)
            return
        _finish(job["id"], "sent", subject=subject, recipient=", ".join(recipients),
                provider_id=provider_id, attempts=attempts)
        return

    if form_key not in FORMS:
        _finish(job["id"], "failed", detail="unknown form", attempts=attempts)
        return
    try:
        payload, attachment = _load_submission(reference)
    except MailError as exc:
        _finish(job["id"], "failed", detail=str(exc), attempts=attempts)
        return

    settings = form_settings(form_key)
    general = general_settings()
    values = variables_for(form_key, payload, reference)
    customer_email = str(payload.get("email") or "")

    if audience == "internal":
        recipient = settings["recipient"]
        subject = render(settings["internalSubject"], values, escape=False)
        attachments = []
        note = ""
        if attachment:
            attachments = _attachment(*attachment)
            note = ("The applicant's CV is attached to this email." if attachments else
                    "A CV was uploaded but is too large to attach — open the request in the "
                    "admin panel to download it securely.")
        html = internal_html(form_key, general, payload, reference, note)
        reply_to = customer_email if _valid_email(customer_email) else ""
    else:
        recipient = customer_email
        subject = render(settings["customerSubject"], values, escape=False)
        html = customer_html(form_key, settings, general, values)
        attachments, reply_to = [], ""
        if not _valid_email(recipient):
            _finish(job["id"], "failed", subject=subject,
                    detail="no valid customer address", attempts=attempts)
            return

    try:
        provider_id = send_email(to=recipient, subject=subject, html=html,
                                 reply_to=reply_to, attachments=attachments, general=general)
    except MailError as exc:
        if attempts >= MAX_ATTEMPTS:
            _finish(job["id"], "failed", subject=subject, recipient=recipient,
                    detail=f"{exc} (gave up after {attempts} attempts)", attempts=attempts)
        else:
            delay = BACKOFF_S[min(attempts - 1, len(BACKOFF_S) - 1)]
            _finish(job["id"], "pending", subject=subject, recipient=recipient,
                    detail=f"{exc} — retrying", attempts=attempts,
                    next_attempt_at=int(time.time()) + delay)
        return
    _finish(job["id"], "sent", subject=subject, recipient=recipient,
            provider_id=provider_id, attempts=attempts)


def process_outbox(limit: int = 10) -> dict:
    """One worker pass. Safe to call from anywhere, any number of times."""
    if not config.RESEND_API_KEY:
        return {"sent": 0, "failed": 0, "pending": 0}
    result = {"sent": 0, "failed": 0, "pending": 0}
    for job in _claim_due(limit):
        before = _log_conn().execute("SELECT status FROM sends WHERE id=?",
                                     (job["id"],)).fetchone()
        _send_job(job)
        after = _log_conn().execute("SELECT status FROM sends WHERE id=?",
                                    (job["id"],)).fetchone()
        status = after["status"] if after else "failed"
        result[status if status in result else "pending"] += 1
        del before
    return result


def outbox_pending() -> int:
    return _log_conn().execute(
        "SELECT COUNT(*) AS c FROM sends WHERE status IN ('pending','sending')").fetchone()["c"]


def record(reference: str, kind: str, form: str, recipient: str, subject: str,
           status: str, detail: str = "", provider_id: str = "") -> None:
    """Log a one-off send (the admin test email) that has no queued job."""
    with _log_lock:
        conn = _log_conn()
        conn.execute(
            "INSERT INTO sends (ts, form, kind, reference, recipient, subject, status,"
            " detail, provider_id, attempts) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (int(time.time()), form, kind, reference, recipient[:200], subject[:200],
             status, detail[:300], provider_id[:80]))
        conn.commit()


def send_test(recipient: str, by: str) -> dict:
    """Admin 'send test email' — friendly outcome only, never provider detail."""
    if not _valid_email(recipient):
        raise MailError("Please provide a valid email address.")
    general = general_settings()
    inner = ('<tr><td style="padding:24px 32px 6px;">'
             f'<h1 style="margin:0 0 14px;font-size:22px;color:{BRAND_INK};font-weight:800;">'
             'Your email settings are working</h1>'
             '<p style="margin:0 0 16px;font-size:16px;line-height:1.65;color:#3f4650;">'
             'This is a test message from the Elite Marcom admin panel. If you can read it, '
             'the sender identity, reply-to address and delivery are all configured correctly.'
             '</p>'
             f'<p style="margin:0;font-size:14px;color:#8a8f98;">Sent by {html_mod.escape(by)} · '
             f'from {html_mod.escape(general["fromName"])} &lt;{html_mod.escape(general["fromEmail"])}&gt; · '
             f'reply-to {html_mod.escape(general["replyTo"])}</p></td></tr>')
    subject = "Elite Marcom — email settings test"
    html = _shell(general, subject, "Test message from the Elite Marcom admin panel", inner)
    try:
        provider_id = send_email(to=recipient, subject=subject, html=html, general=general)
    except MailError as exc:
        record("", "test", "test", recipient, subject, "failed", str(exc))
        raise
    record("", "test", "test", recipient, subject, "sent", "", provider_id)
    return {"ok": True}
