from dataclasses import dataclass

from wickhunter.analytics.report import EventPnL, EventReport, build_event_report
from wickhunter.backtest.replay import EventReplayer
from wickhunter.simulation.hedge_latency import HedgeLatencyModel


@dataclass(frozen=True, slots=True)
class BacktestResult:
    event_count: int
    fill_count: int
    skipped_fill_count: int
    skipped_fill_ratio: float
    total_net_pnl: float
    avg_net_pnl: float
    avg_hedge_latency_ms: float
    avg_slippage_bps: float
    win_rate: float
    max_drawdown: float
    profit_factor: float | None


class BacktestRunner:
    """Runs a simple event-driven backtest from JSONL replay events."""

    def __init__(self, latency_model: HedgeLatencyModel | None = None) -> None:
        self._latency_model = latency_model or HedgeLatencyModel()

    def run_jsonl(self, path: str, *, strict: bool = True) -> BacktestResult:
        events = EventReplayer.from_jsonl(path).run()

        pnls: list[EventPnL] = []
        hedge_results = []
        fill_count = 0
        skipped_fill_count = 0

        for event in events:
            if event.event_type != "fill":
                continue
            fill_count += 1

            try:
                gross_pnl = float(event.payload.get("gross_pnl", 0.0))
                fees = float(event.payload.get("fees", 0.0))
                funding = float(event.payload.get("funding", 0.0))
                hedge_notional = float(event.payload.get("hedge_notional", 0.0))
            except (TypeError, ValueError):
                if strict:
                    raise ValueError("invalid fill payload numeric fields")
                skipped_fill_count += 1
                continue

            if hedge_notional < 0:
                if strict:
                    raise ValueError("hedge_notional must be non-negative")
                skipped_fill_count += 1
                continue

            pnls.append(EventPnL(gross_pnl=gross_pnl, fees=fees, funding=funding))
            hedge_results.append(self._latency_model.simulate(hedge_notional=hedge_notional))

        report: EventReport = build_event_report(pnls=pnls, hedge_results=hedge_results)
        return BacktestResult(
            event_count=len(events),
            fill_count=fill_count,
            skipped_fill_count=skipped_fill_count,
            skipped_fill_ratio=round(skipped_fill_count / fill_count, 6) if fill_count else 0.0,
            total_net_pnl=report.total_net_pnl,
            avg_net_pnl=report.avg_net_pnl,
            avg_hedge_latency_ms=report.avg_hedge_latency_ms,
            avg_slippage_bps=report.avg_slippage_bps,
            win_rate=report.win_rate,
            max_drawdown=report.max_drawdown,
            profit_factor=report.profit_factor,
        )
