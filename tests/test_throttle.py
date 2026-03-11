import unittest

from wickhunter.execution.throttle import CancelThrottle


class TestCancelThrottle(unittest.TestCase):
    def test_reject_before_min_live_time(self) -> None:
        throttle = CancelThrottle(max_cancels_per_window=3, window_seconds=5.0, min_order_live_seconds=0.5)
        ok, reason = throttle.can_cancel(now=10.2, order_created_at=10.0)
        self.assertFalse(ok)
        self.assertEqual(reason, "min_live_time")

    def test_reject_when_cancel_rate_too_high(self) -> None:
        throttle = CancelThrottle(max_cancels_per_window=2, window_seconds=5.0, min_order_live_seconds=0.1)
        for t in (10.2, 10.5):
            ok, reason = throttle.can_cancel(now=t, order_created_at=10.0)
            self.assertTrue(ok, reason)
            throttle.record_cancel(now=t)

        ok, reason = throttle.can_cancel(now=10.8, order_created_at=10.0)
        self.assertFalse(ok)
        self.assertEqual(reason, "cancel_rate_limit")

    def test_allow_after_window_rolls(self) -> None:
        throttle = CancelThrottle(max_cancels_per_window=1, window_seconds=2.0, min_order_live_seconds=0.1)
        ok, _ = throttle.can_cancel(now=10.2, order_created_at=10.0)
        self.assertTrue(ok)
        throttle.record_cancel(now=10.2)

        ok, reason = throttle.can_cancel(now=12.3, order_created_at=10.0)
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
