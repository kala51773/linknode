from dataclasses import dataclass
from typing import Dict
from wickhunter.strategy.universe import InstrumentMeta

@dataclass
class PairScore:
    pair_a: str
    pair_b: str
    score: float
    components: Dict[str, float]
    reason: str = "ok"

class PairSelector:
    """Calculates PRD scoring: score = 0.40 * Corr + 0.35 * R2 - 0.15 * BetaInstability - 0.10 * LiqPenalty"""
    
    def __init__(self, corr_weight: float = 0.4, r2_weight: float = 0.35, insta_weight: float = 0.15, liq_weight: float = 0.10):
        self.w_corr = corr_weight
        self.w_r2 = r2_weight
        self.w_insta = insta_weight
        self.w_liq = liq_weight

    def score_pair(
        self,
        b_meta: InstrumentMeta,
        a_meta: InstrumentMeta,
        stats: Dict[str, float],
        *,
        min_corr: float = 0.70,
        min_r2: float = 0.35,
        max_beta_instability: float = 0.60,
        min_half_life_seconds: float = 10.0,
        max_half_life_seconds: float = 600.0,
    ) -> PairScore:
        """
        stats expected to contain: corr_30d, r2_6h, beta_instability, liquidity_penalty
        """
        corr = stats.get("corr_30d", 0.0)
        r2 = stats.get("r2_6h", 0.0)
        beta_inst = stats.get("beta_instability", 0.0)
        liq_pen = stats.get("liquidity_penalty", 0.0)
        half_life = stats.get("half_life_seconds", 0.0)

        # Thresholds per PRD
        if corr < min_corr:
            # Drop pair if below hard PRD limits
            return PairScore(a_meta.symbol, b_meta.symbol, 0.0, stats, reason="corr_too_low")
        if r2 < min_r2:
            return PairScore(a_meta.symbol, b_meta.symbol, 0.0, stats, reason="r2_too_low")
        if beta_inst > max_beta_instability:
            return PairScore(a_meta.symbol, b_meta.symbol, 0.0, stats, reason="beta_unstable")
        if half_life < min_half_life_seconds or half_life > max_half_life_seconds:
            return PairScore(a_meta.symbol, b_meta.symbol, 0.0, stats, reason="half_life_out_of_range")

        total_score = (
            self.w_corr * corr + 
            self.w_r2 * r2 - 
            self.w_insta * beta_inst - 
            self.w_liq * liq_pen
        )
        
        return PairScore(
            pair_a=a_meta.symbol,
            pair_b=b_meta.symbol,
            score=max(0.0, total_score),
            components=stats,
            reason="ok",
        )

    @staticmethod
    def liquidity_penalty_by_ratio(
        *,
        b_to_a_volume_ratio: float,
        target_ratio: float = 0.10,
        min_ratio: float = 0.02,
        max_ratio: float = 0.35,
    ) -> float:
        """0 means ideal (close to target), 1 means poor liquidity profile."""
        if b_to_a_volume_ratio <= 0:
            return 1.0
        if b_to_a_volume_ratio < min_ratio or b_to_a_volume_ratio > max_ratio:
            return 1.0
        left_span = max(target_ratio - min_ratio, 1e-9)
        right_span = max(max_ratio - target_ratio, 1e-9)
        span = left_span if b_to_a_volume_ratio <= target_ratio else right_span
        return min(1.0, abs(b_to_a_volume_ratio - target_ratio) / span)
