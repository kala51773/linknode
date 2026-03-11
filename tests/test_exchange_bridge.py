import unittest

from wickhunter.exchange.binance_futures import BinanceFuturesClient, BinanceFuturesDepthParser
from wickhunter.exchange.bridge import BinanceSignalBridge
from wickhunter.marketdata.synchronizer import BookSynchronizer
from wickhunter.strategy.quote_engine import QuoteEngine
from wickhunter.strategy.signal_engine import SignalEngine


class TestExchangeBridge(unittest.TestCase):
    def test_ingest_many_feeds_signal_engine(self) -> None:
        signal_engine = SignalEngine(
            quote_engine=QuoteEngine(max_name_risk=1000),
            baseline_depth_5bp=100.0,
            synchronizer=BookSynchronizer(),
        )
        bridge = BinanceSignalBridge(
            client=BinanceFuturesClient(depth_parser=BinanceFuturesDepthParser()),
            signal_engine=signal_engine,
        )

        payloads = [
            '{"e":"depthUpdate","E":1,"s":"BTCUSDT","U":101,"u":101,"pu":100,"b":[["100.0","30.0"]],"a":[]}',
            '{"e":"depthUpdate","E":2,"s":"BTCUSDT","U":102,"u":102,"pu":101,"b":[],"a":[["100.1","5.0"]]}',
        ]

        count = bridge.ingest_many(payloads)
        signal_engine.on_snapshot(last_update_id=100, bids=((99.5, 20.0),), asks=((100.5, 5.0),))
        plan = signal_engine.generate_quote_plan(fair_price=100.0)

        self.assertEqual(count, 2)
        self.assertTrue(plan.armed)
        self.assertEqual(len(plan.levels), 3)


if __name__ == "__main__":
    unittest.main()
