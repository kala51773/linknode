from dataclasses import dataclass

@dataclass
class WickSignal:
    triggered: bool
    depth_drain_ratio: float
    mid_to_fair_gap_bps: float
    expected_bounce_bps: float

class WickDetector:
    """
    Detects local downward wicks on OrderBook using liquidity drain and gap to fair value.
    """
    def __init__(self, min_depth_drain_ratio: float = 0.6, min_gap_bps: float = 20.0):
        self.min_depth_drain_ratio = min_depth_drain_ratio
        self.min_gap_bps = min_gap_bps
        
    def detect(self, current_mid: float, fair_value: float, current_base_depth: float, historical_base_depth: float) -> WickSignal:
        if fair_value <= 0 or current_mid <= 0 or historical_base_depth <= 0:
            return WickSignal(False, 0.0, 0.0, 0.0)
            
        gap_bps = ((fair_value - current_mid) / fair_value) * 10000.0
        depth_drain = 1.0 - (current_base_depth / historical_base_depth)
        
        triggered = False
        if gap_bps >= self.min_gap_bps and depth_drain >= self.min_depth_drain_ratio:
            triggered = True
            
        return WickSignal(
            triggered=triggered,
            depth_drain_ratio=depth_drain,
            mid_to_fair_gap_bps=gap_bps,
            expected_bounce_bps=gap_bps * 0.5  # Expect return to half of gap
        )
