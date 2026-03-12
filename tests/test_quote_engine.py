import unittest

from wickhunter.marketdata.calculators import MicrostructureMetrics
from wickhunter.strategy.quote_engine import QuoteEngine


class TestQuoteEngine(unittest.TestCase):
    def test_arm_and_build_levels(self) -> None:
        engine = QuoteEngine(max_name_risk=2000)
        metrics = MicrostructureMetrics(spread_bps=12.0, depth_5bp_bid=30.0, depth_10bp_bid=40.0)
        armed, reason = engine.should_arm(metrics, baseline_depth_5bp=100.0)
        self.assertTrue(armed)
        self.assertEqual(reason, "ok")

        plan = engine.build_plan(fair_price=100.0, armed=armed, reason=reason)
        self.assertTrue(plan.armed)
        self.assertEqual(len(plan.levels), 3)
        self.assertEqual(plan.levels[0].size, 200.0)
        self.assertEqual(plan.levels[1].size, 300.0)
        self.assertEqual(plan.levels[2].size, 500.0)

    def test_not_armed_when_depth_not_collapsed(self) -> None:
        engine = QuoteEngine()
        metrics = MicrostructureMetrics(spread_bps=10.0, depth_5bp_bid=70.0, depth_10bp_bid=80.0)
        armed, reason = engine.should_arm(metrics, baseline_depth_5bp=100.0)
        self.assertFalse(armed)
        self.assertEqual(reason, "insufficient_depth_collapse")

        plan = engine.build_plan(fair_price=100.0, armed=armed, reason=reason)
        self.assertFalse(plan.armed)
        self.assertEqual(plan.levels, tuple())

    def test_not_armed_when_edge_below_cost_threshold(self) -> None:
        engine = QuoteEngine(theta1=0.0001, theta2=0.0002, theta3=0.0003, min_expected_edge_bps=2.0)
        metrics = MicrostructureMetrics(spread_bps=10.0, depth_5bp_bid=20.0, depth_10bp_bid=30.0)
        armed, reason = engine.should_arm(metrics, baseline_depth_5bp=100.0)
        self.assertFalse(armed)
        self.assertEqual(reason, "edge_below_cost")


if __name__ == "__main__":
    unittest.main()
