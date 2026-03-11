import unittest

from wickhunter.portfolio.position import Fill, Portfolio


class TestPortfolio(unittest.TestCase):
    def test_accumulate_and_reduce_position(self) -> None:
        pf = Portfolio()
        pf.on_fill(Fill(symbol="BTCUSDT", side="BUY", qty=1.0, price=100.0))
        pf.on_fill(Fill(symbol="BTCUSDT", side="BUY", qty=1.0, price=110.0))

        pos = pf.positions["BTCUSDT"]
        self.assertEqual(pos.qty, 2.0)
        self.assertEqual(pos.avg_price, 105.0)

        pf.on_fill(Fill(symbol="BTCUSDT", side="SELL", qty=0.5, price=120.0))
        pos = pf.positions["BTCUSDT"]
        self.assertEqual(pos.qty, 1.5)
        self.assertEqual(pos.avg_price, 105.0)

    def test_flip_position_sets_new_avg(self) -> None:
        pf = Portfolio()
        pf.on_fill(Fill(symbol="ETHUSDT", side="BUY", qty=1.0, price=100.0))
        pf.on_fill(Fill(symbol="ETHUSDT", side="SELL", qty=2.0, price=90.0))

        pos = pf.positions["ETHUSDT"]
        self.assertEqual(pos.qty, -1.0)
        self.assertEqual(pos.avg_price, 90.0)

    def test_gross_notional(self) -> None:
        pf = Portfolio()
        pf.on_fill(Fill(symbol="BTCUSDT", side="BUY", qty=0.1, price=50000.0))
        pf.on_fill(Fill(symbol="ETHUSDT", side="SELL", qty=1.0, price=3000.0))
        gross = pf.gross_notional({"BTCUSDT": 51000.0, "ETHUSDT": 2900.0})
        self.assertEqual(gross, 8000.0)


if __name__ == "__main__":
    unittest.main()
