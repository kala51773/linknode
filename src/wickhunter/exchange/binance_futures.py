import json
from dataclasses import dataclass

from wickhunter.exchange.models import NormalizedDepthEvent


@dataclass(slots=True)
class BinanceFuturesDepthParser:
    """Parses Binance USDⓈ-M diff-depth payload into normalized event format."""

    exchange_name: str = "binance_futures"

    def parse_depth_event(self, payload: str) -> NormalizedDepthEvent:
        raw = json.loads(payload)

        # Binance futures diff stream fields: e, E, s, U, u, b, a
        symbol = raw["s"]
        first_update_id = int(raw["U"])
        final_update_id = int(raw["u"])
        event_ts_ms = int(raw["E"])

        bids = tuple((float(px), float(qty)) for px, qty in raw.get("b", []))
        asks = tuple((float(px), float(qty)) for px, qty in raw.get("a", []))

        return NormalizedDepthEvent(
            exchange=self.exchange_name,
            symbol=symbol,
            first_update_id=first_update_id,
            final_update_id=final_update_id,
            bids=bids,
            asks=asks,
            event_ts_ms=event_ts_ms,
        )


@dataclass(slots=True)
class BinanceFuturesClient:
    """Thin client shell to host REST/WS integration in future milestones."""

    depth_parser: BinanceFuturesDepthParser

    def normalize_depth_payload(self, payload: str) -> NormalizedDepthEvent:
        return self.depth_parser.parse_depth_event(payload)
