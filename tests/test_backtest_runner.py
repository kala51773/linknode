import tempfile
import unittest
from pathlib import Path

from wickhunter.backtest.runner import BacktestRunner


class TestBacktestRunner(unittest.TestCase):
    def test_run_jsonl_builds_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fills.jsonl"
            path.write_text(
                '{"ts_ms": 1, "event_type": "fill", "payload": {"gross_pnl": 10.0, "fees": 1.0, "funding": 0.5, "hedge_notional": 1000.0}}\n'
                '{"ts_ms": 2, "event_type": "quote", "payload": {}}\n'
                '{"ts_ms": 3, "event_type": "fill", "payload": {"gross_pnl": -2.0, "fees": 0.2, "funding": 0.0, "hedge_notional": 500.0}}\n',
                encoding="utf-8",
            )
            result = BacktestRunner().run_jsonl(str(path))

            self.assertEqual(result.event_count, 3)
            self.assertEqual(result.fill_count, 2)
            self.assertEqual(result.skipped_fill_count, 0)
            self.assertEqual(result.skipped_fill_ratio, 0.0)
            self.assertEqual(result.total_net_pnl, 6.3)
            self.assertEqual(result.avg_net_pnl, 3.15)
            self.assertGreater(result.avg_hedge_latency_ms, 0)
            self.assertGreater(result.avg_slippage_bps, 0)
            self.assertEqual(result.win_rate, 0.5)
            self.assertEqual(result.max_drawdown, 2.2)
            self.assertEqual(result.profit_factor, 3.863636)

    def test_run_jsonl_lenient_skips_invalid_fill_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fills_bad.jsonl"
            path.write_text(
                '{"ts_ms": 1, "event_type": "fill", "payload": {"gross_pnl": 2.0, "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n'
                '{"ts_ms": 2, "event_type": "fill", "payload": {"gross_pnl": "oops", "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n',
                encoding="utf-8",
            )
            result = BacktestRunner().run_jsonl(str(path), strict=False)
            self.assertEqual(result.fill_count, 2)
            self.assertEqual(result.skipped_fill_count, 1)
            self.assertEqual(result.skipped_fill_ratio, 0.5)
            self.assertEqual(result.total_net_pnl, 1.9)

    def test_run_jsonl_strict_raises_on_invalid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fills_bad_strict.jsonl"
            path.write_text(
                '{"ts_ms": 1, "event_type": "fill", "payload": {"gross_pnl": "bad", "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                BacktestRunner().run_jsonl(str(path), strict=True)


if __name__ == "__main__":
    unittest.main()
