"""Boundary checks for the VisionHMI layers. No database required."""

from __future__ import annotations

import unittest

from access.audit import entries, record
from access.auth import authenticate, role_for_name
from access.control_gate import authorize_control
from evidence.envelope import accept
from evidence.hub import EventHub
from evidence.query import ids_evidence


class BoundaryTests(unittest.TestCase):
    def test_demo_account_gets_admin_from_the_csv(self) -> None:
        result = authenticate("mariamsalem", "mariam1234")
        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "Admin")
        self.assertEqual(role_for_name("Mariam"), "Admin")

    def test_wrong_password_stays_out(self) -> None:
        result = authenticate("mariamsalem", "nope")
        self.assertFalse(result["ok"])

    def test_chatbot_and_gestures_cannot_control_equipment(self) -> None:
        for caller in ("chatbot", "analytics", "gesture", "assistant"):
            allowed, _reason = authorize_control(caller, "Admin")
            self.assertFalse(allowed)

    def test_operator_dashboard_can_control_and_engineer_cannot(self) -> None:
        allowed, _reason = authorize_control("hmi", "Operator")
        self.assertTrue(allowed)
        allowed, _reason = authorize_control("hmi", "Engineer")
        self.assertFalse(allowed)

    def test_duplicate_event_is_delivered_once(self) -> None:
        hub = EventHub()
        seen: list[str] = []
        hub.subscribe("process.reading", lambda event: seen.append(event["eventId"]))
        event = {"eventId": "proc-1-9", "eventType": "process.reading"}
        self.assertTrue(hub.publish(event))
        self.assertFalse(hub.publish(event))
        self.assertEqual(seen, ["proc-1-9"])

    def test_intake_rejects_a_broken_event_and_ignores_a_repeat(self) -> None:
        rejected = accept({"eventId": "bad-1"})
        self.assertEqual(rejected["code"], "INVALID_EVENT")
        complete = {
            "eventId": "proc-test-1",
            "sourceId": "ITSystemDataset",
            "assetId": "server-1",
            "eventType": "process.reading",
            "observedAt": "2026-11-22T00:00:00+00:00",
            "receivedAt": "2026-11-22T00:00:00+00:00",
            "qualityStatus": "replayed",
            "payload": {"cpuPercent": 10},
            "evidenceRef": "proc-test-1",
        }
        self.assertEqual(accept(complete)["status"], "accepted")
        self.assertEqual(accept(complete)["code"], "DUPLICATE_EVENT")

    def test_ids_query_returns_no_invented_detections(self) -> None:
        result = ids_evidence()
        self.assertEqual(result["code"], "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(result["records"], [])

    def test_audit_records_the_action_and_not_a_secret(self) -> None:
        item = record("mariamsalem", "sign-in", "denied")
        self.assertNotIn("password", item)
        self.assertEqual(entries()[-1]["outcome"], "denied")


if __name__ == "__main__":
    unittest.main()
