"""Read-only detection modules. They record findings and cannot control equipment."""

from __future__ import annotations

import threading
from typing import Any, Callable

Detector = Callable[[dict[str, Any]], dict[str, Any] | None]

_lock = threading.Lock()
_findings: list[dict[str, Any]] = []
_installed = False


def _finding(module_id: str, event: dict[str, Any], reason: str) -> dict[str, Any]:
    event_id = str(event.get("eventId") or "")
    return {
        "findingId": f"{module_id}-{event_id}",
        "moduleId": module_id,
        "eventId": event_id,
        "assetId": event.get("assetId"),
        "eventType": event.get("eventType"),
        "observedAt": event.get("observedAt"),
        "severity": "high",
        "reason": reason,
        "evidenceRef": event.get("evidenceRef") or event_id,
    }


def module_a(event: dict[str, Any]) -> dict[str, Any] | None:
    """Network rule: high latency."""
    payload = event.get("payload") or {}
    latency = payload.get("latencyMs")
    if latency is None or float(latency) < 50:
        return None
    return _finding("A", event, "Latency is at or above 50 ms.")


def module_b(event: dict[str, Any]) -> dict[str, Any] | None:
    """Network rule: high throughput. Independent of module A."""
    payload = event.get("payload") or {}
    network = payload.get("networkMbps")
    if network is None or float(network) < 500:
        return None
    return _finding("B", event, "Network throughput is at or above 500 Mbps.")


def module_c(event: dict[str, Any]) -> dict[str, Any] | None:
    """Process rule: high CPU or temperature."""
    payload = event.get("payload") or {}
    cpu = payload.get("cpuPercent")
    temp = payload.get("tempC")
    if cpu is not None and float(cpu) >= 90:
        return _finding("C", event, "CPU is at or above 90 percent.")
    if temp is not None and float(temp) >= 75:
        return _finding("C", event, "Temperature is at or above 75 C.")
    return None


def _keep(found: dict[str, Any] | None) -> None:
    if not found:
        return
    with _lock:
        if any(item["findingId"] == found["findingId"] for item in _findings):
            return
        _findings.append(found)


def _on_network(event: dict[str, Any]) -> None:
    _keep(module_a(event))
    _keep(module_b(event))


def _on_process(event: dict[str, Any]) -> None:
    _keep(module_c(event))


def install(hub: Any) -> None:
    global _installed
    if _installed:
        return
    hub.subscribe("network.observation", _on_network)
    hub.subscribe("process.reading", _on_process)
    _installed = True


def findings() -> dict[str, object]:
    with _lock:
        rows = [dict(item) for item in _findings]
    return {"status": "ok" if rows else "empty", "code": "OK", "records": rows}


def clear() -> None:
    """Remove recorded findings. Used by tests."""
    with _lock:
        _findings.clear()
