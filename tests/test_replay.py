import tempfile
import unittest
from pathlib import Path

from wickhunter.backtest.replay import EventReplayer, ReplayEvent


class TestReplay(unittest.TestCase):
    def test_events_are_sorted_by_ts(self) -> None:
        events = [
            ReplayEvent(ts_ms=3, event_type="b", payload={}),
            ReplayEvent(ts_ms=1, event_type="a", payload={}),
            ReplayEvent(ts_ms=2, event_type="c", payload={}),
        ]
        ordered = EventReplayer(events).run()
        self.assertEqual([e.ts_ms for e in ordered], [1, 2, 3])

    def test_load_jsonl_and_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                '{"ts_ms": 3, "event_type": "fill", "payload": {"qty": 1}}\n'
                '{"ts_ms": 1, "event_type": "quote", "payload": {}}\n',
                encoding="utf-8",
            )
            ordered = EventReplayer.from_jsonl(path).run()
            self.assertEqual([e.ts_ms for e in ordered], [1, 3])


if __name__ == "__main__":
    unittest.main()
