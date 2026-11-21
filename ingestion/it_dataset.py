"""Module: map one replayed IT-dataset row into the common event model."""

from __future__ import annotations

from typing import Any

from evidence.hub import HUB
from evidence.schema import QUALITY_REPLAYED


def publish_server_sample(
    server: int,
    row_id: int,
    cpu: float,
    temp: float,
    network_mbps: float,
    latency_ms: float,
) -> None:
    base: dict[str, Any] = {
        "sourceId": "ITSystemDataset",
        "server": int(server),
        "cpuPercent": float(cpu),
        "tempC": float(temp),
        "networkMbps": float(network_mbps),
        "latencyMs": float(latency_ms),
        "qualityStatus": QUALITY_REPLAYED,
    }
    HUB.publish({**base, "eventId": f"proc-{server}-{row_id}", "eventType": "process.reading"})
    HUB.publish({**base, "eventId": f"net-{server}-{row_id}", "eventType": "network.observation"})
