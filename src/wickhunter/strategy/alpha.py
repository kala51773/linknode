from dataclasses import dataclass, field
import math

@dataclass(frozen=True, slots=True)
class PairStats:
    beta: float
    gamma: float
    corr: float
    r2: float
    beta_instability: float
    liquidity_penalty: float

@dataclass(frozen=True, slots=True)
class FairValue:
    fair_price: float
    gap: float
    spread: float
    score: float

@dataclass
class ResidualModel:
    """Calculates pair residual and fair value based on PRD V1."""

    stats: PairStats
    model_weight: float = 1.0

    def compute_fair_value(self, p_B_local: float, p_A: float, p_sector: float, cross_venue_fair: float | None = None) -> FairValue:
        # spread_t = log(P_B_local) - β_A * log(P_A) - γ * log(P_sector)
        spread = math.log(p_B_local) - self.stats.beta * math.log(p_A) - self.stats.gamma * math.log(p_sector)
        
        # fair_B_t implied by the model 
        # Since log(fair) = spread + β_A * log(P_A) + γ * log(P_sector), and we expect spread to mean-revert to 0:
        log_fair_model = self.stats.beta * math.log(p_A) + self.stats.gamma * math.log(p_sector)
        fair_model = math.exp(log_fair_model)
        
        if cross_venue_fair is not None and self.model_weight < 1.0:
            fair = (1 - self.model_weight) * cross_venue_fair + self.model_weight * fair_model
        else:
            fair = fair_model
            
        gap = (p_B_local / fair) - 1.0 if fair > 0 else 0.0
        
        score = (
            0.40 * self.stats.corr +
            0.35 * self.stats.r2 -
            0.15 * self.stats.beta_instability -
            0.10 * self.stats.liquidity_penalty
        )
        
        return FairValue(fair_price=fair, gap=gap, spread=spread, score=score)
