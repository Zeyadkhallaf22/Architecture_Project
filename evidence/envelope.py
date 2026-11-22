"""IF-02 read-only intake. One event in, accepted, duplicate, or rejected out."""

from __future__ import annotations

from typing import Any

from evidence.hub import HUB

REQUIRED = (
    "eventId",
    "sourceId",
    "assetId",
    "eventType",
    "observedAt",
    "receivedAt",
    "qualityStatus",
    "payload",
)


def accept(event: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in REQUIRED if event.get(name) in (None, "")]
    event_id = str(event.get("eventId") or "")
    if missing:
        return {
            "status": "rejected",
            "code": "INVALID_EVENT",
            "eventId": event_id,
            "reason": "Missing " + ", ".join(missing),
        }
    if not HUB.publish(event):
        return {"status": "duplicate", "code": "DUPLICATE_EVENT", "eventId": event_id, "intakeRef": event_id}
    return {"status": "accepted", "code": "ACCEPTED", "eventId": event_id, "intakeRef": event_id}
