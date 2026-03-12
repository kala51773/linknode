import time
from dataclasses import dataclass
from typing import Any

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent


@dataclass(slots=True)
class RuntimeRiskState:
    daily_loss_pct: float = 0.0
    events_today: int = 0
    naked_b_exposure_seconds: float = 0.0


@dataclass(slots=True)
class AccountRiskSnapshot:
    ts_ms: int
    asset: str
    wallet_balance: float
    cross_wallet_balance: float | None = None
    balance_delta: float | None = None
    available_balance_ratio: float | None = None


class RiskChecker:
    def __init__(self, limits: RiskLimits) -> None:
        self._limits = limits

    def can_process_fill(self, fill: FillEvent, state: RuntimeRiskState) -> tuple[bool, str]:
        if fill.qty <= 0 or fill.price <= 0:
            return False, "invalid_fill"
        if state.daily_loss_pct >= self._limits.daily_loss_limit_pct:
            return False, "daily_loss_limit"
        if state.events_today >= self._limits.max_events_per_day:
            return False, "max_events_per_day"
        if state.naked_b_exposure_seconds > self._limits.max_naked_b_exposure_seconds:
            return False, "naked_exposure"
        return True, "ok"

    def can_accept_account_snapshot(self, snapshot: AccountRiskSnapshot) -> tuple[bool, str]:
        if snapshot.wallet_balance <= 0:
            return False, "wallet_balance_non_positive"
        if snapshot.wallet_balance < self._limits.min_wallet_balance_usdt:
            return False, "wallet_balance_floor"
        if (
            snapshot.available_balance_ratio is not None
            and snapshot.available_balance_ratio < self._limits.min_available_balance_ratio
        ):
            return False, "available_balance_ratio"
        return True, "ok"


def build_account_snapshot_from_binance(
    payload: dict[str, Any],
    *,
    preferred_asset: str = "USDT",
    ts_ms: int | None = None,
) -> AccountRiskSnapshot | None:
    account_payload: dict[str, Any]
    nested_payload = payload.get("a")
    if isinstance(nested_payload, dict):
        account_payload = nested_payload
    else:
        account_payload = payload

    balances = account_payload.get("B")
    if not isinstance(balances, list) or not balances:
        return None

    selected: dict[str, Any] | None = None
    for item in balances:
        if isinstance(item, dict) and str(item.get("a", "")).upper() == preferred_asset.upper():
            selected = item
            break
    if selected is None:
        first_item = balances[0]
        if not isinstance(first_item, dict):
            return None
        selected = first_item

    raw_asset = selected.get("a", preferred_asset)
    asset = str(raw_asset) if raw_asset is not None else preferred_asset

    wallet_balance = _to_float(selected.get("wb"))
    if wallet_balance is None:
        return None
    cross_wallet_balance = _to_float(selected.get("cw"))
    balance_delta = _to_float(selected.get("bc"))

    available_balance_ratio: float | None = None
    if cross_wallet_balance is not None and wallet_balance > 0:
        available_balance_ratio = cross_wallet_balance / wallet_balance

    return AccountRiskSnapshot(
        ts_ms=int(ts_ms if ts_ms is not None else time.time() * 1000),
        asset=asset,
        wallet_balance=wallet_balance,
        cross_wallet_balance=cross_wallet_balance,
        balance_delta=balance_delta,
        available_balance_ratio=available_balance_ratio,
    )


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
