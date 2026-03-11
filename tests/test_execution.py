import unittest

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.execution.throttle import CancelThrottle
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState


class TestExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ExecutionEngine(
            risk_checker=RiskChecker(RiskLimits()),
            hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0, aggressiveness_bps=2.0),
        )

    def test_generate_hedge_order_when_risk_ok(self) -> None:
        fill = FillEvent(symbol="ALTUSDT", qty=20.0, price=2.0)
        state = RuntimeRiskState(daily_loss_pct=0.5, events_today=2, naked_b_exposure_seconds=0.4)
        result = self.engine.on_b_fill(fill=fill, state=state, reference_price=40_000.0)

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "ok")
        self.assertIsNotNone(result.hedge_order)
        assert result.hedge_order is not None
        self.assertEqual(result.hedge_order.symbol, "BTCUSDT")
        self.assertEqual(result.hedge_order.side, "SELL")


    def test_generate_buy_hedge_for_sell_fill(self) -> None:
        fill = FillEvent(symbol="ALTUSDT", qty=20.0, price=2.0, side="SELL")
        state = RuntimeRiskState(daily_loss_pct=0.5, events_today=2, naked_b_exposure_seconds=0.4)
        result = self.engine.on_b_fill(fill=fill, state=state, reference_price=40_000.0)

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.hedge_order)
        assert result.hedge_order is not None
        self.assertEqual(result.hedge_order.side, "BUY")

    def test_reject_when_risk_limit_hit(self) -> None:
        fill = FillEvent(symbol="ALTUSDT", qty=20.0, price=2.0)
        state = RuntimeRiskState(daily_loss_pct=3.0, events_today=2, naked_b_exposure_seconds=0.4)
        result = self.engine.on_b_fill(fill=fill, state=state, reference_price=40_000.0)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "daily_loss_limit")
        self.assertIsNone(result.hedge_order)

    def test_cancel_decision_uses_throttle(self) -> None:
        engine = ExecutionEngine(
            risk_checker=RiskChecker(RiskLimits()),
            hedge_manager=HedgeManager(hedge_symbol="BTCUSDT"),
            cancel_throttle=CancelThrottle(max_cancels_per_window=1, window_seconds=5.0, min_order_live_seconds=0.2),
        )
        first = engine.request_cancel(now=10.3, order_created_at=10.0)
        second = engine.request_cancel(now=10.6, order_created_at=10.0)

        self.assertTrue(first.accepted)
        self.assertEqual(first.reason, "ok")
        self.assertFalse(second.accepted)
        self.assertEqual(second.reason, "cancel_rate_limit")


if __name__ == "__main__":
    unittest.main()
