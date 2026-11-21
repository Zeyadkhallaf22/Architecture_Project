"""Boundary checks for the VisionHMI layers. No database required."""

from __future__ import annotations

import unittest

from access.auth import authenticate, role_for_name
from access.control_gate import authorize_control
from evidence.hub import EventHub


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

if __name__ == "__main__":
    unittest.main()
