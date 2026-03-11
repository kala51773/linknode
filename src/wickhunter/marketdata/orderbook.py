from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DepthUpdate:
    """Incremental depth update using Binance-like sequence semantics."""

    first_update_id: int
    final_update_id: int
    bids: tuple[tuple[float, float], ...] = ()
    asks: tuple[tuple[float, float], ...] = ()


@dataclass(slots=True)
class LocalOrderBook:
    """Lightweight L2 order book with snapshot + diff synchronization rules."""

    last_update_id: int | None = None
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)

    def load_snapshot(
        self,
        *,
        last_update_id: int,
        bids: tuple[tuple[float, float], ...],
        asks: tuple[tuple[float, float], ...],
    ) -> None:
        self.last_update_id = last_update_id
        self.bids = {price: size for price, size in bids if size > 0}
        self.asks = {price: size for price, size in asks if size > 0}

    def can_accept(self, update: DepthUpdate) -> bool:
        if self.last_update_id is None:
            return False
        return update.first_update_id <= self.last_update_id + 1 <= update.final_update_id

    def apply(self, update: DepthUpdate) -> None:
        if self.last_update_id is None:
            raise ValueError("snapshot must be loaded before diff updates")

        if update.final_update_id <= self.last_update_id:
            return

        if not self.can_accept(update):
            raise ValueError(
                f"sequence gap detected: last={self.last_update_id}, "
                f"incoming=[{update.first_update_id}, {update.final_update_id}]"
            )

        self._upsert_levels(self.bids, update.bids)
        self._upsert_levels(self.asks, update.asks)
        self.last_update_id = update.final_update_id

    @staticmethod
    def _upsert_levels(side: dict[float, float], levels: tuple[tuple[float, float], ...]) -> None:
        for price, size in levels:
            if size <= 0:
                side.pop(price, None)
            else:
                side[price] = size

    @property
    def best_bid(self) -> tuple[float, float] | None:
        if not self.bids:
            return None
        price = max(self.bids)
        return price, self.bids[price]

    @property
    def best_ask(self) -> tuple[float, float] | None:
        if not self.asks:
            return None
        price = min(self.asks)
        return price, self.asks[price]

    @property
    def mid_price(self) -> float | None:
        bid = self.best_bid
        ask = self.best_ask
        if not bid or not ask:
            return None
        return (bid[0] + ask[0]) / 2
