from dataclasses import dataclass

from wickhunter.common.events import FillEvent, HedgeOrder


@dataclass(slots=True)
class HedgeManager:
    """Converts B-leg fills into A-leg hedge orders."""

    hedge_symbol: str
    beta_exec: float = 1.0
    aggressiveness_bps: float = 2.0

    def build_hedge_order(self, fill: FillEvent, reference_price: float) -> HedgeOrder:
        if fill.qty <= 0 or fill.price <= 0 or reference_price <= 0:
            raise ValueError("invalid fill/reference price")

        normalized_side = fill.side.upper()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("invalid fill side")

        hedge_qty = self.beta_exec * fill.qty * fill.price / reference_price
        # B leg buy -> short hedge on A; B leg sell -> long hedge on A.
        side = "SELL" if normalized_side == "BUY" else "BUY"
        price_multiplier = 1 - self.aggressiveness_bps / 10_000 if side == "SELL" else 1 + self.aggressiveness_bps / 10_000
        limit_price = reference_price * price_multiplier
        return HedgeOrder(
            symbol=self.hedge_symbol,
            side=side,
            qty=round(hedge_qty, 8),
            limit_price=round(limit_price, 8),
        )
