from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class InstrumentMeta:
    symbol: str
    base_asset: str
    quote_asset: str
    tick_size: float
    lot_size: float
    volume_24h_usd: float
    status: str = "TRADING"
    contract_type: str = ""

class UniverseManager:
    """Manages the pool of active pairs for screening."""
    def __init__(self) -> None:
        self.active_instruments: Dict[str, InstrumentMeta] = {}

    def update_from_exchange(self, raw_markets: List[Dict[str, Any]]) -> None:
        """Build universe metadata from exchange info."""
        self.active_instruments.clear()
        for m in raw_markets:
            sym = m.get("symbol")
            if not sym: 
                continue
            self.active_instruments[sym] = InstrumentMeta(
                symbol=sym,
                base_asset=m.get("baseAsset", ""),
                quote_asset=m.get("quoteAsset", ""),
                tick_size=float(m.get("tickSize", 0.001)),
                lot_size=float(m.get("stepSize", 0.001)),
                volume_24h_usd=float(m.get("quoteVolume", 0.0)),
                status=str(m.get("status", "TRADING")),
                contract_type=str(m.get("contractType", "")),
            )

    def filter_by_min_volume(self, min_volume_usd: float) -> List[InstrumentMeta]:
        """Returns list of active instruments filtered by 24h volume threshold."""
        return [meta for meta in self.active_instruments.values() if meta.volume_24h_usd >= min_volume_usd]

    def filter_for_discovery(
        self,
        *,
        quote_asset: str = "USDT",
        min_volume_usd: float = 1_000_000.0,
        max_volume_usd: float | None = None,
        allowed_symbols: set[str] | None = None,
        excluded_symbols: set[str] | None = None,
    ) -> List[InstrumentMeta]:
        quote = quote_asset.upper()
        allow = allowed_symbols if allowed_symbols is not None else set()
        deny = excluded_symbols if excluded_symbols is not None else set()
        out: list[InstrumentMeta] = []
        for meta in self.active_instruments.values():
            if meta.status and meta.status.upper() != "TRADING":
                continue
            if meta.quote_asset.upper() != quote:
                continue
            if meta.volume_24h_usd < min_volume_usd:
                continue
            if max_volume_usd is not None and meta.volume_24h_usd > max_volume_usd:
                continue
            if allow and meta.symbol not in allow:
                continue
            if meta.symbol in deny:
                continue
            out.append(meta)
        return out
