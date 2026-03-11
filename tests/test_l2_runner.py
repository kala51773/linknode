import json
import tempfile
import unittest
from pathlib import Path

from wickhunter.backtest.l2_runner import run_l2_backtest_jsonl


class TestL2Runner(unittest.TestCase):
    def test_l2_backtest_outputs_microstructure_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l2_replay.jsonl"
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
                {
                    "ts_ms": 3,
                    "event_type": "depth_update",
                    "payload": {
                        "first_update_id": 102,
                        "final_update_id": 102,
                        "bids": [],
                        "asks": [[100.8, 1.0]],
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = run_l2_backtest_jsonl(str(path))
            self.assertEqual(result.total_events, 3)
            self.assertEqual(result.depth_events, 3)
            self.assertEqual(result.gap_events, 0)
            self.assertEqual(result.ignored_non_depth_events, 0)
            self.assertIsNotNone(result.avg_spread_bps)
            self.assertGreater(result.avg_depth_5bp_bid, 0.0)

    def test_l2_backtest_lenient_skips_gap_and_non_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l2_gap.jsonl"
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
                    "event_type": "fill",
                    "payload": {"qty": 1},
                },
                {
                    "ts_ms": 3,
                    "event_type": "depth_update",
                    "payload": {
                        "first_update_id": 110,
                        "final_update_id": 110,
                        "bids": [],
                        "asks": [],
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = run_l2_backtest_jsonl(str(path), strict=False)
            self.assertEqual(result.gap_events, 1)
            self.assertEqual(result.ignored_non_depth_events, 1)
            self.assertEqual(result.skipped_events, 2)


if __name__ == "__main__":
    unittest.main()
