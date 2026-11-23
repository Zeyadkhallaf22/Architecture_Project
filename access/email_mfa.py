"""One-time email code for sign-in when the face camera is unavailable.

The code is kept in memory for five minutes and is not written to the audit log.
Mail is sent only when this PowerShell window has the SMTP settings.
"""

from __future__ import annotations

import os
import re
import secrets
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr

from access.auth import _same_secret, authenticate

CODE_SECONDS = 300
SENDER_NAME = "VISIONHMI"
MAIL_NAME = "Data Center Unified Operations"
MARIAM_EMAIL = "mariiaamsalem003@gmail.com"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_pending: dict[str, tuple[str, float]] = {}


def resolve_recipient(username: str, email: str) -> str:
    """Use the address the operator typed. Mariam's address is filled in when the box is empty."""
    typed = email.strip()
    if typed:
        return typed
    if username.strip().casefold() == "mariamsalem":
        return MARIAM_EMAIL
    return ""


def _mail_settings() -> dict[str, str] | None:
    host = os.environ.get("MFA_SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    user = os.environ.get("MFA_SMTP_USER", MARIAM_EMAIL).strip() or MARIAM_EMAIL
    password = os.environ.get("MFA_SMTP_PASSWORD", "").strip()
    port = os.environ.get("MFA_SMTP_PORT", "587").strip() or "587"
    if not password:
        return None
    return {"host": host, "user": user, "password": password, "port": port}


def send_login_email(code: str, recipient: str) -> None:
    settings = _mail_settings()
    if settings is None or not _EMAIL.fullmatch(recipient):
        raise RuntimeError("email is not configured")
    message = EmailMessage()
    message["Subject"] = MAIL_NAME
    message["From"] = formataddr((SENDER_NAME, settings["user"]))
    message["To"] = recipient
    message.set_content(
        f"{MAIL_NAME}\n\n"
        f"Your {SENDER_NAME} sign-in code is {code}. It expires in 5 minutes."
    )
    with smtplib.SMTP(settings["host"], int(settings["port"]), timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings["user"], settings["password"])
        smtp.send_message(message)


def issue_email_code(username: str, password: str, email: str = "", sender=send_login_email) -> dict[str, object]:
    """Check the password, then mail a new 6-digit code. The code is not returned."""
    result = authenticate(username, password)
    if not result.get("ok"):
        return result
    recipient = resolve_recipient(str(result["username"]), email)
    if not _EMAIL.fullmatch(recipient):
        return {"ok": False, "error": "Enter a valid email address."}
    sender_account = os.environ.get("MFA_SMTP_USER", MARIAM_EMAIL).strip() or MARIAM_EMAIL
    if _mail_settings() is None and sender is send_login_email:
        return {
            "ok": False,
            "error": (
                f"VISIONHMI is the name on the message, not a mailbox. "
                f"The code is sent from {sender_account}. "
                "Set that Gmail account's app password in the dashboard window, then send again."
            ),
        }
    code = f"{secrets.randbelow(1_000_000):06d}"
    account = str(result["username"])
    _pending[account] = (code, time.time() + CODE_SECONDS)
    try:
        sender(code, recipient)
    except Exception:
        _pending.pop(account, None)
        return {
            "ok": False,
            "error": f"Gmail refused the sign-in for {sender_account}. Check the app password in the dashboard window.",
        }
    return {"ok": True, "username": account, "role": result.get("role") or "", "factor": "email-sent"}


def verify_email_code(username: str, password: str, code: str) -> dict[str, object]:
    """Accept the password plus the emailed code, once, before it expires."""
    result = authenticate(username, password)
    if not result.get("ok"):
        return result
    account = str(result["username"])
    pending = _pending.get(account)
    if pending is None or time.time() > pending[1]:
        _pending.pop(account, None)
        return {"ok": False, "error": "Email code expired. Send a new one."}
    if not _same_secret(code.strip(), pending[0]):
        return {"ok": False, "error": "Wrong email code"}
    _pending.pop(account, None)
    return {**result, "factor": "password+email"}
