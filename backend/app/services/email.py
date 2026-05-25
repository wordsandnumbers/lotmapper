"""Outbound email via Resend.

If RESEND_API_KEY is unset, emails are logged to stdout instead of sent — keeps
dev/test environments happy without a real provider.
"""
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _send(to: list[str], subject: str, html: str) -> None:
    if not to:
        return
    if not settings.resend_api_key:
        logger.info(
            "EMAIL (no RESEND_API_KEY, not sent) to=%s subject=%r body=%s",
            to,
            subject,
            html,
        )
        return
    import resend

    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.email_from,
                "to": to,
                "subject": subject,
                "html": html,
            }
        )
    except Exception as exc:
        # Runs in a BackgroundTask — letting this bubble up produces an
        # unhandled-exception traceback in the server log and surfaces nothing
        # actionable. Log and swallow so a misconfigured sender (unverified
        # domain, bad key, transient 5xx) doesn't pollute logs.
        logger.error(
            "EMAIL send failed to=%s subject=%r: %s", to, subject, exc
        )


def send_access_request_notification(requester_email: str, owner_emails: list[str]) -> None:
    """Notify Owner accounts that someone has requested access."""
    subject = f"Access request from {requester_email}"
    html = (
        f"<p><strong>{requester_email}</strong> has requested access to the "
        f"Parking Lot Mapping Tool.</p>"
        f"<p>Sign in and visit the admin page to approve or ignore the request.</p>"
    )
    _send(owner_emails, subject, html)


def send_signup_link_email(
    recipient_email: str,
    signup_link: str,
    *,
    invited_by: Optional[str] = None,
) -> None:
    """Send the signed link that lets a user set their password.

    Used for both Owner-approved public requests and Owner-initiated invites.
    """
    if invited_by:
        subject = f"You've been invited by {invited_by}"
        intro = (
            f"<p><strong>{invited_by}</strong> has invited you to the "
            f"Parking Lot Mapping Tool.</p>"
        )
    else:
        subject = "Your access request was approved"
        intro = "<p>Your access request has been approved.</p>"
    html = (
        f"{intro}"
        f'<p>Click the link below to set your password and finish creating your account:</p>'
        f'<p><a href="{signup_link}">{signup_link}</a></p>'
        f"<p>This link will expire in 72 hours.</p>"
    )
    _send([recipient_email], subject, html)


def send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    """Send a link that lets a user choose a new password."""
    subject = "Reset your Lot Mapper password"
    html = (
        f"<p>We received a request to reset the password for your Lot Mapper account.</p>"
        f'<p>Click the link below to choose a new password:</p>'
        f'<p><a href="{reset_link}">{reset_link}</a></p>'
        f"<p>This link will expire in 1 hour.</p>"
        f"<p>If you didn't request a password reset, you can safely ignore this email.</p>"
    )
    _send([recipient_email], subject, html)
