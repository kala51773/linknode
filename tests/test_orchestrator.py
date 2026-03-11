import unittest

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import NautilusTraderAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.marketdata.orderbook import DepthUpdate
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine


class TestCoreOrchestrator(unittest.TestCase):
    def test_submit_quote_and_hedge_to_backend(self) -> None:
        signal_engine = SignalEngine(
            quote_engine=QuoteEngine(max_name_risk=1000),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )
        signal_engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 30.0),)))
        signal_engine.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((100.1, 5.0),)))
        signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

        execution_engine = ExecutionEngine(
            risk_checker=RiskChecker(RiskLimits()),
            hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0),
        )
        backend = NautilusTraderAdapter()

        orchestrator = CoreOrchestrator(
            signal_engine=signal_engine,
            execution_engine=execution_engine,
            backend=backend,
        )

        result = orchestrator.on_market_and_fill(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(daily_loss_pct=0.2, events_today=1, naked_b_exposure_seconds=0.2),
            hedge_reference_price=50_000,
        )

        self.assertTrue(result.quote_submit.accepted)
        self.assertIsNotNone(result.hedge_submit)
        assert result.hedge_submit is not None
        self.assertTrue(result.hedge_submit.accepted)


if __name__ == "__main__":
    unittest.main()
