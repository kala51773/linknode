from dataclasses import dataclass

from wickhunter.backtest.replay import EventReplayer
from wickhunter.marketdata.orderbook import DepthUpdate, LocalOrderBook


@dataclass(frozen=True, slots=True)
class DepthReplayResult:
    total_events: int
    snapshot_events: int
    update_events: int
    skipped_events: int
    ignored_non_depth_events: int
    gap_events: int
    last_update_id: int | None
    best_bid: tuple[float, float] | None
    best_ask: tuple[float, float] | None
    mid_price: float | None


def run_depth_replay_jsonl(path: str, *, strict: bool = True) -> DepthReplayResult:
    events = EventReplayer.from_jsonl(path).run()
    book = LocalOrderBook()

    snapshot_events = 0
    update_events = 0
    skipped_events = 0
    ignored_non_depth_events = 0
    gap_events = 0

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
            continue

        if event.event_type != "depth_update":
            ignored_non_depth_events += 1
            skipped_events += 1
            continue

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

    return DepthReplayResult(
        total_events=len(events),
        snapshot_events=snapshot_events,
        update_events=update_events,
        skipped_events=skipped_events,
        ignored_non_depth_events=ignored_non_depth_events,
        gap_events=gap_events,
        last_update_id=book.last_update_id,
        best_bid=book.best_bid,
        best_ask=book.best_ask,
        mid_price=book.mid_price,
    )
