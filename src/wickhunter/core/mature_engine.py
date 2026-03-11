from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from wickhunter.common.events import HedgeOrder
from wickhunter.strategy.quote_engine import QuotePlan


class MatureEngineKind(str, Enum):
    NAUTILUS_TRADER = "nautilus_trader"
    BINANCE_DIRECT = "binance_direct"


@dataclass(frozen=True, slots=True)
class EngineSubmitResult:
    accepted: bool
    backend: MatureEngineKind
    reason: str


class MatureEngineAdapter:
    """Adapter interface for plugging WickHunter into mature trading engines."""

    backend: MatureEngineKind

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:  # pragma: no cover - interface
        raise NotImplementedError

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(slots=True)
class NautilusTraderAdapter(MatureEngineAdapter):
    """Thin adapter shell; maps WickHunter intents to Nautilus-side commands."""

    backend: MatureEngineKind = MatureEngineKind.NAUTILUS_TRADER
    sent_quote_plans: list[QuotePlan] = field(default_factory=list)
    sent_hedge_orders: list[HedgeOrder] = field(default_factory=list)

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:
        if not plan.armed:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="plan_not_armed")
        self.sent_quote_plans.append(plan)
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:
        if order.qty <= 0 or order.limit_price <= 0:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="invalid_hedge_order")
        self.sent_hedge_orders.append(order)
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")


@dataclass(slots=True)
class BinanceDirectAdapter(MatureEngineAdapter):
    """Direct adapter for Binance testing. In production, NautilusTrader is preferred."""
    
    backend: MatureEngineKind = MatureEngineKind("binance_direct")  # type: ignore
    client: Any = None  # Using Any to avoid circular import if needed, but we could typing it properly if we want to

    def submit_quote_plan(self, plan: QuotePlan) -> EngineSubmitResult:
        if not plan.armed:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="plan_not_armed")
        
        # In a real sync-to-async bridge, we might send this to an asyncio queue
        # For M1 MVP, we assume a background task consumes these intents and maps them to client.place_order()
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")

    def submit_hedge_order(self, order: HedgeOrder) -> EngineSubmitResult:
        if order.qty <= 0 or order.limit_price <= 0:
            return EngineSubmitResult(accepted=False, backend=self.backend, reason="invalid_hedge_order")
            
        return EngineSubmitResult(accepted=True, backend=self.backend, reason="ok")
