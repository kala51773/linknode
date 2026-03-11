from dataclasses import dataclass

from wickhunter.common.events import FillEvent, HedgeOrder
from wickhunter.execution.hedge_manager import HedgeManager
from wickhunter.execution.throttle import CancelThrottle
from wickhunter.risk.checks import RiskChecker, RuntimeRiskState


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
    ) -> None:
        self._risk_checker = risk_checker
        self._hedge_manager = hedge_manager
        self._cancel_throttle = cancel_throttle or CancelThrottle()

    def on_b_fill(self, fill: FillEvent, state: RuntimeRiskState, reference_price: float) -> ExecutionResult:
        allowed, reason = self._risk_checker.can_process_fill(fill, state)
        if not allowed:
            return ExecutionResult(accepted=False, reason=reason, hedge_order=None)

        hedge = self._hedge_manager.build_hedge_order(fill, reference_price)
        return ExecutionResult(accepted=True, reason="ok", hedge_order=hedge)

    def request_cancel(self, *, now: float, order_created_at: float) -> CancelDecision:
        allowed, reason = self._cancel_throttle.can_cancel(now=now, order_created_at=order_created_at)
        if not allowed:
            return CancelDecision(accepted=False, reason=reason)

        self._cancel_throttle.record_cancel(now=now)
        return CancelDecision(accepted=True, reason="ok")
