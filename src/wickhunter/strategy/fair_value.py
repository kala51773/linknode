import math
from dataclasses import dataclass

@dataclass
class FairValueState:
    fair_price: float
    confidence: float
    
class FairValueEstimator:
    """
    fair_B_t = w * fair_cross_venue_B_t + (1-w) * fair_model_B_t
    spread_t = log(P_B_local) - beta * log(P_A)
    fair_model_B_t = exp(beta * log(P_A) + mean_spread)
    """
    def __init__(self, venue_weight: float = 0.5):
        self.venue_weight = venue_weight
        self.latest_cross_venue_fair = 0.0
        self.latest_model_fair = 0.0

    def update_cross_venue(self, price: float) -> None:
        """Update fair B from secondary exchange (e.g. OKX)."""
        self.latest_cross_venue_fair = price

    def update_model(self, price_a: float, beta: float, mean_spread: float) -> None:
        """Derive fair B from A price and co-integration parameters."""
        if price_a > 0.0:
            self.latest_model_fair = math.exp(beta * math.log(price_a) + mean_spread)
        else:
            self.latest_model_fair = 0.0

    def get_fair_value(self) -> FairValueState:
        """Blends model and cross-venue fair values."""
        if self.latest_cross_venue_fair > 0 and self.latest_model_fair > 0:
            p = self.venue_weight * self.latest_cross_venue_fair + (1.0 - self.venue_weight) * self.latest_model_fair
            return FairValueState(fair_price=p, confidence=1.0)
        elif self.latest_model_fair > 0:
            return FairValueState(fair_price=self.latest_model_fair, confidence=0.5)
        elif self.latest_cross_venue_fair > 0:
            return FairValueState(fair_price=self.latest_cross_venue_fair, confidence=0.5)
        
        return FairValueState(fair_price=0.0, confidence=0.0)
