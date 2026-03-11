import json
import tempfile
import unittest
from pathlib import Path

from wickhunter.backtest.depth_replay import run_depth_replay_jsonl


class TestDepthReplay(unittest.TestCase):
    def test_replay_snapshot_and_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depth_replay.jsonl"
            rows = [
                {
                    "ts_ms": 1,
                    "event_type": "depth_snapshot",
                    "payload": {
                        "last_update_id": 100,
                        "bids": [[99.0, 1.0]],
                        "asks": [[101.0, 1.0]],
                    },
                },
                {
                    "ts_ms": 2,
                    "event_type": "depth_update",
                    "payload": {
                        "first_update_id": 101,
                        "final_update_id": 101,
                        "bids": [[100.0, 2.0]],
                        "asks": [],
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            result = run_depth_replay_jsonl(str(path))
            self.assertEqual(result.total_events, 2)
            self.assertEqual(result.snapshot_events, 1)
            self.assertEqual(result.update_events, 1)
            self.assertEqual(result.gap_events, 0)
            self.assertEqual(result.ignored_non_depth_events, 0)
            self.assertEqual(result.best_bid, (100.0, 2.0))


    def test_replay_ignores_non_depth_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depth_non_depth.jsonl"
            rows = [
                {
                    "ts_ms": 1,
                    "event_type": "depth_snapshot",
                    "payload": {"last_update_id": 100, "bids": [[99.0, 1.0]], "asks": [[101.0, 1.0]]},
                },
                {"ts_ms": 2, "event_type": "fill", "payload": {"qty": 1}},
                {
                    "ts_ms": 3,
                    "event_type": "depth_update",
                    "payload": {"first_update_id": 101, "final_update_id": 101, "bids": [], "asks": [[100.5, 1.0]]},
                },
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            result = run_depth_replay_jsonl(str(path))
            self.assertEqual(result.total_events, 3)
            self.assertEqual(result.update_events, 1)
            self.assertEqual(result.skipped_events, 1)
            self.assertEqual(result.ignored_non_depth_events, 1)

    def test_replay_lenient_skips_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depth_gap.jsonl"
            rows = [
                {
                    "ts_ms": 1,
                    "event_type": "depth_snapshot",
                    "payload": {"last_update_id": 100, "bids": [[99.0, 1.0]], "asks": [[101.0, 1.0]]},
                },
                {
                    "ts_ms": 2,
                    "event_type": "depth_update",
                    "payload": {"first_update_id": 103, "final_update_id": 103, "bids": [], "asks": []},
                },
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            result = run_depth_replay_jsonl(str(path), strict=False)
            self.assertEqual(result.gap_events, 1)
            self.assertEqual(result.skipped_events, 1)


if __name__ == "__main__":
    unittest.main()
