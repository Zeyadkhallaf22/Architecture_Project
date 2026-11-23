"""Measured checks for the Milestone 3 quality evidence."""

from __future__ import annotations

import time
import unittest

from evidence.envelope import accept
from evidence.hub import HUB
from intelligence.ids import clear, install


def intake_timing(count: int = 200) -> dict[str, float]:
    start = time.perf_counter()
    for index in range(count):
        accept(
            {
                "eventId": f"perf-{index}",
                "sourceId": "ITSystemDataset",
                "assetId": "server-1",
                "eventType": "process.reading",
                "observedAt": "2026-11-23T00:00:00+00:00",
                "receivedAt": "2026-11-23T00:00:00+00:00",
                "qualityStatus": "replayed",
                "payload": {"cpuPercent": 10, "tempC": 40},
                "evidenceRef": f"perf-{index}",
            }
        )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {"events": count, "elapsed_ms": round(elapsed_ms, 2), "per_event_ms": round(elapsed_ms / count, 3)}


class QualityMeasureTests(unittest.TestCase):
    def test_replay_intake_stays_under_one_millisecond_per_event(self) -> None:
        clear()
        install(HUB)
        result = intake_timing()
        self.assertLess(result["per_event_ms"], 1.0)
        print("INTAKE", result)


if __name__ == "__main__":
    unittest.main()
