"""Append-only record of sign-in denials, report exports, and control attempts."""

from __future__ import annotations

from datetime import datetime, timezone

_entries: list[dict[str, str]] = []


def record(actor: str, action: str, outcome: str, target: str = "") -> dict[str, str]:
    item = {
        "at": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "outcome": outcome,
        "target": target,
    }
    _entries.append(item)
    if len(_entries) > 200:
        del _entries[:-200]
    return item


def entries() -> list[dict[str, str]]:
    return list(_entries)
