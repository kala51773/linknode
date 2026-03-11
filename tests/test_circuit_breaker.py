import unittest

from wickhunter.risk.checks import RuntimeRiskState
from wickhunter.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreaker(unittest.TestCase):
    def test_trip_on_latency(self) -> None:
        cb = CircuitBreaker(max_marketdata_latency_ms=250)
        ok, reason = cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=300,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "marketdata_latency")

    def test_trip_on_exchange_restriction(self) -> None:
        cb = CircuitBreaker()
        ok, reason = cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=100,
            consecutive_hedge_failures=0,
            exchange_restricted=True,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "exchange_restricted")

    def test_stays_tripped_without_cooldown(self) -> None:
        cb = CircuitBreaker()
        cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=300,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
            now_monotonic=10.0,
        )
        ok, reason = cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=100,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
            now_monotonic=20.0,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "marketdata_latency")

    def test_auto_resume_after_cooldown(self) -> None:
        cb = CircuitBreaker(cooldown_seconds=5.0)
        cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=300,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
            now_monotonic=10.0,
        )
        ok_before, _ = cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=100,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
            now_monotonic=14.0,
        )
        ok_after, reason_after = cb.evaluate(
            risk_state=RuntimeRiskState(),
            marketdata_latency_ms=100,
            consecutive_hedge_failures=0,
            exchange_restricted=False,
            now_monotonic=16.0,
        )
        self.assertFalse(cb.is_tripped)
        self.assertFalse(ok_before)
        self.assertTrue(ok_after)
        self.assertEqual(reason_after, "ok")


if __name__ == "__main__":
    unittest.main()
