from dataclasses import dataclass, field

from wickhunter.marketdata.orderbook import DepthUpdate, LocalOrderBook


@dataclass(slots=True)
class BookSynchronizer:
    """Buffer-first snapshot synchronizer for Binance-style diff depth streams."""

    book: LocalOrderBook = field(default_factory=LocalOrderBook)
    _buffer: list[DepthUpdate] = field(default_factory=list)
    _synced: bool = False

    @property
    def is_synced(self) -> bool:
        return self._synced

    def on_depth_update(self, update: DepthUpdate) -> None:
        if not self._synced:
            self._buffer.append(update)
            return
        self.book.apply(update)

    def apply_snapshot(
        self,
        *,
        last_update_id: int,
        bids: tuple[tuple[float, float], ...],
        asks: tuple[tuple[float, float], ...],
    ) -> None:
        self.book.load_snapshot(last_update_id=last_update_id, bids=bids, asks=asks)

        # Keep updates which may bridge from snapshot to stream continuity.
        self._buffer = [u for u in self._buffer if u.final_update_id >= last_update_id + 1]
        self._buffer.sort(key=lambda u: (u.first_update_id, u.final_update_id))

        for update in self._buffer:
            self.book.apply(update)

        self._buffer.clear()
        self._synced = True

    def reset(self) -> None:
        self.book = LocalOrderBook()
        self._buffer.clear()
        self._synced = False
