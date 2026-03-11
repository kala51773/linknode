from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wickhunter.common.events import FillEvent, HedgeOrder
from wickhunter.common.recovery import PersistentEventLog
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.execution.order_tracker import OrderTracker, OrderState
from wickhunter.execution.throttle import CancelThrottle
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState

if TYPE_CHECKING:
    from wickhunter.core.mature_engine import ExchangeOrderReport


@dataclass(slots=True)
class ExecutionResult:
    accepted: bool
    reason: str
    hedge_order: HedgeOrder | None


@dataclass(slots=True)
class CancelDecision:
    accepted: bool
    reason: str


class ExecutionEngine:
    """Minimal orchestration: risk gate -> hedge order generation + cancel throttling."""

    def __init__(
        self,
        risk_checker: RiskChecker,
        hedge_manager: HedgeManager,
        cancel_throttle: CancelThrottle | None = None,
        order_tracker: OrderTracker | None = None,
        event_log: PersistentEventLog | None = None,
    ) -> None:
        self._risk_checker = risk_checker
        self._hedge_manager = hedge_manager
        self._cancel_throttle = cancel_throttle or CancelThrottle()
        self._order_tracker = order_tracker or OrderTracker()
        self._event_log = event_log or PersistentEventLog()

    def recover_state(self) -> None:
        """Replay the event log to reconstruct the order tracker state."""
        events = self._event_log.replay_events()
        for event in events:
            etype = event.get("type")
            payload = event.get("payload", {})
            if etype == "order_new":
                try:
                    self._order_tracker.track_order(
                        client_order_id=payload["client_order_id"],
                        symbol=payload["symbol"],
                        side=payload["side"],
                        qty=payload["qty"],
                        price=payload["price"]
                    )
                except Exception:
                    pass
            elif etype == "order_report":
                try:
                    self._order_tracker.on_report(
                        client_order_id=payload.get("client_order_id"),
                        exchange_order_id=payload.get("exchange_order_id"),
                        status=payload.get("status", "UNKNOWN"),
                        filled_qty=payload.get("filled_qty", 0.0)
                    )
                except Exception:
                    pass

    def on_b_fill(self, fill: FillEvent, state: RuntimeRiskState, reference_price: float) -> ExecutionResult:
        allowed, reason = self._risk_checker.can_process_fill(fill, state)
        if not allowed:
            return ExecutionResult(accepted=False, reason=reason, hedge_order=None)

        hedge = self._hedge_manager.build_hedge_order(fill, reference_price)
        return ExecutionResult(accepted=True, reason="ok", hedge_order=hedge)

    def track_order(self, client_order_id: str, symbol: str, side: str, qty: float, price: float) -> OrderState:
        state = self._order_tracker.track_order(client_order_id, symbol, side, qty, price)
        self._event_log.append_event("order_new", {"client_order_id": client_order_id, "symbol": symbol, "side": side, "qty": qty, "price": price})
        return state

    def on_order_report(self, report: "ExchangeOrderReport", client_order_id: str) -> OrderState | None:
        state = self._order_tracker.on_report(
            client_order_id=client_order_id,
            status="REJECTED" if not report.accepted else "NEW",
            exchange_order_id=str(report.order_id) if report.order_id else None,
            filled_qty=report.filled_qty,
        )
        self._event_log.append_event("order_report", {
            "client_order_id": client_order_id,
            "accepted": report.accepted,
            "reason": report.reason,
            "exchange_order_id": str(report.order_id) if report.order_id else None,
            "filled_qty": report.filled_qty
        })
        return state

    def request_cancel(self, *, now: float, order_created_at: float) -> CancelDecision:
        allowed, reason = self._cancel_throttle.can_cancel(now=now, order_created_at=order_created_at)
        if not allowed:
            return CancelDecision(accepted=False, reason=reason)
        self._cancel_throttle.record_cancel(now=now)
        return CancelDecision(accepted=True, reason="ok")
