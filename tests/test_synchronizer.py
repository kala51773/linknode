import unittest

from wickhunter.marketdata.orderbook import DepthUpdate
from wickhunter.marketdata.synchronizer import BookSynchronizer


class TestBookSynchronizer(unittest.TestCase):
    def test_buffer_then_snapshot_replay(self) -> None:
        sync = BookSynchronizer()

        sync.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 1.0),)))
        sync.on_depth_update(DepthUpdate(first_update_id=102, final_update_id=102, asks=((101.0, 3.0),)))

        sync.apply_snapshot(
            last_update_id=100,
            bids=((99.5, 2.0),),
            asks=((101.5, 2.0),),
        )

        self.assertTrue(sync.is_synced)
        self.assertEqual(sync.book.best_bid, (100.0, 1.0))
        self.assertEqual(sync.book.best_ask, (101.0, 3.0))

    def test_drop_stale_buffer_updates(self) -> None:
        sync = BookSynchronizer()
        sync.on_depth_update(DepthUpdate(first_update_id=90, final_update_id=95, bids=((90.0, 1.0),)))
        sync.on_depth_update(DepthUpdate(first_update_id=96, final_update_id=99, bids=((91.0, 1.0),)))
        sync.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 1.0),)))

        sync.apply_snapshot(last_update_id=100, bids=((99.0, 1.0),), asks=((101.0, 1.0),))

        self.assertEqual(sync.book.best_bid, (100.0, 1.0))

    def test_reset_clears_sync_state(self) -> None:
        sync = BookSynchronizer()
        sync.on_depth_update(DepthUpdate(first_update_id=101, final_update_id=101, prev_final_update_id=100, bids=((100.0, 1.0),)))
        sync.apply_snapshot(last_update_id=100, bids=((99.0, 1.0),), asks=((101.0, 1.0),))
        self.assertTrue(sync.is_synced)

        sync.reset()

        self.assertFalse(sync.is_synced)
        self.assertIsNone(sync.book.best_bid)
        self.assertIsNone(sync.book.best_ask)


if __name__ == "__main__":
    unittest.main()
