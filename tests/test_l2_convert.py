import json
import tempfile
import unittest
from pathlib import Path

from wickhunter.backtest.l2_convert import convert_binance_depth_jsonl_to_replay


class TestL2Convert(unittest.TestCase):
    def test_convert_strict_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "depth_raw.jsonl"
            dst = Path(tmp) / "depth_replay.jsonl"
            src.write_text(
                '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[["100.0","1.0"]],"a":[]}\n',
                encoding="utf-8",
            )
            stats = convert_binance_depth_jsonl_to_replay(src, dst)
            self.assertEqual(stats.total_lines, 1)
            self.assertEqual(stats.written_events, 1)
            self.assertEqual(stats.skipped_lines, 0)

            row = json.loads(dst.read_text(encoding="utf-8").strip())
            self.assertEqual(row["event_type"], "depth_update")
            self.assertEqual(row["payload"]["symbol"], "BTCUSDT")

    def test_convert_lenient_skips_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "depth_raw_bad.jsonl"
            dst = Path(tmp) / "depth_replay_bad.jsonl"
            src.write_text(
                '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[],"a":[]}\n'
                '{"bad":true}\n',
                encoding="utf-8",
            )
            stats = convert_binance_depth_jsonl_to_replay(src, dst, strict=False)
            self.assertEqual(stats.total_lines, 2)
            self.assertEqual(stats.written_events, 1)
            self.assertEqual(stats.skipped_lines, 1)


if __name__ == "__main__":
    unittest.main()
