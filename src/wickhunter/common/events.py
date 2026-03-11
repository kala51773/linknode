from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    B_FILL = "B_FILL"
    HEDGE_SUBMIT = "HEDGE_SUBMIT"
    HEDGE_FILLED = "HEDGE_FILLED"
    RISK_REJECTED = "RISK_REJECTED"


@dataclass(frozen=True, slots=True)
class FillEvent:
    symbol: str
    qty: float
    price: float
    side: str = "BUY"


@dataclass(frozen=True, slots=True)
class HedgeOrder:
    symbol: str
    side: str
    qty: float
    limit_price: float
