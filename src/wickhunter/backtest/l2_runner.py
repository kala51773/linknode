from dataclasses import dataclass

from wickhunter.backtest.replay import EventReplayer
from wickhunter.marketdata.calculators import compute_microstructure_metrics
from wickhunter.marketdata.orderbook import DepthUpdate, LocalOrderBook


@dataclass(frozen=True, slots=True)
class L2BacktestResult:
    total_events: int
    depth_events: int
    snapshot_events: int
    update_events: int
    skipped_events: int
    ignored_non_depth_events: int
    gap_events: int
    avg_spread_bps: float | None
    avg_depth_5bp_bid: float
    avg_depth_10bp_bid: float
    avg_mid_move_bps: float | None
    last_update_id: int | None
    best_bid: tuple[float, float] | None
    best_ask: tuple[float, float] | None


def run_l2_backtest_jsonl(path: str, *, strict: bool = True) -> L2BacktestResult:
    events = EventReplayer.from_jsonl(path).run()
    book = LocalOrderBook()

    snapshot_events = 0
    update_events = 0
    skipped_events = 0
    ignored_non_depth_events = 0
    gap_events = 0

    spread_samples: list[float] = []
    depth_5bp_samples: list[float] = []
    depth_10bp_samples: list[float] = []
    mid_prices: list[float] = []

    for event in events:
        if event.event_type == "depth_snapshot":
            payload = event.payload
            try:
                book.load_snapshot(
                    last_update_id=int(payload["last_update_id"]),
                    bids=tuple((float(px), float(sz)) for px, sz in payload.get("bids", [])),
                    asks=tuple((float(px), float(sz)) for px, sz in payload.get("asks", [])),
                )
            except Exception:
                if strict:
                    raise ValueError("invalid depth_snapshot payload")
                skipped_events += 1
                continue
            snapshot_events += 1

        elif event.event_type == "depth_update":
            payload = event.payload
            try:
                update = DepthUpdate(
                    first_update_id=int(payload["first_update_id"]),
                    final_update_id=int(payload["final_update_id"]),
                    bids=tuple((float(px), float(sz)) for px, sz in payload.get("bids", [])),
                    asks=tuple((float(px), float(sz)) for px, sz in payload.get("asks", [])),
                )
                book.apply(update)
            except ValueError as exc:
                if "sequence gap" in str(exc):
                    gap_events += 1
                if strict:
                    raise
                skipped_events += 1
                continue
            except Exception:
                if strict:
                    raise ValueError("invalid depth_update payload")
                skipped_events += 1
                continue
            update_events += 1

        else:
            ignored_non_depth_events += 1
            skipped_events += 1
            continue

        metrics = compute_microstructure_metrics(book)
        if metrics.spread_bps is not None:
            spread_samples.append(metrics.spread_bps)
        depth_5bp_samples.append(metrics.depth_5bp_bid)
        depth_10bp_samples.append(metrics.depth_10bp_bid)
        if book.mid_price is not None:
            mid_prices.append(book.mid_price)

    mid_moves: list[float] = []
    for prev, cur in zip(mid_prices, mid_prices[1:]):
        if prev > 0:
            mid_moves.append(abs((cur - prev) / prev) * 10_000)

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    depth_events = snapshot_events + update_events
    return L2BacktestResult(
        total_events=len(events),
        depth_events=depth_events,
        snapshot_events=snapshot_events,
        update_events=update_events,
        skipped_events=skipped_events,
        ignored_non_depth_events=ignored_non_depth_events,
        gap_events=gap_events,
        avg_spread_bps=_avg(spread_samples),
        avg_depth_5bp_bid=(sum(depth_5bp_samples) / len(depth_5bp_samples)) if depth_5bp_samples else 0.0,
        avg_depth_10bp_bid=(sum(depth_10bp_samples) / len(depth_10bp_samples)) if depth_10bp_samples else 0.0,
        avg_mid_move_bps=_avg(mid_moves),
        last_update_id=book.last_update_id,
        best_bid=book.best_bid,
        best_ask=book.best_ask,
    )
