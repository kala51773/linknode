from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class CancelThrottle:
    """Protects against excessive cancel behavior within a rolling window."""

    max_cancels_per_window: int = 8
    window_seconds: float = 5.0
    min_order_live_seconds: float = 0.3
    _cancel_timestamps: deque[float] = field(default_factory=deque)

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._cancel_timestamps and self._cancel_timestamps[0] < cutoff:
            self._cancel_timestamps.popleft()

    def can_cancel(self, *, now: float, order_created_at: float) -> tuple[bool, str]:
        if now < order_created_at:
            return False, "clock_error"

        live_time = now - order_created_at
        if live_time < self.min_order_live_seconds:
            return False, "min_live_time"

        self._evict_expired(now)
        if len(self._cancel_timestamps) >= self.max_cancels_per_window:
            return False, "cancel_rate_limit"

        return True, "ok"

    def record_cancel(self, *, now: float) -> None:
        self._evict_expired(now)
        self._cancel_timestamps.append(now)
