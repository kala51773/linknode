import unittest

from wickhunter.backtest.okx_tick_pair_backtest import (
    OKXTickPairBacktestConfig,
    OKXTradeTick,
    build_tick_price_frame,
    run_okx_tick_pair_backtest,
)


class TestOKXTickPairBacktest(unittest.TestCase):
    def test_build_tick_price_frame_forward_fills_two_symbols(self) -> None:
        trades_a = [
            OKXTradeTick(symbol="A", ts_ms=1000, price=100.0, size=1.0, side="buy", trade_id="1"),
            OKXTradeTick(symbol="A", ts_ms=1002, price=101.0, size=1.0, side="buy", trade_id="2"),
        ]
        trades_b = [
            OKXTradeTick(symbol="B", ts_ms=1001, price=50.0, size=1.0, side="sell", trade_id="3"),
            OKXTradeTick(symbol="B", ts_ms=1003, price=49.0, size=1.0, side="sell", trade_id="4"),
        ]

        frame = build_tick_price_frame(symbol_a="A", symbol_b="B", trades_a=trades_a, trades_b=trades_b)

        self.assertEqual(list(frame["ts_ms"]), [1001, 1002, 1003])
        self.assertEqual(list(frame["price_a"]), [100.0, 101.0, 101.0])
        self.assertEqual(list(frame["price_b"]), [50.0, 50.0, 49.0])

    def test_backtest_enters_only_on_extreme_tick_spread(self) -> None:
        trades_a = []
        trades_b = []
        for idx in range(1, 1500):
            trades_a.append(OKXTradeTick(symbol="A", ts_ms=idx * 2, price=100.0, size=1.0, side="buy", trade_id=f"a{idx}"))
            price_b = 100.0 if idx < 1200 else (70.0 if idx < 1250 else 100.0)
            trades_b.append(OKXTradeTick(symbol="B", ts_ms=idx * 2 + 1, price=price_b, size=1.0, side="sell", trade_id=f"b{idx}"))

        report, trades_df, equity = run_okx_tick_pair_backtest(
            symbol_a="A",
            symbol_b="B",
            trades_a=trades_a,
            trades_b=trades_b,
            config=OKXTickPairBacktestConfig(
                entry_z=4.0,
                exit_z=1.5,
                fee_bps=0.0,
                warmup_ticks=500,
                z_window=200,
                max_hold_ticks=500,
            ),
            periods_per_year=10_000,
        )

        self.assertGreater(report.ticks, 0)
        self.assertGreaterEqual(report.trades, 1)
        self.assertFalse(trades_df.empty)
        self.assertFalse(equity.empty)


if __name__ == "__main__":
    unittest.main()
