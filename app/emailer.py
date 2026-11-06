"""
Sending X-rays and reports to patients by email.

The SMTP settings (mail server, user, password) come from .env. If they are
not set, email_configured() is False and the app offers a download instead.
"""
import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

from flask import current_app


def email_configured():
    """True when the mail server settings are filled in."""
    cfg = current_app.config
    return bool(cfg["SMTP_HOST"] and cfg["SMTP_SENDER"])


def build_message(to_address, subject, body, attachments):
    """Create an email with files attached. attachments = list of file paths."""
    message = EmailMessage()
    message["From"] = current_app.config["SMTP_SENDER"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    for path in attachments:
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        main_type, sub_type = mime_type.split("/")
        message.add_attachment(Path(path).read_bytes(), maintype=main_type, subtype=sub_type,
                               filename=Path(path).name)
    return message


def send_email(to_address, subject, body, attachments=()):
    """Send the email through the configured SMTP server (encrypted with STARTTLS)."""
    cfg = current_app.config
    message = build_message(to_address, subject, body, attachments)
    with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=20) as server:
        server.starttls()
        if cfg["SMTP_USER"]:
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        server.send_message(message)
