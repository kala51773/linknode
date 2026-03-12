import unittest
from typing import Any

from wickhunter.common.events import HedgeOrder
from wickhunter.core.mature_engine import BinanceDirectAdapter, MatureEngineKind, NautilusTraderAdapter
from wickhunter.strategy.quote_engine import QuoteLevel, QuotePlan


class TestMatureEngineAdapter(unittest.TestCase):
    def test_submit_armed_plan_to_nautilus_adapter(self) -> None:
        adapter = NautilusTraderAdapter()
        plan = QuotePlan(armed=True, levels=(QuoteLevel(price=99.4, size=100),), reason="ok")

        result = adapter.submit_quote_plan(plan)

        self.assertTrue(result.accepted)
        self.assertEqual(result.backend, MatureEngineKind.NAUTILUS_TRADER)
        self.assertEqual(len(adapter.sent_quote_plans), 1)

    def test_reject_unarmed_plan(self) -> None:
        adapter = NautilusTraderAdapter()
        result = adapter.submit_quote_plan(QuotePlan(armed=False, levels=tuple(), reason="not_synced"))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "plan_not_armed")

    def test_submit_hedge_order(self) -> None:
        adapter = NautilusTraderAdapter()
        order = HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.01, limit_price=50_000)

        result = adapter.submit_hedge_order(order)

        self.assertTrue(result.accepted)
        self.assertEqual(len(adapter.sent_hedge_orders), 1)

    def test_nautilus_emergency_stop_noop(self) -> None:
        adapter = NautilusTraderAdapter()

        result = adapter.emergency_stop(reason="marketdata_latency", symbols=("BTCUSDT",))

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "emergency_noop")
        self.assertEqual(adapter.emergency_reasons, ["marketdata_latency"])


