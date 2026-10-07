"""Sends the shopping list by email over SMTP using credentials from .env.
Deliberately plain smtplib - no third-party email service/API key needed,
just the user's own mail account (e.g. a Gmail address + App Password).
"""
import smtplib
from email.message import EmailMessage

from env_config import smtp_settings


def send_shopping_list_email(to_address: str, subject: str, body_text: str):
    """Raises RuntimeError (missing config) or smtplib exceptions on failure."""
    settings, missing = smtp_settings()
    if missing:
        raise RuntimeError(
            "Email isn't configured yet. Add " + ", ".join(missing) + " to your .env file "
            "(see .env.example) and restart the app."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["SMTP_FROM"]
    msg["To"] = to_address
    msg.set_content(body_text)

    port = int(settings["SMTP_PORT"])
    with smtplib.SMTP(settings["SMTP_HOST"], port, timeout=15) as server:
        server.starttls()
        server.login(settings["SMTP_USERNAME"], settings["SMTP_PASSWORD"])
        server.send_message(msg)
