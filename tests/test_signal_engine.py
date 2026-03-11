import unittest

from wickhunter.exchange.models import NormalizedDepthEvent
from wickhunter.marketdata.orderbook import DepthUpdate
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine


class TestSignalEngine(unittest.TestCase):
    def test_plan_blocked_before_sync(self) -> None:
        engine = SignalEngine(
            quote_engine=QuoteEngine(),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )

        plan = engine.generate_quote_plan(fair_price=100.0)
        self.assertFalse(plan.armed)
        self.assertEqual(plan.reason, "not_synced")

    def test_plan_generated_after_sync(self) -> None:
        engine = SignalEngine(
            quote_engine=QuoteEngine(max_name_risk=1000),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )

        engine.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 30.0),)))
        engine.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((100.1, 5.0),)))
        engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

        plan = engine.generate_quote_plan(fair_price=100.0)
        self.assertTrue(plan.armed)
        self.assertEqual(len(plan.levels), 3)

    def test_accept_normalized_depth_event(self) -> None:
        engine = SignalEngine(
            quote_engine=QuoteEngine(max_name_risk=1000),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )

        engine.on_normalized_depth_event(
            NormalizedDepthEvent(
                exchange="binance_futures",
                symbol="BTCUSDT",
                first_update_id=101,
                final_update_id=101,
                bids=((100.0, 30.0),),
                asks=tuple(),
                event_ts_ms=1,
            )
        )
        engine.on_normalized_depth_event(
            NormalizedDepthEvent(
                exchange="binance_futures",
                symbol="BTCUSDT",
                first_update_id=102,
                final_update_id=102,
                bids=tuple(),
                asks=((100.1, 5.0),),
                event_ts_ms=2,
            )
        )
        engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))

        plan = engine.generate_quote_plan(fair_price=100.0)
        self.assertTrue(plan.armed)
        self.assertEqual(plan.reason, "ok")


if __name__ == "__main__":
    unittest.main()
