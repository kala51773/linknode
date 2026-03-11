import unittest

from wickhunter.simulation.hedge_latency import HedgeLatencyModel


class TestLatencyModel(unittest.TestCase):
    def test_simulate_latency_and_slippage(self) -> None:
        model = HedgeLatencyModel(base_latency_ms=10, latency_per_notional_ms=0.01, base_slippage_bps=0.5, slippage_per_notional_bps=0.001)
        result = model.simulate(hedge_notional=100)
        self.assertEqual(result.hedge_latency_ms, 11)
        self.assertAlmostEqual(result.expected_slippage_bps, 0.6)

    def test_negative_notional_rejected(self) -> None:
        model = HedgeLatencyModel()
        with self.assertRaises(ValueError):
            model.simulate(-1)


if __name__ == "__main__":
    unittest.main()
