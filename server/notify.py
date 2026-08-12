"""Elite Marcom website backend — staff notifications (admin Phase 1).

Fail-silent email notification for new customer requests. Recipients come
from the admin setting `notify.emails`; SMTP transport from EM_SMTP_* env.
Only the reference and request kind are sent — never customer details, so a
mailbox compromise leaks nothing personal. WhatsApp push is a later phase
(needs Business API credentials).
"""
from __future__ import annotations

import os
import smtplib
import threading
from email.message import EmailMessage

from . import config

SMTP_HOST = os.environ.get("EM_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("EM_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("EM_SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("EM_SMTP_PASS", "")
SMTP_FROM = os.environ.get("EM_SMTP_FROM", "").strip() or SMTP_USER

KIND_LABELS = {
    "contact": "Contact enquiry",
    "career": "Career application",
    "giveaway_enquiry": "Corporate gifts enquiry",
    "giveaway_notification": "Corporate gifts stock alert signup",
    "rental_enquiry": "Rental enquiry",
    "rental_notification": "Rental notification signup",
}


def _recipients() -> list[str]:
    try:
        from . import adminauth
        emails = adminauth.setting_get("notify.emails") or []
        return [e for e in emails if isinstance(e, str) and "@" in e][:20]
    except Exception:
        return []


def _send(subject: str, body: str, recipients: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


def notify_new_request(kind: str, reference: str) -> None:
    """Queue a background email about a new request. Never raises and never
    blocks the customer's response — notification failure is invisible to
    the public site."""
    if not SMTP_HOST:
        return
    recipients = _recipients()
    if not recipients:
        return
    label = KIND_LABELS.get(kind, "Website request")
    subject = f"[Elite Marcom] New {label} — {reference}"
    body = (
        f"A new {label.lower()} was received on the website.\n\n"
        f"Reference: {reference}\n\n"
        "Open the admin panel to view the full request:\n"
        f"{(config.ALLOWED_ORIGINS[0] if config.ALLOWED_ORIGINS else '')}/admin#requests\n"
    )

    def worker() -> None:
        try:
            _send(subject, body, recipients)
        except Exception as exc:  # fail silent by design
            print(f"[notify] email failed: {exc.__class__.__name__}", flush=True)

    threading.Thread(target=worker, daemon=True).start()
