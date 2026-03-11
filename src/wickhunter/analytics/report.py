from dataclasses import dataclass

from wickhunter.simulation.hedge_latency import HedgeSimulationResult


@dataclass(frozen=True, slots=True)
class EventPnL:
    gross_pnl: float
    fees: float
    funding: float

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees - self.funding


@dataclass(frozen=True, slots=True)
class EventReport:
    event_count: int
    total_net_pnl: float
    avg_hedge_latency_ms: float
    avg_slippage_bps: float


def build_event_report(pnls: list[EventPnL], hedge_results: list[HedgeSimulationResult]) -> EventReport:
    event_count = len(pnls)
    total_net_pnl = round(sum(p.net_pnl for p in pnls), 6)

    if hedge_results:
        avg_latency = sum(h.hedge_latency_ms for h in hedge_results) / len(hedge_results)
        avg_slippage = sum(h.expected_slippage_bps for h in hedge_results) / len(hedge_results)
    else:
        avg_latency = 0.0
        avg_slippage = 0.0

    return EventReport(
        event_count=event_count,
        total_net_pnl=total_net_pnl,
        avg_hedge_latency_ms=round(avg_latency, 3),
        avg_slippage_bps=round(avg_slippage, 6),
    )
