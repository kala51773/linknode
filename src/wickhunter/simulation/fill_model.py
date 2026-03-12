from dataclasses import dataclass
from typing import Optional
from enum import Enum

class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

@dataclass
class FillSimResult:
    filled_qty: float
    avg_price: float
    fully_filled: bool
    queue_pos_remaining: float

class ReplayFillModel:
    """Simulates realistic queue positioning and partial fills."""
    
    def __init__(self, use_queue_positioning: bool = True):
        self.use_queue_positioning = use_queue_positioning

    def simulate_fill(self, 
                      order_side: str, 
                      order_px: float, 
                      order_qty: float, 
                      event_trade_px: float, 
                      event_trade_qty: float, 
                      book_depth_ahead: float = 0.0) -> FillSimResult:
                      
        filled = 0.0
        remaining_queue = book_depth_ahead
        
        # If market moves through our price, fully fill 
        if (order_side == "BUY" and event_trade_px < order_px) or (order_side == "SELL" and event_trade_px > order_px):
            filled = order_qty
            remaining_queue = 0.0
            
        elif event_trade_px == order_px:
            # Trade occurred at our price level
            if self.use_queue_positioning and remaining_queue > 0:
                # We are behind others in queue
                if event_trade_qty > remaining_queue:
                    # Eat through queue
                    event_trade_qty -= remaining_queue
                    remaining_queue = 0.0
                    
                    # Now eat our order
                    filled = min(order_qty, event_trade_qty)
                else:
                    # Not enough trades to reach us
                    remaining_queue -= event_trade_qty
            else:
                # Top of queue
                filled = min(order_qty, event_trade_qty)
                
        return FillSimResult(
            filled_qty=filled,
            avg_price=order_px if filled > 0 else 0.0,
            fully_filled=(filled >= order_qty),
            queue_pos_remaining=max(0.0, remaining_queue)
        )
