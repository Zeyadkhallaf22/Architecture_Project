"""Module: control gate. Only the dashboard may request a control change, and only for Admin or Operator.

The chatbot, analytics, and gestures are read-only. They cannot reach this path.
"""

from __future__ import annotations

READ_ONLY_CALLERS = {"chatbot", "analytics", "gesture", "assistant"}
CONTROL_ROLES = {"admin", "operator"}


def authorize_control(caller: str, role: str | None = None) -> tuple[bool, str]:
    who = (caller or "hmi").strip().casefold()
    if who in READ_ONLY_CALLERS:
        return False, "Read-only component cannot issue equipment commands."
    if who != "hmi":
        return False, "Only the dashboard can request equipment control."
    if role:
        if role.strip().casefold() not in CONTROL_ROLES:
            return False, "This role cannot control equipment."
    return True, "accepted"
