"""
Transactional email service for VADG (SMTP).

Sends verification, password-reset, welcome and generic system emails from the
official address (vadg.office@gmail.com by default). Uses smtplib in a thread
executor so the async event loop is never blocked.

Configuration (environment):
  SMTP_HOST        default smtp.gmail.com
  SMTP_PORT        default 587 (STARTTLS)
  SMTP_USER        SMTP login (default vadg.office@gmail.com)
  SMTP_PASSWORD    SMTP app password (REQUIRED to actually send)
  MAIL_FROM        From address (default = SMTP_USER)
  MAIL_FROM_NAME   Display name (default "VADG")
  FRONTEND_URL     Base URL used to build verification/reset links
  SUPPORT_EMAIL    Support contact shown in email footers

If SMTP_PASSWORD is unset the service logs the message (including the link in
development) instead of sending, so local flows keep working without secrets.
"""

import asyncio
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from typing import Optional

logger = logging.getLogger(__name__)

# Config is read with fallbacks to the legacy variable names already used by the
# contact form (SMTP_SERVER / SENDER_EMAIL / SENDER_PASSWORD), so a single Gmail
# app password configured under either scheme powers all transactional email.
SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("SENDER_EMAIL", "vadg.office@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or os.getenv("SENDER_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "VADG")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "vadg.office@gmail.com")

# Verification/reset links must point at the real frontend. In production the
# default is the live site; locally it is the dev server. Set FRONTEND_URL
# explicitly on the deployment to override.
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")
_DEFAULT_FRONTEND = "https://www.vadg.in" if IS_PRODUCTION else "http://localhost:5173"
FRONTEND_URL = (os.getenv("FRONTEND_URL", _DEFAULT_FRONTEND) or "").rstrip("/")

_BRAND_COLOR = "#2563eb"  # blue-600, matches product UI conventions


def is_configured() -> bool:
    """Whether real SMTP delivery is configured."""
    return bool(SMTP_USER and SMTP_PASSWORD)


def validate_config() -> list:
    """Return a list of production-readiness problems and log them.

    Called at startup so a misconfigured email setup is visible in deploy logs
    instead of failing silently (unsent mail or links pointing at localhost).
    """
    problems = []
    if not is_configured():
        problems.append(
            "SMTP not configured: set SMTP_PASSWORD (or SENDER_PASSWORD). "
            "Verification and password-reset emails will NOT be delivered."
        )
    if IS_PRODUCTION and ("localhost" in FRONTEND_URL or "127.0.0.1" in FRONTEND_URL):
        problems.append(
            f"FRONTEND_URL is '{FRONTEND_URL}' in production: verification/reset "
            f"links will be broken. Set FRONTEND_URL to your live site URL."
        )
    if not FRONTEND_URL.startswith("https://") and IS_PRODUCTION:
        problems.append(
            f"FRONTEND_URL '{FRONTEND_URL}' is not HTTPS in production."
        )
    for p in problems:
        logger.warning("EMAIL CONFIG: %s", p)
    if not problems:
        logger.info(
            "Email service ready (host=%s, from=%s, frontend=%s).",
            SMTP_HOST, MAIL_FROM, FRONTEND_URL,
        )
    return problems


# Surface configuration state in logs at import (startup) time.
validate_config()


