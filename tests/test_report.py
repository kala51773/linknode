import unittest

from wickhunter.analytics.report import EventPnL, build_event_report
from wickhunter.simulation.hedge_latency import HedgeSimulationResult


class TestReport(unittest.TestCase):
    def test_build_event_report(self) -> None:
        report = build_event_report(
            pnls=[EventPnL(gross_pnl=10, fees=1, funding=1), EventPnL(gross_pnl=-2, fees=0.5, funding=0)],
            hedge_results=[
                HedgeSimulationResult(hedge_latency_ms=20, expected_slippage_bps=0.3),
                HedgeSimulationResult(hedge_latency_ms=30, expected_slippage_bps=0.5),
            ],
        )
        self.assertEqual(report.event_count, 2)
        self.assertEqual(report.total_net_pnl, 5.5)
        self.assertEqual(report.avg_net_pnl, 2.75)
        self.assertEqual(report.avg_hedge_latency_ms, 25.0)
        self.assertEqual(report.avg_slippage_bps, 0.4)
        self.assertEqual(report.win_rate, 0.5)
        self.assertEqual(report.max_drawdown, 2.5)
        self.assertEqual(report.profit_factor, 3.2)


if __name__ == "__main__":
    unittest.main()
