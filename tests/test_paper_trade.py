import unittest

from wickhunter.simulation.paper_trade import PaperTradeAccount


class TestPaperTradeAccount(unittest.TestCase):
    def test_long_stop_loss_close_and_pnl(self) -> None:
        account = PaperTradeAccount()
        account.open_position(
            symbol="BTC-USD-SWAP",
            side="LONG",
            qty=2.0,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            fee_bps=10.0,
        )

        close_res = account.on_mark_price(symbol="BTC-USD-SWAP", mark_price=95.0)

        self.assertIsNotNone(close_res)
        assert close_res is not None
        self.assertEqual(close_res.exit_reason, "stop_loss")
        self.assertEqual(close_res.realized_pnl, -10.0)
        self.assertAlmostEqual(close_res.fees, 0.39, places=8)
        self.assertAlmostEqual(close_res.net_pnl, -10.39, places=8)
        self.assertAlmostEqual(account.total_net_pnl, -10.39, places=8)

    def test_short_take_profit_close_and_pnl(self) -> None:
        account = PaperTradeAccount()
        account.open_position(
            symbol="ETH-USDT-SWAP",
            side="SHORT",
            qty=3.0,
            entry_price=100.0,
            stop_loss=108.0,
            take_profit=95.0,
            fee_bps=0.0,
        )

        close_res = account.on_mark_price(symbol="ETH-USDT-SWAP", mark_price=95.0)

        self.assertIsNotNone(close_res)
        assert close_res is not None
        self.assertEqual(close_res.exit_reason, "take_profit")
        self.assertEqual(close_res.realized_pnl, 15.0)
        self.assertEqual(close_res.fees, 0.0)
        self.assertEqual(close_res.net_pnl, 15.0)
        self.assertEqual(account.total_realized_pnl, 15.0)

    def test_mark_without_trigger_holds_position(self) -> None:
        account = PaperTradeAccount()
        account.open_position(
            symbol="BTC-USDT-SWAP",
            side="LONG",
            qty=1.0,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit=120.0,
        )

        close_res = account.on_mark_price(symbol="BTC-USDT-SWAP", mark_price=105.0)

        self.assertIsNone(close_res)
        self.assertEqual(account.total_net_pnl, 0.0)

    def test_manual_close(self) -> None:
        account = PaperTradeAccount()
        account.open_position(
            symbol="BTC-USDT-SWAP",
            side="LONG",
            qty=1.0,
            entry_price=100.0,
        )

        close_res = account.close_position(symbol="BTC-USDT-SWAP", exit_price=102.0, reason="manual_close")

        self.assertEqual(close_res.exit_reason, "manual_close")
        self.assertEqual(close_res.realized_pnl, 2.0)
        self.assertEqual(account.total_realized_pnl, 2.0)

    def test_reject_duplicate_open_position(self) -> None:
        account = PaperTradeAccount()
        account.open_position(
            symbol="BTC-USDT-SWAP",
            side="LONG",
            qty=1.0,
            entry_price=100.0,
        )
        with self.assertRaises(ValueError):
            account.open_position(
                symbol="BTC-USDT-SWAP",
                side="SHORT",
                qty=1.0,
                entry_price=99.0,
            )


if __name__ == "__main__":
    unittest.main()