def _send_sync(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Blocking SMTP send. Runs inside a thread executor."""
    if not is_configured():
        logger.warning(
            "SMTP not configured (SMTP_PASSWORD unset) — email to %s NOT sent. "
            "Subject: %s", to_email, subject
        )
        # Surface the body in logs during development so links are usable.
        logger.info("Email body (not delivered):\n%s", text_body)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((MAIL_FROM_NAME, MAIL_FROM))
    msg["To"] = to_email
    # Keep only the headers a normal personal email carries. Bulk-mail headers
    # (List-Unsubscribe, Auto-Submitted, a hand-built Message-ID) make a low-volume
    # message look like automated marketing and push it to Spam/Promotions, so they
    # are intentionally omitted. The sending server adds its own Message-ID.
    msg["Date"] = formatdate(localtime=True)
    if SUPPORT_EMAIL and SUPPORT_EMAIL != MAIL_FROM:
        msg["Reply-To"] = SUPPORT_EMAIL
    # Plain text must come first in multipart/alternative (least-to-most preferred).
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=20) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(MAIL_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(MAIL_FROM, [to_email], msg.as_string())
        logger.info("✅ Email sent to %s (%s)", to_email, subject)
        return True
    except Exception as e:
        logger.error("❌ Failed to send email to %s: %s", to_email, e)
        return False


async def _send(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Async wrapper — offloads the blocking SMTP call to a thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _send_sync, to_email, subject, html_body, text_body
    )


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------
def _wrap(title: str, body_html: str, cta_text: Optional[str] = None, cta_url: Optional[str] = None) -> str:
    # Deliberately plain: no header bar, logo, coloured button, or marketing
    # footer. A simple text email from a personal-style address is far less
    # likely to be flagged as spam than a branded HTML template with a big CTA
    # button linking to an external domain. The link is shown as plain text.
    action = ""
    if cta_text and cta_url:
        action = f"""
    <p style="margin:0 0 16px 0;"><a href="{cta_url}" style="color:#1a56db;">{cta_text}</a></p>
    <p style="margin:0 0 16px 0;color:#666666;font-size:13px;">
      Or paste this link into your browser:<br>{cta_url}
    </p>"""
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#222222;">
  <div style="max-width:540px;margin:0 auto;padding:24px 20px;font-size:15px;line-height:1.6;">
    <p style="margin:0 0 16px 0;">{body_html}</p>
    {action}
    <p style="margin:24px 0 0 0;color:#888888;font-size:12px;">
      Questions? Just reply to this email or write to {SUPPORT_EMAIL}.
    </p>
  </div>
</body></html>"""


# ---------------------------------------------------------------------------
# Public senders
# ---------------------------------------------------------------------------
async def send_verification_email(to_email: str, name: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/verify-email?token={token}"
    subject = "Confirm your email address"
    html = _wrap(
        "Confirm your email",
        f"Hi {name or 'there'},<br><br>Thanks for signing up. "
        "Please confirm your email address to activate your account. "
        "This link expires soon for your security.",
        cta_text="Confirm my email address",
        cta_url=link,
    )
    text = (
        f"Hi {name or 'there'},\n\nThanks for signing up. Confirm your email address "
        f"by opening this link:\n{link}\n\n"
        f"If you did not create this account, you can ignore this email."
    )
    return await _send(to_email, subject, html, text)


async def send_password_reset_email(to_email: str, name: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your password"
    html = _wrap(
        "Reset your password",
        f"Hi {name or 'there'},<br><br>We received a request to reset your "
        "password. Use the link below to choose a new one. It expires shortly. "
        "If you didn't request this, you can safely ignore this email and your "
        "password will not change.",
        cta_text="Reset my password",
        cta_url=link,
    )
    text = (
        f"Hi {name or 'there'},\n\nReset your password using this link:\n{link}\n\n"
        f"If you did not request this, ignore this email."
    )
    return await _send(to_email, subject, html, text)


async def send_welcome_email(to_email: str, name: str) -> bool:
    subject = "Your account is ready"
    html = _wrap(
        "Welcome aboard",
        f"Hi {name or 'there'},<br><br>Your account is now verified and ready. "
        "You can sign in any time.",
        cta_text="Sign in",
        cta_url=f"{FRONTEND_URL}/login",
    )
    text = f"Hi {name or 'there'},\n\nYour account is verified and ready. Sign in at {FRONTEND_URL}/login"
    return await _send(to_email, subject, html, text)


async def send_password_changed_email(to_email: str, name: str) -> bool:
    subject = "Your password was changed"
    html = _wrap(
        "Password updated",
        f"Hi {name or 'there'},<br><br>This confirms that your "
        f"password was just changed. If this wasn't you, contact "
        f"<a href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a> immediately.",
    )
    text = (
        f"Hi {name or 'there'},\n\nYour password was changed. "
        f"If this wasn't you, contact {SUPPORT_EMAIL} immediately."
    )
    return await _send(to_email, subject, html, text)


# ---------------------------------------------------------------------------
# Admin notifications & billing lifecycle
# ---------------------------------------------------------------------------
# Where operational alerts are delivered. Defaults to the official inbox.
ADMIN_NOTIFY_EMAIL = os.getenv("ADMIN_NOTIFY_EMAIL") or os.getenv("SUPPORT_EMAIL", "vadg.office@gmail.com")


async def _notify_admin(subject: str, body_html: str, text_body: str) -> bool:
    """Send an operational alert to the admin inbox."""
    html = _wrap(subject, body_html)
    return await _send(ADMIN_NOTIFY_EMAIL, f"[VADG Admin] {subject}", html, text_body)


async def send_admin_new_user(name: str, email: str) -> bool:
    """Notify admin that a new user registered."""
    body = (
        f"A new user just registered on VADG.<br><br>"
        f"<strong>Name:</strong> {name}<br>"
        f"<strong>Email:</strong> {email}"
    )
    text = f"New VADG user registered.\nName: {name}\nEmail: {email}"
    return await _notify_admin("New user registered", body, text)


async def send_admin_purchase_request(
    user_name: str, user_email: str, plan_name: str, amount_inr: int,
    credits: int, order_id: str, payment_reference: str = "", note: str = "",
) -> bool:
    """Notify admin that a user has requested a plan and (claims to have) paid."""
    body = (
        f"A user has requested a plan and is awaiting approval.<br><br>"
        f"<strong>User:</strong> {user_name} ({user_email})<br>"
        f"<strong>Plan:</strong> {plan_name}<br>"
        f"<strong>Amount:</strong> ₹{amount_inr}<br>"
        f"<strong>Credits:</strong> {credits}<br>"
        f"<strong>Order ID:</strong> {order_id}<br>"
        f"<strong>Payment reference:</strong> {payment_reference or '—'}<br>"
        f"<strong>Note:</strong> {note or '—'}<br><br>"
        f"Verify the payment, then approve or reject the request from the admin "
        f"dashboard → Payments."
    )
    text = (
        f"VADG plan request awaiting approval.\n"
        f"User: {user_name} ({user_email})\nPlan: {plan_name}\n"
        f"Amount: Rs.{amount_inr}\nCredits: {credits}\nOrder: {order_id}\n"
        f"Payment ref: {payment_reference or '-'}\nNote: {note or '-'}\n"
        f"Approve/reject from the admin dashboard."
    )
    return await _notify_admin("New plan purchase request", body, text)


async def send_purchase_request_ack(to_email: str, name: str, plan_name: str, amount_inr: int, order_id: str) -> bool:
    """Acknowledge to the user that their request was received (pending verification)."""
    subject = "We received your plan request"
    html = _wrap(
        "Request received",
        f"Hi {name or 'there'},<br><br>Thanks — we've received your request for the "
        f"<strong>{plan_name}</strong> plan (₹{amount_inr}).<br><br>"
        f"Your reference is <strong>{order_id}</strong>. Our team will verify your "
        f"payment and activate your report credits, usually within a few hours. "
        f"You'll get an email as soon as it's approved.<br><br>"
        f"If you haven't completed the payment yet, please follow the payment "
        f"instructions shown on the pricing page.",
    )
    text = (
        f"Hi {name or 'there'},\n\nWe received your request for the {plan_name} plan "
        f"(Rs.{amount_inr}). Reference: {order_id}. We'll verify your payment and "
        f"activate your credits shortly.\n\n- VADG"
    )
    return await _send(to_email, subject, html, text)


async def send_purchase_approved(to_email: str, name: str, plan_name: str, credits: int, new_balance: int) -> bool:
    """Tell the user their purchase was approved and credits added."""
    subject = "Your plan is active"
    html = _wrap(
        "Plan activated",
        f"Hi {name or 'there'},<br><br>Good news — your <strong>{plan_name}</strong> "
        f"plan has been approved and <strong>{credits} report credit(s)</strong> "
        f"have been added to your account.<br><br>"
        f"Your available report credits: <strong>{new_balance}</strong>.",
        cta_text="Start an assessment",
        cta_url=f"{FRONTEND_URL}/vadg-ai-diagnosis",
    )
    text = (
        f"Hi {name or 'there'},\n\nYour {plan_name} plan is approved. {credits} "
        f"credit(s) added. Available credits: {new_balance}.\n\n- VADG"
    )
    return await _send(to_email, subject, html, text)


async def send_purchase_rejected(to_email: str, name: str, plan_name: str, reason: str = "") -> bool:
    """Tell the user their request could not be approved."""
    subject = "About your plan request"
    html = _wrap(
        "Request not approved",
        f"Hi {name or 'there'},<br><br>We were unable to approve your request for the "
        f"<strong>{plan_name}</strong> plan at this time."
        + (f"<br><br><strong>Reason:</strong> {reason}" if reason else "")
        + f"<br><br>If you believe this is a mistake or you have completed the "
        f"payment, please reply to <a href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a> "
        f"with your payment reference and we'll help you out.",
    )
    text = (
        f"Hi {name or 'there'},\n\nWe couldn't approve your {plan_name} request."
        + (f" Reason: {reason}." if reason else "")
        + f" Contact {SUPPORT_EMAIL} with your payment reference for help.\n\n- VADG"
    )
    return await _send(to_email, subject, html, text)
