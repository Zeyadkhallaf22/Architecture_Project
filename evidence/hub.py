"""Module: in-process event hub. A repeated eventId is ignored."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], None]


class EventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._seen: set[str] = set()
        self._records: list[dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: dict[str, Any]) -> bool:
        event_id = str(event.get("eventId") or "")
        event_type = str(event.get("eventType") or "")
        with self._lock:
            if event_id and event_id in self._seen:
                return False
            if event_id:
                self._seen.add(event_id)
            self._records.append(dict(event))
            if len(self._records) > 500:
                self._records = self._records[-500:]
            handlers = list(self._handlers.get(event_type, ()))
        for handler in handlers:
            handler(dict(event))
        return True

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._records]


HUB = EventHub()
