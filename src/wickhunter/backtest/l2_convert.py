import json
from dataclasses import dataclass
from pathlib import Path

from wickhunter.exchange.binance_futures import BinanceFuturesDepthParser


@dataclass(frozen=True, slots=True)
class DepthConvertStats:
    total_lines: int
    written_events: int
    skipped_lines: int


def convert_binance_depth_jsonl_to_replay(
    input_path: str | Path,
    output_path: str | Path,
    *,
    strict: bool = True,
) -> DepthConvertStats:
    parser = BinanceFuturesDepthParser()
    in_path = Path(input_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    written = 0
    skipped = 0

    with in_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as dst:
        for line_no, raw in enumerate(src, start=1):
            line = raw.strip()
            if not line:
                continue
            total += 1

            try:
                event = parser.parse_depth_event(line)
            except Exception:
                if strict:
                    raise ValueError(f"line {line_no}: invalid binance depth payload")
                skipped += 1
                continue

            replay_event = {
                "ts_ms": event.event_ts_ms,
                "event_type": "depth_update",
                "payload": {
                    "exchange": event.exchange,
                    "symbol": event.symbol,
                    "first_update_id": event.first_update_id,
                    "final_update_id": event.final_update_id,
                    "bids": event.bids,
                    "asks": event.asks,
                },
            }
            dst.write(json.dumps(replay_event, ensure_ascii=False) + "\n")
            written += 1

    return DepthConvertStats(total_lines=total, written_events=written, skipped_lines=skipped)
