import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("app.mail")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send through SMTP when configured. Returns False when no SMTP server is set up."""
    if not settings.smtp_host:
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 - mail failure must never break the request
        log.exception("Failed to send email to %s", to)
        return False
