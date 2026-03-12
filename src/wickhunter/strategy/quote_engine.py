from dataclasses import dataclass

from wickhunter.marketdata.calculators import MicrostructureMetrics


@dataclass(frozen=True, slots=True)
class QuoteLevel:
    price: float
    size: float


@dataclass(frozen=True, slots=True)
class QuotePlan:
    armed: bool
    levels: tuple[QuoteLevel, ...]
    reason: str


@dataclass(slots=True)
class QuoteEngine:
    theta1: float = 0.006
    theta2: float = 0.010
    theta3: float = 0.016
    max_name_risk: float = 10_000.0
    min_expected_edge_bps: float = 0.0

    def should_arm(self, metrics: MicrostructureMetrics, baseline_depth_5bp: float) -> tuple[bool, str]:
        if baseline_depth_5bp <= 0:
            return False, "invalid_baseline"
        if metrics.spread_bps is None:
            return False, "missing_spread"
        if (self.theta1 * 10_000.0) < self.min_expected_edge_bps:
            return False, "edge_below_cost"

        depth_ratio = metrics.depth_5bp_bid / baseline_depth_5bp
        if depth_ratio > 0.40:
            return False, "insufficient_depth_collapse"
        if metrics.spread_bps > 30:
            return False, "spread_too_wide"
        return True, "ok"

    def build_plan(self, fair_price: float, armed: bool, reason: str = "ok") -> QuotePlan:
        if not armed:
            return QuotePlan(armed=False, levels=tuple(), reason=reason)

        levels = (
            QuoteLevel(price=round(fair_price * (1 - self.theta1), 8), size=round(self.max_name_risk * 0.10, 8)),
            QuoteLevel(price=round(fair_price * (1 - self.theta2), 8), size=round(self.max_name_risk * 0.15, 8)),
            QuoteLevel(price=round(fair_price * (1 - self.theta3), 8), size=round(self.max_name_risk * 0.25, 8)),
        )
        return QuotePlan(armed=True, levels=levels, reason=reason)
