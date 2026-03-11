import unittest

from wickhunter.marketdata.orderbook import DepthUpdate, LocalOrderBook


class TestOrderBook(unittest.TestCase):
    def test_snapshot_then_diff_updates(self) -> None:
        book = LocalOrderBook()
        book.load_snapshot(
            last_update_id=10,
            bids=((100.0, 2.0), (99.0, 5.0)),
            asks=((101.0, 1.0), (102.0, 2.0)),
        )

        book.apply(DepthUpdate(first_update_id=11, final_update_id=11, bids=((100.0, 3.0),), asks=()))
        book.apply(DepthUpdate(first_update_id=12, final_update_id=12, bids=(), asks=((101.0, 0.0),)))

        self.assertEqual(book.best_bid, (100.0, 3.0))
        self.assertEqual(book.best_ask, (102.0, 2.0))
        self.assertEqual(book.mid_price, 101.0)

    def test_gap_raises(self) -> None:
        book = LocalOrderBook()
        book.load_snapshot(last_update_id=20, bids=((10.0, 1.0),), asks=((11.0, 1.0),))

        with self.assertRaises(ValueError):
            book.apply(DepthUpdate(first_update_id=25, final_update_id=25))

    def test_stale_update_ignored(self) -> None:
        book = LocalOrderBook()
        book.load_snapshot(last_update_id=30, bids=((10.0, 2.0),), asks=((11.0, 3.0),))
        book.apply(DepthUpdate(first_update_id=29, final_update_id=30, bids=((10.0, 5.0),)))
        self.assertEqual(book.best_bid, (10.0, 2.0))


if __name__ == "__main__":
    unittest.main()
