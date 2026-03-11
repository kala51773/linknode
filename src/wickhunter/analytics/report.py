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
    avg_net_pnl: float
    avg_hedge_latency_ms: float
    avg_slippage_bps: float
    win_rate: float
    max_drawdown: float
    profit_factor: float | None


def build_event_report(pnls: list[EventPnL], hedge_results: list[HedgeSimulationResult]) -> EventReport:
    event_count = len(pnls)
    net_series = [p.net_pnl for p in pnls]
    total_net_pnl = round(sum(net_series), 6)

    if hedge_results:
        avg_latency = sum(h.hedge_latency_ms for h in hedge_results) / len(hedge_results)
        avg_slippage = sum(h.expected_slippage_bps for h in hedge_results) / len(hedge_results)
    else:
        avg_latency = 0.0
        avg_slippage = 0.0

    wins = sum(1 for n in net_series if n > 0)
    win_rate = (wins / event_count) if event_count else 0.0

    gross_wins = sum(n for n in net_series if n > 0)
    gross_losses = abs(sum(n for n in net_series if n < 0))
    profit_factor = None if gross_losses == 0 else gross_wins / gross_losses

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for net in net_series:
        cumulative += net
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    return EventReport(
        event_count=event_count,
        total_net_pnl=total_net_pnl,
        avg_net_pnl=round(total_net_pnl / event_count, 6) if event_count else 0.0,
        avg_hedge_latency_ms=round(avg_latency, 3),
        avg_slippage_bps=round(avg_slippage, 6),
        win_rate=round(win_rate, 6),
        max_drawdown=round(max_drawdown, 6),
        profit_factor=round(profit_factor, 6) if profit_factor is not None else None,
    )
