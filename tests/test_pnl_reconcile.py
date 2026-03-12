import unittest

from wickhunter.analytics.pnl_reconcile import reconcile_okx_fills_net_pnl


class TestPnLReconcile(unittest.TestCase):
    def test_reconcile_within_tolerance(self) -> None:
        fills = [
            {"pnl": "1.20", "fee": "-0.10"},
            {"pnl": "-0.30", "fee": "-0.05"},
        ]
        result = reconcile_okx_fills_net_pnl(fills=fills, local_net_pnl=0.75, tolerance=1e-9)

        self.assertEqual(result.exchange_realized_pnl, 0.9)
        self.assertEqual(result.exchange_fees, -0.15)
        self.assertEqual(result.exchange_net_pnl, 0.75)
        self.assertTrue(result.within_tolerance)

    def test_reconcile_outside_tolerance(self) -> None:
        fills = [
            {"pnl": "0.2", "fee": "-0.05"},
            {"pnl": "0.1", "fee": "-0.05"},
        ]
        result = reconcile_okx_fills_net_pnl(fills=fills, local_net_pnl=0.0, tolerance=1e-6)

        self.assertEqual(result.exchange_net_pnl, 0.2)
        self.assertFalse(result.within_tolerance)


if __name__ == "__main__":
    unittest.main()
