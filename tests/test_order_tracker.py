import unittest
from wickhunter.execution.order_tracker import OrderTracker

class TestOrderTracker(unittest.TestCase):
    def test_track_and_generate(self):
        tracker = OrderTracker()
        cid = tracker.generate_client_id("test_")
        self.assertTrue(cid.startswith("test_"))
        
        state = tracker.track_order(cid, "BTCUSDT", "BUY", 1.0, 100.0)
        self.assertEqual(state.status, "PENDING")
        self.assertEqual(state.client_order_id, cid)
        
        # Test active tracked
        self.assertEqual(len(tracker.get_open_orders()), 1)
        
    def test_on_report(self):
        tracker = OrderTracker()
        cid = tracker.generate_client_id()
        tracker.track_order(cid, "BTCUSDT", "BUY", 1.0, 100.0)
        
        # Partially filled
        state1 = tracker.on_report(cid, "PARTIALLY_FILLED", "ext123", 0.5)
        self.assertEqual(state1.filled_qty, 0.5)
        self.assertEqual(state1.status, "PARTIALLY_FILLED")
        self.assertEqual(len(tracker.get_open_orders()), 1)
        
        # Fully filled -> terminal
        state2 = tracker.on_report(cid, "FILLED", "ext123", 0.5)
        self.assertEqual(state2.filled_qty, 1.0)
        self.assertEqual(state2.status, "FILLED")
        self.assertEqual(len(tracker.get_open_orders()), 0)
        
        # Test no exist
        state3 = tracker.on_report("bad_id", "FILLED", None, 0)
        self.assertIsNone(state3)
