from dataclasses import dataclass

from wickhunter.exchange.binance_futures import BinanceFuturesClient
from wickhunter.strategy.signal_engine import SignalEngine


@dataclass(slots=True)
class BinanceSignalBridge:
    """Bridges raw Binance depth payloads into SignalEngine normalized ingestion."""

    client: BinanceFuturesClient
    signal_engine: SignalEngine

    def ingest_depth_payload(self, payload: str) -> None:
        event = self.client.normalize_depth_payload(payload)
        self.signal_engine.on_normalized_depth_event(event)

    def ingest_many(self, payloads: list[str]) -> int:
        for payload in payloads:
            self.ingest_depth_payload(payload)
        return len(payloads)
