import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wickhunter.cli.main import (
    run_book_demo,
    run_bridge_demo,
    run_download_l2_snapshot,
    run_convert_depth_jsonl,
    run_replay_depth_file,
    run_cancel_demo,
    run_demo,
    run_exchange_demo,
    run_exchange_signal_demo,
    run_exec_demo,
    run_m3_demo,
    run_m3_replay_file,
    run_backtest_file,
    run_mature_demo,
    run_portfolio_demo,
    run_quote_demo,
    run_runtime_demo,
    run_signal_demo,
    run_sync_demo,
)


class TestCli(unittest.TestCase):
    def test_run_demo_contains_key_context(self) -> None:
        output = run_demo()
        self.assertIn("binance_futures", output)
        self.assertIn("okx_swap", output)
        self.assertIn("HEDGE_A", output)

    def test_run_book_demo_contains_marketdata_fields(self) -> None:
        output = run_book_demo()
        self.assertIn("best_bid=", output)
        self.assertIn("best_ask=", output)
        self.assertIn("mid=", output)

    def test_run_sync_demo_contains_sync_fields(self) -> None:
        output = run_sync_demo()
        self.assertIn("synced=True", output)
        self.assertIn("best_bid=", output)
        self.assertIn("best_ask=", output)

    def test_run_quote_demo_contains_quote_fields(self) -> None:
        output = run_quote_demo()
        self.assertIn("armed=True", output)
        self.assertIn("levels=3", output)
        self.assertIn("reason=ok", output)

    def test_run_signal_demo_contains_signal_fields(self) -> None:
        output = run_signal_demo()
        self.assertIn("armed=True", output)
        self.assertIn("levels=3", output)
        self.assertIn("reason=ok", output)

    def test_run_mature_demo_contains_backend_fields(self) -> None:
        output = run_mature_demo()
        self.assertIn("backend=nautilus_trader", output)
        self.assertIn("quote_ok=True", output)
        self.assertIn("hedge_ok=True", output)

    def test_run_exchange_demo_contains_exchange_fields(self) -> None:
        output = run_exchange_demo()
        self.assertIn("exchange=binance_futures", output)
        self.assertIn("symbol=BTCUSDT", output)
        self.assertIn("update=[100,102]", output)

    def test_run_exchange_signal_demo_contains_pipeline_fields(self) -> None:
        output = run_exchange_signal_demo()
        self.assertIn("source=binance_normalized", output)
        self.assertIn("armed=True", output)
        self.assertIn("levels=3", output)

    def test_run_m3_demo_contains_report_fields(self) -> None:
        output = run_m3_demo()
        self.assertIn("m3_events=2", output)
        self.assertIn("first_ts=1001", output)
        self.assertIn("net_pnl=8.0", output)


    def test_run_m3_replay_file_from_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                '{"ts_ms": 3, "event_type": "fill", "payload": {}}\n'
                '{"ts_ms": 1, "event_type": "fill", "payload": {}}\n',
                encoding="utf-8",
            )
            output = run_m3_replay_file(str(path))
            self.assertIn("m3_events=2", output)
            self.assertIn("first_ts=1", output)
            self.assertIn("last_ts=3", output)


    def test_run_backtest_file_from_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fills.jsonl"
            path.write_text(
                '{"ts_ms": 2, "event_type": "fill", "payload": {"gross_pnl": 2.0, "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n'
                '{"ts_ms": 1, "event_type": "fill", "payload": {"gross_pnl": 1.0, "fees": 0.1, "funding": 0.0, "hedge_notional": 200.0}}\n',
                encoding="utf-8",
            )
            output = run_backtest_file(str(path))
            self.assertIn("events=2", output)
            self.assertIn("fills=2", output)
            self.assertIn("skipped_fills=0", output)
            self.assertIn("skipped_ratio=0.0", output)
            self.assertIn("net_pnl=2.8", output)
            self.assertIn("avg_net=1.4", output)
            self.assertIn("win_rate=1.0", output)
            self.assertIn("max_dd=0.0", output)
            self.assertIn("profit_factor=na", output)


    def test_run_backtest_file_lenient_skips_bad_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fills_bad.jsonl"
            path.write_text(
                '{"ts_ms": 1, "event_type": "fill", "payload": {"gross_pnl": 1.0, "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n'
                '{"ts_ms": 2, "event_type": "fill", "payload": {"gross_pnl": "bad", "fees": 0.1, "funding": 0.0, "hedge_notional": 100.0}}\n',
                encoding="utf-8",
            )
            output = run_backtest_file(str(path), strict=False)
            self.assertIn("events=2", output)
            self.assertIn("skipped_fills=1", output)
            self.assertIn("skipped_ratio=0.5", output)


    @patch("wickhunter.cli.main.fetch_binance_futures_depth_snapshot_with_fallback")
    @patch("wickhunter.cli.main.save_snapshot_as_replay_jsonl")
    def test_run_download_l2_snapshot(self, mock_save, mock_fetch) -> None:
        mock_fetch.return_value = type("Snap", (), {
            "symbol": "BTCUSDT",
            "last_update_id": 123,
            "bids": ((100.0, 1.0),),
            "asks": ((100.1, 2.0),),
            "source_url": "https://fapi1.binance.com/fapi/v1/depth?...",
        })()
        mock_save.return_value = "data/l2_snapshot.jsonl"

        output = run_download_l2_snapshot("BTCUSDT", "data/l2_snapshot.jsonl")
        self.assertIn("snapshot_saved=data/l2_snapshot.jsonl", output)
        self.assertIn("symbol=BTCUSDT", output)
        self.assertIn("source=https://fapi1.binance.com", output)


    def test_run_convert_depth_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw.jsonl"
            dst = Path(tmp) / "replay.jsonl"
            src.write_text(
                '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"b":[],"a":[]}\n'
                '{"invalid":true}\n',
                encoding="utf-8",
            )
            output = run_convert_depth_jsonl(str(src), str(dst), strict=False)
            self.assertIn("converted_total=2", output)
            self.assertIn("written=1", output)
            self.assertIn("skipped=1", output)


    def test_run_replay_depth_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay_depth.jsonl"
            path.write_text(
                '{"ts_ms":1,"event_type":"depth_snapshot","payload":{"last_update_id":100,"bids":[[99,1]],"asks":[[101,1]]}}\n'
                '{"ts_ms":2,"event_type":"depth_update","payload":{"first_update_id":101,"final_update_id":101,"bids":[[100,2]],"asks":[]}}\n',
                encoding="utf-8",
            )
            output = run_replay_depth_file(str(path))
            self.assertIn("events=2", output)
            self.assertIn("snapshots=1", output)
            self.assertIn("updates=1", output)
            self.assertIn("ignored_non_depth=0", output)

    def test_run_bridge_demo_contains_bridge_fields(self) -> None:
        output = run_bridge_demo()
        self.assertIn("bridge_ingested=2", output)
        self.assertIn("armed=True", output)
        self.assertIn("levels=3", output)

    def test_run_portfolio_demo_contains_portfolio_fields(self) -> None:
        output = run_portfolio_demo()
        self.assertIn("positions=2", output)
        self.assertIn("gross_notional=8000.0", output)

    def test_run_runtime_demo_contains_runtime_fields(self) -> None:
        output = run_runtime_demo()
        self.assertIn("runtime_ok=True", output)
        self.assertIn("quote=True", output)
        self.assertIn("hedge=True", output)

    def test_run_exec_demo_contains_execution_fields(self) -> None:
        output = run_exec_demo()
        self.assertIn("accepted=True", output)
        self.assertIn("reason=ok", output)
        self.assertIn("BTCUSDT", output)

    def test_run_cancel_demo_contains_decisions(self) -> None:
        output = run_cancel_demo()
        self.assertIn("d1=min_live_time", output)
        self.assertIn("d2=ok", output)
        self.assertIn("d3=cancel_rate_limit", output)


if __name__ == "__main__":
    unittest.main()
