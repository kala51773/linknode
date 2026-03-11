import time
from dataclasses import dataclass, field

from wickhunter.risk.checks import RuntimeRiskState


@dataclass(slots=True)
class CircuitBreaker:
    """Aggregates hard-stop conditions from runtime state and infra health."""

    max_consecutive_hedge_failures: int = 2
    max_marketdata_latency_ms: int = 250
    cooldown_seconds: float = 0.0
    _tripped_reason: str | None = field(default=None, init=False)
    _tripped_at_monotonic: float | None = field(default=None, init=False)

    @property
    def tripped_reason(self) -> str | None:
        return self._tripped_reason

    @property
    def is_tripped(self) -> bool:
        return self._tripped_reason is not None

    def evaluate(
        self,
        *,
        risk_state: RuntimeRiskState,
        marketdata_latency_ms: int,
        consecutive_hedge_failures: int,
        exchange_restricted: bool,
        now_monotonic: float | None = None,
    ) -> tuple[bool, str]:
        now = time.monotonic() if now_monotonic is None else now_monotonic

        if self.is_tripped and self._can_resume(now):
            self.reset()

        if self.is_tripped:
            return False, self._tripped_reason or "tripped"

        if exchange_restricted:
            self._trip("exchange_restricted", now)
        elif marketdata_latency_ms > self.max_marketdata_latency_ms:
            self._trip("marketdata_latency", now)
        elif consecutive_hedge_failures >= self.max_consecutive_hedge_failures:
            self._trip("hedge_failures", now)
        elif risk_state.naked_b_exposure_seconds > 1.0:
            self._trip("naked_exposure", now)

        if self._tripped_reason:
            return False, self._tripped_reason
        return True, "ok"

    def reset(self) -> None:
        self._tripped_reason = None
        self._tripped_at_monotonic = None

    def _trip(self, reason: str, now_monotonic: float) -> None:
        self._tripped_reason = reason
        self._tripped_at_monotonic = now_monotonic

    def _can_resume(self, now_monotonic: float) -> bool:
        if self._tripped_reason is None:
            return True
        if self.cooldown_seconds <= 0:
            return False
        if self._tripped_at_monotonic is None:
            return False
        return (now_monotonic - self._tripped_at_monotonic) >= self.cooldown_seconds
