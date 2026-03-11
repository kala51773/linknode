import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


TERMINAL_STATUSES = {
    OrderStatus.FILLED.value,
    OrderStatus.CANCELED.value,
    OrderStatus.REJECTED.value,
    OrderStatus.EXPIRED.value,
}


VALID_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING.value: {
        OrderStatus.NEW.value,
        OrderStatus.PARTIALLY_FILLED.value,
        OrderStatus.FILLED.value,
        OrderStatus.CANCELED.value,
        OrderStatus.REJECTED.value,
        OrderStatus.EXPIRED.value,
    },
    OrderStatus.NEW.value: {
        OrderStatus.PARTIALLY_FILLED.value,
        OrderStatus.FILLED.value,
        OrderStatus.CANCELED.value,
        OrderStatus.REJECTED.value,
        OrderStatus.EXPIRED.value,
    },
    OrderStatus.PARTIALLY_FILLED.value: {
        OrderStatus.PARTIALLY_FILLED.value,
        OrderStatus.FILLED.value,
        OrderStatus.CANCELED.value,
        OrderStatus.EXPIRED.value,
    },
    OrderStatus.FILLED.value: {OrderStatus.FILLED.value},
    OrderStatus.CANCELED.value: {OrderStatus.CANCELED.value},
    OrderStatus.REJECTED.value: {OrderStatus.REJECTED.value},
    OrderStatus.EXPIRED.value: {OrderStatus.EXPIRED.value},
}

@dataclass
class OrderState:
    client_order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    status: str = OrderStatus.PENDING.value
    exchange_order_id: Optional[str] = None
    filled_qty: float = 0.0
    intent: str = "unknown"

@dataclass
class OrderTracker:
    """Tracks active orders, generates idempotency keys, and reconciles execution reports."""
    
    orders: Dict[str, OrderState] = field(default_factory=dict)
    closed_orders: Dict[str, OrderState] = field(default_factory=dict)
    _exchange_to_client: Dict[str, str] = field(default_factory=dict)
    
    def generate_client_id(self, prefix: str = "wh_") -> str:
        unique_part = str(uuid.uuid4()).replace("-", "")
        return f"{prefix}{unique_part[:12]}"
        
    def track_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        intent: str = "unknown",
    ) -> OrderState:
        if client_order_id in self.orders:
            raise ValueError(f"Duplicate client order ID tracked: {client_order_id}")
        if client_order_id in self.closed_orders:
            raise ValueError(f"Order already closed: {client_order_id}")
            
        state = OrderState(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            intent=intent,
        )
        self.orders[client_order_id] = state
        return state

    def bind_exchange_order_id(self, client_order_id: str, exchange_order_id: str) -> Optional[OrderState]:
        state = self.orders.get(client_order_id)
        if not state:
            return None
        state.exchange_order_id = exchange_order_id
        self._exchange_to_client[exchange_order_id] = client_order_id
        return state

    def on_report(
        self,
        *,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        status: str,
        filled_qty: float = 0.0,
    ) -> Optional[OrderState]:
        state = self._find_state(client_order_id=client_order_id, exchange_order_id=exchange_order_id)
        if not state:
            return None

        next_status = status.upper()
        if not self._is_valid_transition(state.status, next_status):
            raise ValueError(f"invalid order transition: {state.status} -> {next_status}")

        state.status = next_status
        if exchange_order_id:
            state.exchange_order_id = exchange_order_id
            self._exchange_to_client[exchange_order_id] = state.client_order_id

        if filled_qty > state.filled_qty:
            state.filled_qty = min(filled_qty, state.qty)

        if next_status in TERMINAL_STATUSES:
            self.closed_orders[state.client_order_id] = state
            self.orders.pop(state.client_order_id, None)
            if state.exchange_order_id:
                self._exchange_to_client.pop(state.exchange_order_id, None)

        return state

    def get_order(self, client_order_id: str) -> Optional[OrderState]:
        state = self.orders.get(client_order_id)
        if state is not None:
            return state
        return self.closed_orders.get(client_order_id)

    def find_by_exchange_order_id(self, exchange_order_id: str) -> Optional[OrderState]:
        client_order_id = self._exchange_to_client.get(exchange_order_id)
        if client_order_id is None:
            return None
        return self.orders.get(client_order_id)

    def get_open_orders(self) -> list[OrderState]:
        return list(self.orders.values())

    @staticmethod
    def _is_valid_transition(current_status: str, next_status: str) -> bool:
        allowed = VALID_TRANSITIONS.get(current_status, set())
        return next_status in allowed

    def _find_state(
        self,
        *,
        client_order_id: Optional[str],
        exchange_order_id: Optional[str],
    ) -> Optional[OrderState]:
        if client_order_id:
            state = self.orders.get(client_order_id)
            if state is not None:
                return state
        if exchange_order_id:
            mapped_client_order_id = self._exchange_to_client.get(exchange_order_id)
            if mapped_client_order_id:
                return self.orders.get(mapped_client_order_id)
        return None
