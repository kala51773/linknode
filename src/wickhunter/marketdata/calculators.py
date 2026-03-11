from dataclasses import dataclass

from wickhunter.marketdata.orderbook import LocalOrderBook


@dataclass(frozen=True, slots=True)
class MicrostructureMetrics:
    spread_bps: float | None
    depth_5bp_bid: float
    depth_10bp_bid: float


def _depth_within_bps(book: LocalOrderBook, bps: float) -> float:
    best_bid = book.best_bid
    if not best_bid:
        return 0.0

    best_bid_price = best_bid[0]
    cutoff = best_bid_price * (1 - bps / 10_000)
    return sum(size for price, size in book.bids.items() if price >= cutoff)


def compute_microstructure_metrics(book: LocalOrderBook) -> MicrostructureMetrics:
    best_bid = book.best_bid
    best_ask = book.best_ask

    if not best_bid or not best_ask:
        spread_bps = None
    else:
        mid = (best_bid[0] + best_ask[0]) / 2
        spread_bps = ((best_ask[0] - best_bid[0]) / mid) * 10_000 if mid > 0 else None

    return MicrostructureMetrics(
        spread_bps=spread_bps,
        depth_5bp_bid=_depth_within_bps(book, bps=5),
        depth_10bp_bid=_depth_within_bps(book, bps=10),
    )
