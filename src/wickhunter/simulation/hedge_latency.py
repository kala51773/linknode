from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HedgeSimulationResult:
    hedge_latency_ms: int
    expected_slippage_bps: float


@dataclass(slots=True)
class HedgeLatencyModel:
    """Toy model for latency/slippage approximation in M3 replay simulations."""

    base_latency_ms: int = 35
    latency_per_notional_ms: float = 0.002
    base_slippage_bps: float = 0.4
    slippage_per_notional_bps: float = 0.00005

    def simulate(self, hedge_notional: float) -> HedgeSimulationResult:
        if hedge_notional < 0:
            raise ValueError("hedge_notional must be non-negative")

        latency = int(round(self.base_latency_ms + hedge_notional * self.latency_per_notional_ms))
        slippage = self.base_slippage_bps + hedge_notional * self.slippage_per_notional_bps
        return HedgeSimulationResult(hedge_latency_ms=latency, expected_slippage_bps=round(slippage, 6))
