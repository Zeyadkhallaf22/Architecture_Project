"""RabbitMQ broker for IF-03. One delivery per eventId. Subscribers see the message after the broker."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from typing import Any

import pika

EXCHANGE = "visionhmi.events"
QUEUE = "visionhmi.evidence"
DEFAULT_URL = "amqp://guest:guest@127.0.0.1:5672/"

EventHandler = Callable[[dict[str, Any]], None]


class RabbitBroker:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("RABBITMQ_URL") or DEFAULT_URL
        self._lock = threading.Lock()
        self._pub_lock = threading.Lock()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._seen: set[str] = set()
        self._dispatched: set[str] = set()
        self._records: list[dict[str, Any]] = []
        self._ready = threading.Event()
        self._pub: pika.BlockingConnection | None = None
        self._pub_channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def start(self) -> None:
        self._pub = pika.BlockingConnection(pika.URLParameters(self.url))
        self._pub_channel = self._pub.channel()
        self._pub_channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)

    def listen(self) -> None:
        threading.Thread(target=self._consume, name="rabbit-consumer", daemon=True).start()
        if not self._ready.wait(8):
            raise TimeoutError("RabbitMQ consumer did not start")

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: dict[str, Any]) -> bool:
        event_id = str(event.get("eventId") or "")
        with self._lock:
            if event_id and event_id in self._seen:
                return False
            if event_id:
                self._seen.add(event_id)
        body = json.dumps(event).encode("utf-8")
        try:
            with self._pub_lock:
                if self._pub_channel is None:
                    raise RuntimeError("RabbitMQ is not started")
                self._pub_channel.basic_publish(
                    exchange=EXCHANGE,
                    routing_key=str(event.get("eventType") or "event"),
                    body=body,
                    properties=pika.BasicProperties(delivery_mode=2, message_id=event_id or None),
                )
        except Exception:
            with self._lock:
                self._seen.discard(event_id)
            raise
        return True

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._records]

    def _consume(self) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self.url))
        channel = connection.channel()
        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        channel.queue_declare(QUEUE, durable=True)
        channel.queue_bind(QUEUE, EXCHANGE, routing_key="#")
        channel.basic_consume(QUEUE, self._on_message, auto_ack=False)
        self._ready.set()
        channel.start_consuming()

    def _on_message(self, channel: Any, method: Any, _properties: Any, body: bytes) -> None:
        event = json.loads(body.decode("utf-8"))
        event_id = str(event.get("eventId") or "")
        event_type = str(event.get("eventType") or "")
        with self._lock:
            if event_id and event_id in self._dispatched:
                channel.basic_ack(method.delivery_tag)
                return
            if event_id:
                self._dispatched.add(event_id)
            self._records.append(dict(event))
            if len(self._records) > 500:
                self._records = self._records[-500:]
            handlers = list(self._handlers.get(event_type, ()))
        for handler in handlers:
            handler(dict(event))
        channel.basic_ack(method.delivery_tag)
