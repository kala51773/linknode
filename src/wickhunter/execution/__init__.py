from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wickhunter.execution.engine import CancelDecision, ExecutionEngine, ExecutionResult
    from wickhunter.execution.hedge_manager import HedgeManager
    from wickhunter.execution.order_tracker import OrderState, OrderTracker
    from wickhunter.execution.throttle import CancelThrottle

__all__ = [
    "ExecutionEngine",
    "ExecutionResult",
    "CancelDecision",
    "HedgeManager",
    "CancelThrottle",
    "OrderTracker",
    "OrderState",
]


def __getattr__(name: str) -> Any:
    if name in {"ExecutionEngine", "ExecutionResult", "CancelDecision"}:
        from wickhunter.execution.engine import CancelDecision, ExecutionEngine, ExecutionResult

        return {
            "ExecutionEngine": ExecutionEngine,
            "ExecutionResult": ExecutionResult,
            "CancelDecision": CancelDecision,
        }[name]
    if name == "HedgeManager":
        from wickhunter.execution.hedge_manager import HedgeManager

        return HedgeManager
    if name == "CancelThrottle":
        from wickhunter.execution.throttle import CancelThrottle

        return CancelThrottle
    if name in {"OrderTracker", "OrderState"}:
        from wickhunter.execution.order_tracker import OrderState, OrderTracker

        return {"OrderTracker": OrderTracker, "OrderState": OrderState}[name]
    raise AttributeError(name)
