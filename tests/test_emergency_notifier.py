import json
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch
from uuid import uuid4

from wickhunter.common.emergency import EmergencyNotifier


class TestEmergencyNotifier(unittest.TestCase):
    def test_notify_persists_event_jsonl(self) -> None:
        path = Path(__file__).parent / f"tmp_emergency_{uuid4().hex}.jsonl"
        notifier = EmergencyNotifier(log_path=str(path))

        try:
            errors = notifier.notify(
                event_type="runtime_emergency",
                payload={"reason": "marketdata_latency", "symbols": ["BTCUSDT"]},
            )
            self.assertEqual(errors, [])

            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["event_type"], "runtime_emergency")
            self.assertEqual(row["payload"]["reason"], "marketdata_latency")
            self.assertEqual(row["payload"]["symbols"], ["BTCUSDT"])
        finally:
            path.unlink(missing_ok=True)

    def test_notify_collects_webhook_error(self) -> None:
        notifier = EmergencyNotifier(webhook_url="https://example.invalid/webhook")

        with patch("wickhunter.common.emergency.request.urlopen", side_effect=URLError("unreachable")):
            errors = notifier.notify(event_type="runtime_emergency", payload={"reason": "exchange_restricted"})

        self.assertEqual(len(errors), 1)
        self.assertIn("webhook_failed", errors[0])


if __name__ == "__main__":
    unittest.main()
