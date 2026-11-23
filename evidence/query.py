"""IF-04 reads events the broker has delivered."""

from __future__ import annotations

from evidence.envelope import get_hub


def operational_evidence(asset_id: str = "", event_type: str = "") -> dict[str, object]:
    rows = get_hub().records()
    if asset_id:
        rows = [row for row in rows if str(row.get("assetId") or "") == asset_id]
    if event_type:
        rows = [row for row in rows if str(row.get("eventType") or "") == event_type]
    return {
        "status": "ok" if rows else "empty",
        "code": "OK",
        "records": rows,
    }


def ids_evidence() -> dict[str, object]:
    return {
        "status": "unavailable",
        "code": "DEPENDENCY_UNAVAILABLE",
        "records": [],
        "message": "IDS is not part of this prototype. No detections were created.",
    }
