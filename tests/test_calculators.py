import unittest

from wickhunter.marketdata.calculators import compute_microstructure_metrics
from wickhunter.marketdata.orderbook import LocalOrderBook


class TestCalculators(unittest.TestCase):
    def test_compute_metrics(self) -> None:
        book = LocalOrderBook()
        book.load_snapshot(
            last_update_id=1,
            bids=((100.0, 2.0), (99.96, 3.0), (99.8, 5.0)),
            asks=((100.04, 2.0),),
        )

        metrics = compute_microstructure_metrics(book)

        self.assertIsNotNone(metrics.spread_bps)
        assert metrics.spread_bps is not None
        self.assertGreater(metrics.spread_bps, 0)
        self.assertEqual(metrics.depth_5bp_bid, 5.0)
        self.assertEqual(metrics.depth_10bp_bid, 5.0)

    def test_empty_book_metrics(self) -> None:
        metrics = compute_microstructure_metrics(LocalOrderBook())
        self.assertIsNone(metrics.spread_bps)
        self.assertEqual(metrics.depth_5bp_bid, 0.0)
        self.assertEqual(metrics.depth_10bp_bid, 0.0)


if __name__ == "__main__":
    unittest.main()
