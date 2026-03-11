from dataclasses import dataclass, field

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


@dataclass(slots=True)
class WickHunterRuntime:
    """High-level runtime wiring exchange ingestion, orchestration, and portfolio updates."""

    bridge: BinanceSignalBridge
    orchestrator: CoreOrchestrator
    portfolio: Portfolio = field(default_factory=Portfolio)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def on_market_payloads(self, payloads: list[str]) -> int:
        return self.bridge.ingest_many(payloads)

    def on_snapshot(
        self,
        *,
        last_update_id: int,
        bids: tuple[tuple[float, float], ...],
        asks: tuple[tuple[float, float], ...],
    ) -> None:
        self.bridge.signal_engine.on_snapshot(last_update_id=last_update_id, bids=bids, asks=asks)

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
        allowed, reason = self.circuit_breaker.evaluate(
            risk_state=risk_state,
            marketdata_latency_ms=marketdata_latency_ms,
            consecutive_hedge_failures=consecutive_hedge_failures,
            exchange_restricted=exchange_restricted,
        )
        if not allowed:
            return RuntimeStepResult(False, reason, False, False)

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
        )
