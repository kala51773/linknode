import time
from dataclasses import dataclass, field
from typing import Any

from wickhunter.common.emergency import EmergencyNotifier
from wickhunter.common.events import FillEvent
from wickhunter.core.orchestrator import CoreOrchestrator
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.portfolio.position import Fill as PositionFill, Portfolio
from wickhunter.risk.checks import RuntimeRiskState
from wickhunter.risk.circuit_breaker import CircuitBreaker


@dataclass(frozen=True, slots=True)
class RuntimeStepResult:
    accepted: bool
    reason: str
    quote_submitted: bool
    hedge_submitted: bool
    emergency_triggered: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeEmergencyEvent:
    ts_ms: int
    reason: str
    backend_emergency_ok: bool
    backend_reason: str
    symbols: tuple[str, ...]


@dataclass(slots=True)
class WickHunterRuntime:
    """High-level runtime wiring exchange ingestion, orchestration, and portfolio updates."""

    bridge: BinanceSignalBridge
    orchestrator: CoreOrchestrator
    portfolio: Portfolio = field(default_factory=Portfolio)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    emergency_symbols: tuple[str, ...] = ()
    emergency_events: list[RuntimeEmergencyEvent] = field(default_factory=list)
    emergency_notifier: EmergencyNotifier | None = None
    emergency_notification_errors: list[str] = field(default_factory=list)
    halted: bool = False

    def on_market_payloads(self, payloads: list[str]) -> int:
        return self.bridge.ingest_many(payloads)

    def on_user_report(self, payload: dict[str, Any]) -> None:
        """Process incoming private exchange reports (orders, trades)."""
        if self.halted:
            return
        # Route to backend adapter for tracking/reconciliation
        self.orchestrator.backend.on_execution_report(payload)

    def on_snapshot(
        self,
        *,
        last_update_id: int,
        bids: tuple[tuple[float, float], ...],
        asks: tuple[tuple[float, float], ...],
    ) -> None:
        self.bridge.signal_engine.on_snapshot(last_update_id=last_update_id, bids=bids, asks=asks)

    def reset_halt(self) -> None:
        self.halted = False
        self.circuit_breaker.reset()

    def step(
        self,
        *,
        fair_price: float,
        fill: FillEvent,
        risk_state: RuntimeRiskState,
        hedge_reference_price: float,
        marketdata_latency_ms: int,
        consecutive_hedge_failures: int,
        exchange_restricted: bool,
    ) -> RuntimeStepResult:
        if self.halted:
            return RuntimeStepResult(False, "runtime_halted", False, False, False)

        allowed, reason = self.circuit_breaker.evaluate(
            risk_state=risk_state,
            marketdata_latency_ms=marketdata_latency_ms,
            consecutive_hedge_failures=consecutive_hedge_failures,
            exchange_restricted=exchange_restricted,
        )
        if not allowed:
            emergency_triggered = self._trigger_emergency_stop(reason)
            return RuntimeStepResult(False, reason, False, False, emergency_triggered)

        result = self.orchestrator.on_market_and_fill(
            fair_price=fair_price,
            fill=fill,
            risk_state=risk_state,
            hedge_reference_price=hedge_reference_price,
        )

        # Track B-leg fill into portfolio (demo-level accounting path).
        self.portfolio.on_fill(
            PositionFill(symbol=fill.symbol, side=fill.side, qty=fill.qty, price=fill.price)
        )

        hedge_submitted = bool(result.hedge_submit and result.hedge_submit.accepted)
        return RuntimeStepResult(
            accepted=True,
            reason="ok",
            quote_submitted=result.quote_submit.accepted,
            hedge_submitted=hedge_submitted,
            emergency_triggered=False,
        )

    def _trigger_emergency_stop(self, reason: str) -> bool:
        if self.halted:
            return False

        backend_result = self.orchestrator.backend.emergency_stop(
            reason=reason,
            symbols=self.emergency_symbols,
        )
        
        # Confirmation/Escalation: if backend failed or symbols might still be exposed
        success = backend_result.accepted
        if not success:
            # We already halted, but we should escalate if the cancel command failed
            self.emergency_notification_errors.append(f"emergency_stop_failed:{backend_result.reason}")
            # In a real system, we might retry here or send an even more urgent alert.
        
        self.halted = True
        self.emergency_events.append(
            RuntimeEmergencyEvent(
                ts_ms=int(time.time() * 1000),
                reason=reason,
                backend_emergency_ok=backend_result.accepted,
                backend_reason=backend_result.reason,
                symbols=self.emergency_symbols,
            )
        )
        self._notify_emergency_event(self.emergency_events[-1])
        return True

    def _notify_emergency_event(self, event: RuntimeEmergencyEvent) -> None:
        notifier = self.emergency_notifier
        if notifier is None:
            return

        try:
            errors = notifier.notify(
                event_type="runtime_emergency",
                payload={
                    "ts_ms": event.ts_ms,
                    "reason": event.reason,
                    "backend_emergency_ok": event.backend_emergency_ok,
                    "backend_reason": event.backend_reason,
                    "symbols": list(event.symbols),
                },
            )
        except Exception as exc:
            self.emergency_notification_errors.append(f"notifier_exception:{exc}")
            return

        self.emergency_notification_errors.extend(errors)
