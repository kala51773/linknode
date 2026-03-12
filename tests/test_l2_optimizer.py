import unittest

from wickhunter.analytics.report import EventReport
from wickhunter.backtest.l2_simulator import L2TuningConfig, L2TuningResult, select_best_tuning_result


class TestL2Optimizer(unittest.TestCase):
    def test_select_best_prefers_min_event_eligible(self) -> None:
        results = [
            L2TuningResult(
                config=L2TuningConfig(theta1=1e-5, theta2=2e-5, theta3=3e-5, baseline_depth_5bp=1e9),
                report=EventReport(event_count=0, total_net_pnl=0.0, avg_hedge_latency_ms=0.0, avg_slippage_bps=0.0),
            ),
            L2TuningResult(
                config=L2TuningConfig(theta1=1e-4, theta2=2e-4, theta3=3e-4, baseline_depth_5bp=1e9),
                report=EventReport(event_count=20, total_net_pnl=-5.0, avg_hedge_latency_ms=35.0, avg_slippage_bps=0.4),
            ),
            L2TuningResult(
                config=L2TuningConfig(theta1=2e-4, theta2=4e-4, theta3=6e-4, baseline_depth_5bp=1e9),
                report=EventReport(event_count=40, total_net_pnl=-2.0, avg_hedge_latency_ms=36.0, avg_slippage_bps=0.5),
            ),
        ]

        best = select_best_tuning_result(results, min_events=10)
        assert best is not None
        self.assertEqual(best.report.total_net_pnl, -2.0)
        self.assertEqual(best.report.event_count, 40)

    def test_select_best_falls_back_when_no_eligible_events(self) -> None:
        results = [
            L2TuningResult(
                config=L2TuningConfig(theta1=1e-5, theta2=2e-5, theta3=3e-5, baseline_depth_5bp=1e9),
                report=EventReport(event_count=0, total_net_pnl=0.0, avg_hedge_latency_ms=0.0, avg_slippage_bps=0.0),
            ),
            L2TuningResult(
                config=L2TuningConfig(theta1=2e-5, theta2=4e-5, theta3=6e-5, baseline_depth_5bp=1e9),
                report=EventReport(event_count=3, total_net_pnl=-1.0, avg_hedge_latency_ms=30.0, avg_slippage_bps=0.2),
            ),
        ]

        best = select_best_tuning_result(results, min_events=10)
        assert best is not None
        self.assertEqual(best.report.event_count, 3)
        self.assertEqual(best.report.total_net_pnl, -1.0)


if __name__ == "__main__":
    unittest.main()
