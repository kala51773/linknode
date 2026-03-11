import unittest
from pathlib import Path
from uuid import uuid4

from wickhunter.cli.main import (
    run_book_demo,
    run_bridge_demo,
    run_cancel_demo,
    run_demo,
    run_exchange_demo,
    run_exchange_signal_demo,
    run_exec_demo,
    run_m3_demo,
    run_m3_replay_file,
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
        path = Path(__file__).parent / f"tmp_cli_replay_{uuid4().hex}.jsonl"
        try:
            path.write_text(
                '{"ts_ms": 3, "event_type": "fill", "payload": {}}\n'
                '{"ts_ms": 1, "event_type": "fill", "payload": {}}\n',
                encoding="utf-8",
            )
            output = run_m3_replay_file(str(path))
            self.assertIn("m3_events=2", output)
            self.assertIn("first_ts=1", output)
            self.assertIn("last_ts=3", output)
        finally:
            path.unlink(missing_ok=True)

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
