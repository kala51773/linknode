from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedDepthEvent:
    exchange: str
    symbol: str
    first_update_id: int
    final_update_id: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    event_ts_ms: int
