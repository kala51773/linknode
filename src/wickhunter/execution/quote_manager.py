import time
from typing import Dict, Optional, List
from wickhunter.common.logger import setup_logger

logger = setup_logger("wickhunter.execution.quote_manager")

class QuoteManager:
    """Manages B-leg Quote lifecycle, throttling, and min time-in-force."""
    
    def __init__(self, min_order_live_seconds: float = 0.5, max_cancels_per_10s: int = 15):
        self.min_order_live_seconds = min_order_live_seconds
        self.max_cancels_per_10s = max_cancels_per_10s
        self.active_quotes: Dict[str, float] = {} # order_id -> create_ts
        self.cancel_timestamps: List[float] = []

    def can_cancel(self, order_id: str) -> bool:
        now = time.time()
        
        # Check order age
        create_ts = self.active_quotes.get(order_id, 0.0)
        if now - create_ts < self.min_order_live_seconds:
            logger.debug(f"Block cancel {order_id}: age {now - create_ts:.2f}s < {self.min_order_live_seconds}s")
            return False
            
        # Check global throttle window
        self._prune_cancel_history(now)
        if len(self.cancel_timestamps) >= self.max_cancels_per_10s:
            logger.warning("Cancel rate limit reached. Delaying cancellation.")
            return False
            
        return True

    def register_quote(self, order_id: str) -> None:
        self.active_quotes[order_id] = time.time()
        
    def record_cancel(self, order_id: str) -> None:
        self.cancel_timestamps.append(time.time())
        if order_id in self.active_quotes:
            del self.active_quotes[order_id]

    def _prune_cancel_history(self, now: float) -> None:
        # Keep only cancels from the last 10 seconds
        cutoff = now - 10.0
        self.cancel_timestamps = [ts for ts in self.cancel_timestamps if ts > cutoff]
