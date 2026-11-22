"""Module: map one replayed IT-dataset row into the IF-02 event envelope."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from evidence.envelope import accept
from evidence.schema import QUALITY_REPLAYED


def publish_server_sample(
    server: int,
    row_id: int,
    cpu: float,
    temp: float,
    network_mbps: float,
    latency_ms: float,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    asset = f"server-{int(server)}"
    payload = {
        "cpuPercent": float(cpu),
        "tempC": float(temp),
        "networkMbps": float(network_mbps),
        "latencyMs": float(latency_ms),
    }
    results = []
    for event_type, event_id in (
        ("process.reading", f"proc-{server}-{row_id}"),
        ("network.observation", f"net-{server}-{row_id}"),
    ):
        results.append(
            accept(
                {
                    "eventId": event_id,
                    "sourceId": "ITSystemDataset",
                    "assetId": asset,
                    "eventType": event_type,
                    "observedAt": now,
                    "receivedAt": now,
                    "qualityStatus": QUALITY_REPLAYED,
                    "payload": payload,
                    "evidenceRef": event_id,
                }
            )
        )
    return results
