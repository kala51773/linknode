import unittest
from typing import Any

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


class FakeNotifier:
    def __init__(self, *, errors: list[str] | None = None, exc: Exception | None = None) -> None:
        self.errors = list(errors or [])
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def notify(self, *, event_type: str, payload: dict[str, Any]) -> list[str]:
        self.calls.append({"event_type": event_type, "payload": payload})
        if self.exc is not None:
            raise self.exc
        return list(self.errors)


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
        return WickHunterRuntime(bridge=bridge, orchestrator=orchestrator, emergency_symbols=("BTCUSDT",))

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
        self.assertTrue(res.emergency_triggered)

    def test_runtime_halts_after_emergency_trigger(self) -> None:
        runtime = self._build_runtime()
        first = runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(),
            hedge_reference_price=50_000,
            marketdata_latency_ms=999,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )
        second = runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(),
            hedge_reference_price=50_000,
            marketdata_latency_ms=50,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )

        self.assertFalse(first.accepted)
        self.assertTrue(first.emergency_triggered)
        self.assertFalse(second.accepted)
        self.assertEqual(second.reason, "runtime_halted")
        self.assertEqual(len(runtime.emergency_events), 1)
        self.assertEqual(runtime.emergency_events[0].reason, "marketdata_latency")
        self.assertTrue(runtime.halted)

    def test_runtime_notifies_emergency_event(self) -> None:
        runtime = self._build_runtime()
        notifier = FakeNotifier()
        runtime.emergency_notifier = notifier

        runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(),
            hedge_reference_price=50_000,
            marketdata_latency_ms=999,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )

        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(notifier.calls[0]["event_type"], "runtime_emergency")
        self.assertEqual(notifier.calls[0]["payload"]["reason"], "marketdata_latency")
        self.assertEqual(runtime.emergency_notification_errors, [])

    def test_runtime_notifier_exception_collected(self) -> None:
        runtime = self._build_runtime()
        runtime.emergency_notifier = FakeNotifier(exc=RuntimeError("notify_boom"))

        runtime.step(
            fair_price=100.0,
            fill=FillEvent(symbol="ALTUSDT", qty=5, price=10),
            risk_state=RuntimeRiskState(),
            hedge_reference_price=50_000,
            marketdata_latency_ms=999,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )

        self.assertEqual(len(runtime.emergency_notification_errors), 1)
        self.assertIn("notifier_exception:notify_boom", runtime.emergency_notification_errors[0])


if __name__ == "__main__":
    unittest.main()
