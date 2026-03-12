import unittest

from wickhunter.execution.order_tracker import OrderTracker


class TestOrderTracker(unittest.TestCase):
    def test_track_and_reconcile_with_exchange_id(self) -> None:
        tracker = OrderTracker()
        state = tracker.track_order(
            client_order_id="wh_h_abc",
            symbol="BTCUSDT",
            side="SELL",
            qty=0.02,
            price=50_000.0,
            intent="hedge",
        )
        self.assertEqual(state.status, "PENDING")

        tracker.on_report(client_order_id="wh_h_abc", exchange_order_id="101", status="NEW")
        self.assertEqual(tracker.find_by_exchange_order_id("101").status, "NEW")

        terminal = tracker.on_report(exchange_order_id="101", status="FILLED", filled_qty=0.02)
        assert terminal is not None
        self.assertEqual(terminal.status, "FILLED")
        self.assertEqual(terminal.filled_qty, 0.02)
        self.assertEqual(tracker.get_open_orders(), [])
        self.assertEqual(tracker.closed_orders["wh_h_abc"].status, "FILLED")

    def test_invalid_transition_raises(self) -> None:
        tracker = OrderTracker()
        tracker.track_order(
            client_order_id="wh_q_abc",
            symbol="ALTUSDT",
            side="BUY",
            qty=10.0,
            price=99.0,
            intent="quote",
        )
        tracker.on_report(client_order_id="wh_q_abc", status="NEW")
        tracker.on_report(client_order_id="wh_q_abc", status="FILLED", filled_qty=10.0)

        with self.assertRaises(ValueError):
            tracker.on_report(client_order_id="wh_q_abc", status="PARTIALLY_FILLED", filled_qty=5.0)

    def test_generate_client_id_has_prefix(self) -> None:
        tracker = OrderTracker()
        cid = tracker.generate_client_id(prefix="wh_x_")
        self.assertTrue(cid.startswith("wh_x_"))
        self.assertGreater(len(cid), 10)

    def test_partial_fill_then_full_fill_transitions(self) -> None:
        tracker = OrderTracker()
        tracker.track_order(
            client_order_id="wh_partial_1",
            symbol="BTCUSDT",
            side="BUY",
            qty=1.0,
            price=100.0,
            intent="quote",
        )
        state = tracker.on_report(client_order_id="wh_partial_1", status="PARTIALLY_FILLED", filled_qty=0.4)
        assert state is not None
        self.assertEqual(state.status, "PARTIALLY_FILLED")
        self.assertEqual(state.filled_qty, 0.4)

        final_state = tracker.on_report(client_order_id="wh_partial_1", status="FILLED", filled_qty=1.0)
        assert final_state is not None
        self.assertEqual(final_state.status, "FILLED")
        self.assertEqual(final_state.filled_qty, 1.0)
        self.assertEqual(len(tracker.get_open_orders()), 0)


if __name__ == "__main__":
    unittest.main()
