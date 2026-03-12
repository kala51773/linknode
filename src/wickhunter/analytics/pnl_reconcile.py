from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PnLReconcileResult:
    exchange_realized_pnl: float
    exchange_fees: float
    exchange_net_pnl: float
    local_net_pnl: float
    diff: float
    tolerance: float
    within_tolerance: bool


def reconcile_okx_fills_net_pnl(
    *,
    fills: list[dict[str, Any]],
    local_net_pnl: float,
    tolerance: float = 1e-8,
) -> PnLReconcileResult:
    """Reconcile local net pnl against OKX fill-level fee + realized-pnl totals."""
    realized = 0.0
    fees = 0.0
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        realized += _to_float(fill.get("pnl"))
        fees += _to_float(fill.get("fee"))
    exchange_net = realized + fees
    diff = local_net_pnl - exchange_net
    return PnLReconcileResult(
        exchange_realized_pnl=round(realized, 12),
        exchange_fees=round(fees, 12),
        exchange_net_pnl=round(exchange_net, 12),
        local_net_pnl=round(local_net_pnl, 12),
        diff=round(diff, 12),
        tolerance=tolerance,
        within_tolerance=abs(diff) <= tolerance,
    )


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
