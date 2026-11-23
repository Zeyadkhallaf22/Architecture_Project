"""Module: sign-in. The password stays on the server. The role comes from Grad_role.csv."""

from __future__ import annotations

import csv
import hmac
from pathlib import Path

LOGIN_USERNAME = "mariamsalem"
LOGIN_PASSWORD = "mariam1234"
FALLBACK_CODE = "face-fallback"
ROSTER_PATH = Path(__file__).resolve().parents[1] / "Grad_role.csv"


def _same_secret(left: str, right: str) -> bool:
    a = left.encode("utf-8")
    b = right.encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def role_for_name(name: str) -> str:
    target = name.casefold().replace(" ", "")
    if not ROSTER_PATH.is_file():
        return ""
    with ROSTER_PATH.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            full = (row.get("Names") or "").strip()
            compact = full.casefold().replace(" ", "")
            if compact == target or compact.startswith(target):
                return (row.get("Role") or "").strip()
    return ""


def authenticate(username: str, password: str) -> dict[str, object]:
    """Check the demo account and attach the CSV role. Roles are not decided in the browser."""
    name = username.strip()
    if not _same_secret(name, LOGIN_USERNAME) or not _same_secret(password, LOGIN_PASSWORD):
        return {"ok": False, "error": "Wrong username or password"}
    return {"ok": True, "username": LOGIN_USERNAME, "role": role_for_name("Mariam Salem") or "Admin"}


def authenticate_fallback(username: str, password: str, code: str) -> dict[str, object]:
    """Password plus the fallback code. Used only when the face camera is unavailable."""
    result = authenticate(username, password)
    if not result.get("ok"):
        return result
    if not _same_secret(code.strip(), FALLBACK_CODE):
        return {"ok": False, "error": "Wrong fallback code"}
    return {**result, "factor": "password+code"}
