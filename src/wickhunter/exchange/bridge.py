from dataclasses import dataclass

from wickhunter.exchange.binance_futures import BinanceFuturesClient
from wickhunter.exchange.okx_swap import OKXSwapClient
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


@dataclass(slots=True)
class OKXSignalBridge:
    """Bridges raw OKX depth payloads into SignalEngine normalized ingestion."""

    client: OKXSwapClient
    signal_engine: SignalEngine

    def ingest_depth_payload(self, payload: str) -> bool:
        try:
            event = self.client.normalize_depth_payload(payload)
        except ValueError:
            return False
        self.signal_engine.on_normalized_depth_event(event)
        return True

    def ingest_many(self, payloads: list[str]) -> int:
        accepted = 0
        for payload in payloads:
            accepted += 1 if self.ingest_depth_payload(payload) else 0
        return accepted
