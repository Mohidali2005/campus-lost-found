# backend/services/email_service.py
# ─────────────────────────────────────────────────────────────────────────────
# Email notification service for the LUMS Lost & Found app.
#
# Currently handles one type of notification:
#   send_message_notification() — emails the item poster when someone messages them
#
# Uses Python's built-in smtplib so no extra pip packages are needed.
# Recommended SMTP provider: Brevo (brevo.com) — free, 300 emails/day, no 2FA.
#
# If SMTP credentials are not set in .env, all functions silently do nothing.
# The app works perfectly without email — it's purely an enhancement.
# ─────────────────────────────────────────────────────────────────────────────

import smtplib                              # Python stdlib — sends emails over SMTP
import logging                             # for logging success/failure without crashing
from email.mime.text import MIMEText       # wraps the plain-text email body
from email.mime.multipart import MIMEMultipart  # the outer email envelope (From/To/Subject + body)

from backend.config import settings        # reads SMTP_HOST, SMTP_PORT, etc. from .env

# Module-level logger — logs show up in the uvicorn console with the module name
logger = logging.getLogger(__name__)


def send_message_notification(
    to_email: str,          # recipient — the item poster's @lums.edu.pk address
    item_title: str,        # e.g. "Black MacBook Charger"
    item_id: int,           # DB id — used so the poster can find the item
    item_type: str,         # "lost" or "found" — used in the subject line
    sender_name: str,       # name of the person who left the message
    message_preview: str,   # the message text (we show up to 300 chars)
) -> None:
    """
    Sends an email to the item poster telling them someone left a message.

    Called as a FastAPI BackgroundTask — runs AFTER the HTTP response is sent
    so the API never slows down waiting for SMTP.

    If SMTP is not configured (smtp_host is blank in .env), this function
    returns immediately without doing anything — no error, no crash.
    """

    # ── Guard: skip silently if SMTP is not configured ────────────────────────
    # This lets the app run without any email setup during development.
    if not settings.smtp_host or not settings.smtp_user:
        logger.debug("SMTP not configured — skipping email notification")
        return

    # ── Build the email subject ───────────────────────────────────────────────
    # e.g. "New message on your LOST item: "Black MacBook Charger""
    subject = f'New message on your {item_type.upper()} item: "{item_title}"'

    # ── Build the plain-text email body ───────────────────────────────────────
    # Keep it simple and informative — no HTML needed for a student app.
    # We truncate the message preview to 300 chars to avoid huge emails.
    preview = message_preview[:300]
    if len(message_preview) > 300:
        preview += "..."   # show "..." if we cut the message short

    body = f"""Hi there,

Someone sent a message on your {item_type} item listing: "{item_title}"

From: {sender_name}
Message: {preview}

To read and reply, open the LUMS Lost & Found site and look for item #{item_id}.

—
LUMS Campus Lost & Found
"""

    # ── Assemble the MIME email ───────────────────────────────────────────────
    # MIMEMultipart = the "envelope" that holds From/To/Subject headers + body parts
    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from      # shown in the inbox as the sender name/address
    msg["To"] = to_email                  # the poster's LUMS email
    msg["Subject"] = subject

    # Attach the plain-text body — "plain" means no HTML formatting
    msg.attach(MIMEText(body, "plain"))

    # ── Connect to SMTP and send ──────────────────────────────────────────────
    # We wrap in try/except so a failed email NEVER crashes the API.
    # The message was already saved to DB — email is best-effort only.
    try:
        # 'with' ensures the SMTP connection is closed even if something goes wrong
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()   # upgrade the connection to TLS encryption (required by most providers)
            server.login(settings.smtp_user, settings.smtp_password)  # authenticate with the SMTP server
            server.send_message(msg)  # actually send the email

        logger.info("Email notification sent to %s for item #%d", to_email, item_id)

    except Exception as exc:
        # Log the error but do NOT re-raise — the caller (BackgroundTask) doesn't
        # care about the result, and we never want email failure to affect the user.
        logger.warning("Email notification failed for item #%d: %s", item_id, exc)
