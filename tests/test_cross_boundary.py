"""One test that crosses ingestion, evidence, detection, and the control gate."""

from __future__ import annotations

import unittest

from access.auth import authenticate_fallback
from access.control_gate import authorize_control
from evidence.envelope import accept
from evidence.hub import HUB
from evidence.query import operational_evidence
from intelligence.ids import clear, findings, install


class CrossBoundaryTests(unittest.TestCase):
    def test_reading_is_stored_detected_and_cannot_control(self) -> None:
        clear()
        install(HUB)
        event = {
            "eventId": "proc-cross-1",
            "sourceId": "ITSystemDataset",
            "assetId": "server-2",
            "eventType": "process.reading",
            "observedAt": "2026-11-23T00:00:00+00:00",
            "receivedAt": "2026-11-23T00:00:00+00:00",
            "qualityStatus": "replayed",
            "payload": {"cpuPercent": 95, "tempC": 40, "networkMbps": 10, "latencyMs": 4},
            "evidenceRef": "proc-cross-1",
        }
        self.assertEqual(accept(event)["status"], "accepted")
        stored = operational_evidence("server-2", "process.reading")
        self.assertEqual(stored["records"][-1]["eventId"], "proc-cross-1")
        recorded = [item for item in findings()["records"] if item["eventId"] == "proc-cross-1"]
        self.assertEqual(recorded[0]["moduleId"], "C")
        allowed, _reason = authorize_control("chatbot", "Admin")
        self.assertFalse(allowed)
        fallback = authenticate_fallback("mariamsalem", "mariam1234", "face-fallback")
        self.assertTrue(fallback["ok"])
        self.assertEqual(fallback["factor"], "password+code")


if __name__ == "__main__":
    unittest.main()
