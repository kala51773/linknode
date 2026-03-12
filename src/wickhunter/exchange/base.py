from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

@dataclass
class UnifiedOrder:
    exchange: str
    symbol: str
    order_id: str
    client_order_id: str
    side: str
    status: str
    price: float
    qty: float
    filled_qty: float

class BaseExchangeClient(ABC):
    """Abstract interface for multi-exchange integration per PRD M4."""
    
    @abstractmethod
    async def place_order(self, symbol: str, side: str, qty: float, price: float = 0.0, order_type: str = "LIMIT", time_in_force: str = "GTC") -> Dict[str, Any]:
        pass
        
    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    async def get_open_orders(self, symbol: str) -> List[UnifiedOrder]:
        pass

    @abstractmethod
    async def stream_depth(self, symbol: str, callback: Callable[[str], None], speed: str = "") -> None:
        pass
