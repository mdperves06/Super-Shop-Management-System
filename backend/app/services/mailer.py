import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("app.mail")


def smtp_configured() -> bool:
    return bool(settings.smtp_host)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send through SMTP. Returns False (never raises) when SMTP is unset or delivery fails, so a mail outage
    cannot break the request; the caller decides what to log."""
    if not smtp_configured():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    mode = settings.smtp_security.lower()
    try:
        context = ssl.create_default_context()
        if mode == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10, context=context)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with client as smtp:
            if mode == "starttls":
                smtp.starttls(context=context)
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception("Failed to send email to %s", to)
        return False
