import unittest

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent
from wickhunter.core.mature_engine import NautilusTraderAdapter
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.execution.engine import ExecutionEngine
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState
from wickhunter.runtime import WickHunterRuntime
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine


class TestRuntime(unittest.TestCase):
    def _build_runtime(self) -> WickHunterRuntime:
        signal_engine = SignalEngine(
            quote_engine=QuoteEngine(max_name_risk=1000),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )
        bridge = BinanceSignalBridge(
            client=BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser()),
            signal_engine=signal_engine,
        )
        orchestrator = CoreOrchestrator(
            signal_engine=signal_engine,
            execution_engine=ExecutionEngine(
                risk_checker=RiskChecker(RiskLimits()),
                hedge_manager=HedgeManager(hedge_symbol="BTCUSDT", beta_exec=1.0),
            ),
            backend=NautilusTraderAdapter(),
        )
        return WickHunterRuntime(bridge=bridge, orchestrator=orchestrator)

    def test_runtime_step_success(self) -> None:
        runtime = self._build_runtime()
        runtime.on_market_payloads([
            '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}',
            '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}',
        ])
        runtime.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

        res = runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(daily_loss_pct=0.1, events_today=1, naked_b_exposure_seconds=0.2),
            hedge_reference_price=50_000,
            marketdata_latency_ms=50,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )
        self.assertTrue(res.accepted)
        self.assertTrue(res.quote_submitted)
        self.assertTrue(res.hedge_submitted)


    def test_runtime_tracks_sell_fill_as_short_position(self) -> None:
        runtime = self._build_runtime()
        runtime.on_market_payloads([
            '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}',
            '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}',
        ])
        runtime.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

        runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=2, price=10, side="SELL"),
            risk_state=RuntimeRiskState(daily_loss_pct=0.1, events_today=1, naked_b_exposure_seconds=0.2),
            hedge_reference_price=50_000,
            marketdata_latency_ms=50,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )

        self.assertEqual(runtime.portfolio.positions["ALTUSDT"].qty, -2.0)

    def test_runtime_step_blocked_by_circuit_breaker(self) -> None:
        runtime = self._build_runtime()
        res = runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(),
            hedge_reference_price=50_000,
            marketdata_latency_ms=999,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )
        self.assertFalse(res.accepted)
        self.assertEqual(res.reason, "marketdata_latency")


if __name__ == "__main__":
    unittest.main()
