from dataclasses import dataclass

from wickhunter.common.config import RiskLimits
from wickhunter.common.events import FillEvent


@dataclass(slots=True)
class RuntimeRiskState:
    daily_loss_pct: float = 0.0
    events_today: int = 0
    naked_b_exposure_seconds: float = 0.0


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
