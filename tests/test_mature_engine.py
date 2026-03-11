import unittest

from wickhunter.common.events import HedgeOrder
from wickhunter.core.mature_engine import MatureEngineKind, NautilusTraderAdapter
from wickhunter.strategy.quote_engine import QuoteLevel, QuotePlan


class TestMatureEngineAdapter(unittest.TestCase):
    def test_submit_armed_plan_to_nautilus_adapter(self) -> None:
        adapter = NautilusTraderAdapter()
        plan = QuotePlan(armed=True, levels=(QuoteLevel(price=99.4, size=100),), reason="ok")

        result = adapter.submit_quote_plan(plan)

        self.assertTrue(result.accepted)
        self.assertEqual(result.backend, MatureEngineKind.NAUTILUS_TRADER)
        self.assertEqual(len(adapter.sent_quote_plans), 1)

    def test_reject_unarmed_plan(self) -> None:
        adapter = NautilusTraderAdapter()
        result = adapter.submit_quote_plan(QuotePlan(armed=False, levels=tuple(), reason="not_synced"))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "plan_not_armed")

    def test_submit_hedge_order(self) -> None:
        adapter = NautilusTraderAdapter()
        order = HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.01, limit_price=50_000)

        result = adapter.submit_hedge_order(order)

        self.assertTrue(result.accepted)
        self.assertEqual(len(adapter.sent_hedge_orders), 1)


if __name__ == "__main__":
    unittest.main()
