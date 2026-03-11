from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: str
    qty: float
    price: float


@dataclass(slots=True)
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0

    def apply_fill(self, fill: Fill) -> None:
        signed_qty = fill.qty if fill.side.upper() == "BUY" else -fill.qty
        new_qty = self.qty + signed_qty

        if self.qty == 0 or (self.qty > 0 and signed_qty > 0) or (self.qty < 0 and signed_qty < 0):
            notional = abs(self.qty) * self.avg_price + abs(signed_qty) * fill.price
            self.qty = new_qty
            self.avg_price = 0.0 if self.qty == 0 else notional / abs(self.qty)
            return

        # reducing or flipping position
        if self.qty > 0 > new_qty or self.qty < 0 < new_qty:
            self.avg_price = fill.price
        if new_qty == 0:
            self.avg_price = 0.0
        self.qty = new_qty


@dataclass(slots=True)
class Portfolio:
    positions: dict[str, Position] = field(default_factory=dict)

    def on_fill(self, fill: Fill) -> Position:
        position = self.positions.setdefault(fill.symbol, Position(symbol=fill.symbol))
        position.apply_fill(fill)
        return position

    def gross_notional(self, mark_prices: dict[str, float]) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            mark = mark_prices.get(symbol, pos.avg_price)
            total += abs(pos.qty) * mark
        return round(total, 8)