class FakeBinanceClient:
    def __init__(
        self,
        responses: list[Any],
        cancel_responses: list[Any] | None = None,
        cancel_order_responses: list[Any] | None = None,
        open_orders_response: list[dict[str, Any]] | Exception | None = None,
        order_status_responses: dict[str, Any] | None = None,
        default_order_status: dict[str, Any] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.cancel_responses = list(cancel_responses or [])
        self.cancel_order_responses = list(cancel_order_responses or [])
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[str] = []
        self.cancel_order_calls: list[dict[str, Any]] = []
        self.open_orders_response = open_orders_response if open_orders_response is not None else []
        self.order_status_responses = dict(order_status_responses or {})
        self.order_status_calls: list[str] = []
        self.default_order_status = dict(default_order_status or {})

    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float = 0.0,
        order_type: str = "LIMIT",
        time_in_force: str = "GTC",
        new_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "new_client_order_id": new_client_order_id,
            }
        )

        if not self.responses:
            raise RuntimeError("no_fake_response")

        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def cancel_all_open_orders(self, symbol: str) -> Any:
        self.cancel_calls.append(symbol)
        if not self.cancel_responses:
            return {"status": "ok"}
        nxt = self.cancel_responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def cancel_order(
        self,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> Any:
        self.cancel_order_calls.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "orig_client_order_id": orig_client_order_id,
            }
        )
        if not self.cancel_order_responses:
            return {"status": "CANCELED", "orderId": order_id, "origClientOrderId": orig_client_order_id}
        nxt = self.cancel_order_responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def get_open_orders(self, symbol: str) -> list[dict[str, Any]]:
        if isinstance(self.open_orders_response, Exception):
            raise self.open_orders_response
        return list(self.open_orders_response)

    async def get_order_status(
        self,
        symbol: str,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        cid = orig_client_order_id or ""
        self.order_status_calls.append(cid)
        if cid in self.order_status_responses:
            resp = self.order_status_responses[cid]
            if isinstance(resp, Exception):
                raise resp
            if isinstance(resp, dict):
                return resp
        if self.default_order_status:
            payload = dict(self.default_order_status)
            payload.setdefault("clientOrderId", cid)
            return payload
        return {"code": -2013, "msg": "Order does not exist."}


class TestBinanceDirectAdapter(unittest.TestCase):
    def test_submit_hedge_order_success(self) -> None:
        client = FakeBinanceClient([{"orderId": 101, "status": "NEW"}])
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertTrue(result.accepted)
        self.assertEqual(result.backend, MatureEngineKind.BINANCE_DIRECT)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.order_id, 101)
        self.assertIsNotNone(result.client_order_id)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(adapter.order_reports[-1].intent, "hedge")
        assert result.client_order_id is not None
        state = adapter.order_tracker.get_order(result.client_order_id)
        assert state is not None
        self.assertEqual(state.status, "NEW")
        self.assertEqual(state.exchange_order_id, "101")
        self.assertEqual(state.intent, "hedge")
        self.assertEqual(client.calls[0]["new_client_order_id"], result.client_order_id)

    def test_retry_on_retryable_code_then_success(self) -> None:
        client = FakeBinanceClient(
            [
                {"code": -1007, "msg": "Timeout waiting for response from backend server."},
                {"orderId": 202, "status": "NEW"},
            ]
        )
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertTrue(result.accepted)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(adapter.order_reports[0].exchange_code, -1007)
        self.assertEqual(adapter.order_reports[1].order_id, 202)

    def test_retry_timeout_then_duplicate_client_id_recovers_existing_order(self) -> None:
        client = FakeBinanceClient(
            responses=[
                {"code": -1007, "msg": "Timeout waiting for response from backend server."},
                {"code": -2010, "msg": "Duplicate order sent."},
            ],
            default_order_status={"orderId": 909, "status": "NEW", "executedQty": "0"},
        )
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertTrue(result.accepted)
        self.assertEqual(result.order_id, 909)
        self.assertEqual(len(client.calls), 2)
        self.assertGreaterEqual(len(client.order_status_calls), 1)

    def test_reject_non_retryable_exchange_error(self) -> None:
        client = FakeBinanceClient([{"code": -2019, "msg": "Margin is insufficient."}])
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "exchange_reject:-2019")
        self.assertEqual(result.exchange_code, -2019)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(client.calls), 1)
        assert result.client_order_id is not None
        state = adapter.order_tracker.get_order(result.client_order_id)
        assert state is not None
        self.assertEqual(state.status, "REJECTED")

    def test_submit_quote_plan_uses_first_level(self) -> None:
        client = FakeBinanceClient([{"orderId": 303, "status": "NEW"}])
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ALTUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        plan = QuotePlan(
            armed=True,
            levels=(QuoteLevel(price=99.1, size=10.0), QuoteLevel(price=98.0, size=20.0)),
            reason="ok",
        )

        result = adapter.submit_quote_plan(plan)

        self.assertTrue(result.accepted)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["symbol"], "ALTUSDT")
        self.assertEqual(client.calls[0]["side"], "BUY")
        self.assertEqual(client.calls[0]["price"], 99.1)
        self.assertEqual(client.calls[0]["qty"], 10.0)
        self.assertEqual(client.calls[0]["new_client_order_id"], result.client_order_id)

    def test_submit_quote_plan_skips_when_quote_unchanged(self) -> None:
        client = FakeBinanceClient([{"orderId": 303, "status": "NEW"}])
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ALTUSDT",
            min_quote_price_move_bps=2.0,
            min_quote_size_change_ratio=0.2,
            min_requote_interval_seconds=0.0,
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        p1 = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1, size=10.0),), reason="ok")
        p2 = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1001, size=10.1),), reason="ok")

        first = adapter.submit_quote_plan(p1)
        second = adapter.submit_quote_plan(p2)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(second.reason, "quote_unchanged")
        self.assertEqual(len(client.calls), 1)

    def test_submit_quote_plan_requotes_with_cancel_when_price_moves(self) -> None:
        client = FakeBinanceClient(
            [{"orderId": 303, "status": "NEW"}, {"orderId": 304, "status": "NEW"}],
            cancel_order_responses=[{"status": "CANCELED"}],
        )
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ALTUSDT",
            min_quote_price_move_bps=0.5,
            min_quote_size_change_ratio=0.0,
            min_requote_interval_seconds=0.0,
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        adapter.quote_manager.min_order_live_seconds = 0.0

        p1 = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1, size=10.0),), reason="ok")
        p2 = QuotePlan(armed=True, levels=(QuoteLevel(price=98.9, size=10.0),), reason="ok")

        first = adapter.submit_quote_plan(p1)
        second = adapter.submit_quote_plan(p2)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(len(client.cancel_order_calls), 1)
        self.assertEqual(client.cancel_order_calls[0]["orig_client_order_id"], first.client_order_id)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["price"], 98.9)

    def test_submit_quote_plan_respects_requote_interval(self) -> None:
        client = FakeBinanceClient([{"orderId": 303, "status": "NEW"}])
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ALTUSDT",
            min_quote_price_move_bps=0.01,
            min_quote_size_change_ratio=0.0,
            min_requote_interval_seconds=30.0,
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        adapter.quote_manager.min_order_live_seconds = 0.0
        p1 = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1, size=10.0),), reason="ok")
        p2 = QuotePlan(armed=True, levels=(QuoteLevel(price=98.9, size=10.0),), reason="ok")

        first = adapter.submit_quote_plan(p1)
        second = adapter.submit_quote_plan(p2)

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(second.reason, "quote_requote_throttled")
        self.assertEqual(len(client.calls), 1)

    def test_on_execution_report_moves_order_to_filled(self) -> None:
        client = FakeBinanceClient([{"orderId": 404, "status": "NEW"}])
        adapter = BinanceDirectAdapter(client=client, max_retries=1, retry_backoff_seconds=0.0)

        submit = adapter.submit_hedge_order(HedgeOrder(symbol="BTCUSDT", side="SELL", qty=0.02, limit_price=50_000))
        assert submit.client_order_id is not None

        state = adapter.on_execution_report(
            {"c": submit.client_order_id, "i": 404, "X": "FILLED", "z": "0.02"}
        )

        assert state is not None
        self.assertEqual(state.status, "FILLED")
        self.assertEqual(state.filled_qty, 0.02)
        self.assertEqual(adapter.order_tracker.get_open_orders(), [])

    def test_submit_quote_plan_missing_symbol_rejected(self) -> None:
        client = FakeBinanceClient([])
        adapter = BinanceDirectAdapter(client=client)
        plan = QuotePlan(armed=True, levels=(QuoteLevel(price=99.1, size=10.0),), reason="ok")

        result = adapter.submit_quote_plan(plan)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "quote_symbol_missing")

    def test_emergency_stop_cancel_all_symbols(self) -> None:
        client = FakeBinanceClient([], cancel_responses=[{"status": "ok"}, {"status": "ok"}])
        adapter = BinanceDirectAdapter(client=client, max_retries=1, retry_backoff_seconds=0.0)

        result = adapter.emergency_stop(reason="marketdata_latency", symbols=("BTCUSDT", "ETHUSDT"))

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "emergency_cancel_ok")
        self.assertEqual(client.cancel_calls, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(len(adapter.emergency_reports), 2)
        self.assertTrue(all(r.accepted for r in adapter.emergency_reports))

    def test_emergency_stop_retry_and_fail(self) -> None:
        client = FakeBinanceClient(
            [],
            cancel_responses=[
                {"code": -1007, "msg": "Timeout"},
                {"code": -2019, "msg": "Margin is insufficient."},
            ],
        )
        adapter = BinanceDirectAdapter(client=client, max_retries=2, retry_backoff_seconds=0.0)

        result = adapter.emergency_stop(reason="exchange_restricted", symbols=("BTCUSDT",))

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "emergency_cancel_failed")
        self.assertEqual(result.exchange_code, -2019)
        self.assertEqual(client.cancel_calls, ["BTCUSDT", "BTCUSDT"])
        self.assertEqual(len(adapter.emergency_reports), 1)
        self.assertFalse(adapter.emergency_reports[0].accepted)

    def test_reconcile_open_orders_strict_success_when_consistent(self) -> None:
        client = FakeBinanceClient([], open_orders_response=[])
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ETHUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        report = adapter.reconcile_open_orders_strict()

        self.assertTrue(report.success)
        self.assertEqual(report.reason, "ok")
        self.assertEqual(report.exchange_open_orders, 0)
        self.assertEqual(report.local_open_after, 0)

    def test_reconcile_open_orders_marks_not_found_as_expired(self) -> None:
        client = FakeBinanceClient(
            [],
            open_orders_response=[],
            order_status_responses={"wh_local_1": {"code": -2013, "msg": "Order does not exist."}},
        )
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ETHUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        adapter.order_tracker.track_order(
            client_order_id="wh_local_1",
            symbol="ETHUSDT",
            side="BUY",
            qty=1.0,
            price=1000.0,
            intent="quote",
        )

        report = adapter.reconcile_open_orders_strict()
        state = adapter.order_tracker.get_order("wh_local_1")

        self.assertTrue(report.success)
        self.assertEqual(report.assumed_closed, 1)
        self.assertEqual(report.local_open_after, 0)
        assert state is not None
        self.assertEqual(state.status, "EXPIRED")

    def test_reconcile_open_orders_reports_unresolved_when_status_query_fails(self) -> None:
        client = FakeBinanceClient(
            [],
            open_orders_response=[],
            order_status_responses={"wh_local_2": RuntimeError("status_down")},
        )
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ETHUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        adapter.order_tracker.track_order(
            client_order_id="wh_local_2",
            symbol="ETHUSDT",
            side="BUY",
            qty=1.0,
            price=1000.0,
            intent="quote",
        )

        report = adapter.reconcile_open_orders_strict()

        self.assertFalse(report.success)
        self.assertEqual(report.reason, "reconcile_unresolved")
        self.assertEqual(report.status_query_failures, 1)
        self.assertEqual(report.unresolved_local, 1)
        self.assertIn("wh_local_2", report.unresolved_client_order_ids)

    def test_reconcile_open_orders_reports_query_failed_when_open_orders_call_fails(self) -> None:
        client = FakeBinanceClient([], open_orders_response=RuntimeError("open_orders_down"))
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ETHUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )

        report = adapter.reconcile_open_orders_strict()

        self.assertFalse(report.success)
        self.assertEqual(report.reason, "reconcile_exchange_query_failed")
        self.assertIn("open_orders_down", report.error_detail or "")

    def test_reconcile_open_orders_identifies_filled_canceled_and_unknown(self) -> None:
        client = FakeBinanceClient(
            [],
            open_orders_response=[],
            order_status_responses={
                "wh_local_filled": {"clientOrderId": "wh_local_filled", "orderId": 1, "status": "FILLED", "executedQty": "1"},
                "wh_local_canceled": {"clientOrderId": "wh_local_canceled", "orderId": 2, "status": "CANCELED", "executedQty": "0"},
                "wh_local_unknown": {"clientOrderId": "wh_local_unknown", "orderId": 3, "status": "PENDING_NEW", "executedQty": "0"},
            },
        )
        adapter = BinanceDirectAdapter(
            client=client,
            quote_symbol="ETHUSDT",
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        for cid in ("wh_local_filled", "wh_local_canceled", "wh_local_unknown"):
            adapter.order_tracker.track_order(
                client_order_id=cid,
                symbol="ETHUSDT",
                side="BUY",
                qty=1.0,
                price=1000.0,
                intent="quote",
            )

        report = adapter.reconcile_open_orders_strict()

        self.assertFalse(report.success)
        self.assertEqual(report.reason, "reconcile_unresolved")
        self.assertEqual(report.resolved_via_status, 2)
        self.assertEqual(report.unresolved_local, 1)
        self.assertIn("wh_local_unknown", report.unresolved_client_order_ids)


if __name__ == "__main__":
    unittest.main()
