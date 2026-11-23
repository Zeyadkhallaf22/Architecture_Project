"""Boundary checks for the VisionHMI layers. No database required."""

from __future__ import annotations

import unittest

from access.audit import entries, record
from access.auth import authenticate, role_for_name
from access.email_mfa import MARIAM_EMAIL, issue_email_code, verify_email_code
from chatbot_server import answer_from_facts
from access.control_gate import authorize_control
from evidence.envelope import accept
from evidence.hub import HUB, EventHub
from intelligence.ids import clear, findings, install, module_a, module_c


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

    def test_intake_follows_the_configured_broker(self) -> None:
        from evidence.envelope import configure_hub, get_hub

        other = EventHub()
        previous = get_hub()
        configure_hub(other)
        try:
            routed = {
                "eventId": "routed-1",
                "sourceId": "ITSystemDataset",
                "assetId": "server-3",
                "eventType": "process.reading",
                "observedAt": "2026-11-23T00:00:00+00:00",
                "receivedAt": "2026-11-23T00:00:00+00:00",
                "qualityStatus": "replayed",
                "payload": {"cpuPercent": 5},
                "evidenceRef": "routed-1",
            }
            self.assertEqual(accept(routed)["status"], "accepted")
            self.assertEqual(other.records()[-1]["eventId"], "routed-1")
        finally:
            configure_hub(previous)

    def test_ids_records_a_detection_and_ignores_a_normal_reading(self) -> None:
        clear()
        install(HUB)
        normal = {
            "eventId": "net-normal-1",
            "eventType": "network.observation",
            "payload": {"latencyMs": 4, "networkMbps": 10},
            "evidenceRef": "net-normal-1",
        }
        self.assertIsNone(module_a(normal))
        self.assertIsNone(module_c({"eventType": "process.reading", "payload": {"cpuPercent": 10, "tempC": 40}}))
        high = {
            "eventId": "net-high-1",
            "sourceId": "ITSystemDataset",
            "assetId": "server-1",
            "eventType": "network.observation",
            "observedAt": "2026-11-23T00:00:00+00:00",
            "receivedAt": "2026-11-23T00:00:00+00:00",
            "qualityStatus": "replayed",
            "payload": {"latencyMs": 80, "networkMbps": 12},
            "evidenceRef": "net-high-1",
        }
        self.assertEqual(accept(high)["status"], "accepted")
        recorded = findings()["records"]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["moduleId"], "A")
        self.assertEqual(recorded[0]["evidenceRef"], "net-high-1")

    def test_email_code_works_once_and_is_not_returned(self) -> None:
        seen: dict[str, str] = {}

        def capture(code: str, recipient: str) -> None:
            seen["code"] = code
            seen["recipient"] = recipient

        issued = issue_email_code("mariamsalem", "mariam1234", sender=capture)
        self.assertTrue(issued["ok"])
        self.assertEqual(seen["recipient"], MARIAM_EMAIL)
        self.assertNotIn(seen["code"], issued.values())
        typed = issue_email_code("mariamsalem", "mariam1234", "other@example.com", sender=capture)
        self.assertTrue(typed["ok"])
        self.assertEqual(seen["recipient"], "other@example.com")
        self.assertFalse(verify_email_code("mariamsalem", "mariam1234", "face-fallback")["ok"])
        accepted = verify_email_code("mariamsalem", "mariam1234", seen["code"])
        self.assertTrue(accepted["ok"])
        self.assertEqual(accepted["factor"], "password+email")
        self.assertFalse(verify_email_code("mariamsalem", "mariam1234", seen["code"])["ok"])

    def test_recommendation_question_uses_the_analytics_tab_records(self) -> None:
        facts = [
            {
                "section": "risk",
                "text": "Severe risk summary: business risk is High with score 45. 7 critical recommendations and 4 high recommendations.",
            },
            {
                "section": "recommendation",
                "text": "AI recommendation high for Server 2: Server 2 has low CPU headroom. Evidence: CPU is 53.2%. Action: Review workload growth.",
            },
        ]
        reply = answer_from_facts("what is your recommendations?", facts)
        self.assertIn("Action: Review workload growth", reply)
        self.assertNotIn("Severe risk summary", reply)

    def test_active_alarm_question_returns_only_active_alarms(self) -> None:
        facts = [
            {"section": "server", "text": "Server 1 is ONLINE. CPU 77.6%, RAM 60.5%. Alarms: CPU, temperature, and down tag flags are clear."},
            {"section": "alarms", "text": "Alarm history has 5 events and 2 active."},
            {"section": "alarms", "text": "Active alarm on Server 1 at 2026-08-10: Server 1 taken offline. Severity CRITICAL."},
            {"section": "alarms", "text": "Cleared alarm on Server 4 at 2026-08-09: temperature recovered. Severity WARNING."},
            {"section": "metric", "text": "Server 1 CPU is 77.6%."},
        ]
        reply = answer_from_facts("give me only active alarms", facts)
        self.assertIn("Active alarm on Server 1", reply)
        self.assertIn("2 active", reply)
        self.assertNotIn("tag flags are clear", reply)
        self.assertNotIn("Cleared alarm", reply)
        self.assertNotIn("CPU is 77.6%", reply)

    def test_audit_records_the_action_and_not_a_secret(self) -> None:
        item = record("mariamsalem", "sign-in", "denied")
        self.assertNotIn("password", item)
        self.assertEqual(entries()[-1]["outcome"], "denied")


if __name__ == "__main__":
    unittest.main()
