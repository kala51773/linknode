from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PaperCloseResult:
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    exit_reason: str
    realized_pnl: float
    fees: float
    net_pnl: float


@dataclass(slots=True)
class PaperPosition:
    symbol: str
    side: str  # LONG or SHORT
    qty: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    fee_bps: float = 0.0
    is_open: bool = True

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.side == "LONG":
            return (mark_price - self.entry_price) * self.qty
        return (self.entry_price - mark_price) * self.qty

    def close(self, exit_price: float, reason: str) -> PaperCloseResult:
        if not self.is_open:
            raise ValueError("position already closed")
        if exit_price <= 0:
            raise ValueError("exit_price must be positive")

        realized = self.unrealized_pnl(exit_price)
        # Entry + exit fee model on turnover notional.
        fees = 0.0
        if self.fee_bps > 0:
            fees = (self.entry_price * self.qty + exit_price * self.qty) * (self.fee_bps / 10000.0)

        self.is_open = False
        return PaperCloseResult(
            symbol=self.symbol,
            side=self.side,
            qty=self.qty,
            entry_price=self.entry_price,
            exit_price=exit_price,
            exit_reason=reason,
            realized_pnl=round(realized, 8),
            fees=round(fees, 8),
            net_pnl=round(realized - fees, 8),
        )

    def stop_or_take_trigger(self, mark_price: float) -> tuple[bool, str]:
        if not self.is_open:
            return False, "closed"

        if self.side == "LONG":
            if self.stop_loss is not None and mark_price <= self.stop_loss:
                return True, "stop_loss"
            if self.take_profit is not None and mark_price >= self.take_profit:
                return True, "take_profit"
            return False, "hold"

        if self.stop_loss is not None and mark_price >= self.stop_loss:
            return True, "stop_loss"
        if self.take_profit is not None and mark_price <= self.take_profit:
            return True, "take_profit"
        return False, "hold"


@dataclass(slots=True)
class PaperTradeAccount:
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    close_history: list[PaperCloseResult] = field(default_factory=list)

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        fee_bps: float = 0.0,
    ) -> PaperPosition:
        norm_side = side.upper()
        if norm_side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG or SHORT")
        if qty <= 0:
            raise ValueError("qty must be positive")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        existing = self.positions.get(symbol)
        if existing is not None and existing.is_open:
            raise ValueError(f"open position already exists for {symbol}")

        pos = PaperPosition(
            symbol=symbol,
            side=norm_side,
            qty=qty,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fee_bps=fee_bps,
        )
        self.positions[symbol] = pos
        return pos

    def close_position(self, *, symbol: str, exit_price: float, reason: str = "manual_close") -> PaperCloseResult:
        pos = self.positions.get(symbol)
        if pos is None:
            raise KeyError(f"position not found: {symbol}")
        result = pos.close(exit_price=exit_price, reason=reason)
        self.close_history.append(result)
        return result

    def on_mark_price(self, *, symbol: str, mark_price: float) -> PaperCloseResult | None:
        pos = self.positions.get(symbol)
        if pos is None or not pos.is_open:
            return None

        trigger, reason = pos.stop_or_take_trigger(mark_price)
        if not trigger:
            return None
        return self.close_position(symbol=symbol, exit_price=mark_price, reason=reason)

    @property
    def total_realized_pnl(self) -> float:
        return round(sum(item.realized_pnl for item in self.close_history), 8)

    @property
    def total_net_pnl(self) -> float:
        return round(sum(item.net_pnl for item in self.close_history), 8)
